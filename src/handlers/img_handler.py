"""
Image Command Handler for keyword-based image retrieval.

Handles !img [keyword] commands by looking up the keyword
in the image mapping and sending the corresponding image.
"""

from typing import Dict, Any
import base64

from src.handlers.command_handler import ParsedCommand, extract_event_context
from src.services.drive_service import get_drive_service
from src.services.line_service import get_line_service
from src.utils.logger import get_logger

logger = get_logger("handlers.img")

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
                "filename": mapping.filename,
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
        
        # Send image using LINE SDK
        # Note: LINE requires image to be hosted at a URL for imagemap/image messages
        # For direct binary upload, we need to use the push message with image content
        
        # For now, we'll send a text message indicating the image
        # In production, you'd upload to a CDN or use LINE's blob upload
        success = await _send_image_via_line(
            line_service,
            reply_token,
            context.get("group_id"),
            image_bytes,
            mapping.filename,
        )
        
        if success:
            logger.info(f"Image sent successfully: {mapping.keyword}")
        
        return success
        
    except Exception as e:
        logger.error(f"Image command failed: {e}", exc_info=True)
        if reply_token:
            await line_service.reply_text(reply_token, MSG_ERROR)
        return False


async def _send_image_via_line(
    line_service,
    reply_token: str,
    group_id: str,
    image_bytes: bytes,
    filename: str,
) -> bool:
    """
    Send image to LINE.
    
    Note: LINE Messaging API requires images to be hosted at HTTPS URLs.
    For local deployment without image hosting, we'd need to either:
    1. Upload to a cloud storage and use the URL
    2. Use the LINE Blob API (requires additional setup)
    3. Convert to a shareable URL via Cloudflare Tunnel
    
    For now, this sends a placeholder message.
    In production, integrate with your image hosting solution.
    """
    # Placeholder: In production, implement proper image hosting/sending
    # Options:
    # - Upload to Google Cloud Storage/S3 and use presigned URL
    # - Use LINE's blob upload API
    # - Host via the FastAPI server with a static route (requires HTTPS)
    
    # For MVP, just confirm the image was found
    size_kb = len(image_bytes) / 1024
    message = f"📷 圖片: {filename}\n大小: {size_kb:.1f} KB\n\n(圖片直接發送功能開發中)"
    
    if reply_token:
        return await line_service.reply_text(reply_token, message)
    elif group_id:
        return await line_service.push_text(group_id, message)
    
    return False
