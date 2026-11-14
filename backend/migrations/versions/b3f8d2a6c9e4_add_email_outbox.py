"""Add the e-mail outbox and the eka_mailer role that sends it.

Revision ID: b3f8d2a6c9e4
Revises: a7e3c9f1d4b2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3f8d2a6c9e4"
down_revision: Union[str, Sequence[str], None] = "a7e3c9f1d4b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Capability role of the dispatcher. The login that runs it is
    # provisioned separately and switches to this role with SET ROLE.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_catalog.pg_roles
                WHERE rolname = 'eka_mailer'
            ) THEN
                CREATE ROLE eka_mailer
                    NOLOGIN
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOREPLICATION
                    NOBYPASSRLS;
            END IF;

            ALTER ROLE eka_mailer
                NOLOGIN
                NOSUPERUSER
                NOCREATEDB
                NOCREATEROLE
                NOREPLICATION
                NOBYPASSRLS;
        END;
        $$;

        REVOKE eka_mailer FROM eka_runtime;
    """)

    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancelled_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.PrimaryKeyConstraint("id", name="pk_email_outbox"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_email_outbox_organization_id_organizations",
        ),
        sa.UniqueConstraint(
            "reference_id",
            "kind",
            name="uq_email_outbox_reference",
        ),
        sa.CheckConstraint(
            "kind IN ('invitation')",
            name="ck_email_outbox_kind",
        ),
        sa.CheckConstraint(
            "(sent_at IS NULL AND cancelled_at IS NULL) OR body IS NULL",
            name="ck_email_outbox_body_cleared",
        ),
    )

    # The application only adds e-mails, and only for a pending invitation
    # of an organization it manages, sent to the invited address. It cannot
    # read the outbox back, so a leaked runtime session cannot collect the
    # links. The dispatcher reads and marks rows, and nothing else.
    op.execute("""
        REVOKE ALL ON public.email_outbox FROM PUBLIC;

        GRANT INSERT ON public.email_outbox TO eka_runtime;

        GRANT USAGE ON SCHEMA public TO eka_mailer;
        GRANT SELECT ON public.email_outbox TO eka_mailer;
        GRANT UPDATE (body, attempts, last_error, sent_at, cancelled_at)
            ON public.email_outbox
            TO eka_mailer;

        GRANT SELECT ON public.email_outbox TO eka_rls_helper;
        GRANT UPDATE (body, cancelled_at)
            ON public.email_outbox
            TO eka_rls_helper;

        ALTER TABLE public.email_outbox ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.email_outbox FORCE ROW LEVEL SECURITY;

        CREATE POLICY email_outbox_insert_policy
        ON public.email_outbox
        FOR INSERT
        TO eka_runtime
        WITH CHECK (
            kind = 'invitation'
            AND sent_at IS NULL
            AND cancelled_at IS NULL
            AND attempts = 0
            AND body IS NOT NULL
            AND app_private.can_manage_organization(organization_id)
            AND EXISTS (
                SELECT 1
                FROM public.organization_invitations AS i
                WHERE i.id = reference_id
                  AND i.organization_id = email_outbox.organization_id
                  AND i.email = recipient
                  AND i.status = 'pending'
                  AND i.expires_at = email_outbox.expires_at
            )
        );

        CREATE POLICY email_outbox_mailer_select_policy
        ON public.email_outbox
        FOR SELECT
        TO eka_mailer
        USING (true);

        CREATE POLICY email_outbox_mailer_update_policy
        ON public.email_outbox
        FOR UPDATE
        TO eka_mailer
        USING (true)
        WITH CHECK (true);
    """)

    # Once an e-mail is sent or cancelled it never changes again, and a body
    # can only be cleared, never rewritten: the dispatcher cannot be used to
    # send something the application did not write.
    op.execute("""
        CREATE FUNCTION app_private.protect_email_outbox()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF OLD.sent_at IS NOT NULL OR OLD.cancelled_at IS NOT NULL THEN
                RAISE EXCEPTION
                    'a sent or cancelled email cannot change'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            IF NEW.body IS NOT NULL
               AND NEW.body IS DISTINCT FROM OLD.body THEN
                RAISE EXCEPTION
                    'an outbox email body can only be cleared'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            IF NEW.attempts < OLD.attempts THEN
                RAISE EXCEPTION
                    'delivery attempts cannot decrease'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            RETURN NEW;
        END;
        $function$;

        REVOKE ALL ON FUNCTION app_private.protect_email_outbox()
            FROM PUBLIC;

        CREATE TRIGGER trg_protect_email_outbox
        BEFORE UPDATE ON public.email_outbox
        FOR EACH ROW
        EXECUTE FUNCTION app_private.protect_email_outbox();
    """)

    # An invitation that stops being pending (accepted, revoked, expired)
    # cancels its unsent e-mail and erases the link at once.
    op.execute("""
        CREATE FUNCTION app_private.cancel_invitation_email()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            UPDATE public.email_outbox
            SET body = NULL,
                cancelled_at = clock_timestamp()
            WHERE kind = 'invitation'
              AND reference_id = NEW.id
              AND sent_at IS NULL
              AND cancelled_at IS NULL;

            RETURN NULL;
        END;
        $function$;

        ALTER FUNCTION app_private.cancel_invitation_email()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.cancel_invitation_email()
            FROM PUBLIC;

        CREATE TRIGGER trg_cancel_invitation_email
        AFTER UPDATE OF status ON public.organization_invitations
        FOR EACH ROW
        WHEN (OLD.status = 'pending' AND NEW.status <> 'pending')
        EXECUTE FUNCTION app_private.cancel_invitation_email();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER trg_cancel_invitation_email
            ON public.organization_invitations;
        DROP FUNCTION app_private.cancel_invitation_email();
    """)

    op.drop_table("email_outbox")

    op.execute("""
        DROP FUNCTION app_private.protect_email_outbox();
        REVOKE USAGE ON SCHEMA public FROM eka_mailer;
    """)
