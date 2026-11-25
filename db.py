import os

from sqlmodel import SQLModel, Session, create_engine

DEFAULT_DATABASE_URL = "sqlite:///sliceflow.db"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL


DATABASE_URL = database_url()
engine = create_engine(DATABASE_URL)


def create_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session