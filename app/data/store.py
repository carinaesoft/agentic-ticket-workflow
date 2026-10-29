"""In-memory store over the reference data files.

The files are read once at construction; every lookup afterwards is a pure in-memory read,
so the store is safe to use from async activities.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.domain.models import Customer, Invoice, KbArticle

DATA_DIR = Path(__file__).parent

_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class DataStore:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self._customers = {
            c.customer_id: c
            for c in (Customer.model_validate(r) for r in _load(data_dir / "customers.json"))
        }
        self._invoices = [Invoice.model_validate(r) for r in _load(data_dir / "invoices.json")]
        self._articles = [KbArticle.model_validate(r) for r in _load(data_dir / "kb.json")]
        self.allowed_values: dict[str, list[str]] = _load(data_dir / "allowed_values.json")

    def get_customer(self, customer_id: str) -> Customer | None:
        return self._customers.get(customer_id)

    def invoices_for(self, customer_id: str) -> list[Invoice]:
        return [i for i in self._invoices if i.customer_id == customer_id]

    def search_kb(self, query: str, limit: int = 3) -> list[KbArticle]:
        """Articles ranked by how many query words they contain (title + text)."""
        wanted = _words(query)
        scored = []
        for article in self._articles:
            score = len(wanted & _words(f"{article.title} {article.text}"))
            if score:
                scored.append((-score, article.article_id, article))
        scored.sort(key=lambda item: (item[0], item[1]))
        return [article for _, _, article in scored[:limit]]

    def kb_ids(self) -> list[str]:
        return [a.article_id for a in self._articles]


def _load(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)
