"""Search index for the e5-base embedding model (Phase 6, AJ-2b).

Revision ID: d2f7a3c9e5b1
Revises: c8e4f2a6b1d9

AJ-2a measured larger models of the multilingual e5 family on the large
evaluation library; intfloat/multilingual-e5-base passed the rule (Portuguese
questions on English documents 0.25 to 0.42 in hybrid search, 0.58 with the
reranker; no group lost; codes 1.00; leaks 0; about 100 ms) and becomes the
default model. Its vectors (768 numbers) get their own partial HNSW index,
next to the index of e5-small, whose vectors stay until they are no longer
needed: vectors of different models are never mixed.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d2f7a3c9e5b1"
down_revision: Union[str, Sequence[str], None] = "c8e4f2a6b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX ix_chunk_embeddings_e5_base_hnsw
            ON public.chunk_embeddings
            USING hnsw ((embedding::vector(768)) vector_cosine_ops)
            WHERE model = 'intfloat/multilingual-e5-base';
    """)


def downgrade() -> None:
    op.execute("DROP INDEX public.ix_chunk_embeddings_e5_base_hnsw;")
