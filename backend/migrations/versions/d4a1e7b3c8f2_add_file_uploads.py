"""Files uploaded by members, read by the file_upload connector.

Revision ID: d4a1e7b3c8f2
Revises: c9f4b2a8e6d1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4a1e7b3c8f2"
down_revision: Union[str, Sequence[str], None] = "c9f4b2a8e6d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CURRENT_USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"
WORKER_ORGANIZATION = (
    "organization_id = "
    "NULLIF(current_setting('app.organization_id', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "file_uploads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("uploader_email", sa.String(length=320), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "original_object_key", sa.String(length=500), nullable=False
        ),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_file_uploads"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_file_uploads_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["data_connections.id"],
            ondelete="CASCADE",
            name="fk_file_uploads_connection_id_data_connections",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_file_uploads_uploaded_by_users",
        ),
        sa.CheckConstraint(
            "visibility IN ('organization', 'private')",
            name="ck_file_uploads_visibility",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'deleted')",
            name="ck_file_uploads_status",
        ),
        sa.CheckConstraint(
            "(status = 'deleted') = (deleted_at IS NOT NULL)",
            name="ck_file_uploads_deleted_at",
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_file_uploads_sha256",
        ),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 20971520",
            name="ck_file_uploads_size",
        ),
    )

    # Uploaders see and delete their own uploads only. A new upload must be
    # by the caller, under the caller's own e-mail, into a live
    # file_upload connection of an organization the caller belongs to.
    op.execute(f"""
        REVOKE ALL ON public.file_uploads FROM PUBLIC;

        GRANT SELECT, INSERT ON public.file_uploads TO eka_runtime;
        GRANT UPDATE (status, deleted_at) ON public.file_uploads
            TO eka_runtime;
        GRANT SELECT ON public.file_uploads TO eka_worker;

        ALTER TABLE public.file_uploads ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.file_uploads FORCE ROW LEVEL SECURITY;

        CREATE POLICY file_uploads_select_policy
        ON public.file_uploads
        FOR SELECT
        TO eka_runtime
        USING (uploaded_by = {CURRENT_USER});

        CREATE POLICY file_uploads_insert_policy
        ON public.file_uploads
        FOR INSERT
        TO eka_runtime
        WITH CHECK (
            uploaded_by = {CURRENT_USER}
            AND status = 'active'
            AND deleted_at IS NULL
            AND app_private.has_active_membership(organization_id)
            AND EXISTS (
                SELECT 1
                FROM public.users AS u
                WHERE u.id = uploaded_by
                  AND u.email = uploader_email
            )
        );

        CREATE POLICY file_uploads_update_policy
        ON public.file_uploads
        FOR UPDATE
        TO eka_runtime
        USING (uploaded_by = {CURRENT_USER})
        WITH CHECK (uploaded_by = {CURRENT_USER});

        CREATE POLICY file_uploads_worker_select_policy
        ON public.file_uploads
        FOR SELECT
        TO eka_worker
        USING ({WORKER_ORGANIZATION});

        CREATE TRIGGER trg_require_active_organization
        BEFORE INSERT ON public.file_uploads
        FOR EACH ROW
        EXECUTE FUNCTION app_private.require_active_organization();

        -- Members need two narrow rights to upload: to see the upload
        -- connections of their organization (not the others), and to queue
        -- the sync of such a connection (seeing only jobs they queued).
        CREATE POLICY data_connections_member_upload_policy
        ON public.data_connections
        FOR SELECT
        TO eka_runtime
        USING (
            provider = 'file_upload'
            AND app_private.has_active_membership(organization_id)
        );

        CREATE POLICY background_jobs_member_sync_policy
        ON public.background_jobs
        FOR INSERT
        TO eka_runtime
        WITH CHECK (
            kind = 'connection.sync'
            AND status = 'queued'
            AND attempts = 0
            AND locked_by IS NULL
            AND locked_at IS NULL
            AND finished_at IS NULL
            AND last_error IS NULL
            AND created_by_user_id = {CURRENT_USER}
            AND app_private.has_active_membership(organization_id)
            AND EXISTS (
                SELECT 1
                FROM public.data_connections AS c
                WHERE c.id = (payload ->> 'connection_id')::uuid
                  AND c.organization_id = background_jobs.organization_id
                  AND c.provider = 'file_upload'
            )
        );

        CREATE POLICY background_jobs_own_select_policy
        ON public.background_jobs
        FOR SELECT
        TO eka_runtime
        USING (created_by_user_id = {CURRENT_USER});
    """)

    # The connection must be a live file_upload connection of the same
    # organization; a deleted upload stays deleted.
    op.execute("""
        CREATE FUNCTION app_private.protect_file_uploads()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NOT EXISTS (
                    SELECT 1
                    FROM public.data_connections AS c
                    WHERE c.id = NEW.connection_id
                      AND c.organization_id = NEW.organization_id
                      AND c.provider = 'file_upload'
                      AND c.status <> 'disconnected'
                ) THEN
                    RAISE EXCEPTION
                        'uploads go to a live file upload connection of the '
                        'same organization'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                RETURN NEW;
            END IF;

            IF OLD.status = 'deleted' THEN
                RAISE EXCEPTION 'a deleted upload cannot change'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            IF NEW.status = 'deleted' THEN
                NEW.deleted_at := clock_timestamp();
            END IF;
            RETURN NEW;
        END;
        $function$;

        ALTER FUNCTION app_private.protect_file_uploads()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.protect_file_uploads()
            FROM PUBLIC;

        CREATE TRIGGER trg_protect_file_uploads
        BEFORE INSERT OR UPDATE ON public.file_uploads
        FOR EACH ROW
        EXECUTE FUNCTION app_private.protect_file_uploads();
    """)


def downgrade() -> None:
    op.execute("""
        DROP POLICY background_jobs_own_select_policy
            ON public.background_jobs;
        DROP POLICY background_jobs_member_sync_policy
            ON public.background_jobs;
        DROP POLICY data_connections_member_upload_policy
            ON public.data_connections;
    """)
    op.drop_table("file_uploads")
    op.execute("DROP FUNCTION app_private.protect_file_uploads();")
