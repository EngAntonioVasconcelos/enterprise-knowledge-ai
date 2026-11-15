"""Documents with immutable versions and row-level security (ADR-003).

Revision ID: f3a8c6e1b9d4
Revises: e1c5a9d2f7b3

The documents table created in the first migration was a placeholder that
no code used and that had no row-level security. This migration reshapes
it, and refuses to run if it holds any row, so no data can be lost.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a8c6e1b9d4"
down_revision: Union[str, Sequence[str], None] = "e1c5a9d2f7b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


WORKER_ORGANIZATION = (
    "organization_id = "
    "NULLIF(current_setting('app.organization_id', true), '')::uuid"
)


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.documents) THEN
                RAISE EXCEPTION
                    'documents is not empty: this migration reshapes the '
                    'table and would lose rows; move them first';
            END IF;
        END;
        $$;

        REVOKE ALL ON public.documents FROM eka_runtime;
    """)

    op.drop_column("documents", "source")
    op.alter_column(
        "documents",
        "external_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.add_column(
        "documents", sa.Column("connection_id", sa.Uuid(), nullable=False)
    )
    op.add_column(
        "documents",
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "last_synced_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "documents",
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_documents_connection_id_data_connections",
        "documents",
        "data_connections",
        ["connection_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_documents_connection_external_id",
        "documents",
        ["connection_id", "external_id"],
    )
    op.create_check_constraint(
        "ck_documents_status",
        "documents",
        "status IN ('pending', 'active', 'failed', 'removed')",
    )
    op.create_check_constraint(
        "ck_documents_active_has_version",
        "documents",
        "status <> 'active' OR current_version_id IS NOT NULL",
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("source_revision", sa.String(length=255), nullable=True),
        sa.Column(
            "source_modified_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "original_object_key", sa.String(length=500), nullable=True
        ),
        sa.Column(
            "normalized_object_key", sa.String(length=500), nullable=True
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_document_versions_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_document_versions_organization_id_organizations",
        ),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_number",
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'ready', 'failed')",
            name="ck_document_versions_status",
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_document_versions_content_hash",
        ),
        sa.CheckConstraint(
            "(status = 'ready') = (ready_at IS NOT NULL)",
            name="ck_document_versions_ready_at",
        ),
    )
    op.create_foreign_key(
        "fk_documents_current_version_id_document_versions",
        "documents",
        "document_versions",
        ["current_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Ingestion is the worker's job: it writes documents and versions, for
    # the organization of its current job only. The API reads them, for
    # owners and admins for now; members get access through the source
    # permissions (next step). Nobody deletes a version directly.
    op.execute(f"""
        GRANT SELECT ON public.documents TO eka_runtime;
        GRANT SELECT ON public.document_versions TO eka_runtime;

        GRANT SELECT, INSERT ON public.documents TO eka_worker;
        GRANT UPDATE (
            title, description, mime_type, status, current_version_id,
            last_synced_at, removed_at, updated_at
        ) ON public.documents TO eka_worker;
        GRANT SELECT, INSERT ON public.document_versions TO eka_worker;
        GRANT UPDATE (status, error, ready_at)
            ON public.document_versions TO eka_worker;

        GRANT SELECT ON public.documents TO eka_rls_helper;
        GRANT SELECT ON public.document_versions TO eka_rls_helper;

        ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.documents FORCE ROW LEVEL SECURITY;
        ALTER TABLE public.document_versions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.document_versions FORCE ROW LEVEL SECURITY;

        CREATE POLICY documents_select_policy
        ON public.documents
        FOR SELECT
        TO eka_runtime
        USING (app_private.can_manage_organization(organization_id));

        CREATE POLICY document_versions_select_policy
        ON public.document_versions
        FOR SELECT
        TO eka_runtime
        USING (app_private.can_manage_organization(organization_id));

        CREATE POLICY documents_worker_select_policy
        ON public.documents
        FOR SELECT
        TO eka_worker
        USING ({WORKER_ORGANIZATION});

        CREATE POLICY documents_worker_insert_policy
        ON public.documents
        FOR INSERT
        TO eka_worker
        WITH CHECK (
            {WORKER_ORGANIZATION}
            AND status = 'pending'
            AND current_version_id IS NULL
            AND EXISTS (
                SELECT 1
                FROM public.data_connections AS c
                WHERE c.id = connection_id
                  AND c.organization_id = documents.organization_id
                  AND c.status <> 'disconnected'
            )
        );

        CREATE POLICY documents_worker_update_policy
        ON public.documents
        FOR UPDATE
        TO eka_worker
        USING ({WORKER_ORGANIZATION})
        WITH CHECK ({WORKER_ORGANIZATION});

        CREATE POLICY document_versions_worker_select_policy
        ON public.document_versions
        FOR SELECT
        TO eka_worker
        USING ({WORKER_ORGANIZATION});

        CREATE POLICY document_versions_worker_insert_policy
        ON public.document_versions
        FOR INSERT
        TO eka_worker
        WITH CHECK (
            {WORKER_ORGANIZATION}
            AND status = 'processing'
            AND ready_at IS NULL
            AND EXISTS (
                SELECT 1
                FROM public.documents AS d
                WHERE d.id = document_id
                  AND d.organization_id = document_versions.organization_id
            )
        );

        CREATE POLICY document_versions_worker_update_policy
        ON public.document_versions
        FOR UPDATE
        TO eka_worker
        USING ({WORKER_ORGANIZATION})
        WITH CHECK ({WORKER_ORGANIZATION});
    """)

    # The database numbers versions, lets a version move only from
    # processing to ready or failed, and lets a document point only at a
    # ready version of its own.
    op.execute("""
        CREATE FUNCTION app_private.number_document_version()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            -- Serialize numbering per document (the unique constraint on
            -- document and number is the final word).
            PERFORM pg_advisory_xact_lock(
                hashtextextended('document-version:' || NEW.document_id::text, 0)
            );

            SELECT COALESCE(max(version_number), 0) + 1
            INTO NEW.version_number
            FROM public.document_versions
            WHERE document_id = NEW.document_id;

            RETURN NEW;
        END;
        $function$;

        ALTER FUNCTION app_private.number_document_version()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.number_document_version()
            FROM PUBLIC;

        CREATE TRIGGER trg_number_document_version
        BEFORE INSERT ON public.document_versions
        FOR EACH ROW
        EXECUTE FUNCTION app_private.number_document_version();

        CREATE FUNCTION app_private.protect_document_versions()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF OLD.status <> 'processing' THEN
                RAISE EXCEPTION
                    'a processed document version cannot change'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            IF NEW.status = 'ready' THEN
                NEW.ready_at := clock_timestamp();
            ELSE
                NEW.ready_at := NULL;
            END IF;

            RETURN NEW;
        END;
        $function$;

        REVOKE ALL ON FUNCTION app_private.protect_document_versions()
            FROM PUBLIC;

        CREATE TRIGGER trg_protect_document_versions
        BEFORE UPDATE ON public.document_versions
        FOR EACH ROW
        EXECUTE FUNCTION app_private.protect_document_versions();

        CREATE FUNCTION app_private.protect_documents()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF NEW.current_version_id IS NOT NULL
               AND NEW.current_version_id IS DISTINCT FROM
                   OLD.current_version_id
               AND NOT EXISTS (
                   SELECT 1
                   FROM public.document_versions AS v
                   WHERE v.id = NEW.current_version_id
                     AND v.document_id = NEW.id
                     AND v.status = 'ready'
               ) THEN
                RAISE EXCEPTION
                    'the current version must be a ready version of the '
                    'same document'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            IF NEW.status = 'removed' AND OLD.status <> 'removed' THEN
                NEW.removed_at := clock_timestamp();
            ELSIF NEW.status <> 'removed' THEN
                NEW.removed_at := NULL;
            END IF;

            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END;
        $function$;

        ALTER FUNCTION app_private.protect_documents()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.protect_documents()
            FROM PUBLIC;

        CREATE TRIGGER trg_protect_documents
        BEFORE UPDATE ON public.documents
        FOR EACH ROW
        EXECUTE FUNCTION app_private.protect_documents();

        CREATE TRIGGER trg_require_active_organization
        BEFORE INSERT ON public.documents
        FOR EACH ROW
        EXECUTE FUNCTION app_private.require_active_organization();
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.documents) THEN
                RAISE EXCEPTION
                    'documents is not empty: downgrading would lose rows';
            END IF;
        END;
        $$;

        DROP TRIGGER trg_require_active_organization ON public.documents;
        DROP TRIGGER trg_protect_documents ON public.documents;
        DROP FUNCTION app_private.protect_documents();
    """)

    op.drop_constraint(
        "fk_documents_current_version_id_document_versions",
        "documents",
        type_="foreignkey",
    )
    op.drop_table("document_versions")
    op.execute("""
        DROP FUNCTION app_private.protect_document_versions();
        DROP FUNCTION app_private.number_document_version();

        ALTER TABLE public.documents NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE public.documents DISABLE ROW LEVEL SECURITY;
        DROP POLICY documents_select_policy ON public.documents;
        DROP POLICY documents_worker_select_policy ON public.documents;
        DROP POLICY documents_worker_insert_policy ON public.documents;
        DROP POLICY documents_worker_update_policy ON public.documents;

        REVOKE ALL ON public.documents FROM eka_worker;
        REVOKE ALL ON public.documents FROM eka_rls_helper;
        REVOKE ALL ON public.documents FROM eka_runtime;
        GRANT SELECT, INSERT, UPDATE ON public.documents TO eka_runtime;
    """)

    op.drop_constraint(
        "ck_documents_active_has_version", "documents", type_="check"
    )
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.drop_constraint(
        "uq_documents_connection_external_id", "documents", type_="unique"
    )
    op.drop_constraint(
        "fk_documents_connection_id_data_connections",
        "documents",
        type_="foreignkey",
    )
    op.drop_column("documents", "removed_at")
    op.drop_column("documents", "last_synced_at")
    op.drop_column("documents", "current_version_id")
    op.drop_column("documents", "connection_id")
    op.alter_column(
        "documents",
        "external_id",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.add_column(
        "documents",
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.alter_column("documents", "source", server_default=None)
