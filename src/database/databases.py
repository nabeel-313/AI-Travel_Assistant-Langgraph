from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models.user import Base
import os
from dotenv import load_dotenv

load_dotenv()


class Database:
    def __init__(self, database_url: str = None):
        # Get URL directly from environment - NO settings import
        url = database_url or os.getenv("DATABASE_URL")
        self.engine = create_engine(url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def create_tables(self):
        Base.metadata.create_all(bind=self.engine)

    def get_session(self):
        return self.SessionLocal()


# Create instance
database = Database()
