import secrets
import json
from datetime import datetime
from src.cache.redis_client import redis_client
from src.loggers import Logger

logger = Logger(__name__).get_logger()


class SessionManager:
    def __init__(self):
        self.session_prefix = "session:"
        self.session_expiry = 1 * 60 * 15  # 15 minutes

    async def create_session(self, user_id: int, user_data: dict = None) -> str:
        """Create new session and return session token"""
        try:
            session_token = secrets.token_urlsafe(32)
            session_key = f"{self.session_prefix}{session_token}"

            session_data = {
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat(),
                "user_data": user_data or {}
            }

            logger.info(f"Creating session - Key: {session_key}")
            logger.info(f"Session data: {session_data}")

            is_connected = await redis_client.is_connected()
            logger.info(f"Redis connected: {is_connected}")

            # Check Redis connection
            if not is_connected:
                logger.error("Redis not connected")
                return None

            success = await redis_client.set_json(session_key, session_data, self.session_expiry)
            logger.info(f"Session storage result: {success}")

            if success:
                # Verify the session was stored
                stored_data = await redis_client.get_json(session_key)
                logger.info(f"Session verification - Found: {stored_data is not None}")
                if stored_data:
                    logger.info(f"Session created successfully for user {user_id}")
                else:
                    logger.error("Session created but not retrievable")
                return session_token
            else:
                logger.error("Failed to create session in Redis")
                return None

        except Exception as e:
            logger.error(f"Session creation error: {e}", exc_info=True)
            return None

    async def get_session(self, session_token: str) -> dict:
        """Get session data by token"""
        if not session_token:
            logger.warning("No session token provided")
            return None

        session_key = f"{self.session_prefix}{session_token}"
        logger.info("Looking up session")

        # Get the raw data from Redis first
        raw_data = await redis_client.get(session_key)
        logger.info(f"Raw data from Redis: {raw_data}")

        if not raw_data:
            logger.warning(f"No raw data found for session: {session_key}")
            return None

        # Try to parse as JSON
        try:
            session_data = json.loads(raw_data)
            logger.info(f"JSON parsed successfully: {session_data}")

            # Refresh session expiry on access
            await redis_client.set_json(session_key, session_data, self.session_expiry)
            logger.info(f"Session retrieved for user: {session_data.get('user_id')}")
            return session_data
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Raw data that failed to parse: {raw_data}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing session: {e}")
            return None

    async def delete_session(self, session_token: str) -> bool:
        """Delete session by token"""
        session_key = f"{self.session_prefix}{session_token}"
        return await redis_client.delete(session_key)

    async def get_user_id(self, session_token: str) -> int:
        """Get user ID from session token"""
        session = await self.get_session(session_token)
        return session.get("user_id") if session else None

    async def is_valid_session(self, session_token: str) -> bool:
        """Check if session is valid"""
        session = await self.get_session(session_token)
        return session is not None

    async def clear_user_conversation_state(self, user_id: str, session_id: str):
        """Clear user's LangGraph conversation state from Redis"""
        try:
            key = f"conversation_state:{user_id}:{session_id}"
            success = await redis_client.delete(key)
            if success:
                logger.info(f"Cleared conversation state for user: {user_id}")
            return success
        except Exception as e:
            logger.error(f"Error clearing conversation state: {e}")
            return False


# Global session manager instance
session_manager = SessionManager()
