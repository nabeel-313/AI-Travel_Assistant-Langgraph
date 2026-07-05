"""
Production-grade settings with environment validation and type safety.
"""
import os
import re
from functools import lru_cache
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class SecuritySettings(BaseModel):
    """Security-related settings."""
    secret_key: str = Field(default="", alias="SECRET_KEY")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Password settings
    password_min_length: int = 8
    password_max_length: int = 128

    @field_validator("secret_key", mode="before")
    @classmethod
    def validate_secret_key(cls, v):
        if not v or v == "change-me-in-production":
            import secrets
            return secrets.token_urlsafe(32)
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v


class DatabaseSettings(BaseModel):
    """Database connection settings."""
    database_url: str = Field(default="", alias="DATABASE_URL")
    async_database_url: str = Field(default="", alias="ASYNC_DATABASE_URL")
    db_pool_size: int = 20
    db_max_overflow: int = 30
    db_pool_timeout: int = 30
    db_pool_recycle: int = 3600

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v):
        if not v:
            return "postgresql://nabeel:momin.123@localhost:5432/travel_db"
        return v


class RedisSettings(BaseModel):
    """Redis connection settings."""
    redis_url: str = Field(default="", alias="REDIS_URL")
    redis_max_connections: int = 50
    redis_socket_timeout: int = 5
    redis_socket_connect_timeout: int = 5
    redis_retry_on_timeout: bool = True
    redis_health_check_interval: int = 30
    session_ttl_seconds: int = 86400  # 24 hours

    @field_validator("redis_url", mode="before")
    @classmethod
    def validate_redis_url(cls, v):
        if not v:
            return "redis://localhost:6379/0"
        return v


class LLMSettings(BaseModel):
    """LLM provider settings."""
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    serpapi_api_key: str = Field(default="", alias="SERPAPI_API_KEY")
    openweathermap_api_key: str = Field(default="", alias="OPENWEATHERMAP_API_KEY")

    @field_validator("groq_api_key", "google_api_key", mode="before")
    @classmethod
    def validate_api_keys(cls, v):
        if not v:
            return ""
        return v


class RateLimitSettings(BaseModel):
    """Rate limiting settings."""
    enabled: bool = True
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10


class TimeoutSettings(BaseModel):
    """Timeout settings for various operations."""
    default_timeout: int = 30
    llm_timeout: int = 60
    tool_timeout: int = 30
    database_query_timeout: int = 10
    redis_operation_timeout: int = 5


class RetrySettings(BaseModel):
    """Retry settings for transient failures."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0


class CircuitBreakerSettings(BaseModel):
    """Circuit breaker settings for external APIs."""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    expected_exception: str = "Exception"


class LoggingSettings(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    format: str = "json"  # json or text
    log_dir: str = "logs"
    max_file_size_mb: int = 100
    backup_count: int = 5


class Settings(BaseSettings):
    """Main application settings."""
    # Application
    app_name: str = "Travel AI Assistant"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # Sub-settings
    security: SecuritySettings = SecuritySettings()
    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    llm: LLMSettings = LLMSettings()
    rate_limit: RateLimitSettings = RateLimitSettings()
    timeout: TimeoutSettings = TimeoutSettings()
    retry: RetrySettings = RetrySettings()
    circuit_breaker: CircuitBreakerSettings = CircuitBreakerSettings()
    logging: LoggingSettings = LoggingSettings()

    # CORS
    cors_origins: List[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]

    # API
    api_v1_prefix: str = "/api/v1"
    api_title: str = "Travel AI Assistant API"
    api_description: str = "Production-grade AI Travel Assistant with LangGraph"

    # Health check
    health_check_path: str = "/health"
    health_check_detailed: bool = False

    # Feature flags
    enable_metrics: bool = True
    enable_tracing: bool = False
    enable_profiling: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"
        populate_by_name = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience accessors
settings = get_settings()
