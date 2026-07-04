from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.config.settings import settings
import os

class AsyncDatabase:
    def __init__(self):
        # Use async URL from settings or convert sync URL
        database_url = settings.ASYNC_DATABASE_URL or settings.DATABASE_URL.replace(
            "postgresql://", "postgresql+asyncpg://"
        )

        self.engine = create_async_engine(
            database_url,
            pool_size=20,
            max_overflow=30,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False
        )
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def get_session(self) -> AsyncSession:
        async with self.async_session() as session:
            try:
                yield session
            finally:
                await session.close()

    async def create_tables(self):
        from sqlalchemy import MetaData
        async with self.engine.begin() as conn:
            # Import your Base here to avoid circular imports
            from .models.user import Base
            await conn.run_sync(Base.metadata.create_all)

# Global async database instance
async_database = AsyncDatabase()
