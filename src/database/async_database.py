from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from src.config.settings import settings
from src.loggers import Logger

logger = Logger(__name__).get_logger()


class AsyncDatabase:
    """Production-grade async database manager with connection pooling and health checks."""

    def __init__(self):
        """
        Initialize async database with connection pooling.
        """
        # Use async URL from settings or convert sync URL
        database_url = settings.ASYNC_DATABASE_URL or settings.DATABASE_URL.replace(
            "postgresql://", "postgresql+asyncpg://"
        )

        # Determine pool class based on settings
        pool_class = NullPool if settings.DATABASE_USE_NULL_POOL else None

        self.engine = create_async_engine(
            database_url,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=settings.DATABASE_POOL_RECYCLE,
            pool_timeout=settings.DATABASE_POOL_TIMEOUT,
            poolclass=pool_class,
            echo=settings.DATABASE_ECHO
        )

        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        logger.info(
            f"Async database engine created - Pool size: {settings.DATABASE_POOL_SIZE}, "
            f"Max overflow: {settings.DATABASE_MAX_OVERFLOW}"
        )

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a new async database session.

        Usage:
            async with async_database.get_session() as session:
                result = await session.execute(select(User))
        """
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def get_raw_session(self) -> AsyncSession:
        """
        Get a raw async session (caller manages commit/rollback).

        Usage:
            session = await async_database.get_raw_session()
            try:
                result = await session.execute(select(User))
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
        """
        return self.async_session()

    async def create_tables(self):
        """Create all database tables."""
        try:
            from .models.user import Base
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Async database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating async tables: {e}")
            raise

    async def is_connected(self) -> bool:
        """Check if database is connected."""
        try:
            async with self.engine.connect() as conn:
                from sqlalchemy import text
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Async database connection check failed: {e}")
            return False

    async def get_pool_status(self) -> dict:
        """Get connection pool status."""
        try:
            pool = self.engine.pool
            if hasattr(pool, 'size'):
                return {
                    "size": pool.size(),
                    "checked_in": pool.checkedin() if hasattr(pool, 'checkedin') else None,
                    "checked_out": pool.checkedout() if hasattr(pool, 'checkedout') else None,
                    "overflow": pool.overflow() if hasattr(pool, 'overflow') else None
                }
            return {"pool_type": type(pool).__name__}
        except Exception as e:
            logger.error(f"Error getting pool status: {e}")
            return {"error": str(e)}

    async def dispose(self):
        """Dispose of the engine and all connections."""
        try:
            await self.engine.dispose()
            logger.info("Async database engine disposed")
        except Exception as e:
            logger.error(f"Error disposing async database engine: {e}")


# Global async database instance
async_database = AsyncDatabase()


# Convenience function for FastAPI dependency injection
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for async database session.

    Usage:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(select(User))
            return result.scalars().all()
    """
    async for session in async_database.get_session():
        yield session
