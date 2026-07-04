from sqlalchemy.orm import Session
from src.database.models.user import User
from src.auth.utils import password_utils
from src.cache.session_manager import session_manager
from src.loggers import Logger

logger = Logger(__name__).get_logger()


class AuthenticationService:
    def __init__(self, db_session: Session):
        self.db = db_session

    async def register_user(self, email: str, password: str, name: str = None) -> dict:
        """Register a new user"""
        try:
            logger.info(f"Registration attempt for email: {email}")

            # Check if user already exists
            existing_user = self.db.query(User).filter(User.email == email).first()
            if existing_user:
                logger.warning(f"User already exists: {email}")
                return {"success": False, "error": "User already exists"}

            # Validate password strength
            if not password_utils.is_strong_password(password):
                logger.warning(f"Password too weak for: {email}")
                return {"success": False, "error": "Password too weak. Minimum 8 characters required"}

            # Create new user
            logger.info(f"Hashing password for: {email}")
            hashed_password = password_utils.hash_password(password)
            logger.info("Password hashed successfully:...")

            new_user = User(
                email=email,
                password_hash=hashed_password,
                name=name
            )

            self.db.add(new_user)
            self.db.commit()
            self.db.refresh(new_user)

            logger.info(f"New user registered successfully. User ID: {new_user.id}")
            return {"success": True, "user_id": new_user.id}

        except Exception as e:
            self.db.rollback()
            logger.error(f"Registration error: {e}", exc_info=True)
            return {"success": False, "error": "Registration failed"}

    async def login_user(self, email: str, password: str) -> dict:
        """Authenticate user and create session"""
        try:
            logger.info(f"Login attempt for email: {email}")
            user = self.db.query(User).filter(User.email == email).first()
            logger.info(f"User found: {user is not None}")

            if not user:
                logger.warning(f"No user found with email: {email}")
                return {"success": False, "error": "Invalid credentials"}

            logger.info("Verifying password...")
            password_valid = password_utils.verify_password(password, user.password_hash)
            logger.info(f"Password verification result: {password_valid}")

            if not password_valid:
                logger.warning(f"Invalid password for user: {email}")
                return {"success": False, "error": "Invalid credentials"}

            # Create session
            user_data = {
                "email": user.email,
                "name": user.name
            }
            logger.info(f"Creating session for user ID: {user.id}")
            session_token = await session_manager.create_session(user.id, user_data)
            logger.info(f"Session created: {session_token is not None}")

            if not session_token:
                logger.error("Session creation failed")
                return {"success": False, "error": "Session creation failed"}

            logger.info(f"User logged in successfully: {email}")
            return {
                "success": True,
                "session_token": session_token,
                "user_data": user_data
            }

        except Exception as e:
            logger.error(f"Login error details: {e}", exc_info=True)
            return {"success": False, "error": "Login failed"}

    async def logout_user(self, session_token: str) -> bool:
        """Logout user by invalidating session"""
        return await session_manager.delete_session(session_token)

    async def get_current_user(self, session_token: str) -> dict:
        """Get current user from session"""
        session_data = await session_manager.get_session(session_token)
        if not session_data:
            return None

        user_id = session_data.get("user_id")
        user = self.db.query(User).filter(User.id == user_id).first()

        if user:
            return {
                "id": user.id,
                "email": user.email,
                "name": user.name
            }
        return None

    async def change_password(self, session_token: str, current_password: str, new_password: str) -> dict:
        """Change user password"""
        try:
            user_data = await self.get_current_user(session_token)
            if not user_data:
                return {"success": False, "error": "User not authenticated"}

            user = self.db.query(User).filter(User.id == user_data["id"]).first()
            if not user:
                return {"success": False, "error": "User not found"}

            # Verify current password
            if not password_utils.verify_password(current_password, user.password_hash):
                return {"success": False, "error": "Current password is incorrect"}

            # Validate new password
            if not password_utils.is_strong_password(new_password):
                return {"success": False, "error": "New password too weak"}

            # Update password
            user.password_hash = password_utils.hash_password(new_password)
            self.db.commit()

            logger.info(f"Password changed for user: {user.email}")
            return {"success": True}

        except Exception as e:
            self.db.rollback()
            logger.error(f"Password change error: {e}")
            return {"success": False, "error": "Password change failed"}
