"""Uploads shared with chosen people (AL-8b).

A file sent with visibility "people" is read by its uploader and by the
members they chose. The chosen readers live in file_upload_readers, which
only app_private.add_upload_readers writes: it checks that the caller sent
the file and that every reader is an active member of its organization,
and keeps each reader's e-mail so the worker turns them into "user"
permissions without reading users. Only the worker reads the table, inside
its organization; nobody else learns who was chosen.

Downgrade refuses while any upload uses "people": going back would leave
those files without the readers their documents were shared with.

Revision ID: c2f8e5a1d7b3
Revises: e9c4a7b2d6f1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2f8e5a1d7b3"
down_revision: Union[str, Sequence[str], None] = "e9c4a7b2d6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


WORKER_ORGANIZATION = (
    "organization_id = "
    "NULLIF(current_setting('app.organization_id', true), '')::uuid"
)


def upgrade() -> None:
    op.drop_constraint("ck_file_uploads_visibility", "file_uploads", type_="check")
    op.create_check_constraint(
        "ck_file_uploads_visibility",
        "file_uploads",
        "visibility IN ('organization', 'private', 'people')",
    )

    op.create_table(
        "file_upload_readers",
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reader_email", sa.String(length=320), nullable=False),
        sa.PrimaryKeyConstraint("upload_id", "user_id", name="pk_file_upload_readers"),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["file_uploads.id"],
            ondelete="CASCADE",
            name="fk_file_upload_readers_upload_id_file_uploads",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_file_upload_readers_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_file_upload_readers_user_id_users",
        ),
    )

    op.execute(f"""
        REVOKE ALL ON public.file_upload_readers FROM PUBLIC;

        GRANT SELECT ON public.file_upload_readers TO eka_worker;
        GRANT SELECT, INSERT ON public.file_upload_readers TO eka_rls_helper;
        GRANT SELECT ON public.file_uploads TO eka_rls_helper;

        ALTER TABLE public.file_upload_readers ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.file_upload_readers FORCE ROW LEVEL SECURITY;

        CREATE POLICY file_upload_readers_worker_select_policy
        ON public.file_upload_readers
        FOR SELECT
        TO eka_worker
        USING ({WORKER_ORGANIZATION});

        CREATE FUNCTION app_private.add_upload_readers(
            p_upload_id uuid,
            p_user_ids uuid[]
        )
        RETURNS integer
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            v_organization_id uuid;
            v_wanted integer;
            v_added integer;
        BEGIN
            SELECT f.organization_id INTO v_organization_id
            FROM public.file_uploads AS f
            WHERE f.id = p_upload_id
              AND f.visibility = 'people'
              AND f.status = 'active'
              AND f.uploaded_by =
                  NULLIF(current_setting('app.user_id', true), '')::uuid;
            IF v_organization_id IS NULL
               OR NOT app_private.has_active_membership(v_organization_id) THEN
                RAISE EXCEPTION 'not an upload of the caller shared with people'
                    USING ERRCODE = '42501';
            END IF;

            SELECT count(DISTINCT x) INTO v_wanted
            FROM unnest(p_user_ids) AS x;
            IF v_wanted < 1 OR v_wanted > 50 THEN
                RAISE EXCEPTION 'choose from 1 to 50 readers'
                    USING ERRCODE = '22023';
            END IF;

            INSERT INTO public.file_upload_readers (
                upload_id, organization_id, user_id, reader_email
            )
            SELECT p_upload_id, v_organization_id, u.id, lower(u.email)
            FROM public.users AS u
            JOIN public.organization_memberships AS m
              ON m.user_id = u.id
             AND m.organization_id = v_organization_id
             AND m.is_active
            WHERE u.id IN (SELECT DISTINCT x FROM unnest(p_user_ids) AS x)
              AND u.is_active
            ON CONFLICT DO NOTHING;
            GET DIAGNOSTICS v_added = ROW_COUNT;

            IF v_added <> v_wanted THEN
                RAISE EXCEPTION 'every reader must be an active member'
                    USING ERRCODE = '22023';
            END IF;
            RETURN v_added;
        END;
        $function$;

        ALTER FUNCTION app_private.add_upload_readers(uuid, uuid[])
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.add_upload_readers(uuid, uuid[])
            FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION app_private.add_upload_readers(uuid, uuid[])
            TO eka_runtime;
    """)


def downgrade() -> None:
    op.execute("""
        DO $check$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM public.file_uploads WHERE visibility = 'people'
            ) THEN
                RAISE EXCEPTION
                    'uploads shared with people exist: downgrade refused';
            END IF;
        END;
        $check$;

        DROP FUNCTION app_private.add_upload_readers(uuid, uuid[]);
        REVOKE SELECT ON public.file_uploads FROM eka_rls_helper;
    """)
    op.drop_table("file_upload_readers")
    op.drop_constraint("ck_file_uploads_visibility", "file_uploads", type_="check")
    op.create_check_constraint(
        "ck_file_uploads_visibility",
        "file_uploads",
        "visibility IN ('organization', 'private')",
    )
