from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Project imports ────────────────────────────────────────────────────────────
# Import both model modules so that their table definitions are registered on
# the shared Base.metadata before autogenerate/upgrade runs.
import backlog_generation.models  # noqa: F401  (registers issues/hierarchy/links)
import backlog_generation.backlog_models  # noqa: F401  (registers backlogs/epics/stories)
import backlog_generation.approval_models  # noqa: F401  (registers approval_events)
from backlog_generation.models import Base

# ── Alembic config ─────────────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Tables managed by this project — autogenerate will only touch these.
_MANAGED_TABLES = {
    "issues", "issue_hierarchy", "issue_links",
    "backlogs", "generated_epics", "generated_stories",
    "approval_events",
}


def _include_object(obj, name, type_, reflected, compare_to):
    """Restrict autogenerate to only the tables owned by this project."""
    if type_ == "table":
        return name in _MANAGED_TABLES
    return True


def _get_url() -> str:
    """Return DB URL from the environment, falling back to alembic.ini."""
    import os
    from pathlib import Path

    # Load .env so POSTGRES_DSN is available even when alembic is run directly.
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
        except ImportError:
            pass  # python-dotenv not installed; rely on shell env

    postgres_dsn = os.getenv("POSTGRES_DSN", "").strip()
    if postgres_dsn:
        if postgres_dsn.startswith("postgresql://"):
            return postgres_dsn.replace("postgresql://", "postgresql+psycopg://", 1)
        return postgres_dsn
    return config.get_main_option("sqlalchemy.url", "")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

