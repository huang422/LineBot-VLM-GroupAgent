"""
Admin notification utility for critical alerts.

Provides a simple interface to send push notifications to
configured admin users for system alerts and errors.
"""

from typing import Optional, List
from enum import Enum

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger("utils.admin_notifier")


class AlertLevel(Enum):
    """Alert severity levels."""
    CRITICAL = "critical"  # System down, immediate action needed
    WARNING = "warning"    # Degraded service, attention needed
    INFO = "info"          # Informational notices


# Alert level priority (lower = more severe)
ALERT_PRIORITY = {
    AlertLevel.CRITICAL: 0,
    AlertLevel.WARNING: 1,
    AlertLevel.INFO: 2,
}


def should_notify(alert_level: AlertLevel, configured_level: str) -> bool:
    """
    Check if alert should trigger notification based on configured threshold.

    Args:
        alert_level: Severity of the alert
        configured_level: Minimum level configured for notifications

    Returns:
        True if alert meets or exceeds configured threshold
    """
    try:
        threshold = AlertLevel(configured_level)
    except ValueError:
        threshold = AlertLevel.WARNING

    return ALERT_PRIORITY[alert_level] <= ALERT_PRIORITY[threshold]


async def notify_admins(
    message: str,
    level: AlertLevel = AlertLevel.WARNING,
    admin_ids: Optional[List[str]] = None,
) -> int:
    """
    Send notification to configured admin users.

    Args:
        message: Alert message content
        level: Alert severity level
        admin_ids: Override admin user IDs (uses config if not provided)

    Returns:
        Number of successful notifications sent
    """
    settings = get_settings()

    # Check if we should notify based on configured level
    if not should_notify(level, settings.admin_alert_level):
        logger.debug(f"Alert level {level.value} below threshold, not notifying")
        return 0

    # Get admin IDs
    target_ids = admin_ids or settings.admin_user_id_list

    if not target_ids:
        logger.warning("No admin user IDs configured for notifications")
        return 0

    # Format message with level indicator
    level_emoji = {
        AlertLevel.CRITICAL: "\U0001F6A8",  # rotating light
        AlertLevel.WARNING: "\u26a0\ufe0f",  # warning sign
        AlertLevel.INFO: "\u2139\ufe0f",     # information
    }

    formatted_message = f"{level_emoji.get(level, '')} [{level.value.upper()}] {message}"

    # Import here to avoid circular imports
    from src.services.line_service import get_line_service
    line_service = get_line_service()

    success_count = 0
    for admin_id in target_ids:
        try:
            if await line_service.push_text(admin_id, formatted_message):
                success_count += 1
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id[:8]}...: {e}")

    logger.info(
        f"Admin notifications sent: {success_count}/{len(target_ids)}",
        extra={"alert_level": level.value}
    )

    return success_count


async def notify_critical(message: str) -> int:
    """Send critical alert to admins."""
    return await notify_admins(message, AlertLevel.CRITICAL)


async def notify_warning(message: str) -> int:
    """Send warning alert to admins."""
    return await notify_admins(message, AlertLevel.WARNING)


async def notify_info(message: str) -> int:
    """Send informational alert to admins."""
    return await notify_admins(message, AlertLevel.INFO)
