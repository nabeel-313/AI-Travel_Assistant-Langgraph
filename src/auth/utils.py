import re
from typing import Tuple

from passlib.context import CryptContext

from src.config.settings import settings
from src.loggers import Logger

logger = Logger(__name__).get_logger()

# Password hashing context
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],  # argon2 is preferred, bcrypt for legacy
    deprecated="auto",
    argon2__memory_cost=65536,  # 64MB
    argon2__time_cost=3,
    argon2__parallelism=4,
)


class PasswordUtils:
    """Password hashing and verification utilities."""

    # Password strength regex patterns
    UPPERCASE_PATTERN = re.compile(r'[A-Z]')
    LOWERCASE_PATTERN = re.compile(r'[a-z]')
    DIGIT_PATTERN = re.compile(r'\d')
    SPECIAL_PATTERN = re.compile(r'[!@#$%^&*(),.?":{}|<>]')

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password for storing.

        Args:
            password: Plain text password

        Returns:
            Hashed password string
        """
        try:
            return pwd_context.hash(password)
        except Exception as e:
            logger.error(f"Password hashing error: {e}")
            raise ValueError("Failed to hash password")

    @staticmethod
    async def hash_password_async(password: str) -> str:
        """
        Async hash a password for storing.

        Args:
            password: Plain text password

        Returns:
            Hashed password string
        """
        import asyncio
        try:
            # Run hash in executor to not block
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, pwd_context.hash, password)
        except Exception as e:
            logger.error(f"Async password hashing error: {e}")
            raise ValueError("Failed to hash password")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a stored password against one provided by user.

        Args:
            plain_password: Plain text password to verify
            hashed_password: Stored hashed password

        Returns:
            True if password matches, False otherwise
        """
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False

    @staticmethod
    async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
        """
        Async verify a stored password against one provided by user.

        Args:
            plain_password: Plain text password to verify
            hashed_password: Stored hashed password

        Returns:
            True if password matches, False otherwise
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, pwd_context.verify, plain_password, hashed_password
            )
        except Exception as e:
            logger.error(f"Async password verification error: {e}")
            return False

    @staticmethod
    def is_strong_password(password: str) -> Tuple[bool, str]:
        """
        Check if password meets strength requirements.

        Args:
            password: Password to check

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not password:
            return False, "Password is required"

        if len(password) < settings.security.password_min_length:
            return False, f"Password must be at least {settings.security.password_min_length} characters"

        if len(password) > settings.security.password_max_length:
            return False, f"Password must not exceed {settings.security.password_max_length} characters"

        # Check for uppercase
        if not PasswordUtils.UPPERCASE_PATTERN.search(password):
            return False, "Password must contain at least one uppercase letter"

        # Check for lowercase
        if not PasswordUtils.LOWERCASE_PATTERN.search(password):
            return False, "Password must contain at least one lowercase letter"

        # Check for digit
        if not PasswordUtils.DIGIT_PATTERN.search(password):
            return False, "Password must contain at least one digit"

        # Check for special character
        if not PasswordUtils.SPECIAL_PATTERN.search(password):
            return False, "Password must contain at least one special character"

        return True, ""

    @staticmethod
    def needs_rehash(password_hash: str) -> bool:
        """
        Check if a password hash needs to be rehashed with a different algorithm.

        Args:
            password_hash: The stored password hash

        Returns:
            True if rehash is needed, False otherwise
        """
        try:
            return pwd_context.needs_update(password_hash)
        except Exception as e:
            logger.error(f"Password hash check error: {e}")
            return False


password_utils = PasswordUtils()
