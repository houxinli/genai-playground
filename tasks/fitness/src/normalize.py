"""Exercise-name normalization driven by an editable glossary.

The same lift shows up under many spellings (`chin assist` / `assisted chin up` /
`辅助引体` / `chin up assist`). The glossary at `config/exercises.json` maps every
known alias to a canonical slug plus its weight semantics so progression can be
computed correctly. Unknown names fall through to a slug and are flagged so they
can be folded into the glossary later.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .model import WEIGHT_LOADED

DEFAULT_GLOSSARY = Path(__file__).resolve().parent.parent / "config" / "exercises.json"


def _slug(raw: str) -> str:
    return re.sub(r"\s+", "_", raw.strip().lower())


class Normalizer:
    def __init__(self, glossary_path: Optional[Path] = None):
        path = glossary_path or DEFAULT_GLOSSARY
        self.aliases: dict[str, str] = {}
        self.exercises: dict[str, dict] = {}
        self.unmapped: set[str] = set()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.exercises = data.get("exercises", {})
            for alias, canon in data.get("aliases", {}).items():
                self.aliases[self._key(alias)] = canon

    @staticmethod
    def _key(name: str) -> str:
        return re.sub(r"\s+", " ", name.strip().lower())

    def __call__(self, raw: str) -> tuple[str, str]:
        canon = self.aliases.get(self._key(raw))
        if canon is None:
            self.unmapped.add(raw)
            return _slug(raw), WEIGHT_LOADED
        meta = self.exercises.get(canon, {})
        return canon, meta.get("weight_type", WEIGHT_LOADED)

    def display_name(self, canonical: str) -> str:
        return self.exercises.get(canonical, {}).get("name", canonical)

    def muscle(self, canonical: str) -> str:
        return self.exercises.get(canonical, {}).get("muscle", "")
