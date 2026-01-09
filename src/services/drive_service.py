"""
Google Drive Service for prompt and asset synchronization.

Handles authentication, file downloads, caching, and
automatic polling for changes to prompts and image mappings.
"""

import asyncio
import hashlib
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime
import json

from src.config import get_settings
from src.models.cached_asset import CachedAsset
from src.models.prompt_config import PromptConfig, DEFAULT_PROMPT_CONFIG
from src.models.image_mapping import ImageMappingConfig, DEFAULT_IMAGE_CONFIG, extract_drive_folder_id
from src.utils.logger import get_logger

logger = get_logger("services.drive")

# File names in Google Drive
SYSTEM_PROMPT_FILE = "system_prompt.md"
IMAGE_MAP_FILE = "image_map.json"
IMAGES_FOLDER = "images"


class DriveError(Exception):
    """Base exception for Drive service errors."""
    pass


class DriveAuthError(DriveError):
    """Raised for authentication errors."""
    pass


class DriveService:
    """
    Service for Google Drive file synchronization.
    
    Provides:
    - Service account authentication
    - File download with MD5 checksum validation
    - Local caching with LRU eviction
    - Background polling for automatic sync
    
    Attributes:
        folder_id: Google Drive folder ID to sync from
        cache_dir: Local directory for cached files
        sync_interval: Seconds between sync checks
        is_configured: Whether Drive integration is enabled
    """
    
    def __init__(
        self,
        service_account_file: Optional[str] = None,
        folder_id: Optional[str] = None,
        cache_dir: Optional[str] = None,
        sync_interval: Optional[int] = None,
    ):
        """
        Initialize Drive service.
        
        Args:
            service_account_file: Path to service account JSON
            folder_id: Google Drive folder ID
            cache_dir: Local cache directory
            sync_interval: Sync interval in seconds
        """
        settings = get_settings()

        self.service_account_file = service_account_file or settings.google_service_account_file
        raw_folder_id = folder_id or settings.drive_folder_id

        # Extract folder_id from URL if a URL was provided
        if raw_folder_id:
            try:
                self.folder_id = extract_drive_folder_id(raw_folder_id)
            except ValueError as e:
                logger.warning(f"Invalid folder_id format: {e}")
                self.folder_id = None
        else:
            self.folder_id = None

        self.cache_dir = Path(cache_dir or settings.cache_dir)
        self.sync_interval = sync_interval or settings.drive_sync_interval_seconds

        # Check if Drive is configured
        self.is_configured = bool(self.service_account_file and self.folder_id)
        
        # Google API client (lazy initialized)
        self._service = None
        self._sheets_service = None
        self._credentials = None
        
        # Cached data
        self._prompt_config: PromptConfig = DEFAULT_PROMPT_CONFIG
        self._image_config: ImageMappingConfig = DEFAULT_IMAGE_CONFIG
        self._cached_assets: Dict[str, CachedAsset] = {}
        
        # Background sync state
        self._sync_task: Optional[asyncio.Task] = None
        self._is_syncing = False
        self._last_sync: Optional[datetime] = None
        
        # Ensure cache directory exists
        if self.is_configured:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / "images").mkdir(exist_ok=True)
        
        logger.info(
            f"DriveService initialized: configured={self.is_configured}, "
            f"sync_interval={self.sync_interval}s"
        )
    
    def _get_service(self):
        """Get or create Google Drive API service."""
        if self._service is not None:
            return self._service
        
        if not self.is_configured:
            raise DriveError("Google Drive is not configured")
        
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            
            self._credentials = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=[
                    'https://www.googleapis.com/auth/drive.readonly',
                    'https://www.googleapis.com/auth/spreadsheets.readonly'
                ]
            )

            self._service = build('drive', 'v3', credentials=self._credentials)
            # Also create Sheets service for reading spreadsheets
            self._sheets_service = build('sheets', 'v4', credentials=self._credentials)
            logger.info("Google Drive and Sheets API services created")
            return self._service
            
        except Exception as e:
            logger.error(f"Failed to create Drive service: {e}")
            raise DriveAuthError(f"Authentication failed: {e}")
    
    @property
    def prompt_config(self) -> PromptConfig:
        """Get current prompt configuration."""
        return self._prompt_config
    
    @property
    def image_config(self) -> ImageMappingConfig:
        """Get current image mapping configuration."""
        return self._image_config
    
    async def sync_all(self) -> Tuple[bool, bool]:
        """
        Sync all configuration files from Drive.
        
        Returns:
            Tuple of (prompt_updated, images_updated)
        """
        if not self.is_configured:
            logger.debug("Drive not configured, skipping sync")
            return (False, False)
        
        self._is_syncing = True
        prompt_updated = False
        images_updated = False
        
        try:
            # Sync prompt file
            prompt_updated = await self._sync_prompt()
            
            # Sync image mapping
            images_updated = await self._sync_image_map()
            
            self._last_sync = datetime.utcnow()
            
            if prompt_updated or images_updated:
                logger.info(
                    f"Sync complete: prompt={prompt_updated}, images={images_updated}"
                )
            
        except Exception as e:
            logger.error(f"Sync failed: {e}", exc_info=True)
            # Continue with cached data
            
        finally:
            self._is_syncing = False
        
        return (prompt_updated, images_updated)
    
    async def _sync_prompt(self) -> bool:
        """
        Sync system prompt from Drive (supports both .md and Google Docs).

        Priority order:
        1. Google Docs named "system_prompt" (preferred, easier to edit)
        2. Markdown file "system_prompt.md" (fallback)

        Returns:
            True if prompt was updated
        """
        try:
            # Try to find Google Docs first
            doc_info = await self._find_file("system_prompt")
            if doc_info and doc_info.get('mimeType') == 'application/vnd.google-apps.document':
                logger.debug("Found system_prompt as Google Docs")
                content = await self._download_google_doc(doc_info['id'])
                if content:
                    file_id = doc_info['id']
                    modified_time = doc_info.get('modifiedTime', '')
                    return await self._update_prompt_config(content, file_id, '', modified_time)

            # Fallback to markdown file
            file_info = await self._find_file(SYSTEM_PROMPT_FILE)
            if not file_info:
                logger.warning(f"No system_prompt found (tried Docs and .md)")
                return False

            file_id = file_info['id']
            md5_checksum = file_info.get('md5Checksum', '')
            modified_time = file_info.get('modifiedTime', '')

            # Check if we need to download
            if not self._prompt_config.needs_update(md5_checksum):
                logger.debug("Prompt unchanged, skipping download")
                return False

            # Download content
            content = await self._download_file_content(file_id)
            if not content:
                return False

            return await self._update_prompt_config(content, file_id, md5_checksum, modified_time)

        except Exception as e:
            logger.error(f"Prompt sync failed: {e}")
            return False

    async def _download_google_doc(self, doc_id: str) -> Optional[str]:
        """
        Download Google Docs content as plain text.

        Args:
            doc_id: Google Docs file ID

        Returns:
            Document content as plain text, or None if failed
        """
        try:
            # Ensure services are initialized
            service = self._get_service()

            # Export as plain text
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None,
                lambda: service.files().export(
                    fileId=doc_id,
                    mimeType='text/plain'
                ).execute()
            )

            return content.decode('utf-8')

        except Exception as e:
            logger.error(f"Google Docs download failed: {e}")
            return None

    async def _update_prompt_config(
        self,
        content: str,
        file_id: str,
        md5_checksum: str,
        modified_time: str
    ) -> bool:
        """
        Update prompt configuration.

        Args:
            content: Prompt content
            file_id: File ID
            md5_checksum: MD5 checksum (empty for Google Docs)
            modified_time: Modified time string

        Returns:
            True if updated successfully
        """
        # Parse modified time
        mod_dt = datetime.utcnow()
        if modified_time:
            try:
                mod_dt = datetime.fromisoformat(modified_time.replace('Z', '+00:00'))
            except ValueError:
                pass

        # Update prompt config
        self._prompt_config = PromptConfig(
            content=content,
            file_id=file_id,
            modified_time=mod_dt,
            md5_checksum=md5_checksum,
            version=self._prompt_config.version + 1,
        )

        logger.info(
            f"Prompt updated to version {self._prompt_config.version}, "
            f"length={len(content)} chars"
        )

        # Update the hej handler with new prompt
        from src.handlers.hej_handler import set_prompt_config
        set_prompt_config(self._prompt_config)

        return True
    
    async def _sync_image_map(self) -> bool:
        """
        Sync image mapping from Drive (supports both JSON and Google Sheets).

        Priority order:
        1. Google Sheets named "image_map" (preferred, easier to edit)
        2. JSON file "image_map.json" (fallback)

        Returns:
            True if image config was updated
        """
        try:
            # Try to find Google Sheets first
            sheet_info = await self._find_file("image_map")
            if sheet_info and sheet_info.get('mimeType') == 'application/vnd.google-apps.spreadsheet':
                logger.debug("Found image_map as Google Sheets")
                new_config = await self._load_image_map_from_sheets(sheet_info['id'])
                if new_config:
                    return await self._update_image_config(new_config)

            # Fallback to JSON file
            file_info = await self._find_file(IMAGE_MAP_FILE)
            if not file_info:
                logger.debug(f"No image_map found (tried Sheets and JSON)")
                return False

            file_id = file_info['id']

            # Download content
            content = await self._download_file_content(file_id)
            if not content:
                return False

            # Parse JSON
            try:
                new_config = ImageMappingConfig.from_json(content)
            except ValueError as e:
                logger.error(f"Invalid image_map.json: {e}")
                return False

            return await self._update_image_config(new_config)

        except Exception as e:
            logger.error(f"Image map sync failed: {e}")
            return False

    async def _load_image_map_from_sheets(self, sheet_id: str) -> Optional[ImageMappingConfig]:
        """
        Load image mappings from Google Sheets.

        Expected format (first sheet):
        | keyword | filename | file_id |
        |---------|----------|---------|
        | 瑜珈褲  | 01.jpg   | https://drive.google.com/... |
        | 騎哈雷  | 02.jpg   | https://drive.google.com/... |

        Args:
            sheet_id: Google Sheets file ID

        Returns:
            ImageMappingConfig or None if failed
        """
        try:
            # Ensure services are initialized
            self._get_service()

            if not self._sheets_service:
                logger.error("Sheets service not initialized")
                return None

            # Read the first sheet (A1:C1000)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._sheets_service.spreadsheets().values().get(
                    spreadsheetId=sheet_id,
                    range='A1:C1000'
                ).execute()
            )

            values = result.get('values', [])
            if not values or len(values) < 2:
                logger.warning("Google Sheets is empty or has no data rows")
                return None

            # Parse rows (skip header)
            from src.models.image_mapping import ImageMapping
            mappings = []

            for i, row in enumerate(values[1:], start=2):  # Skip header row
                if len(row) < 3:
                    logger.warning(f"Row {i} has insufficient columns, skipping")
                    continue

                keyword = row[0].strip()
                filename = row[1].strip()
                file_id = row[2].strip()

                if not keyword or not filename or not file_id:
                    logger.warning(f"Row {i} has empty fields, skipping")
                    continue

                try:
                    mapping = ImageMapping(
                        keyword=keyword,
                        filename=filename,
                        file_id=file_id
                    )
                    mappings.append(mapping)
                except ValueError as e:
                    logger.warning(f"Invalid mapping at row {i}: {e}")
                    continue

            if not mappings:
                logger.warning("No valid mappings found in Google Sheets")
                return None

            return ImageMappingConfig(
                mappings=mappings,
                version=1,
                updated_at=datetime.utcnow()
            )

        except Exception as e:
            logger.error(f"Failed to load from Google Sheets: {e}")
            return None

    async def _update_image_config(self, new_config: ImageMappingConfig) -> bool:
        """
        Update image config if changed.

        Args:
            new_config: New ImageMappingConfig to apply

        Returns:
            True if config was updated
        """
        # Check if content actually changed by comparing mappings
        old_keywords = set(m.keyword for m in self._image_config.mappings)
        new_keywords = set(m.keyword for m in new_config.mappings)

        if old_keywords == new_keywords and len(self._image_config.mappings) == len(new_config.mappings):
            # Check if file_ids are the same
            old_mapping_dict = {m.keyword: m.file_id for m in self._image_config.mappings}
            new_mapping_dict = {m.keyword: m.file_id for m in new_config.mappings}
            if old_mapping_dict == new_mapping_dict:
                logger.debug("Image config unchanged")
                return False

        self._image_config = new_config
        logger.info(
            f"Image config updated: version={new_config.version}, "
            f"mappings={len(new_config.mappings)}"
        )

        return True
    
    async def _find_file(self, filename: str) -> Optional[dict]:
        """
        Find a file in the Drive folder by name.
        
        Args:
            filename: File name to find
            
        Returns:
            File metadata dict or None
        """
        try:
            service = self._get_service()
            
            query = f"name='{filename}' and '{self.folder_id}' in parents and trashed=false"
            
            # Run blocking API call in thread pool
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: service.files().list(
                    q=query,
                    fields="files(id, name, md5Checksum, modifiedTime, mimeType)",
                    pageSize=1,
                ).execute()
            )
            
            files = results.get('files', [])
            return files[0] if files else None
            
        except Exception as e:
            logger.error(f"File search failed: {e}")
            return None
    
    async def _download_file_content(self, file_id: str) -> Optional[str]:
        """
        Download file content as text.
        
        Args:
            file_id: Google Drive file ID
            
        Returns:
            File content as string, or None if failed
        """
        try:
            service = self._get_service()
            
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None,
                lambda: service.files().get_media(fileId=file_id).execute()
            )
            
            return content.decode('utf-8')
            
        except Exception as e:
            logger.error(f"File download failed: {e}")
            return None
    
    async def download_image(self, file_id: str, filename: str) -> Optional[bytes]:
        """
        Download an image file from Drive.
        
        Args:
            file_id: Google Drive file ID
            filename: Original filename for caching
            
        Returns:
            Image bytes, or None if failed
        """
        # Check cache first
        cache_path = self.cache_dir / "images" / filename
        if cache_path.exists():
            logger.debug(f"Image cache hit: {filename}")
            return cache_path.read_bytes()
        
        try:
            service = self._get_service()
            
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None,
                lambda: service.files().get_media(fileId=file_id).execute()
            )
            
            # Cache the image
            cache_path.write_bytes(content)
            logger.info(f"Image cached: {filename}, size={len(content)} bytes")
            
            return content
            
        except Exception as e:
            logger.error(f"Image download failed: {e}")
            return None
    
    async def start_background_sync(self) -> None:
        """Start background polling for automatic sync."""
        if not self.is_configured:
            logger.info("Drive not configured, background sync disabled")
            return
        
        if self._sync_task is not None:
            logger.warning("Background sync already running")
            return
        
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info(f"Background sync started (interval={self.sync_interval}s)")
    
    async def stop_background_sync(self) -> None:
        """Stop background sync task."""
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None
            logger.info("Background sync stopped")
    
    async def _sync_loop(self) -> None:
        """Background sync loop."""
        # Initial sync
        await self.sync_all()
        
        while True:
            try:
                await asyncio.sleep(self.sync_interval)
                await self.sync_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sync loop error: {e}")
                # Continue running despite errors
    
    def get_stats(self) -> dict:
        """Get service statistics."""
        return {
            "is_configured": self.is_configured,
            "is_syncing": self._is_syncing,
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "prompt_version": self._prompt_config.version,
            "image_mappings": len(self._image_config.mappings),
            "sync_interval": self.sync_interval,
        }


# Global singleton instance
_drive_service: Optional[DriveService] = None


def get_drive_service() -> DriveService:
    """Get or create the global DriveService instance."""
    global _drive_service
    if _drive_service is None:
        _drive_service = DriveService()
    return _drive_service


async def close_drive_service() -> None:
    """Stop and close the global DriveService."""
    global _drive_service
    if _drive_service:
        await _drive_service.stop_background_sync()
        _drive_service = None
