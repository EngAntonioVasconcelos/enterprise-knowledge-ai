"""Download the reranking model once and see what it does.

Downloads BAAI/bge-reranker-v2-m3 in its INT8 ONNX form (about 570 MB)
into EMBEDDING_CACHE_DIR (default backend/var/models, ignored by Git),
then asks it to order a few passages for a Portuguese question whose
answer is written in English, and shows how long it takes on this CPU.

Run from the backend folder (needs internet the first time):
    python -m scripts.try_reranker
"""

import sys
import time
from pathlib import Path

from app.core.config import settings
from app.services.reranking import RERANK_CANDIDATES, FastEmbedReranker


QUERY = "quem pode conduzir empilhadores?"
PASSAGES = [
    "Only staff with a valid forklift licence may operate forklifts.",
    "Cada camiao faz uma revisao completa a cada 40 000 quilometros.",
    "High-visibility vests and safety boots are mandatory in all loading areas.",
    "When an employee uses a private car for work, mileage is paid at 0.40 euros.",
]


def main() -> int:
    cache_dir = Path(settings.EMBEDDING_CACHE_DIR).resolve()
    print(f"Model cache: {cache_dir}")
    started = time.perf_counter()
    model = FastEmbedReranker(str(cache_dir), allow_download=True)
    print(f"Model ready in {time.perf_counter() - started:.1f} s ({model.model})")

    started = time.perf_counter()
    scores = model.score(QUERY, PASSAGES)
    print(f"Scored {len(PASSAGES)} passages in {time.perf_counter() - started:.2f} s")
    print(f'\nQuestion: "{QUERY}" (higher is a better answer)')
    for score, passage in sorted(zip(scores, PASSAGES), reverse=True):
        print(f"  {score:7.3f}  {passage}")

    # A realistic load: the reranker reads the first RERANK_CANDIDATES
    # passages of about 1200 characters each.
    long_passages = [(p + " ") * 15 for p in PASSAGES] * (RERANK_CANDIDATES // len(PASSAGES))
    started = time.perf_counter()
    model.score(QUERY, long_passages)
    print(
        f"\n{len(long_passages)} passages of about 1200 characters: "
        f"{time.perf_counter() - started:.2f} s on this computer"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
