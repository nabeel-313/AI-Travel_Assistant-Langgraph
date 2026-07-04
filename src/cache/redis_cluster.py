import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
from src.config.settings import settings
from src.loggers import Logger

logger = Logger(__name__).get_logger()


class RedisClusterClient:
    def __init__(self):
        self.cluster_pool = None
        self.client = None

    async def connect(self):
        """Connect to Redis with connection pooling"""
        try:
            self.cluster_pool = ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=50,
                decode_responses=True
            )
            self.client = redis.Redis(connection_pool=self.cluster_pool)
            await self.client.ping()
            logger.info("Redis cluster client connected with connection pooling")
        except Exception as e:
            logger.error(f"Redis cluster connection failed: {e}")
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
        if not await self.is_connected():
            return None
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None

    async def delete(self, key: str):
        if not await self.is_connected():
            return False
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False

    async def set_json(self, key: str, value: dict, expire: int = None):
        import json
        return await self.set(key, json.dumps(value), expire)

    async def get_json(self, key: str):
        import json
        data = await self.get(key)
        if not data:
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f"Redis get_json JSON decode error: {e}")
            return None


# Global cluster instance
redis_cluster = RedisClusterClient()
