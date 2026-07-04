import redis.asyncio as redis
from config.settings import settings
import json
from src.loggers import Logger

logger = Logger(__name__).get_logger()


class AsyncRedisClient:
    def __init__(self):
        self.redis_url = settings.REDIS_URL
        self.client = None
        self.pool = None

    async def connect(self):
        """Async connection setup"""
        try:
            self.pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=20,
                decode_responses=True
            )
            self.client = redis.Redis(connection_pool=self.pool)
            await self.client.ping()
            logger.info("Async Redis connected with connection pooling")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self.client = None

    async def is_connected(self):
        try:
            if self.client:
                await self.client.ping()
                return True
            return False
        except:
            return False

    async def set(self, key: str, value: str, expire: int = None):
        """Async set key-value pair with optional expiration"""
        if not await self.is_connected():
            return False
        try:
            if expire:
                await self.client.setex(key, expire, value)
            else:
                await self.client.set(key, value)
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False

    async def get(self, key: str):
        """Async get value by key"""
        if not await self.is_connected():
            return None
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None

    async def delete(self, key: str):
        """Async delete key"""
        if not await self.is_connected():
            return False
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False

    async def set_json(self, key: str, value: dict, expire: int = None):
        """Async set JSON object"""
        logger.info(f"Creating cache for {value}")
        return await self.set(key, json.dumps(value), expire)

    async def get_json(self, key: str):
        """Async get JSON object"""
        data = await self.get(key)
        logger.info(f"Redis get_json -  Raw data: {data}") # can add key:{key}

        if not data:
            return None

        try:
            parsed_data = json.loads(data)
            logger.info(f"Redis get_json - loaded successfully: {type(parsed_data)}")
            return parsed_data
        except json.JSONDecodeError as e:
            logger.error(f"Redis get_json - JSON decode error: {e}")
            logger.error(f"Problematic data: {data}")
            return None

    async def exists(self, key: str):
        """Async check if key exists"""
        if not await self.is_connected():
            return False
        try:
            return await self.client.exists(key) == 1
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False

# ✅ Global async instance
redis_client = AsyncRedisClient()

# ✅ Async initialization (call this at app startup)
async def init_redis():
    await redis_client.connect()
