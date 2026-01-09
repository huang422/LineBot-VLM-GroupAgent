"""
Input validation and security utilities.

Provides LINE webhook signature validation and input sanitization
to protect against injection attacks and malformed requests.
"""

import hmac
import hashlib
import base64
import re
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("validators")

# Regex patterns for input sanitization
PROMPT_INJECTION_PATTERNS = [
    r"(?i)ignore\s+(previous|above|all)\s+instructions?",
    r"(?i)disregard\s+(previous|above|all)\s+instructions?",
    r"(?i)forget\s+(previous|above|all)\s+instructions?",
    r"(?i)you\s+are\s+now\s+",
    r"(?i)act\s+as\s+if\s+",
    r"(?i)pretend\s+(you|to)\s+",
    r"(?i)system\s*:\s*",
    r"(?i)assistant\s*:\s*",
    r"(?i)\[INST\]",
    r"(?i)\[/INST\]",
    r"(?i)<\|im_start\|>",
    r"(?i)<\|im_end\|>",
]


def validate_line_signature(
    body: bytes,
    signature: str,
    channel_secret: str
) -> bool:
    """
    Validate LINE webhook signature using HMAC-SHA256.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        body: Raw request body bytes
        signature: X-Line-Signature header value
        channel_secret: LINE channel secret

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Calculate expected signature
        hash_value = hmac.new(
            channel_secret.encode("utf-8"),
            body,
            hashlib.sha256
        ).digest()
        expected_signature = base64.b64encode(hash_value).decode("utf-8")

        # Constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(signature, expected_signature)

        if not is_valid:
            logger.warning(
                f"LINE signature validation failed - "
                f"Received: {signature[:20]}..., "
                f"Expected: {expected_signature[:20]}..., "
                f"Secret: {channel_secret[:8]}..., "
                f"Body length: {len(body)}"
            )
        else:
            logger.debug("LINE signature validation succeeded")

        return is_valid

    except Exception as e:
        logger.error(f"Signature validation error: {e}", exc_info=True)
        return False


def sanitize_prompt(prompt: str, max_length: int = 4000) -> str:
    """
    Sanitize user prompt to prevent injection attacks.
    
    Args:
        prompt: Raw user input from !hej command
        max_length: Maximum allowed prompt length
        
    Returns:
        Sanitized prompt string
    """
    if not prompt:
        return ""
    
    # Strip whitespace
    sanitized = prompt.strip()
    
    # Truncate if too long
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
        logger.info(f"Prompt truncated from {len(prompt)} to {max_length} chars")
    
    return sanitized


def detect_prompt_injection(prompt: str) -> Optional[str]:
    """
    Detect potential prompt injection attempts.
    
    Args:
        prompt: User prompt to check
        
    Returns:
        Matched pattern if injection detected, None otherwise
    """
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, prompt):
            return pattern
    return None


def validate_line_user_id(user_id: str) -> bool:
    """
    Validate LINE user ID format.
    
    Args:
        user_id: LINE user ID to validate
        
    Returns:
        True if valid format (Uxxxxxxxx...)
    """
    if not user_id:
        return False
    return bool(re.match(r"^U[a-f0-9]{32}$", user_id))


def validate_line_group_id(group_id: str) -> bool:
    """
    Validate LINE group or room ID format.
    
    Args:
        group_id: LINE group/room ID to validate
        
    Returns:
        True if valid format (Cxxxxxxxx... or Rxxxxxxxx...)
    """
    if not group_id:
        return False
    return bool(re.match(r"^[CR][a-f0-9]{32}$", group_id))


def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """
    Mask sensitive data for logging, showing only first/last chars.
    
    Args:
        data: Sensitive string to mask
        visible_chars: Number of chars to show at start/end
        
    Returns:
        Masked string (e.g., "Uabc...xyz1")
    """
    if not data or len(data) <= visible_chars * 2:
        return "***"
    return f"{data[:visible_chars]}...{data[-visible_chars:]}"


def validate_image_content_type(content_type: str) -> bool:
    """
    Validate image content type is supported.
    
    Args:
        content_type: MIME type from Content-Type header
        
    Returns:
        True if supported image format
    """
    supported_types = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
    }
    return content_type.lower() in supported_types
