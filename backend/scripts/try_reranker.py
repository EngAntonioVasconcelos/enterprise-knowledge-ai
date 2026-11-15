"""Download the reranking model once and see what it does.

Downloads BAAI/bge-reranker-v2-m3 in its INT8 ONNX form (about 570 MB)
into EMBEDDING_CACHE_DIR (default backend/var/models, ignored by Git),
then asks it to order a few passages for a Portuguese question whose
answer is written in English, and times 20 or 10 passages, whole or cut
to 600 characters, on this CPU.

Run from the backend folder (needs internet the first time):
    python -m scripts.try_reranker
"""

import sys
import time
from pathlib import Path

from app.core.config import settings
from app.services.reranking import FastEmbedReranker


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

    # Realistic loads: passages of about 1200 characters, read whole or cut
    # to their first 600 (RERANK_MAX_CHARS), 20 or 10 of them
    # (RERANK_CANDIDATES).
    print("\nTime on this computer for realistic loads:")
    for count in (20, 10):
        for chars in (1200, 600):
            passages = [((p + " ") * 15)[:chars] for p in PASSAGES] * (count // len(PASSAGES) + 1)
            started = time.perf_counter()
            model.score(QUERY, passages[:count])
            print(f"  {count} passages of {chars} characters: {time.perf_counter() - started:.2f} s")
    print(
        f"Settings now: RERANK_CANDIDATES={settings.RERANK_CANDIDATES}, "
        f"RERANK_MAX_CHARS={settings.RERANK_MAX_CHARS}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
