from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class DatabaseSessionManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def init(self, database_url: str) -> None:
        self._engine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            future=True,
        )
        self._sessionmaker = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            autoflush=False,
        )
        logger.info("Database engine initialized")

    async def create_all(self) -> None:
        if self._engine is None:
            raise RuntimeError("Database engine is not initialized")
        async with self._engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        logger.info("Database schema is ready")

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None
            logger.info("Database engine disposed")

    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._sessionmaker is None:
            raise RuntimeError("Database sessionmaker is not initialized")
        return self._sessionmaker

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory()() as session:
            yield session


sessionmanager = DatabaseSessionManager()
