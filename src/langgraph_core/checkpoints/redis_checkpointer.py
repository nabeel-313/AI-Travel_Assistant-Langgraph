from typing import Any, Dict, Optional
from langgraph.checkpoint.base import BaseCheckpointSaver
from src.cache.redis_client import redis_client
from src.loggers import Logger

logger = Logger(__name__).get_logger()


class RedisCheckpointer(BaseCheckpointSaver):
    def __init__(self, ttl_days: int = 7):
        self.ttl_seconds = ttl_days * 24 * 60 * 60  # Convert days to seconds

    async def aget(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Async get checkpoint from Redis"""
        try:
            thread_id = config.get("configurable", {}).get("thread_id")
            if not thread_id:
                return None

            key = f"checkpoint:{thread_id}"
            checkpoint_data = await redis_client.get_json(key)

            if checkpoint_data:
                logger.info(f"Retrieved checkpoint for thread: {thread_id}")
                return checkpoint_data
            return None

        except Exception as e:
            logger.error(f"Error getting checkpoint: {e}")
            return None

    async def aput(self, config: Dict[str, Any], checkpoint: Dict[str, Any]) -> None:
        """Async save checkpoint to Redis with TTL"""
        try:
            thread_id = config.get("configurable", {}).get("thread_id")
            if not thread_id:
                return

            key = f"checkpoint:{thread_id}"
            await redis_client.set_json(key, checkpoint, expire=self.ttl_seconds)
            logger.info(f"Saved checkpoint for thread: {thread_id} (TTL: {self.ttl_seconds}s)")

        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")

    async def alist(self, config: Dict[str, Any]) -> list:
        """Async list all checkpoints for a user"""
        # This would require Redis SCAN implementation
        # For now, return empty list
        return []

    async def adelete(self, config: Dict[str, Any]) -> None:
        """Async delete checkpoint"""
        try:
            thread_id = config.get("configurable", {}).get("thread_id")
            if not thread_id:
                return

            key = f"checkpoint:{thread_id}"
            await redis_client.delete(key)
            logger.info(f"Deleted checkpoint for thread: {thread_id}")

        except Exception as e:
            logger.error(f"Error deleting checkpoint: {e}")
