"""
Async authentication service for user registration and login.
"""
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database.models.user import User
from src.loggers import Logger
from src.cache.session_manager import session_manager
from src.auth.utils import password_utils

logger = Logger(__name__).get_logger()


class AsyncAuthenticationService:
    """Async authentication service for user management."""

    def __init__(self, db_session: AsyncSession):
        """
        Initialize the authentication service.

        Args:
            db_session: SQLAlchemy async session
        """
        self.db = db_session

    async def register_user(
        self,
        email: str,
        password: str,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register a new user.

        Args:
            email: User email address
            password: Plain text password
            name: Optional user name

        Returns:
            Dict with success status and user_id or error
        """
        try:
            # Validate password strength
            is_valid, error_msg = password_utils.is_strong_password(password)
            if not is_valid:
                return {"success": False, "error": error_msg}

            # Check if user already exists
            result = await self.db.execute(
                select(User).where(User.email == email)
            )
            existing_user = result.scalar_one_or_none()

            if existing_user:
                return {"success": False, "error": "User already exists"}

            # Hash password and create user
            hashed_password = await password_utils.hash_password_async(password)
            new_user = User(
                email=email,
                hashed_password=hashed_password,
                name=name
            )

            self.db.add(new_user)
            await self.db.commit()
            await self.db.refresh(new_user)

            logger.info(f"User registered successfully: {email}")
            return {"success": True, "user_id": new_user.id}

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Registration error: {e}")
            return {"success": False, "error": "Registration failed"}

    async def login_user(
        self,
        email: str,
        password: str
    ) -> Dict[str, Any]:
        """
        Authenticate user and create session.

        Args:
            email: User email address
            password: Plain text password

        Returns:
            Dict with success status, session_token, and user_id or error
        """
        try:
            # Find user
            result = await self.db.execute(
                select(User).where(User.email == email)
            )
            user = result.scalar_one_or_none()

            if not user:
                logger.warning(f"Login attempt for non-existent user: {email}")
                return {"success": False, "error": "Invalid credentials"}

            # Verify password asynchronously
            password_valid = await password_utils.verify_password_async(
                password, user.hashed_password
            )

            if not password_valid:
                logger.warning(f"Failed login attempt for user: {email}")
                return {"success": False, "error": "Invalid credentials"}

            # Check if password needs rehash
            if password_utils.needs_rehash(user.hashed_password):
                new_hash = await password_utils.hash_password_async(password)
                user.hashed_password = new_hash
                await self.db.commit()
                logger.info(f"Password rehashed for user: {email}")

            # Create session
            user_data = {
                "id": user.id,
                "email": user.email,
                "name": user.name
            }

            session_token = await session_manager.create_session(user.id, user_data)
            if not session_token:
                logger.error(f"Session creation failed for user: {email}")
                return {"success": False, "error": "Session creation failed"}

            logger.info(f"User logged in successfully: {email}")
            return {
                "success": True,
                "session_token": session_token,
                "user_id": user.id
            }

        except Exception as e:
            logger.error(f"Login error: {e}")
            return {"success": False, "error": "Authentication failed"}

    async def get_current_user(self, session_token: str) -> Optional[Dict[str, Any]]:
        """
        Get user from session token.

        Args:
            session_token: Session token from login

        Returns:
            User data dict or None if session invalid
        """
        if not session_token:
            return None

        try:
            session_data = await session_manager.get_session(session_token)
            if not session_data:
                return None

            return session_data.get("user_data")
        except Exception as e:
            logger.error(f"Error getting current user: {e}")
            return None

    async def logout_user(self, session_token: str) -> bool:
        """
        Logout user by deleting session.

        Args:
            session_token: Session token to invalidate

        Returns:
            True if logout successful
        """
        try:
            return await session_manager.delete_session(session_token)
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return False
