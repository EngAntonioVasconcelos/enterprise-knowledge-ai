import warnings
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.core.config import settings
from app.db.base import Base
# Registers every model on Base.metadata, so autogenerate and
# 'alembic check' see all tables, including ones added later.
import app.models  # noqa: F401


config = context.config

# SQLAlchemy does not know pgvector's 'vector' type when it reads the
# database. Those columns are excluded below (DATABASE_ONLY), so the
# warning is noise; hide only that one message.
warnings.filterwarnings("ignore", message="Did not recognize type 'vector'")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


target_metadata = Base.metadata

# Database-only objects that the models leave out on purpose: the
# full-text column PostgreSQL generates for each chunk, its index, and
# the vector table (pgvector types are used through SQL only).
DATABASE_ONLY = {
    ("column", "content_tsv"),
    ("index", "ix_document_chunks_content_tsv"),
    ("table", "chunk_embeddings"),
    ("index", "ix_chunk_embeddings_document_id"),
    ("index", "ix_chunk_embeddings_e5_small_hnsw"),
    ("index", "ix_chunk_embeddings_e5_base_hnsw"),
}


def include_object(object_, name, type_, reflected, compare_to):
    return (type_, name) not in DATABASE_ONLY


def get_migration_database_url() -> str:
    url = settings.MIGRATION_DATABASE_URL

    if not url:
        raise RuntimeError(
            "MIGRATION_DATABASE_URL must be configured "
            "to execute Alembic migrations."
        )

    return url


def run_migrations_offline() -> None:
    url = get_migration_database_url()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(
        config.config_ini_section,
        {},
    )

    configuration["sqlalchemy.url"] = (
        get_migration_database_url().replace("%", "%%")
    )

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
