"""
Async Queue Service for LLM request processing.

Manages the request queue with max size enforcement,
semaphore-based concurrency control (1 concurrent request),
and a constantly-running worker for sequential processing.
"""

import asyncio
from typing import Optional, Callable, Awaitable, Any
from datetime import datetime

from src.models.llm_request import LLMRequest
from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger("services.queue")


class QueueFullError(Exception):
    """Raised when the queue is at maximum capacity."""
    
    def __init__(self, queue_size: int, max_size: int):
        self.queue_size = queue_size
        self.max_size = max_size
        super().__init__(f"Queue is full: {queue_size}/{max_size} requests pending")


class QueueService:
    """
    Async queue service for managing LLM inference requests.
    
    Features:
    - Maximum queue size enforcement (default: 10)
    - Semaphore-based concurrency control (1 concurrent inference)
    - Constantly-running worker for sequential processing
    - Queue position feedback for users
    - Timeout handling for long-running requests
    
    Attributes:
        queue: asyncio.Queue for pending requests
        max_size: Maximum pending requests allowed
        semaphore: Limits concurrent processing to 1
        timeout_seconds: Maximum processing time per request
        is_running: Whether the worker is active
    """
    
    def __init__(
        self,
        max_size: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        concurrency: int = 1,
    ):
        """
        Initialize queue service.
        
        Args:
            max_size: Maximum queue size (default from config)
            timeout_seconds: Request timeout (default from config)
            concurrency: Number of concurrent workers (must be 1 for GPU)
        """
        settings = get_settings()
        self.max_size = max_size or settings.queue_max_size
        self.timeout_seconds = timeout_seconds or settings.queue_timeout_seconds
        
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=self.max_size)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.is_running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._processor: Optional[Callable[[LLMRequest], Awaitable[Any]]] = None
        
        # Statistics
        self._total_processed = 0
        self._total_errors = 0
        self._start_time: Optional[datetime] = None
        
        logger.info(
            f"QueueService initialized: max_size={self.max_size}, "
            f"timeout={self.timeout_seconds}s, concurrency={concurrency}"
        )
    
    @property
    def current_size(self) -> int:
        """Get current number of pending requests."""
        return self.queue.qsize()
    
    @property
    def is_full(self) -> bool:
        """Check if queue is at capacity."""
        return self.queue.full()
    
    @property
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return self.queue.empty()
    
    async def enqueue(self, request: LLMRequest) -> int:
        """
        Add a request to the queue.
        
        Args:
            request: LLMRequest to enqueue
            
        Returns:
            Queue position (1-indexed)
            
        Raises:
            QueueFullError: If queue is at maximum capacity
        """
        if self.is_full:
            raise QueueFullError(self.current_size, self.max_size)
        
        await self.queue.put(request)
        position = self.current_size
        
        logger.info(
            f"Request enqueued at position {position}",
            extra={
                "request_id": request.request_id,
                "queue_size": position,
            }
        )
        
        return position
    
    def try_enqueue_nowait(self, request: LLMRequest) -> Optional[int]:
        """
        Try to enqueue without waiting.
        
        Args:
            request: LLMRequest to enqueue
            
        Returns:
            Queue position if successful, None if queue is full
        """
        try:
            self.queue.put_nowait(request)
            position = self.current_size
            
            logger.info(
                f"Request enqueued at position {position}",
                extra={
                    "request_id": request.request_id,
                }
            )
            
            return position
        except asyncio.QueueFull:
            logger.warning(
                "Queue full, request rejected",
                extra={"request_id": request.request_id}
            )
            return None
    
    def set_processor(
        self,
        processor: Callable[[LLMRequest], Awaitable[Any]]
    ) -> None:
        """
        Set the request processor callback.
        
        Args:
            processor: Async function that processes LLMRequest
        """
        self._processor = processor
        logger.debug("Request processor registered")
    
    async def start_worker(self) -> None:
        """Start the background worker task."""
        if self.is_running:
            logger.warning("Worker already running")
            return
        
        if self._processor is None:
            raise RuntimeError("No processor set. Call set_processor() first.")
        
        self.is_running = True
        self._start_time = datetime.utcnow()
        self._worker_task = asyncio.create_task(self._worker_loop())
        
        logger.info("Queue worker started")
    
    async def stop_worker(self, graceful: bool = True) -> None:
        """
        Stop the background worker.
        
        Args:
            graceful: If True, finish processing current request
        """
        self.is_running = False
        
        if self._worker_task:
            if graceful:
                # Wait for current request to finish
                try:
                    await asyncio.wait_for(self._worker_task, timeout=self.timeout_seconds)
                except asyncio.TimeoutError:
                    logger.warning("Graceful shutdown timed out, cancelling")
                    self._worker_task.cancel()
            else:
                self._worker_task.cancel()
            
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        logger.info(
            f"Queue worker stopped. Processed: {self._total_processed}, "
            f"Errors: {self._total_errors}"
        )
    
    async def _worker_loop(self) -> None:
        """Main worker loop - runs continuously processing requests."""
        logger.info("Worker loop started")
        
        while self.is_running:
            try:
                # Wait for a request with timeout to allow shutdown checks
                try:
                    request = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=1.0  # Check is_running every second
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process with semaphore (ensures single concurrency)
                async with self.semaphore:
                    await self._process_request(request)
                
                self.queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("Worker loop cancelled")
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}", exc_info=True)
                self._total_errors += 1
    
    async def _process_request(self, request: LLMRequest) -> None:
        """Process a single request with timeout handling."""
        start_time = datetime.utcnow()
        
        try:
            logger.info(
                f"Processing request",
                extra={
                    "request_id": request.request_id,
                    "age_seconds": request.age_seconds,
                }
            )
            
            # Process with timeout
            await asyncio.wait_for(
                self._processor(request),
                timeout=self.timeout_seconds
            )
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            self._total_processed += 1
            
            logger.info(
                f"Request completed",
                extra={
                    "request_id": request.request_id,
                    "duration_ms": duration_ms,
                }
            )
            
        except asyncio.TimeoutError:
            self._total_errors += 1
            logger.error(
                f"Request timed out after {self.timeout_seconds}s",
                extra={"request_id": request.request_id}
            )
            # Let the processor handle timeout notification if needed
            
        except Exception as e:
            self._total_errors += 1
            logger.error(
                f"Request processing error: {e}",
                extra={"request_id": request.request_id},
                exc_info=True
            )
            
            # Retry if allowed
            if request.can_retry:
                request.increment_retry()
                try:
                    self.queue.put_nowait(request)
                    logger.info(
                        f"Request requeued for retry",
                        extra={
                            "request_id": request.request_id,
                            "retry_count": request.retry_count,
                        }
                    )
                except asyncio.QueueFull:
                    logger.warning("Cannot requeue - queue is full")
    
    def get_stats(self) -> dict:
        """Get queue statistics for monitoring."""
        uptime = None
        if self._start_time:
            uptime = (datetime.utcnow() - self._start_time).total_seconds()
        
        return {
            "current_size": self.current_size,
            "max_size": self.max_size,
            "is_running": self.is_running,
            "total_processed": self._total_processed,
            "total_errors": self._total_errors,
            "uptime_seconds": uptime,
        }
    
    def get_estimated_wait(self) -> int:
        """
        Estimate wait time in seconds for new request.
        
        Based on average processing time assumption of 15 seconds.
        """
        avg_processing_time = 15  # seconds per request (estimate)
        return self.current_size * avg_processing_time


# Global singleton instance
_queue_service: Optional[QueueService] = None


def get_queue_service() -> QueueService:
    """Get or create the global QueueService instance."""
    global _queue_service
    if _queue_service is None:
        _queue_service = QueueService()
    return _queue_service
