"""
Web Command Handler for LLM inference with web search results.

Handles !web commands by:
1. Checking rate limits
2. Performing web search using Tavily AI
3. Creating LLMRequest with search results as context
4. Enqueuing for processing
"""

from typing import Dict, Any

from src.handlers.command_handler import ParsedCommand, extract_event_context
from src.models.llm_request import LLMRequest
from src.services.rate_limit_service import get_rate_limit_service
from src.services.queue_service import get_queue_service
from src.services.line_service import get_line_service
from src.services.message_cache_service import get_cached_message
from src.services.conversation_context_service import get_context_as_text
from src.services.web_search_service import (
    get_web_search_service,
    WebSearchError,
)
from src.utils.logger import get_logger

logger = get_logger("handlers.web")

# Response messages
MSG_QUEUED = "🔄 收到！正在搜尋並處理您的請求..."
MSG_QUEUE_FULL = "⚠️ 抱歉，系統目前繁忙。請稍後再試。"
MSG_RATE_LIMITED = "⚠️ 您的請求太頻繁了。請在 {seconds} 秒後再試。"
MSG_EMPTY_PROMPT = "❓ 請在 !web 後輸入您的搜尋問題。例如：!web 台灣最新新聞"
MSG_SEARCH_ERROR = "⚠️ 網路搜尋暫時無法使用，請稍後再試。"
MSG_ERROR = "❌ 處理請求時發生錯誤，請稍後再試。"


def get_current_prompt() -> str:
    """Get the current system prompt from drive service or default."""
    from src.handlers.hej_handler import get_current_prompt as hej_get_prompt
    return hej_get_prompt()


async def handle_web_command(
    command: ParsedCommand,
    event: Dict[str, Any],
) -> bool:
    """
    Handle !web command for LLM inference with web search.

    Performs a web search first, then includes the results as context
    for the LLM to generate an informed response.

    Args:
        command: Parsed command data
        event: Original LINE webhook event

    Returns:
        True if request was successfully queued
    """
    context = extract_event_context(event)
    user_id = context["user_id"]
    group_id = context["group_id"]
    reply_token = context["reply_token"]

    line_service = get_line_service()
    rate_limit_service = get_rate_limit_service()
    queue_service = get_queue_service()
    web_search_service = get_web_search_service()

    # Validate we have required context
    if not user_id or not group_id:
        logger.warning("Missing user_id or group_id in event")
        return False

    # Check for empty prompt
    if not command.argument:
        if reply_token:
            await line_service.reply_text(reply_token, MSG_EMPTY_PROMPT)
        return False

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
        # Perform web search
        search_query = command.argument
        logger.info(f"Performing web search: {search_query[:50]}...")

        try:
            search_response = await web_search_service.search(
                query=search_query,
                max_results=3,
            )
            web_search_results = search_response.to_context_text() if search_response.has_results else None

            # Search results logged at debug level only if needed for troubleshooting

        except WebSearchError as e:
            logger.error(f"Web search failed: {e}")
            # Continue without search results but warn user
            web_search_results = None

        # Get quoted message content from cache if replying
        context_text = None
        if command.quoted_message_id:
            cached_msg = get_cached_message(command.quoted_message_id)
            if cached_msg and cached_msg["type"] == "text" and cached_msg["text"]:
                context_text = cached_msg["text"]
                logger.info(f"Retrieved quoted text from cache: {context_text[:50]}...")

        # Get conversation history for this group
        conversation_history = get_context_as_text(group_id, max_messages=5)
        if conversation_history:
            logger.info(
                f"📚 Conversation history for this request ({len(conversation_history)} chars)"
            )

        # Create LLM request with web search results
        request = LLMRequest(
            user_id=user_id,
            group_id=group_id,
            prompt=command.argument,
            system_prompt=get_current_prompt(),
            reply_token=reply_token,
            context_text=context_text,
            conversation_history=conversation_history,
            web_search_results=web_search_results,
        )

        # Try to enqueue
        position = queue_service.try_enqueue_nowait(request)

        if position is None:
            logger.warning("Queue full, request rejected")
            if reply_token:
                await line_service.reply_text(reply_token, MSG_QUEUE_FULL)
            return False

        logger.info(
            f"Request queued",
            extra={
                "request_id": request.request_id,
                "position": position,
                "has_web_search": request.has_web_search,
            }
        )

        return True

    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        if reply_token:
            await line_service.reply_text(reply_token, MSG_ERROR)
        return False

    except Exception as e:
        logger.error(f"Unexpected error in web handler: {e}", exc_info=True)
        if reply_token:
            await line_service.reply_text(reply_token, MSG_ERROR)
        return False
