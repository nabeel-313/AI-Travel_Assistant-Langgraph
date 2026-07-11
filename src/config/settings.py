"""
Production-grade settings with environment validation and type safety.
"""
import os
import re
from functools import lru_cache
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecuritySettings(BaseSettings):
    """Security-related settings."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

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


class DatabaseSettings(BaseSettings):
    """Database connection settings."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(default="", alias="DATABASE_URL")
    async_database_url: str = Field(default="", alias="ASYNC_DATABASE_URL")
    db_pool_size: int = Field(default=20, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=30, alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(default=3600, alias="DB_POOL_RECYCLE")
    db_use_null_pool: bool = Field(default=False, alias="DB_USE_NULL_POOL")
    db_echo: bool = Field(default=False, alias="DB_ECHO")

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v):
        if not v:
            return "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}"
        return v


class RedisSettings(BaseSettings):
    """Redis connection settings."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    redis_url: str = Field(default="", alias="REDIS_URL")
    redis_max_connections: int = Field(default=50, alias="REDIS_MAX_CONNECTIONS")
    redis_socket_timeout: int = Field(default=5, alias="REDIS_SOCKET_TIMEOUT")
    redis_socket_connect_timeout: int = Field(default=5, alias="REDIS_SOCKET_CONNECT_TIMEOUT")
    redis_retry_on_timeout: bool = Field(default=True, alias="REDIS_RETRY_ON_TIMEOUT")
    redis_health_check_interval: int = Field(default=30, alias="REDIS_HEALTH_CHECK_INTERVAL")
    session_ttl_seconds: int = Field(default=86400, alias="SESSION_TTL_SECONDS")  # 24 hours

    @field_validator("redis_url", mode="before")
    @classmethod
    def validate_redis_url(cls, v):
        if not v:
            return "redis://localhost:6379/0"
        return v


class LLMSettings(BaseSettings):
    """LLM provider settings."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

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
    # NOTE: these are BaseSettings subclasses (not plain BaseModel), so each
    # one independently reads .env / the environment when instantiated here.
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

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
