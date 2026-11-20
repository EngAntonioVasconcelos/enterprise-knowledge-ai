"""Download the embedding model once and see what it does.

Downloads intfloat/multilingual-e5-small (about 470 MB) into
EMBEDDING_CACHE_DIR (default backend/var/models, ignored by Git), then
compares a few sentences so you can see "meaning" as numbers: similar
meanings score close to 1, unrelated ones lower, across languages.

Run from the backend folder (needs internet the first time):
    python -m scripts.try_embeddings
Another model of the family (AJ-2), for example:
    python -m scripts.try_embeddings --model intfloat/multilingual-e5-base
"""

import argparse
import math
import sys
import time
from pathlib import Path

from app.core.config import settings
from app.services.embeddings import E5_MODEL, E5_MODELS, FastEmbedE5


QUERY = "quantos dias de ferias tenho por ano?"
PASSAGES = [
    "Cada colaborador tem direito a 25 dias uteis de descanso anual.",
    "Employees are entitled to 25 working days of paid vacation per year.",
    "O reembolso de despesas de viagem e feito em 30 dias.",
    "The office parking lot closes at 8 pm.",
]


def cosine(a, b) -> float:
    return sum(x * y for x, y in zip(a, b)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Download an embedding model and try it.")
    parser.add_argument("--model", choices=sorted(E5_MODELS), default=E5_MODEL)
    args = parser.parse_args()
    cache_dir = Path(settings.EMBEDDING_CACHE_DIR).resolve()
    print(f"Model cache: {cache_dir}")
    started = time.perf_counter()
    model = FastEmbedE5(str(cache_dir), model=args.model, allow_download=True)
    print(f"Model ready in {time.perf_counter() - started:.1f} s ({model.model}, {model.dims} numbers per text)")

    started = time.perf_counter()
    query = model.embed_query(QUERY)
    passages = model.embed_passages(PASSAGES)
    print(f"Embedded 5 texts in {time.perf_counter() - started:.2f} s")
    print(f"First numbers of the question's vector: {[round(v, 3) for v in query[:6]]} ...")
    print(f'\nQuestion: "{QUERY}"')
    for passage, vector in sorted(zip(PASSAGES, passages), key=lambda p: -cosine(query, p[1])):
        print(f"  {cosine(query, vector):.3f}  {passage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
