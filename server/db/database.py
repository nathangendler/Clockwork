import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

# PostgreSQL connection settings
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "clockwork")

# Build connection URL
if POSTGRES_PASSWORD:
    DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
else:
    DATABASE_URL = f"postgresql://{POSTGRES_USER}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables in the database."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get a database session. Use as a context manager or call .close() when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
