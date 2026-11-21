"""The audit of the agent's data tool (AL-4).

app_private.record_agent_tool_call (AL-2) accepted only search_documents.
It now also accepts query_data, which must name the connection queried, a
connection of the same organization. The row still names no person and
holds no text: not the question, not the query, not the rows.

Revision ID: d7e3b9c5a2f8
Revises: c3f9a1e7d2b4
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d7e3b9c5a2f8"
down_revision: Union[str, Sequence[str], None] = "c3f9a1e7d2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD = "app_private.record_agent_tool_call(uuid, text, integer, integer, integer)"
NEW = "app_private.record_agent_tool_call(uuid, text, integer, integer, integer, uuid)"


def _function(signature: str, tools: str, connection_check: str, details: str) -> str:
    return f"""
        CREATE FUNCTION {signature}
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
            IF p_tool NOT IN ({tools}) THEN
                RAISE EXCEPTION 'unknown tool' USING ERRCODE = '22023';
            END IF;
            {connection_check}
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
                {details},
                clock_timestamp()
            );
        END;
        $function$;
    """


def _grants(signature: str) -> str:
    return f"""
        ALTER FUNCTION {signature} OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION {signature} FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION {signature} TO eka_runtime;
    """


COUNTS = """
                    'step', GREATEST(LEAST(p_step, 100), 0),
                    'results', GREATEST(LEAST(p_results, 1000), 0),
                    'ms', GREATEST(LEAST(p_ms, 3600000), 0)"""


def upgrade() -> None:
    op.execute(f"DROP FUNCTION {OLD};")
    op.execute(
        _function(
            "app_private.record_agent_tool_call("
            "p_organization_id uuid, p_tool text, p_step integer, "
            "p_results integer, p_ms integer, p_connection_id uuid DEFAULT NULL)",
            "'search_documents', 'query_data'",
            """
            IF (p_tool = 'query_data') <> (p_connection_id IS NOT NULL) THEN
                RAISE EXCEPTION 'query_data names its connection, and only it'
                    USING ERRCODE = '22023';
            END IF;
            IF p_connection_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM public.data_connections
                WHERE id = p_connection_id
                  AND organization_id = p_organization_id
            ) THEN
                RAISE EXCEPTION 'unknown connection' USING ERRCODE = '22023';
            END IF;
            """,
            "jsonb_strip_nulls(jsonb_build_object('tool', p_tool, "
            "'connection_id', p_connection_id," + COUNTS + "))",
        )
    )
    op.execute(_grants(NEW))


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {NEW};")
    op.execute(
        _function(
            "app_private.record_agent_tool_call("
            "p_organization_id uuid, p_tool text, p_step integer, "
            "p_results integer, p_ms integer)",
            "'search_documents'",
            "",
            "jsonb_build_object('tool', p_tool," + COUNTS + ")",
        )
    )
    op.execute(_grants(OLD))
