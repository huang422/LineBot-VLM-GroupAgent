"""
Image Command Handler for keyword-based image retrieval.

Handles !img [keyword] commands by looking up the keyword
in the image mapping and sending the corresponding image.
"""

from typing import Dict, Any, Optional
import uuid
from pathlib import Path

from src.handlers.command_handler import ParsedCommand, extract_event_context
from src.services.drive_service import get_drive_service
from src.services.line_service import get_line_service
from src.services.message_cache_service import cache_message
from src.utils.logger import get_logger
from src.config import get_settings

logger = get_logger("handlers.img")

# Temporary image storage
TEMP_IMAGE_DIR = Path("/tmp/linebot_images")

# Response messages
MSG_NO_KEYWORD = "❓ 請指定圖片關鍵字。例如：!img 架構圖"
MSG_NOT_FOUND = "❌ 找不到「{keyword}」。\n\n可用的關鍵字：\n{keywords}"
MSG_NO_KEYWORDS = "ℹ️ 目前沒有設定任何圖片關鍵字。"
MSG_SENDING = "📷 正在發送圖片..."
MSG_ERROR = "❌ 無法取得圖片，請稍後再試。"
MSG_NOT_CONFIGURED = "⚠️ 圖片功能未設定。請聯繫管理員。"


async def handle_img_command(
    command: ParsedCommand,
    event: Dict[str, Any],
) -> bool:
    """
    Handle !img command for image retrieval.
    
    Args:
        command: Parsed command data (argument = keyword)
        event: Original LINE webhook event
        
    Returns:
        True if image was sent successfully
    """
    context = extract_event_context(event)
    reply_token = context["reply_token"]
    keyword = command.argument.strip()
    
    line_service = get_line_service()
    drive_service = get_drive_service()
    
    # Check if keyword provided
    if not keyword:
        if reply_token:
            await line_service.reply_text(reply_token, MSG_NO_KEYWORD)
        return False
    
    # Check if Drive is configured
    if not drive_service.is_configured:
        logger.warning("Image requested but Drive not configured")
        if reply_token:
            await line_service.reply_text(reply_token, MSG_NOT_CONFIGURED)
        return False
    
    image_config = drive_service.image_config
    
    # Check if any mappings exist
    if not image_config.mappings:
        if reply_token:
            await line_service.reply_text(reply_token, MSG_NO_KEYWORDS)
        return False
    
    # Look up keyword
    mapping = image_config.get_by_keyword(keyword)
    
    if not mapping:
        # Build list of available keywords
        available = image_config.keywords[:10]  # First 10
        keywords_str = "、".join(available)
        if len(image_config.keywords) > 10:
            keywords_str += f"\n...還有 {len(image_config.keywords) - 10} 個"
        
        message = MSG_NOT_FOUND.format(keyword=keyword, keywords=keywords_str)
        
        if reply_token:
            await line_service.reply_text(reply_token, message)
        
        logger.info(f"Unknown image keyword: {keyword}")
        return False
    
    try:
        logger.info(
            f"Fetching image",
            extra={
                "keyword": keyword,
                "image_filename": mapping.filename,
                "user_id": context.get("user_id"),
            }
        )
        
        # Download image from Drive (will use cache if available)
        image_bytes = await drive_service.download_image(
            mapping.file_id,
            mapping.filename,
        )
        
        if not image_bytes:
            logger.error(f"Failed to download image: {mapping.filename}")
            if reply_token:
                await line_service.reply_text(reply_token, MSG_ERROR)
            
            # Notify admins about missing image
            await line_service.notify_admins(
                f"圖片下載失敗: {mapping.keyword} → {mapping.filename}"
            )
            return False
        
        # Ensure image is JPEG (converts HEIC etc.)
        from src.services.image_service import convert_to_jpeg
        
        # 1. Generate Original (Full Quality)
        original_bytes = convert_to_jpeg(image_bytes, max_dimension=None)
        if not original_bytes:
             logger.error(f"Failed to convert original image: {mapping.filename}")
             original_bytes = image_bytes # Fallback
             
        # 2. Generate Preview (Small Size < 1MB)
        preview_bytes = convert_to_jpeg(image_bytes, max_dimension=512)
        if not preview_bytes:
             logger.warning("Failed to generate preview, using original")
             preview_bytes = original_bytes

        # Send image using LINE SDK
        # We need to save both files and generate URLs
        success, message_id, image_url = await _send_image_pair_via_line(
            line_service,
            reply_token,
            context.get("group_id"),
            original_bytes,
            preview_bytes,
            mapping.filename,
        )

        if success:
            logger.info(f"Image sent successfully: {mapping.keyword}")
            # Cache the sent image message
            if message_id:
                cache_message(message_id, "image", image_url=image_url)
                logger.debug(f"Cached bot image message: id={message_id}, url={image_url}")

        return success
        
    except Exception as e:
        logger.error(f"Image command failed: {e}", exc_info=True)
        if reply_token:
            await line_service.reply_text(reply_token, MSG_ERROR)
        return False


async def _send_image_pair_via_line(
    line_service,
    reply_token: str,
    group_id: str,
    original_bytes: bytes,
    preview_bytes: bytes,
    filename: str,
) -> tuple[bool, Optional[str], str]:
    """
    Send image pair (original + preview) to LINE.

    Args:
        line_service: LINE service instance
        reply_token: Reply token
        group_id: Group ID for fallback
        original_bytes: Full quality image data
        preview_bytes: Resized preview data
        filename: Original filename

    Returns:
        Tuple of (success, message_id, original_url)
    """
    try:
        # Generate unique filenames
        unique_id = uuid.uuid4()
        original_filename = f"{unique_id}.jpg"
        preview_filename = f"{unique_id}_preview.jpg"
        
        original_path = TEMP_IMAGE_DIR / original_filename
        preview_path = TEMP_IMAGE_DIR / preview_filename

        # Save images
        original_path.write_bytes(original_bytes)
        preview_path.write_bytes(preview_bytes)
        logger.debug(f"Saved images: {original_filename}, {preview_filename}")

        # Build URLs
        settings = get_settings()
        base_url = _get_public_base_url(settings)
        original_url = f"{base_url}/images/{original_filename}"
        preview_url = f"{base_url}/images/{preview_filename}"

        logger.info(f"Sending image. Original: {original_url}, Preview: {preview_url}")

        # Send image with separate preview URL
        if reply_token:
            success, message_id, _ = await line_service.reply_image(
                reply_token=reply_token,
                original_url=original_url,
                preview_url=preview_url,
            )
            if success:
                logger.debug("Image sent via reply_token")
                return (True, message_id, original_url)

        # Fallback to push message
        if group_id:
            logger.warning("Push image not implemented, falling back to text notification")
            size_kb = len(original_bytes) / 1024
            message = f"📷 圖片: {filename}\n大小: {size_kb:.1f} KB\n\n查看圖片: {original_url}"
            success = await line_service.push_text(group_id, message)
            return (success, None, original_url)

        return (False, None, original_url)

    except Exception as e:
        logger.error(f"Failed to send image via LINE: {e}", exc_info=True)
        return (False, None, "")


def _get_public_base_url(settings) -> str:
    """
    Get the public base URL for the application.

    In production with Cloudflare Tunnel, this should be set in environment
    as PUBLIC_BASE_URL. For local testing, falls back to local URL.

    Args:
        settings: Application settings

    Returns:
        Base URL (e.g., "https://your-tunnel.trycloudflare.com")
    """
    # Check if PUBLIC_BASE_URL is configured
    public_url = getattr(settings, "public_base_url", None)
    if public_url:
        return public_url.rstrip("/")

    # Fallback to local URL (won't work with LINE webhook)
    logger.warning(
        "PUBLIC_BASE_URL not configured. "
        "Set PUBLIC_BASE_URL in .env to your Cloudflare Tunnel URL"
    )
    return f"http://{settings.host}:{settings.port}"
