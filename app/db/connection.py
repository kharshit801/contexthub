"""Database connection management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def get_engine(readonly: bool = False):
    """Get SQLAlchemy engine. Use readonly=True for agent SQL execution."""
    settings = get_settings()
    url = settings.database_url_readonly if readonly else settings.database_url
    return create_engine(url, echo=False)


def get_session(readonly: bool = False):
    """Get a new database session."""
    engine = get_engine(readonly=readonly)
    Session = sessionmaker(bind=engine)
    return Session()


def get_readonly_engine():
    """Get read-only engine for agent SQL execution."""
    return get_engine(readonly=True)
