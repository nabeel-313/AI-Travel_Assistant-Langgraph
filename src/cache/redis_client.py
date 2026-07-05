import asyncio
import json
import time
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from src.config.settings import settings
from src.loggers import Logger

logger = Logger(__name__).get_logger()


class AsyncRedisClient:
    """Production-grade async Redis client with reconnection and health checks."""

    def __init__(
        self,
        max_connections: int = 20,
        socket_timeout: int = 5,
        socket_connect_timeout: int = 5,
        socket_keepalive: bool = True,
        health_check_interval: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        self.redis_url = settings.REDIS_URL
        self.max_connections = max_connections
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.socket_keepalive = socket_keepalive
        self.health_check_interval = health_check_interval
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self.client: Optional[redis.Redis] = None
        self.pool: Optional[ConnectionPool] = None
        self._is_connected: bool = False
        self._health_check_task: Optional[asyncio.Task] = None
        self._last_health_check: float = 0
        self._consecutive_failures: int = 0
        self._max_consecutive_failures: int = 5

    async def connect(self) -> bool:
        """Async connection setup with retry logic."""
        for attempt in range(self.max_retries):
            try:
                self.pool = ConnectionPool.from_url(
                    self.redis_url,
                    max_connections=self.max_connections,
                    decode_responses=True,
                    socket_timeout=self.socket_timeout,
                    socket_connect_timeout=self.socket_connect_timeout,
                    socket_keepalive=self.socket_keepalive,
                    retry_on_timeout=True,
                    health_check_interval=self.health_check_interval
                )
                self.client = redis.Redis(connection_pool=self.pool)

                # Test connection
                await self.client.ping()
                self._is_connected = True
                self._consecutive_failures = 0

                # Start health check background task
                self._start_health_check()

                logger.info("Async Redis connected with connection pooling")
                return True

            except Exception as e:
                logger.warning(f"Redis connection attempt {attempt + 1}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    logger.error(f"Redis connection failed after {self.max_retries} attempts: {e}")
                    self._is_connected = False
                    return False
        return False

    async def reconnect(self) -> bool:
        """Attempt to reconnect to Redis."""
        logger.info("Attempting to reconnect to Redis...")

        # Clean up existing connection
        await self.disconnect()

        # Attempt reconnection
        return await self.connect()

    async def disconnect(self):
        """Clean up Redis connection."""
        self._stop_health_check()

        if self.client:
            try:
                await self.client.aclose()
            except Exception as e:
                logger.error(f"Error closing Redis client: {e}")
            finally:
                self.client = None

        if self.pool:
            try:
                await self.pool.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting pool: {e}")
            finally:
                self.pool = None

        self._is_connected = False
        logger.info("Redis connection closed")

    def _start_health_check(self):
        """Start background health check task."""
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(self._health_check_loop())

    def _stop_health_check(self):
        """Stop background health check task."""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(asyncio.gather(self._health_check_task, return_exceptions=True))
            except Exception:
                pass
            self._health_check_task = None

    async def _health_check_loop(self):
        """Background health check loop."""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self.health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check and return status."""
        result = {
            "connected": False,
            "latency_ms": None,
            "last_check": self._last_health_check,
            "consecutive_failures": self._consecutive_failures,
            "error": None
        }

        if not self.client:
            result["error"] = "Client not initialized"
            return result

        try:
            start = time.perf_counter()
            await self.client.ping()
            latency = (time.perf_counter() - start) * 1000

            result["connected"] = True
            result["latency_ms"] = round(latency, 2)
            self._last_health_check = time.time()
            self._consecutive_failures = 0

        except Exception as e:
            result["error"] = str(e)
            self._consecutive_failures += 1

            # Attempt reconnection if too many failures
            if self._consecutive_failures >= self._max_consecutive_failures:
                logger.warning(f"Too many consecutive failures ({self._consecutive_failures}), attempting reconnection...")
                await self.reconnect()

        return result

    async def is_connected(self) -> bool:
        """Check if Redis is connected."""
        if not self._is_connected or not self.client:
            return False

        try:
            await self.client.ping()
            return True
        except Exception:
            self._is_connected = False
            return False

    async def set(self, key: str, value: str, expire: int = None) -> bool:
        """Async set key-value pair with optional expiration."""
        if not await self.is_connected():
            # Attempt reconnection
            if not await self.reconnect():
                return False

        for attempt in range(self.max_retries):
            try:
                if expire:
                    await self.client.setex(key, expire, value)
                else:
                    await self.client.set(key, value)
                return True
            except Exception as e:
                logger.warning(f"Redis set attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"Redis set error after {self.max_retries} attempts: {e}")
                    return False
        return False

    async def get(self, key: str) -> Optional[str]:
        """Async get value by key."""
        if not await self.is_connected():
            if not await self.reconnect():
                return None

        for attempt in range(self.max_retries):
            try:
                return await self.client.get(key)
            except Exception as e:
                logger.warning(f"Redis get attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"Redis get error after {self.max_retries} attempts: {e}")
                    return None
        return None

    async def delete(self, key: str) -> bool:
        """Async delete key."""
        if not await self.is_connected():
            if not await self.reconnect():
                return False

        for attempt in range(self.max_retries):
            try:
                await self.client.delete(key)
                return True
            except Exception as e:
                logger.warning(f"Redis delete attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"Redis delete error after {self.max_retries} attempts: {e}")
                    return False
        return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        if not await self.is_connected():
            if not await self.reconnect():
                return 0

        try:
            keys = []
            async for key in self.client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                return await self.client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Redis delete_pattern error: {e}")
            return 0

    async def set_json(self, key: str, value: dict, expire: int = None) -> bool:
        """Async set JSON object."""
        logger.debug(f"Creating cache for key: {key}")
        return await self.set(key, json.dumps(value), expire)

    async def get_json(self, key: str) -> Optional[dict]:
        """Async get JSON object."""
        data = await self.get(key)

        if not data:
            return None

        try:
            parsed_data = json.loads(data)
            logger.debug(f"Redis get_json - loaded successfully for key: {key}")
            return parsed_data
        except json.JSONDecodeError as e:
            logger.error(f"Redis get_json - JSON decode error for key {key}: {e}")
            logger.error(f"Problematic data: {data[:200]}...")
            return None

    async def exists(self, key: str) -> bool:
        """Async check if key exists."""
        if not await self.is_connected():
            if not await self.reconnect():
                return False

        try:
            return await self.client.exists(key) == 1
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on a key."""
        if not await self.is_connected():
            if not await self.reconnect():
                return False

        try:
            return await self.client.expire(key, seconds)
        except Exception as e:
            logger.error(f"Redis expire error: {e}")
            return False

    async def ttl(self, key: str) -> int:
        """Get TTL of a key."""
        if not await self.is_connected():
            if not await self.reconnect():
                return -2

        try:
            return await self.client.ttl(key)
        except Exception as e:
            logger.error(f"Redis ttl error: {e}")
            return -2

    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a key value."""
        if not await self.is_connected():
            if not await self.reconnect():
                return None

        try:
            return await self.client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Redis incr error: {e}")
            return None

    async def decr(self, key: str, amount: int = 1) -> Optional[int]:
        """Decrement a key value."""
        if not await self.is_connected():
            if not await self.reconnect():
                return None

        try:
            return await self.client.decrby(key, amount)
        except Exception as e:
            logger.error(f"Redis decr error: {e}")
            return None

    async def get_many(self, keys: List[str]) -> Dict[str, Optional[str]]:
        """Get multiple keys at once."""
        if not keys:
            return {}

        if not await self.is_connected():
            if not await self.reconnect():
                return {k: None for k in keys}

        try:
            values = await self.client.mget(keys)
            return dict(zip(keys, values))
        except Exception as e:
            logger.error(f"Redis get_many error: {e}")
            return {k: None for k in keys}

    async def set_many(self, mapping: Dict[str, str], expire: int = None) -> bool:
        """Set multiple keys at once."""
        if not mapping:
            return True

        if not await self.is_connected():
            if not await self.reconnect():
                return False

        try:
            pipe = self.client.pipeline()
            for key, value in mapping.items():
                if expire:
                    pipe.setex(key, expire, value)
                else:
                    pipe.set(key, value)
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Redis set_many error: {e}")
            return False

    async def get_info(self) -> Optional[dict]:
        """Get Redis server info."""
        if not await self.is_connected():
            return None

        try:
            return await self.client.info()
        except Exception as e:
            logger.error(f"Redis get_info error: {e}")
            return None

    @property
    def connection_info(self) -> Dict[str, Any]:
        """Get connection information."""
        return {
            "url": self.redis_url.split("@")[-1] if "@" in self.redis_url else self.redis_url,  # Hide credentials
            "max_connections": self.max_connections,
            "is_connected": self._is_connected,
            "last_health_check": self._last_health_check,
            "consecutive_failures": self._consecutive_failures
        }


# Global async instance
redis_client = AsyncRedisClient()


# Async initialization (call this at app startup)
async def init_redis() -> bool:
    """Initialize Redis connection."""
    return await redis_client.connect()


# Async cleanup (call this at app shutdown)
async def close_redis():
    """Close Redis connection."""
    await redis_client.disconnect()
