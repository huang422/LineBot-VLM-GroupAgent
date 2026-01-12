"""
Scheduler Service for scheduled message sending.

Handles scheduled tasks like:
- Weekly reminder messages
- Periodic notifications
- Time-based bot actions
"""

from typing import Optional, List, Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

from src.utils.logger import get_logger
from src.config import get_settings

logger = get_logger("services.scheduler")


class SchedulerService:
    """
    Service for managing scheduled tasks.

    Uses APScheduler with async support to schedule recurring
    messages and notifications.
    """

    def __init__(self):
        """Initialize the scheduler service."""
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        logger.info("SchedulerService initialized")

    def start(self) -> None:
        """Start the scheduler."""
        if not self.is_running:
            self.scheduler.start()
            self.is_running = True
            logger.info("✅ Scheduler started")

    def shutdown(self) -> None:
        """Shutdown the scheduler gracefully."""
        if self.is_running:
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("Scheduler stopped")

    def add_weekly_message(
        self,
        job_id: str,
        day_of_week: str,
        hour: int,
        minute: int,
        group_id: str,
        message: str,
    ) -> bool:
        """
        Add a weekly scheduled message.

        Args:
            job_id: Unique identifier for this job
            day_of_week: Day name (mon, tue, wed, thu, fri, sat, sun)
            hour: Hour (0-23)
            minute: Minute (0-59)
            group_id: LINE group ID to send message to
            message: Message text to send

        Returns:
            True if job was added successfully
        """
        try:
            from src.services.line_service import get_line_service

            async def send_scheduled_message():
                """Async task to send the scheduled message."""
                line_service = get_line_service()
                logger.info(
                    f"Sending scheduled message",
                    extra={
                        "job_id": job_id,
                        "group_id": group_id[:8],
                        "message_text": message[:30],
                    }
                )

                success = await line_service.push_text(
                    to=group_id,
                    text=message,
                    notification_disabled=False,
                )

                if success:
                    logger.info(f"Scheduled message sent successfully: {job_id}")
                else:
                    logger.error(f"Failed to send scheduled message: {job_id}")

            # Create cron trigger for weekly schedule
            trigger = CronTrigger(
                day_of_week=day_of_week,
                hour=hour,
                minute=minute,
                timezone="Asia/Taipei",  # Taiwan timezone
            )

            # Add job to scheduler
            self.scheduler.add_job(
                send_scheduled_message,
                trigger=trigger,
                id=job_id,
                name=f"Weekly message: {message[:20]}",
                replace_existing=True,
            )

            logger.info(
                f"Added weekly job",
                extra={
                    "job_id": job_id,
                    "schedule": f"{day_of_week} {hour:02d}:{minute:02d}",
                    "group_id": group_id[:8],
                }
            )
            return True

        except Exception as e:
            logger.error(f"Failed to add scheduled job: {e}", exc_info=True)
            return False

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a scheduled job.

        Args:
            job_id: Job identifier

        Returns:
            True if job was removed
        """
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to remove job {job_id}: {e}")
            return False

    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        List all scheduled jobs.

        Returns:
            List of job information dictionaries
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return jobs

    def get_stats(self) -> Dict[str, Any]:
        """
        Get scheduler statistics.

        Returns:
            Dictionary with scheduler status
        """
        return {
            "running": self.is_running,
            "job_count": len(self.scheduler.get_jobs()),
            "jobs": self.list_jobs(),
        }


# Global singleton instance
_scheduler_service: Optional[SchedulerService] = None


def get_scheduler_service() -> SchedulerService:
    """Get or create the global SchedulerService instance."""
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service


def close_scheduler_service() -> None:
    """Close the global SchedulerService instance."""
    global _scheduler_service
    if _scheduler_service:
        _scheduler_service.shutdown()
        _scheduler_service = None
