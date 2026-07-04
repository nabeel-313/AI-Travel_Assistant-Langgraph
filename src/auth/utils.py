from passlib.context import CryptContext
from src.loggers import Logger

logger = Logger(__name__).get_logger()

# Password hashing context
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],  # bcrypt only for legacy verification
    deprecated="auto",
)


class PasswordUtils:
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password for storing"""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a stored password against one provided by user"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def is_strong_password(password: str) -> bool:
        """Check if password meets strength requirements"""
        if len(password) < 8:
            return False
        # Add more strength checks as needed
        return True


password_utils = PasswordUtils()
