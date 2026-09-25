"""
migrations/env.py
-----------------
Alembic environment — wired to the application's ORM models and config.

Key design decisions
--------------------
1. The database URL comes exclusively from app.core.config.settings
   (which reads from environment variables / .env).
   No connection strings are ever hardcoded here.

2. We use the *synchronous* psycopg2 driver for Alembic because Alembic's
   run_migrations_online() is synchronous.  The async asyncpg driver is
   used at runtime by the FastAPI application.
   The helper get_sync_url() in database.py converts asyncpg → psycopg2.

3. All ORM models are imported here so Alembic can compare them against
   the live database schema when generating auto-migrations.
   If you add a new model, import it in the "Import all models" block.

4. target_metadata is set to Base.metadata so Alembic knows the full
   schema to diff against.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Make sure the project root is on sys.path so `app.*` imports work
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import all models so Alembic can detect schema changes
# ---------------------------------------------------------------------------
# fmt: off
from app.database.database import Base          # noqa: E402  (Base must come first)
from app.database.models import (               # noqa: E402, F401
    AuditLog,
    Conversation,
    Document,
    DocumentPermission,
    DocumentVersion,
    Message,
    OTPCode,
    Permission,
    Role,
    RolePermission,
    Session,
    User,
    UserRole,
)
# fmt: on

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Inject DATABASE_URL from settings (never from alembic.ini)
# ---------------------------------------------------------------------------
from app.database.database import get_sync_url  # noqa: E402

config.set_main_option("sqlalchemy.url", get_sync_url())


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Generates SQL scripts without connecting to the database.
    Useful for reviewing changes or running against a managed DB
    where direct connections are not allowed.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Render Postgres-specific constructs correctly
        render_as_batch=False,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode — connects to the database directly.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
