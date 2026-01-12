"""
Hej Command Handler for LLM inference requests.

Handles !hej commands by:
1. Checking rate limits
2. Creating LLMRequest from parsed command
3. Enqueuing for processing
4. Sending queue feedback to user
"""

from typing import Dict, Any, Optional

from src.handlers.command_handler import ParsedCommand, extract_event_context
from src.models.llm_request import LLMRequest
from src.models.prompt_config import DEFAULT_PROMPT_CONFIG
from src.services.rate_limit_service import get_rate_limit_service
from src.services.queue_service import get_queue_service, QueueFullError
from src.services.line_service import get_line_service
from src.services.message_cache_service import get_cached_message
from src.services.drive_service import get_drive_service
from src.utils.logger import get_logger

logger = get_logger("handlers.hej")

# Response messages
MSG_QUEUED = "🔄 收到！正在處理您的請求... (隊列位置: {position}，預計等待 {wait}秒)"
MSG_QUEUE_FULL = "⚠️ 抱歉，系統目前繁忙。請稍後再試。"
MSG_RATE_LIMITED = "⚠️ 您的請求太頻繁了。請在 {seconds} 秒後再試。"
MSG_EMPTY_PROMPT = "❓ 請在 !hej 後輸入您的問題。例如：!hej 今天天氣如何？"
MSG_ERROR = "❌ 處理請求時發生錯誤，請稍後再試。"


# Global prompt config (will be updated by Drive sync)
_current_prompt_config = DEFAULT_PROMPT_CONFIG


def get_current_prompt() -> str:
    """Get the current system prompt."""
    return _current_prompt_config.content


def set_prompt_config(config) -> None:
    """Update the current prompt config (called by Drive sync)."""
    global _current_prompt_config
    _current_prompt_config = config
    logger.info(f"Prompt config updated to version {config.version}")


async def handle_hej_command(
    command: ParsedCommand,
    event: Dict[str, Any],
) -> bool:
    """
    Handle !hej command for LLM inference or image keyword search.

    First checks if the argument matches an image keyword.
    If it does, sends the image directly (like !img).
    Otherwise, proceeds with LLM inference.

    Args:
        command: Parsed command data
        event: Original LINE webhook event

    Returns:
        True if request was successfully queued or image was sent
    """
    context = extract_event_context(event)
    user_id = context["user_id"]
    group_id = context["group_id"]
    reply_token = context["reply_token"]

    line_service = get_line_service()
    rate_limit_service = get_rate_limit_service()
    queue_service = get_queue_service()
    drive_service = get_drive_service()

    # Validate we have required context
    if not user_id or not group_id:
        logger.warning("Missing user_id or group_id in event")
        return False

    # Check for empty prompt (unless it's a reply with content)
    if not command.argument and not command.has_quoted_content:
        if reply_token:
            await line_service.reply_text(reply_token, MSG_EMPTY_PROMPT)
        return False

    # NEW: Check if argument matches an image keyword
    # Only check if there's an argument and Drive is configured
    if command.argument and drive_service.is_configured:
        keyword = command.argument.strip()
        image_config = drive_service.image_config

        # Check if this keyword matches an image
        if image_config.mappings:
            mapping = image_config.get_by_keyword(keyword)

            if mapping:
                # Found matching image - send it like !img does
                logger.info(f"!hej matched image keyword: {keyword}, sending image")
                from src.handlers.img_handler import handle_img_command

                # Create a temporary command object for img handler
                img_command = ParsedCommand(
                    command_type=command.command_type,  # Keep original type for logging
                    argument=keyword,
                    raw_text=command.raw_text,
                    is_reply=command.is_reply,
                    quoted_message_id=command.quoted_message_id,
                    quoted_message_type=command.quoted_message_type,
                    quoted_message_text=command.quoted_message_text,
                )

                # Delegate to img handler
                return await handle_img_command(img_command, event)
    
    # Check rate limit
    allowed, seconds_until_reset, remaining = await rate_limit_service.check_and_record(user_id)
    
    if not allowed:
        logger.info(
            f"Rate limit exceeded",
            extra={"reset_in": seconds_until_reset}
        )
        if reply_token:
            await line_service.reply_text(
                reply_token,
                MSG_RATE_LIMITED.format(seconds=seconds_until_reset)
            )
        return False
    
    try:
        # Get quoted message content from cache if replying
        context_text = None
        quoted_image_message_id = None
        quoted_image_url = None

        if command.quoted_message_id:
            cached_msg = get_cached_message(command.quoted_message_id)
            if cached_msg:
                if cached_msg["type"] == "text" and cached_msg["text"]:
                    context_text = cached_msg["text"]
                    logger.info(f"Retrieved quoted text from cache: {context_text[:50]}...")
                elif cached_msg["type"] == "image":
                    # Check if this is a bot-sent image with URL in cache
                    if cached_msg.get("image_url"):
                        quoted_image_url = cached_msg["image_url"]
                        logger.info(f"Retrieved bot-sent image URL from cache: {quoted_image_url}")
                    else:
                        # User-sent image, need to download from LINE
                        quoted_image_message_id = command.quoted_message_id
                        logger.info("Quoted message is a user-sent image, will download from LINE")
            else:
                logger.warning(f"Quoted message {command.quoted_message_id} not found in cache")

        # Create LLM request
        request = LLMRequest(
            user_id=user_id,
            group_id=group_id,
            prompt=command.argument or "請分析這個內容",  # Default for reply-only
            system_prompt=get_current_prompt(),
            reply_token=reply_token,
            context_text=context_text,
            # Note: context_image_base64 will be populated by the processor if needed
        )

        # Store quoted image info for later processing
        if quoted_image_message_id:
            request._quoted_image_message_id = quoted_image_message_id
        if quoted_image_url:
            request._quoted_image_url = quoted_image_url
        
        # Try to enqueue
        position = queue_service.try_enqueue_nowait(request)
        
        if position is None:
            # Queue is full
            logger.warning("Queue full, request rejected")
            if reply_token:
                await line_service.reply_text(reply_token, MSG_QUEUE_FULL)
            return False
        
        logger.info(
            f"Request queued",
            extra={
                "request_id": request.request_id,
                "position": position,
                "has_context": command.has_quoted_content,
            }
        )

        # Don't send queue confirmation - will reply directly with LLM response
        # The LLM response will use reply_token if still valid, otherwise push message

        return True
        
    except ValueError as e:
        # Validation error in LLMRequest
        logger.error(f"Invalid request: {e}")
        if reply_token:
            await line_service.reply_text(reply_token, MSG_ERROR)
        return False
        
    except Exception as e:
        logger.error(f"Unexpected error in hej handler: {e}", exc_info=True)
        if reply_token:
            await line_service.reply_text(reply_token, MSG_ERROR)
        return False
