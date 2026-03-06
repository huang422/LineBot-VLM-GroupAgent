"""
LINE Messaging Service for webhook handling and message sending.

Handles LINE platform integration including:
- Webhook event parsing
- Message content download
- Reply and push message sending
- Image message handling
"""

from typing import Optional, Dict, Any, List
from io import BytesIO
import httpx

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger("services.line")

# LINE API endpoints
LINE_API_BASE = "https://api.line.me/v2"
LINE_DATA_API_BASE = "https://api-data.line.me/v2"

# Timeouts
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0


class LineError(Exception):
    """Base exception for LINE service errors."""
    pass


class LineAuthError(LineError):
    """Raised for authentication/signature errors."""
    pass


class LineApiError(LineError):
    """Raised for LINE API errors."""
    pass


class LineService:
    """
    Service for LINE Messaging API integration.
    
    Attributes:
        channel_secret: LINE channel secret for signature validation
        channel_access_token: LINE access token for API calls
        client: Async HTTP client
    """
    
    def __init__(
        self,
        channel_secret: Optional[str] = None,
        channel_access_token: Optional[str] = None,
    ):
        """
        Initialize LINE service.
        
        Args:
            channel_secret: Override config channel secret
            channel_access_token: Override config access token
        """
        settings = get_settings()
        self.channel_secret = channel_secret or settings.line_channel_secret
        self.channel_access_token = channel_access_token or settings.line_channel_access_token
        
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=CONNECT_TIMEOUT,
                read=READ_TIMEOUT,
                write=30.0,
                pool=10.0,
            ),
            headers={
                "Authorization": f"Bearer {self.channel_access_token}",
                "Content-Type": "application/json",
            }
        )
        
        logger.info("LineService initialized")
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def reply_text(
        self,
        reply_token: str,
        text: str,
        notification_disabled: bool = False,
    ) -> tuple[bool, Optional[str], str]:
        """
        Send a text reply using reply token.

        Args:
            reply_token: LINE reply token (validity varies; use within 30s to be safe)
            text: Message text to send
            notification_disabled: If True, don't trigger notification

        Returns:
            Tuple of (success: bool, message_id: Optional[str], text: str)
        """
        # LINE limits message to 5000 characters
        if len(text) > 5000:
            text = text[:4997] + "..."

        payload = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
            "notificationDisabled": notification_disabled,
        }

        try:
            response = await self.client.post(
                f"{LINE_API_BASE}/bot/message/reply",
                json=payload,
            )

            if response.status_code == 200:
                logger.debug("Reply sent successfully")
                # Extract message ID from response if available
                response_data = response.json()
                sent_messages = response_data.get("sentMessages", [])
                message_id = sent_messages[0]["id"] if sent_messages else None
                return (True, message_id, text)
            else:
                error_body = response.text[:200]
                logger.error(f"Reply failed: {response.status_code} - {error_body}")
                return (False, None, text)

        except Exception as e:
            logger.error(f"Reply error: {e}")
            return (False, None, text)
    
    async def push_text(
        self,
        to: str,
        text: str,
        notification_disabled: bool = False,
    ) -> bool:
        """
        Send a push message to user/group.
        
        Args:
            to: User ID or group ID to send to
            text: Message text
            notification_disabled: If True, don't trigger notification
            
        Returns:
            True if successful
        """
        if len(text) > 5000:
            text = text[:4997] + "..."
        
        payload = {
            "to": to,
            "messages": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
            "notificationDisabled": notification_disabled,
        }
        
        try:
            response = await self.client.post(
                f"{LINE_API_BASE}/bot/message/push",
                json=payload,
            )
            
            if response.status_code == 200:
                logger.warning(f"Push message sent (paid) to {to[:8]}...")
                return True
            else:
                logger.error(f"Push failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Push error: {e}")
            return False
    
    async def reply_image(
        self,
        reply_token: str,
        original_url: str,
        preview_url: Optional[str] = None,
    ) -> tuple[bool, Optional[str], str]:
        """
        Send an image reply using URLs.

        Args:
            reply_token: LINE reply token
            original_url: Full-size image URL (HTTPS required)
            preview_url: Preview image URL (optional, uses original if not provided)

        Returns:
            Tuple of (success: bool, message_id: Optional[str], image_url: str)
        """
        payload = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "image",
                    "originalContentUrl": original_url,
                    "previewImageUrl": preview_url or original_url,
                }
            ],
        }

        try:
            response = await self.client.post(
                f"{LINE_API_BASE}/bot/message/reply",
                json=payload,
            )

            if response.status_code == 200:
                logger.debug("Image reply sent successfully")
                # Extract message ID from response if available
                response_data = response.json()
                sent_messages = response_data.get("sentMessages", [])
                message_id = sent_messages[0]["id"] if sent_messages else None
                return (True, message_id, original_url)
            else:
                error_body = response.text[:200]
                logger.error(f"Image reply failed: {response.status_code} - {error_body}")
                return (False, None, original_url)
        except Exception as e:
            logger.error(f"Image reply error: {e}")
            return (False, None, original_url)
    
    async def send_loading_animation(
        self,
        chat_id: str,
        loading_seconds: int = 60,
    ) -> bool:
        """
        Send a loading animation to indicate the bot is processing.

        This is FREE and does not count toward message quotas.
        Shows a typing/loading indicator to the user for up to 60 seconds.

        Args:
            chat_id: User ID or group ID
            loading_seconds: Duration in seconds (5-60, default 60)

        Returns:
            True if successful
        """
        loading_seconds = max(5, min(60, loading_seconds))

        payload = {
            "chatId": chat_id,
            "loadingSeconds": loading_seconds,
        }

        try:
            response = await self.client.post(
                f"{LINE_API_BASE}/bot/chat/loading/start",
                json=payload,
            )

            if response.status_code in (200, 202):
                logger.debug(f"Loading animation sent to {chat_id[:8]}... ({loading_seconds}s)")
                return True
            else:
                logger.debug(f"Loading animation failed: {response.status_code}")
                return False

        except Exception as e:
            logger.debug(f"Loading animation error: {e}")
            return False

    async def get_message_content_with_type(
        self, 
        message_id: str
    ) -> tuple[Optional[BytesIO], Optional[str]]:
        """
        Download message content with content type.
        
        Args:
            message_id: LINE message ID
            
        Returns:
            Tuple of (content BytesIO, content_type string) or (None, None)
        """
        try:
            response = await self.client.get(
                f"{LINE_DATA_API_BASE}/bot/message/{message_id}/content",
            )
            
            if response.status_code == 200:
                content = BytesIO(response.content)
                content_type = response.headers.get("content-type", "application/octet-stream")
                return (content, content_type)
            else:
                return (None, None)
                
        except Exception as e:
            logger.error(f"Content download error: {e}")
            return (None, None)
    
    async def notify_admins(
        self,
        message: str,
        admin_user_ids: Optional[List[str]] = None,
    ) -> int:
        """
        Send notification to admin users.
        
        Args:
            message: Alert message
            admin_user_ids: List of admin user IDs (uses config if not provided)
            
        Returns:
            Number of successful notifications
        """
        settings = get_settings()
        admin_ids = admin_user_ids or settings.admin_user_id_list
        
        if not admin_ids:
            logger.warning("No admin user IDs configured for notifications")
            return 0
        
        success_count = 0
        for admin_id in admin_ids:
            if await self.push_text(admin_id, f"🚨 Alert: {message}"):
                success_count += 1
        
        logger.info(f"Admin notifications sent: {success_count}/{len(admin_ids)}")
        return success_count


# Global singleton instance
_line_service: Optional[LineService] = None


def get_line_service() -> LineService:
    """Get or create the global LineService instance."""
    global _line_service
    if _line_service is None:
        _line_service = LineService()
    return _line_service


async def close_line_service() -> None:
    """Close the global LineService instance."""
    global _line_service
    if _line_service:
        await _line_service.close()
        _line_service = None
