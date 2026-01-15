"""
Configuration loader for LINE Bot.

Loads and validates environment variables using Pydantic Settings.
All configuration is centralized here for easy management.
"""

from functools import lru_cache
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # ==========================================================================
    # LINE Messaging API
    # ==========================================================================
    line_channel_secret: str = Field(
        ...,
        description="LINE channel secret for webhook signature validation"
    )
    line_channel_access_token: str = Field(
        ...,
        description="LINE channel access token for sending messages"
    )
    
    # ==========================================================================
    # Ollama Configuration
    # ==========================================================================
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL"
    )
    ollama_model: str = Field(
        default="gemma3:12b",
        description="Ollama model name for inference"
    )
    
    # ==========================================================================
    # Google Drive Configuration
    # ==========================================================================
    google_service_account_file: Optional[str] = Field(
        default=None,
        description="Path to Google service account JSON file"
    )
    drive_folder_id: Optional[str] = Field(
        default=None,
        description="Google Drive folder ID containing prompts and images"
    )
    drive_sync_interval_seconds: int = Field(
        default=45,
        ge=30,
        le=120,
        description="Interval between Drive sync checks (30-120s)"
    )
    
    # ==========================================================================
    # Admin Configuration
    # ==========================================================================
    admin_user_ids: str = Field(
        default="",
        description="Comma-separated LINE user IDs for admin notifications"
    )
    admin_alert_level: str = Field(
        default="warning",
        description="Minimum alert level: critical, warning, info"
    )
    
    @field_validator("admin_alert_level")
    @classmethod
    def validate_alert_level(cls, v: str) -> str:
        allowed = {"critical", "warning", "info"}
        if v.lower() not in allowed:
            raise ValueError(f"admin_alert_level must be one of: {allowed}")
        return v.lower()
    
    @property
    def admin_user_id_list(self) -> list[str]:
        """Parse comma-separated admin user IDs into a list."""
        if not self.admin_user_ids:
            return []
        return [uid.strip() for uid in self.admin_user_ids.split(",") if uid.strip()]
    
    # ==========================================================================
    # Rate Limiting
    # ==========================================================================
    rate_limit_max_requests: int = Field(
        default=30,
        ge=1,
        le=100,
        description="Maximum requests per user per window"
    )
    rate_limit_window_seconds: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Rate limit window in seconds"
    )
    
    # ==========================================================================
    # Queue Configuration
    # ==========================================================================
    queue_max_size: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum pending LLM requests in queue"
    )
    queue_timeout_seconds: int = Field(
        default=120,
        ge=30,
        le=600,
        description="Request timeout in seconds"
    )
    
    # ==========================================================================
    # Cache Configuration
    # ==========================================================================
    cache_dir: str = Field(
        default="/tmp/linebot_cache",
        description="Local cache directory for Drive assets"
    )
    cache_max_size_mb: int = Field(
        default=100,
        ge=10,
        le=1024,
        description="Maximum cache size in MB"
    )
    
    # ==========================================================================
    # Server Configuration
    # ==========================================================================
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, ge=1, le=65535, description="Server port")
    log_level: str = Field(default="INFO", description="Logging level")
    public_base_url: Optional[str] = Field(
        default=None,
        description="Public HTTPS URL for the server (e.g., Cloudflare Tunnel URL)"
    )
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of: {allowed}")
        return v.upper()
    
    # ==========================================================================
    # Default System Prompt (fallback when Drive not configured)
    # ==========================================================================
    default_system_prompt: str = Field(
        default="""You are a helpful AI assistant in a LINE group chat.
Respond concisely and helpfully in the same language the user uses.
If analyzing images, describe what you see clearly and answer any questions about the content.
Be friendly but professional.""",
        description="Default system prompt when Google Drive is not configured"
    )

    # ==========================================================================
    # Scheduled Messages Configuration
    # ==========================================================================
    scheduled_messages_enabled: bool = Field(
        default=False,
        description="Enable scheduled message feature"
    )
    scheduled_group_id: Optional[str] = Field(
        default=None,
        description="LINE group ID for scheduled messages"
    )

    # ==========================================================================
    # Web Search Configuration (Tavily AI)
    # ==========================================================================
    tavily_api_key: Optional[str] = Field(
        default=None,
        description="Tavily API key for web search (!web command)"
    )


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses lru_cache to ensure settings are loaded only once.
    Call get_settings.cache_clear() to reload settings.
    
    Returns:
        Settings instance with validated configuration
        
    Raises:
        ValidationError: If required settings are missing or invalid
    """
    return Settings()


# Convenience: use get_settings() instead of this to avoid import-time errors
# settings = get_settings()
