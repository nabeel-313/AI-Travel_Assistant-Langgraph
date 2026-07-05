import secrets
import json
from datetime import datetime
from typing import Optional, Dict, Any

from src.cache.redis_client import redis_client
from src.loggers import Logger

logger = Logger(__name__).get_logger()


class SessionManager:
    """Production-grade session manager with error handling and reconnection support."""

    def __init__(self, session_prefix: str = "session:", session_expiry: int = 900):
        """
        Initialize SessionManager.

        Args:
            session_prefix: Prefix for session keys in Redis
            session_expiry: Session expiry in seconds (default: 15 minutes)
        """
        self.session_prefix = session_prefix
        self.session_expiry = session_expiry

    async def _ensure_connection(self) -> bool:
        """Ensure Redis connection is available."""
        try:
            if await redis_client.is_connected():
                return True

            # Attempt reconnection
            logger.info("Redis not connected, attempting reconnection...")
            return await redis_client.reconnect()
        except Exception as e:
            logger.error(f"Error checking Redis connection: {e}")
            return False

    async def create_session(self, user_id: int, user_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Create new session and return session token."""
        try:
            # Ensure connection
            if not await self._ensure_connection():
                logger.error("Cannot create session: Redis not available")
                return None

            session_token = secrets.token_urlsafe(32)
            session_key = f"{self.session_prefix}{session_token}"

            session_data = {
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat(),
                "user_data": user_data or {}
            }

            logger.info(f"Creating session for user {user_id} - Key: {session_key}")

            success = await redis_client.set_json(session_key, session_data, self.session_expiry)

            if success:
                # Verify the session was stored
                stored_data = await redis_client.get_json(session_key)
                if stored_data:
                    logger.info(f"Session created successfully for user {user_id}")
                    return session_token
                else:
                    logger.error("Session created but not retrievable")
                    return None
            else:
                logger.error("Failed to create session in Redis")
                return None

        except Exception as e:
            logger.error(f"Session creation error: {e}", exc_info=True)
            return None

    async def get_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """Get session data by token."""
        if not session_token:
            logger.warning("No session token provided")
            return None

        try:
            # Ensure connection
            if not await self._ensure_connection():
                logger.error("Cannot get session: Redis not available")
                return None

            session_key = f"{self.session_prefix}{session_token}"

            # Get the raw data from Redis first
            raw_data = await redis_client.get(session_key)

            if not raw_data:
                logger.debug(f"No session found for key: {session_key}")
                return None

            # Try to parse as JSON
            try:
                session_data = json.loads(raw_data)

                # Refresh session expiry on access
                await redis_client.set_json(session_key, session_data, self.session_expiry)
                logger.debug(f"Session retrieved for user: {session_data.get('user_id')}")
                return session_data
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error for session {session_key}: {e}")
                # Try to delete corrupted session
                await redis_client.delete(session_key)
                return None

        except Exception as e:
            logger.error(f"Unexpected error getting session: {e}", exc_info=True)
            return None

    async def delete_session(self, session_token: str) -> bool:
        """Delete session by token."""
        if not session_token:
            return False

        try:
            if not await self._ensure_connection():
                return False

            session_key = f"{self.session_prefix}{session_token}"
            success = await redis_client.delete(session_key)

            if success:
                logger.info(f"Session deleted: {session_key}")

            return success
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False

    async def get_user_id(self, session_token: str) -> Optional[int]:
        """Get user ID from session token."""
        session = await self.get_session(session_token)
        return session.get("user_id") if session else None

    async def is_valid_session(self, session_token: str) -> bool:
        """Check if session is valid."""
        session = await self.get_session(session_token)
        return session is not None

    async def refresh_session(self, session_token: str) -> bool:
        """Refresh session expiry without retrieving data."""
        if not session_token:
            return False

        try:
            if not await self._ensure_connection():
                return False

            session_key = f"{self.session_prefix}{session_token}"

            # Get current session data
            session_data = await self.get_session(session_token)
            if not session_data:
                return False

            # Re-set with new expiry
            return await redis_client.set_json(session_key, session_data, self.session_expiry)

        except Exception as e:
            logger.error(f"Error refreshing session: {e}")
            return False

    async def update_session_data(self, session_token: str, user_data: Dict[str, Any]) -> bool:
        """Update session user data."""
        if not session_token:
            return False

        try:
            if not await self._ensure_connection():
                return False

            session_key = f"{self.session_prefix}{session_token}"

            # Get current session
            session_data = await self.get_session(session_token)
            if not session_data:
                return False

            # Update user_data
            session_data["user_data"] = user_data
            session_data["updated_at"] = datetime.utcnow().isoformat()

            return await redis_client.set_json(session_key, session_data, self.session_expiry)

        except Exception as e:
            logger.error(f"Error updating session data: {e}")
            return False

    async def clear_user_conversation_state(self, user_id: str, session_id: str) -> bool:
        """Clear user's LangGraph conversation state from Redis."""
        try:
            if not await self._ensure_connection():
                return False

            key = f"conversation_state:{user_id}:{session_id}"
            success = await redis_client.delete(key)

            if success:
                logger.info(f"Cleared conversation state for user: {user_id}")

            return success
        except Exception as e:
            logger.error(f"Error clearing conversation state: {e}")
            return False

    async def get_all_user_sessions(self, user_id: int) -> list:
        """Get all active sessions for a user (requires secondary index)."""
        try:
            if not await self._ensure_connection():
                return []

            # This would require maintaining a user->sessions index
            # For now, return empty list as this is a more advanced feature
            logger.debug("get_all_user_sessions called - not fully implemented")
            return []

        except Exception as e:
            logger.error(f"Error getting user sessions: {e}")
            return []

    async def delete_all_user_sessions(self, user_id: int) -> int:
        """Delete all sessions for a user."""
        try:
            if not await self._ensure_connection():
                return 0

            # This would require maintaining a user->sessions index
            # For now, return 0 as this is a more advanced feature
            logger.debug("delete_all_user_sessions called - not fully implemented")
            return 0

        except Exception as e:
            logger.error(f"Error deleting user sessions: {e}")
            return 0


# Global session manager instance
session_manager = SessionManager()
