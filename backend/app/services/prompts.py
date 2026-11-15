"""Prompts as code (Phase 6, AJ-1).

Every prompt the product sends to a language model is a text file in
app/prompts, named <name>_<version>.txt, reviewed and tested like code. A
change of wording is a new version, measured with the answer evaluation
(scripts/evaluate_answers.py) before it becomes the default. Every answer
records the prompt id it was made with: name, version and the first
characters of the file's SHA-256, so an edited file can never pass as the
old one.

A file has two parts, "=== system ===" (the rules) and "=== user ===" (the
message, with {{placeholders}}).
"""

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SYSTEM_MARK = "=== system ==="
USER_MARK = "=== user ==="


@dataclass(frozen=True)
class Prompt:
    prompt_id: str
    system: str
    user_template: str

    def render(self, **values: str) -> str:
        text = self.user_template
        for key, value in values.items():
            text = text.replace("{{" + key + "}}", value)
        if "{{" in text:
            raise ValueError(f"prompt {self.prompt_id} has an unfilled placeholder")
        return text


@lru_cache(maxsize=None)
def load_prompt(name: str, version: str) -> Prompt:
    raw = (PROMPTS_DIR / f"{name}_{version}.txt").read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if not text.startswith(SYSTEM_MARK) or USER_MARK not in text:
        raise ValueError(f"prompt {name}_{version} must have a system and a user part")
    system, user = text[len(SYSTEM_MARK):].split(USER_MARK, 1)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return Prompt(f"{name}-{version}-{digest}", system.strip(), user.strip())
