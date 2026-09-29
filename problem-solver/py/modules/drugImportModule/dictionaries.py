"""Словари сопоставления английских терминов источников с элементами базы знаний (data/*.tsv)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .config import CONFIG


@dataclass
class DrugName:
    rx_name: str               # имя RxNorm (английское МНН)
    ru: str                    # русское основное название
    synonyms: list[str] = field(default_factory=list)
    kb_id: str = ""            # системный идентификатор, если препарат уже есть в БЗ
    priority: int = 0          # порядок в словаре — чем меньше, тем распространённее
    fda_name: str = ""         # имя в openFDA, если отличается от RxNorm

    @property
    def openfda(self) -> str:
        return self.fda_name or self.rx_name

    @property
    def sys_id(self) -> str:
        return self.kb_id or re.sub(r"[^a-z0-9]+", "_", self.rx_name.lower()).strip("_")


@dataclass
class Term:
    source: str                # термин источника (MedDRA или MeSH)
    kind: str                  # symptom | disease
    ru: str
    sys_id: str
    cls: str


def _rows(name: str) -> list[list[str]]:
    with open(os.path.join(CONFIG.data_dir, name), encoding="utf-8") as f:
        return [line.rstrip("\n").split("\t") for line in f if line.strip() and not line.startswith("#")]


class Dictionaries:
    def __init__(self) -> None:
        self.drugs: dict[str, DrugName] = {}
        for i, r in enumerate(_rows("drugs_ru.tsv")):
            r += [""] * (5 - len(r))
            syn = [s.strip() for s in r[2].split(";") if s.strip()]
            self.drugs[r[0].lower()] = DrugName(r[0], r[1], syn, r[3], i, r[4])
        self.by_ru = {d.ru.lower(): d for d in self.drugs.values()}
        for d in self.drugs.values():
            for s in d.synonyms:
                self.by_ru.setdefault(s.lower(), d)
        self.reactions = {r[0]: Term(r[0], "symptom", r[1], r[2], r[3]) for r in _rows("reactions_ru.tsv")}
        self.indications = {r[0]: Term(r[0], r[1], r[2], r[3], r[4]) for r in _rows("indications_ru.tsv")}

    def drug(self, rx_name: str) -> DrugName | None:
        return self.drugs.get(rx_name.lower())

    def drug_by_ru(self, ru_name: str) -> DrugName | None:
        return self.by_ru.get(ru_name.lower())

    def ranked(self, names: list[str]) -> list[DrugName]:
        """Препараты из списка источника, для которых есть русское название, — по распространённости."""
        found = {d.rx_name: d for n in names if (d := self.drug(n))}
        return sorted(found.values(), key=lambda d: d.priority)


DICTS = Dictionaries()
