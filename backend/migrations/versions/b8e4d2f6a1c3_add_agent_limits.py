"""Agent limits per organization and the audit of tool calls (AL-2).

agent_max_steps bounds the model calls one answer may make (answer,
relevance check, another attempt); agent_max_tool_calls bounds the tool
calls (searches). Each tool call is recorded in audit_events without the
person and without the question: only the tool, the step, how many results
and how long it took.

Revision ID: b8e4d2f6a1c3
Revises: f2c7a9e4b6d1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e4d2f6a1c3"
down_revision: Union[str, Sequence[str], None] = "f2c7a9e4b6d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "agent_max_steps",
            sa.Integer(),
            server_default=sa.text("4"),
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "agent_max_tool_calls",
            sa.Integer(),
            server_default=sa.text("6"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_organizations_agent_max_steps",
        "organizations",
        "agent_max_steps BETWEEN 1 AND 8",
    )
    op.create_check_constraint(
        "ck_organizations_agent_max_tool_calls",
        "organizations",
        "agent_max_tool_calls BETWEEN 1 AND 12",
    )

    # A member records a tool call made for their own question, in their
    # own organization. The row names no person (actor_user_id is NULL)
    # and holds no text from the question or the documents.
    op.execute("""
        CREATE FUNCTION app_private.record_agent_tool_call(
            p_organization_id uuid,
            p_tool text,
            p_step integer,
            p_results integer,
            p_ms integer
        )
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF NOT app_private.has_active_membership(p_organization_id) THEN
                RAISE EXCEPTION 'not a member of this organization'
                    USING ERRCODE = '42501';
            END IF;
            IF p_tool NOT IN ('search_documents') THEN
                RAISE EXCEPTION 'unknown tool' USING ERRCODE = '22023';
            END IF;
            INSERT INTO public.audit_events (
                organization_id, actor_user_id, actor_database_login,
                action, target_type, target_id, details, created_at
            )
            VALUES (
                p_organization_id,
                NULL,
                session_user,
                'agent.tool_call',
                'organization',
                p_organization_id,
                jsonb_build_object(
                    'tool', p_tool,
                    'step', GREATEST(LEAST(p_step, 100), 0),
                    'results', GREATEST(LEAST(p_results, 1000), 0),
                    'ms', GREATEST(LEAST(p_ms, 3600000), 0)
                ),
                clock_timestamp()
            );
        END;
        $function$;

        ALTER FUNCTION
            app_private.record_agent_tool_call(uuid, text, integer, integer, integer)
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION
            app_private.record_agent_tool_call(uuid, text, integer, integer, integer)
            FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION
            app_private.record_agent_tool_call(uuid, text, integer, integer, integer)
            TO eka_runtime;
    """)


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION app_private.record_agent_tool_call"
        "(uuid, text, integer, integer, integer);"
    )
    op.drop_constraint(
        "ck_organizations_agent_max_tool_calls", "organizations", type_="check"
    )
    op.drop_constraint(
        "ck_organizations_agent_max_steps", "organizations", type_="check"
    )
    op.drop_column("organizations", "agent_max_tool_calls")
    op.drop_column("organizations", "agent_max_steps")
