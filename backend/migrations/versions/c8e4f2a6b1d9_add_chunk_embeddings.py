"""Vectors of passages, for search by meaning (Phase 6, RAG Core).

Revision ID: c8e4f2a6b1d9
Revises: b5d9e2a7c4f1

One row per passage and model: vectors of different models are never
compared, so changing model means adding rows, not rewriting them. The
vector column has no fixed size for the same reason; each model gets its
own partial HNSW index at its size (this migration: the default model,
intfloat/multilingual-e5-small, 384 dimensions, cosine distance).

Readers of a vector are the readers of its passage, which are the readers
of its document: the policy asks document_chunks, whose policy asks
documents. Only the worker writes vectors; the worker may now queue one
kind of job itself, "document.embed", for its own organization.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c8e4f2a6b1d9"
down_revision: Union[str, Sequence[str], None] = "b5d9e2a7c4f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


WORKER_ORGANIZATION = (
    "organization_id = "
    "NULLIF(current_setting('app.organization_id', true), '')::uuid"
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE public.chunk_embeddings (
            chunk_id uuid NOT NULL
                REFERENCES public.document_chunks (id) ON DELETE CASCADE,
            model text NOT NULL,
            organization_id uuid NOT NULL
                REFERENCES public.organizations (id),
            document_id uuid NOT NULL REFERENCES public.documents (id),
            dims integer NOT NULL,
            embedding vector NOT NULL,
            created_at timestamptz NOT NULL,
            CONSTRAINT pk_chunk_embeddings PRIMARY KEY (chunk_id, model),
            CONSTRAINT ck_chunk_embeddings_model
                CHECK (length(model) BETWEEN 1 AND 200),
            CONSTRAINT ck_chunk_embeddings_dims
                CHECK (dims BETWEEN 1 AND 4096 AND vector_dims(embedding) = dims)
        );

        CREATE INDEX ix_chunk_embeddings_document_id
            ON public.chunk_embeddings (document_id);

        -- Approximate nearest neighbours for the default model.
        CREATE INDEX ix_chunk_embeddings_e5_small_hnsw
            ON public.chunk_embeddings
            USING hnsw ((embedding::vector(384)) vector_cosine_ops)
            WHERE model = 'intfloat/multilingual-e5-small';

        ALTER TABLE public.chunk_embeddings ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.chunk_embeddings FORCE ROW LEVEL SECURITY;

        GRANT SELECT ON public.chunk_embeddings TO eka_runtime;
        GRANT SELECT, INSERT, DELETE ON public.chunk_embeddings TO eka_worker;
        GRANT INSERT ON public.background_jobs TO eka_worker;
    """)

    op.execute(f"""
        CREATE POLICY chunk_embeddings_select_policy
        ON public.chunk_embeddings
        FOR SELECT
        TO eka_runtime
        USING (
            EXISTS (
                SELECT 1
                FROM public.document_chunks AS c
                WHERE c.id = chunk_embeddings.chunk_id
            )
        );

        CREATE POLICY chunk_embeddings_worker_select_policy
        ON public.chunk_embeddings
        FOR SELECT
        TO eka_worker
        USING ({WORKER_ORGANIZATION});

        CREATE POLICY chunk_embeddings_worker_insert_policy
        ON public.chunk_embeddings
        FOR INSERT
        TO eka_worker
        WITH CHECK (
            {WORKER_ORGANIZATION}
            AND EXISTS (
                SELECT 1
                FROM public.document_chunks AS c
                WHERE c.id = chunk_id
                  AND c.document_id = chunk_embeddings.document_id
                  AND c.organization_id = chunk_embeddings.organization_id
            )
        );

        CREATE POLICY chunk_embeddings_worker_delete_policy
        ON public.chunk_embeddings
        FOR DELETE
        TO eka_worker
        USING ({WORKER_ORGANIZATION});

        -- The worker queues the vectors of a version it just synchronized;
        -- nothing else, and only for the organization it works for.
        CREATE POLICY background_jobs_worker_embed_insert_policy
        ON public.background_jobs
        FOR INSERT
        TO eka_worker
        WITH CHECK (
            {WORKER_ORGANIZATION}
            AND kind = 'document.embed'
            AND status = 'queued'
            AND attempts = 0
            AND locked_by IS NULL
            AND locked_at IS NULL
            AND finished_at IS NULL
            AND last_error IS NULL
            AND created_by_user_id IS NULL
        );
    """)


def downgrade() -> None:
    op.execute("""
        DROP POLICY background_jobs_worker_embed_insert_policy
            ON public.background_jobs;
        REVOKE INSERT ON public.background_jobs FROM eka_worker;
        DROP TABLE public.chunk_embeddings;
    """)
