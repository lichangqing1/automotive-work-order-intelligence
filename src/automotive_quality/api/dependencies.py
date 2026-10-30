from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from automotive_quality.domains.retrieval.service import RetrievalService
from automotive_quality.infrastructure.database.case_repository import PostgresCaseRepository
from automotive_quality.infrastructure.database.session import get_engine


def database_session() -> Generator[Session, None, None]:
    session = sessionmaker(bind=get_engine(), expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()


def retrieval_service(session: Annotated[Session, Depends(database_session)]) -> RetrievalService:
    return RetrievalService(PostgresCaseRepository(session))
