"""
Reload Command Handler for manual Drive sync.

Handles !reload command to force immediate synchronization
of prompts and configuration from Google Drive.
"""

from typing import Dict, Any

from src.handlers.command_handler import ParsedCommand, extract_event_context
from src.services.drive_service import get_drive_service
from src.services.line_service import get_line_service
from src.utils.logger import get_logger

logger = get_logger("handlers.reload")

# Response messages
MSG_RELOADING = "🔄 正在重新載入設定..."
MSG_SUCCESS = "✅ 設定已更新！\n• 提示詞: {prompt_status}\n• 圖片設定: {image_status}"
MSG_NO_CHANGES = "ℹ️ 設定已是最新，無需更新。"
MSG_NOT_CONFIGURED = "⚠️ Google Drive 同步未設定。請聯繫管理員。"
MSG_ERROR = "❌ 重新載入失敗，請稍後再試。"


async def handle_reload_command(
    command: ParsedCommand,
    event: Dict[str, Any],
) -> bool:
    """
    Handle !reload command for manual Drive sync.
    
    Args:
        command: Parsed command data
        event: Original LINE webhook event
        
    Returns:
        True if reload was triggered successfully
    """
    context = extract_event_context(event)
    reply_token = context["reply_token"]
    
    line_service = get_line_service()
    drive_service = get_drive_service()
    
    # Check if Drive is configured
    if not drive_service.is_configured:
        logger.info("Reload requested but Drive not configured")
        if reply_token:
            await line_service.reply_text(reply_token, MSG_NOT_CONFIGURED)
        return False
    
    try:
        logger.info(
            "Manual reload triggered"
        )
        
        # Trigger sync
        prompt_updated, images_updated = await drive_service.sync_all()
        
        # Build response message
        if prompt_updated or images_updated:
            prompt_status = "已更新 ✓" if prompt_updated else "無變更"
            image_status = "已更新 ✓" if images_updated else "無變更"
            
            message = MSG_SUCCESS.format(
                prompt_status=prompt_status,
                image_status=image_status,
            )
        else:
            message = MSG_NO_CHANGES
        
        if reply_token:
            await line_service.reply_text(reply_token, message)
        
        return True
        
    except Exception as e:
        logger.error(f"Reload command failed: {e}", exc_info=True)
        if reply_token:
            await line_service.reply_text(reply_token, MSG_ERROR)
        return False
