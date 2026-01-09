"""
Structured logging configuration for LINE Bot.

Provides consistent logging format across all modules with:
- Structured JSON output for production
- Human-readable format for development
- Request ID tracking for debugging (thread-safe/async-safe)
- Sensitive data masking
"""

import logging
import sys
from datetime import datetime
from typing import Optional, Dict, Any
import json
import contextvars

# Context variable to hold log context (async-safe)
_log_context: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar("log_context", default={})


class ContextFilter(logging.Filter):
    """Filter to inject context variables into log records."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        context = _log_context.get()
        for key, value in context.items():
            # Set the attribute on the record so formatters can use it
            setattr(record, key, value)
        return True


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging in production."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = self._mask_id(record.user_id)
        if hasattr(record, "group_id"):
            log_data["group_id"] = self._mask_id(record.group_id)
        if hasattr(record, "command"):
            log_data["command"] = record.command
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
            
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_data, ensure_ascii=False)
    
    @staticmethod
    def _mask_id(id_value: str) -> str:
        """Mask LINE IDs for privacy, showing only first/last 4 chars."""
        if not id_value or len(id_value) < 12:
            return "***"
        return f"{id_value[:4]}...{id_value[-4:]}"


class DevelopmentFormatter(logging.Formatter):
    """Human-readable formatter for development."""
    
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        
        # Build base message
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        base = f"{color}{timestamp} [{record.levelname:8}]{self.RESET} {record.name}: {record.getMessage()}"
        
        # Add context if present
        context_parts = []
        if hasattr(record, "request_id"):
            context_parts.append(f"req={record.request_id[:8]}")
        if hasattr(record, "user_id"):
            context_parts.append(f"user={record.user_id[:8]}...")
        if hasattr(record, "command"):
            context_parts.append(f"cmd={record.command}")
        if hasattr(record, "duration_ms"):
            context_parts.append(f"took={record.duration_ms}ms")
            
        if context_parts:
            base += f" ({', '.join(context_parts)})"
            
        # Add exception if present
        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"
            
        return base


def setup_logging(
    level: str = "INFO",
    json_output: bool = False,
    logger_name: Optional[str] = None
) -> logging.Logger:
    """
    Configure and return a logger instance.
    """
    # Configure root logger to capture all logs if needed, 
    # but here we focus on the specific logger or root
    logger = logging.getLogger(logger_name or "linebot")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logger.level)
    
    # Set formatter based on environment
    if json_output:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(DevelopmentFormatter())
    
    # Add context filter
    handler.addFilter(ContextFilter())
    
    logger.addHandler(handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger for a specific module."""
    return logging.getLogger(f"linebot.{name}")


class LogContext:
    """Context manager for adding extra fields to log records using contextvars."""
    
    def __init__(self, logger: logging.Logger, **kwargs):
        self.new_context = kwargs
        self.token = None
        
    def __enter__(self):
        # Merge new context with existing context
        current_context = _log_context.get()
        updated_context = current_context.copy()
        updated_context.update(self.new_context)
        
        # Set new context and save token for reset
        self.token = _log_context.set(updated_context)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Reset context to previous state
        if self.token:
            _log_context.reset(self.token)
        return False


# Create default logger on import
logger = setup_logging()
