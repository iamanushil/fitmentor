import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

# Make the fitmentor package importable when running alembic from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fitmentor.db.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alembic will compare Base.metadata against the live DB for --autogenerate
target_metadata = Base.metadata


def get_url() -> str:
    # Prefer DATABASE_URL env var; fall back to alembic.ini (empty by design)
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://fitmentor:fitmentor@localhost:5432/fitmentor",
    )


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL only)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live async DB connection."""
    engine = create_async_engine(get_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
