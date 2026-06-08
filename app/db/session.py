from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from urllib.parse import quote_plus
from dotenv import load_dotenv
import os

load_dotenv()


def build_database_url() -> str:
    host     = os.getenv("DB_HOST")
    port     = os.getenv("DB_PORT", "5432")
    user     = quote_plus(os.getenv("DB_USER", ""))
    password = quote_plus(os.getenv("DB_PASSWORD", ""))  # handles special chars like @, #, $
    name     = os.getenv("DB_NAME")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


DATABASE_URL = build_database_url()

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
