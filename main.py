"""
LINE Bot with Local Ollama VLM Integration - Main Application.

FastAPI application with:
- LINE webhook endpoint
- Health check endpoint
- Background queue worker
- Startup/shutdown lifecycle management
"""

from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from src.config import get_settings
from src.utils.logger import setup_logging, get_logger, LogContext
from src.utils.validators import validate_line_signature

# Services
from src.services.line_service import get_line_service, close_line_service
from src.services.ollama_service import get_ollama_service, close_ollama_service
from src.services.queue_service import get_queue_service
from src.services.rate_limit_service import get_rate_limit_service
from src.services.image_service import download_and_process_image
from src.services.drive_service import get_drive_service, close_drive_service
from src.services.scheduler_service import get_scheduler_service, close_scheduler_service
from src.services.web_search_service import close_web_search_service

# Handlers
from src.handlers.command_handler import (
    parse_webhook_message,
    extract_event_context,
    CommandType,
)
from src.handlers.hej_handler import handle_hej_command
from src.handlers.reload_handler import handle_reload_command
from src.handlers.img_handler import handle_img_command
from src.handlers.web_handler import handle_web_command

# Models
from src.models.llm_request import LLMRequest

from src.services.message_cache_service import cache_message
from src.services.conversation_context_service import (
    add_message as add_context_message,
    get_stats as get_context_stats,
)

logger = get_logger("main")


async def process_llm_request(request: LLMRequest) -> None:
    """
    Process a queued LLM request.
    
    This is the callback registered with the queue service worker.
    Handles the actual Ollama inference and LINE response.
    """
    line_service = get_line_service()
    ollama_service = get_ollama_service()
    
    logger.info(
        f"Processing LLM request",
        extra={
            "request_id": request.request_id,
            "user_id": request.user_id,
            "has_image": request.is_multimodal,
        }
    )
    
    try:
        # Check if we need to download an image for multimodal request
        image_base64 = request.context_image_base64
        
        # Handle quoted image
        # Scenario 1: Bot-sent image (URL cached)
        if hasattr(request, "_quoted_image_url") and request._quoted_image_url:
            logger.debug(f"Loading bot-sent image from URL: {request._quoted_image_url}")
            try:
                # Download image from our own server
                import httpx
                from io import BytesIO
                from src.services.image_service import process_image_bytes

                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        request._quoted_image_url, 
                        timeout=30.0,
                        follow_redirects=True
                    )
                    if response.status_code == 200:
                        # Process the image
                        image_io = BytesIO(response.content)
                        image_base64 = process_image_bytes(image_io)
                        logger.info("Bot-sent image loaded and processed successfully")
                    else:
                        logger.warning(f"Failed to load bot-sent image: HTTP {response.status_code}")
            except Exception as e:
                logger.error(f"Error loading bot-sent image: {e}", exc_info=True)
        
        # Scenario 2: User-sent image (Download from LINE)
        elif hasattr(request, "_quoted_image_message_id") and request._quoted_image_message_id:
            logger.debug(f"Downloading quoted user image: {request._quoted_image_message_id}")
            # Use original download logic for user images
            image_base64 = await download_and_process_image(request._quoted_image_message_id)
            if image_base64:
                logger.info("User quoted image downloaded and processed successfully")
            else:
                logger.warning("Failed to download quoted user image")
        
        # Call Ollama for inference
        response_text = await ollama_service.generate(
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            image_base64=image_base64,
            context_text=request.context_text,
            conversation_history=request.conversation_history,
            web_search_results=request.web_search_results,
        )

        # Helper to add bot response to conversation context
        def add_bot_response_to_context():
            settings = get_settings()
            bot_user_id = "BOT_" + settings.line_channel_secret[:8]
            add_context_message(request.group_id, bot_user_id, response_text, "text")
            logger.debug("Added bot response to conversation context")

        # Try to use reply_token first (valid for ~60s), fallback to push message
        success = False
        if request.reply_token:
            # Try reply first (faster and doesn't count against rate limits)
            success, sent_message_id, sent_text = await line_service.reply_text(
                reply_token=request.reply_token,
                text=response_text,
            )
            if success:
                logger.info(
                    f"Response sent via reply_token",
                    extra={"request_id": request.request_id}
                )
                # Cache the bot's response for potential future quotes
                if sent_message_id:
                    cache_message(sent_message_id, "text", sent_text)
                    logger.debug(f"Cached bot response: id={sent_message_id}")
                add_bot_response_to_context()

        if not success:
            # Reply token expired or failed, use push message
            success = await line_service.push_text(
                to=request.group_id,
                text=response_text,
            )
            if success:
                logger.info(
                    f"Response sent via push message",
                    extra={"request_id": request.request_id}
                )
                add_bot_response_to_context()
            else:
                logger.error(
                    f"Failed to send response",
                    extra={"request_id": request.request_id}
                )

    except Exception as e:
        logger.error(
            f"LLM request processing failed: {e}",
            extra={"request_id": request.request_id},
            exc_info=True
        )

        # Try to notify user of error (use reply_token if available, otherwise push)
        try:
            if request.reply_token:
                await line_service.reply_text(
                    reply_token=request.reply_token,
                    text="❌ 處理請求時發生錯誤，請稍後再試。",
                )
            else:
                await line_service.push_text(
                    to=request.group_id,
                    text="❌ 處理請求時發生錯誤，請稍後再試。",
                )
        except Exception:
            pass  # Best effort notification


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup initialization and graceful shutdown.
    """
    settings = get_settings()
    
    # Configure logging
    setup_logging(
        level=settings.log_level,
        json_output=False,  # Use readable format for now
    )
    
    logger.info("=" * 50)
    logger.info("LINE Bot with Ollama VLM - Starting up")
    logger.info("=" * 50)
    
    # Initialize services
    line_service = get_line_service()
    ollama_service = get_ollama_service()
    queue_service = get_queue_service()
    rate_limit_service = get_rate_limit_service()
    drive_service = get_drive_service()
    scheduler_service = get_scheduler_service()
    
    # Health check Ollama
    if await ollama_service.health_check():
        logger.info("✅ Ollama service is available")
    else:
        logger.warning("⚠️ Ollama service is not responding - bot will retry on requests")
    
    # Register queue processor
    queue_service.set_processor(process_llm_request)
    
    # Start queue worker
    await queue_service.start_worker()
    logger.info("✅ Queue worker started")
    
    # Start Drive background sync (if configured)
    await drive_service.start_background_sync()
    if drive_service.is_configured:
        logger.info("✅ Drive sync started")
    else:
        logger.info("ℹ️ Drive sync not configured, using default prompts")

    # Start scheduler and configure scheduled messages
    scheduler_service.start()
    if settings.scheduled_messages_enabled and settings.scheduled_group_id:
        # 排程 1: 每週一晚上 9:00
        scheduler_service.add_weekly_message(
            job_id="monday_workout_reminder",
            day_of_week="mon",
            hour=21,
            minute=0,
            group_id=settings.scheduled_group_id,
            message="明天操一下嗎?",
        )

        # 排程 2: 每週五下午 6:30
        scheduler_service.add_weekly_message(
            job_id="pineapple_workout_reminder",
            day_of_week="mon",
            hour=21,
            minute=30,
            group_id=settings.scheduled_group_id,
            message="啊哈！@鳳梨 還沒回覆督促一下",
        )

        logger.info("✅ Scheduled messages configured")
    else:
        logger.info("ℹ️ Scheduled messages not enabled")

    logger.info(f"🚀 Server ready on {settings.host}:{settings.port}")
    logger.info("=" * 50)
    
    yield  # Application runs here
    
    # Shutdown
    logger.info("Shutting down...")

    # Stop queue worker gracefully
    await queue_service.stop_worker(graceful=True)

    # Stop scheduler
    close_scheduler_service()

    # Stop Drive sync
    await close_drive_service()

    # Close service connections
    await close_web_search_service()
    await close_ollama_service()
    await close_line_service()

    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="LINE Bot with Ollama VLM",
    description="LINE chatbot with local Ollama VLM integration",
    version="1.0.0",
    lifespan=lifespan,
)

# Setup temporary image directory for serving images via HTTPS
TEMP_IMAGE_DIR = Path("/tmp/linebot_images")
TEMP_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files for serving images
app.mount("/images", StaticFiles(directory=str(TEMP_IMAGE_DIR)), name="images")


@app.get("/")
async def root():
    """Root endpoint - redirects to health check."""
    return JSONResponse({
        "message": "LINE Bot is running",
        "endpoints": {
            "health": "/health",
            "webhook": "/webhook (POST only)"
        }
    })


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring.

    Returns service status and queue statistics.
    """
    queue_service = get_queue_service()
    ollama_service = get_ollama_service()
    rate_limit_service = get_rate_limit_service()
    drive_service = get_drive_service()
    scheduler_service = get_scheduler_service()

    ollama_healthy = await ollama_service.health_check()

    return JSONResponse({
        "status": "healthy" if ollama_healthy else "degraded",
        "services": {
            "ollama": "up" if ollama_healthy else "down",
            "queue": queue_service.get_stats(),
            "rate_limit": rate_limit_service.get_stats(),
            "drive": drive_service.get_stats(),
            "scheduler": scheduler_service.get_stats(),
            "conversation_context": get_context_stats(),
        }
    })


@app.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: str = Header(..., alias="X-Line-Signature"),
):
    """
    LINE webhook endpoint.
    
    Receives webhook events from LINE, validates signature,
    parses commands, and enqueues requests for processing.
    
    Returns 200 immediately to acknowledge receipt.
    """
    # Read raw body for signature validation
    body = await request.body()
    
    # Validate signature
    settings = get_settings()
    if not validate_line_signature(body, x_line_signature, settings.line_channel_secret):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # Parse JSON body
    try:
        import json
        body_json = json.loads(body.decode('utf-8'))
        logger.debug(f"Parsed webhook body: {len(body_json.get('events', []))} events")
    except Exception as e:
        logger.error(f"Failed to parse webhook body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Process events
    events = body_json.get("events", [])
    logger.debug(f"Processing {len(events)} events")
    
    for event in events:
        try:
            await handle_webhook_event(event)
        except Exception as e:
            logger.error(f"Error handling event: {e}", exc_info=True)
            # Continue processing other events
    
    # Always return 200 to acknowledge receipt
    return JSONResponse({"status": "ok"})


async def handle_webhook_event(event: Dict[str, Any]) -> None:
    """
    Handle a single webhook event.

    Args:
        event: LINE webhook event dictionary
    """
    event_type = event.get("type")

    # Only handle message events
    if event_type != "message":
        logger.debug(f"Ignoring event type: {event_type}")
        return

    # Debug: Log the message content and event structure
    message = event.get("message", {})
    message_type = message.get("type")
    message_text = message.get("text", "")
    message_id = message.get("id")
    logger.debug(f"Received message - type: {message_type}, text: {message_text[:50]}")

    # Extract context for conversation history
    source = event.get("source", {})
    user_id = source.get("userId")
    group_id = source.get("groupId") or source.get("roomId") or user_id

    # Cache this message for potential future quote/reply
    if message_id:
        cache_message(message_id, message_type, message_text if message_type == "text" else None)
        logger.debug(f"Cached message: id={message_id}, type={message_type}")

    # Add to conversation context (for all text and image messages)
    if user_id and group_id and message_type in ["text", "image", "sticker"]:
        # For text messages, store the actual text
        # For other types, store a description
        if message_type == "text" and message_text:
            add_context_message(group_id, user_id, message_text, message_type)
        elif message_type == "image":
            add_context_message(group_id, user_id, "[圖片]", message_type)
        elif message_type == "sticker":
            add_context_message(group_id, user_id, "[貼圖]", message_type)

        logger.debug(f"Added to conversation context: group={group_id[:8]}, type={message_type}")

    # Log full event structure for debugging reply/quote feature
    import json
    logger.debug(f"Full event structure: {json.dumps(event, ensure_ascii=False)}")

    # Parse command from message
    command = parse_webhook_message(event)

    if command is None:
        # Not a command message - ignore
        logger.debug(f"Not a command message (no ! prefix)")
        return

    if not command.is_valid:
        # Unknown command - could optionally send help message
        logger.debug(f"Unknown command in message: {command.command_type}")
        return
    
    context = extract_event_context(event)
    
    with LogContext(
        logger,
        user_id=context.get("user_id"),
        command=command.command_type.value,
    ):
        # Route to appropriate handler
        if command.command_type == CommandType.HEJ:
            await handle_hej_command(command, event)

        elif command.command_type == CommandType.IMG:
            await handle_img_command(command, event)

        elif command.command_type == CommandType.WEB:
            await handle_web_command(command, event)

        elif command.command_type == CommandType.RELOAD:
            await handle_reload_command(command, event)


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,  # Don't use reload in production
        log_level=settings.log_level.lower(),
    )
