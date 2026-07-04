from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.models.user import User
from src.loggers import Logger
from src.cache.redis_cluster import redis_cluster
from src.cache.session_manager import session_manager

logger = Logger(__name__).get_logger()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AsyncAuthenticationService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    async def register_user(self, email: str, password: str, name: str = None):
        try:
            # Check if user already exists
            existing_user = await self.db.execute(
                select(User).where(User.email == email)
            )
            if existing_user.scalar_one_or_none():
                return {"success": False, "error": "User already exists"}

            # Create new user
            hashed_password = self.hash_password(password)
            new_user = User(
                email=email,
                hashed_password=hashed_password,
                name=name
            )

            self.db.add(new_user)
            await self.db.commit()
            await self.db.refresh(new_user)

            return {"success": True, "user_id": new_user.id}

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Registration error: {e}")
            return {"success": False, "error": str(e)}

    async def login_user(self, email: str, password: str):
        try:
            # Find user
            result = await self.db.execute(
                select(User).where(User.email == email)
            )
            user = result.scalar_one_or_none()

            if not user or not self.verify_password(password, user.hashed_password):
                return {"success": False, "error": "Invalid credentials"}

            # Create session
            user_data = {
                "id": user.id,
                "email": user.email,
                "name": user.name
            }

            session_token = await session_manager.create_session(user.id, user_data)
            if not session_token:
                return {"success": False, "error": "Session creation failed"}

            return {
                "success": True,
                "session_token": session_token,
                "user_id": user.id
            }

        except Exception as e:
            logger.error(f"Login error: {e}")
            return {"success": False, "error": str(e)}

    async def get_current_user(self, session_token: str):
        """Get user from session token"""
        if not session_token:
            return None

        session_data = await session_manager.get_session(session_token)
        if not session_data:
            return None

        return session_data.get("user_data")
