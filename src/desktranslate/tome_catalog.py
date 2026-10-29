from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from desktranslate.tome import normalize_ocr_text


@dataclass(frozen=True)
class CatalogTask:
    english_name: str
    chinese_name: str
    description_template: str = ""
    role: str = "unknown"
    aliases: tuple[str, ...] = ()

    def description(self, target: int) -> str:
        return self.description_template.replace("{{target}}", str(target))


class TomeCatalog:
    def __init__(self, tasks: list[CatalogTask]) -> None:
        self.tasks = tasks

    @classmethod
    def load(cls, path: Path) -> "TomeCatalog":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls([
            CatalogTask(
                english_name=item["english_name"],
                chinese_name=item["chinese_name"],
                description_template=item.get("description_template", ""),
                role=item.get("role", "unknown"),
                aliases=tuple(item.get("aliases", [])),
            )
            for item in payload
        ])

    def match(self, observed: str, threshold: float = 0.55) -> CatalogTask | None:
        needle = _key(observed)
        best: tuple[float, CatalogTask] | None = None
        for task in self.tasks:
            for name in (task.chinese_name, task.english_name, *task.aliases):
                candidate = _key(name)
                if not needle or not candidate:
                    continue
                score = 1.0 if candidate in needle else SequenceMatcher(None, needle, candidate).ratio()
                if best is None or score > best[0]:
                    best = (score, task)
        return best[1] if best is not None and best[0] >= threshold else None


def _key(text: str) -> str:
    return "".join(ch for ch in normalize_ocr_text(text).casefold() if ch.isalnum())
