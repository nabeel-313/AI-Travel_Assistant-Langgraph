from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from src.config.settings import settings
from src.loggers import Logger
from .models.user import Base

logger = Logger(__name__).get_logger()


class Database:
    """Production-grade sync database manager with connection pooling and health checks."""

    def __init__(self, database_url: str = None):
        """
        Initialize database with connection pooling.

        Args:
            database_url: Optional database URL override
        """
        url = database_url or settings.DATABASE_URL

        # Create engine with connection pooling
        self.engine: Engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,  # Verify connection before checkout
            pool_recycle=settings.DATABASE_POOL_RECYCLE,
            pool_timeout=settings.DATABASE_POOL_TIMEOUT,
            echo=settings.DATABASE_ECHO,
        )

        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        logger.info(
            f"Database engine created - Pool size: {settings.DATABASE_POOL_SIZE}, "
            f"Max overflow: {settings.DATABASE_MAX_OVERFLOW}"
        )

    def create_tables(self):
        """Create all database tables."""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            raise

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def get_session_context(self) -> Generator[Session, None, None]:
        """
        Get a database session as a context manager.

        Usage:
            with database.get_session_context() as session:
                session.query(User).all()
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False

    def get_pool_status(self) -> dict:
        """Get connection pool status."""
        pool = self.engine.pool
        return {
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "invalid": pool.invalidatedcount() if hasattr(pool, 'invalidatedcount') else None
        }

    def dispose(self):
        """Dispose of the engine and all connections."""
        try:
            self.engine.dispose()
            logger.info("Database engine disposed")
        except Exception as e:
            logger.error(f"Error disposing database engine: {e}")


# Create global database instance
database = Database()


# Convenience function for dependency injection
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database session.

    Usage:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            return db.query(User).all()
    """
    db = database.get_session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
