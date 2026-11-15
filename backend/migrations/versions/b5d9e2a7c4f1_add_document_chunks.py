"""Documents are cut into chunks that can be searched (Phase 6, RAG Core).

Revision ID: b5d9e2a7c4f1
Revises: f9d2b6e4a1c7

A chunk is a passage of one document version: a section or a few
paragraphs, with its exact position in the text so an answer can cite it.
Chunks are derived data: the worker writes them when a version is
synchronized, and nobody edits them.

Who may read a chunk is not decided here again: the policy asks whether
the chunk's document is visible, so the document rules (source
permissions, connection scope, membership) apply to chunks by
construction.

Also creates the pgvector extension (vectors arrive in the next step) and
eka_search_text, so a word typed without accents still finds the accented
one.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b5d9e2a7c4f1"
down_revision: Union[str, Sequence[str], None] = "f9d2b6e4a1c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Accented letters and their plain forms, lower and upper case (written
# with escapes so this file stays ASCII).
ACCENTED = (
    "\u00e1\u00e0\u00e2\u00e3\u00e4\u00e5\u00e9\u00e8\u00ea\u00eb"
    "\u00ed\u00ec\u00ee\u00ef\u00f3\u00f2\u00f4\u00f5\u00f6\u00fa"
    "\u00f9\u00fb\u00fc\u00e7\u00f1\u00fd\u00ff"
    "\u00c1\u00c0\u00c2\u00c3\u00c4\u00c5\u00c9\u00c8\u00ca\u00cb"
    "\u00cd\u00cc\u00ce\u00cf\u00d3\u00d2\u00d4\u00d5\u00d6\u00da"
    "\u00d9\u00db\u00dc\u00c7\u00d1\u00dd"
)
PLAIN = "aaaaaaeeeeiiiiooooouuuucnyy" + "AAAAAAEEEEIIIIOOOOOUUUUCNY"
assert len(ACCENTED) == len(PLAIN)


WORKER_ORGANIZATION = (
    "organization_id = "
    "NULLIF(current_setting('app.organization_id', true), '')::uuid"
)


def upgrade() -> None:
    op.execute(f"""
        CREATE EXTENSION IF NOT EXISTS vector;

        -- Lower case without accents, for search on both sides (stored
        -- passages and the query). Built on translate(), which is
        -- immutable, so it can feed a generated column; no extension.
        CREATE FUNCTION public.eka_search_text(value text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        PARALLEL SAFE
        STRICT
        AS $function$
            SELECT lower(translate(value, '{ACCENTED}', '{PLAIN}'))
        $function$;

        GRANT EXECUTE ON FUNCTION public.eka_search_text(text)
            TO eka_runtime, eka_worker;
    """)

    op.execute("""
        CREATE TABLE public.document_chunks (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL
                REFERENCES public.organizations (id),
            document_id uuid NOT NULL REFERENCES public.documents (id),
            version_id uuid NOT NULL REFERENCES public.document_versions (id),
            ordinal integer NOT NULL,
            heading text,
            content text NOT NULL,
            start_char integer NOT NULL,
            end_char integer NOT NULL,
            token_estimate integer NOT NULL,
            created_at timestamptz NOT NULL,
            content_tsv tsvector GENERATED ALWAYS AS (
                to_tsvector(
                    'simple'::regconfig,
                    public.eka_search_text(
                        COALESCE(heading, '') || ' ' || content
                    )
                )
            ) STORED,
            CONSTRAINT uq_document_chunks_version_ordinal
                UNIQUE (version_id, ordinal),
            CONSTRAINT ck_document_chunks_ordinal CHECK (ordinal >= 0),
            CONSTRAINT ck_document_chunks_span
                CHECK (start_char >= 0 AND end_char > start_char),
            CONSTRAINT ck_document_chunks_content
                CHECK (length(content) > 0 AND length(content) <= 8000),
            CONSTRAINT ck_document_chunks_tokens CHECK (token_estimate > 0)
        );

        CREATE INDEX ix_document_chunks_document_id
            ON public.document_chunks (document_id);
        CREATE INDEX ix_document_chunks_organization_id
            ON public.document_chunks (organization_id);
        CREATE INDEX ix_document_chunks_content_tsv
            ON public.document_chunks USING gin (content_tsv);

        ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.document_chunks FORCE ROW LEVEL SECURITY;

        GRANT SELECT ON public.document_chunks TO eka_runtime;
        GRANT SELECT, INSERT, DELETE ON public.document_chunks TO eka_worker;
    """)

    op.execute(f"""
        -- A person reads a chunk exactly when they can read its document.
        CREATE POLICY document_chunks_select_policy
        ON public.document_chunks
        FOR SELECT
        TO eka_runtime
        USING (
            EXISTS (
                SELECT 1
                FROM public.documents AS d
                WHERE d.id = document_chunks.document_id
            )
        );

        CREATE POLICY document_chunks_worker_select_policy
        ON public.document_chunks
        FOR SELECT
        TO eka_worker
        USING ({WORKER_ORGANIZATION});

        CREATE POLICY document_chunks_worker_insert_policy
        ON public.document_chunks
        FOR INSERT
        TO eka_worker
        WITH CHECK (
            {WORKER_ORGANIZATION}
            AND EXISTS (
                SELECT 1
                FROM public.document_versions AS v
                WHERE v.id = version_id
                  AND v.document_id = document_chunks.document_id
                  AND v.organization_id = document_chunks.organization_id
            )
        );

        CREATE POLICY document_chunks_worker_delete_policy
        ON public.document_chunks
        FOR DELETE
        TO eka_worker
        USING ({WORKER_ORGANIZATION});
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE public.document_chunks;
        DROP FUNCTION public.eka_search_text(text);
        DROP EXTENSION IF EXISTS vector;
    """)
