"""Клиент внешнего источника — Wikidata (https://www.wikidata.org), точка доступа SPARQL.

Wikidata — база знаний в модели RDF: утверждения «объект — свойство — значение». Модуль отправляет
SPARQL-запросы и получает результаты в формате SPARQL JSON. Все запросы делаются пачкой сразу на все
объекты. Каждый ответ кэшируется на диске (ключ — текст запроса); если источник недоступен, используется
резервный снимок ответов (data/offline_snapshot.json).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from typing import Any

import requests

from .config import CONFIG

logger = logging.getLogger(__name__)


class SourceError(Exception):
    """Источник недоступен и в кэше нет ответа."""


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


class Wikidata:
    def __init__(self) -> None:
        os.makedirs(CONFIG.cache_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": CONFIG.user_agent, "Accept": "application/sparql-results+json"})
        self._lock = threading.Lock()
        self.stats = {"network": 0, "cache": 0, "snapshot": 0, "failed": 0}
        self.snapshot: dict[str, Any] = {}
        if os.path.exists(CONFIG.snapshot_path):
            with open(CONFIG.snapshot_path, encoding="utf-8") as f:
                self.snapshot = json.load(f)

    def _count(self, key: str) -> None:
        with self._lock:
            self.stats[key] += 1

    def select(self, sparql: str, timeout: float | None = None) -> list[dict]:
        """SPARQL SELECT → список строк {переменная: значение}."""
        sparql = " ".join(sparql.split())
        path = os.path.join(CONFIG.cache_dir, hashlib.sha1(sparql.encode()).hexdigest() + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self._count("cache")
                return json.load(f)["rows"]
        if not CONFIG.offline:
            try:
                r = self.session.get(CONFIG.endpoint, params={"query": sparql, "format": "json"},
                                     timeout=timeout or CONFIG.request_timeout)
                r.raise_for_status()
                rows = [{k: v["value"] for k, v in b.items()} for b in r.json()["results"]["bindings"]]
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"query": sparql, "rows": rows}, f, ensure_ascii=False)
                self._count("network")
                return rows
            except (requests.RequestException, ValueError, KeyError) as e:
                logger.warning("Wikidata не ответила: %s", e)
        if sparql in self.snapshot:
            self._count("snapshot")
            return self.snapshot[sparql]
        self._count("failed")
        raise SourceError(sparql[:120])

    # ------------------------------------------------------------------ запросы модуля
    @staticmethod
    def _values(qids: list[str]) -> str:
        return " ".join(f"wd:{q}" for q in qids)

    def labels(self, qids: list[str]) -> list[dict]:
        """Русское и английское название, описание, число статей в Википедиях (мера известности)."""
        return self.select(f"""SELECT ?item ?ru ?en ?descr ?sl WHERE {{ VALUES ?item {{ {self._values(qids)} }}
            OPTIONAL {{ ?item rdfs:label ?ru FILTER(lang(?ru) = "ru") }}
            OPTIONAL {{ ?item rdfs:label ?en FILTER(lang(?en) = "en") }}
            OPTIONAL {{ ?item schema:description ?descr FILTER(lang(?descr) = "ru") }}
            OPTIONAL {{ ?item wikibase:sitelinks ?sl }} }}""")

    def links(self, qids: list[str], props: list[str]) -> list[dict]:
        """Значения-объекты и строки (истинные утверждения wdt:) с русскими названиями значений."""
        return self.select(f"""SELECT ?item ?prop ?val ?valLabel WHERE {{ VALUES ?item {{ {self._values(qids)} }}
            VALUES ?prop {{ {" ".join("wdt:" + p for p in props)} }} ?item ?prop ?val .
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ru,en". }} }}""")

    def quantities(self, qids: list[str], props: list[str]) -> list[dict]:
        """Величины в нормализованных единицах СИ (кг, м, с) — лучшего ранга."""
        # вся цепочка — внутри каждой ветки UNION, иначе оптимизатор начинает с общей части и перебирает
        # все величины Wikidata (запрос не укладывается в минуту)
        parts = " UNION ".join(
            f'{{ ?item p:{p} ?st . ?st psn:{p} ?n . ?n wikibase:quantityAmount ?amount . ?st wikibase:rank ?rank . '
            f'BIND("{p}" AS ?prop) }}' for p in props)
        return self.select(f"""SELECT ?item ?prop ?amount WHERE {{ VALUES ?item {{ {self._values(qids)} }}
            {parts} FILTER(?rank != wikibase:DeprecatedRank) }}""")

    def times(self, qids: list[str], props: list[str]) -> list[dict]:
        """Даты с точностью (11 — день, 10 — месяц, 9 — год)."""
        parts = " UNION ".join(
            f'{{ ?item p:{p} ?st . ?st psv:{p} ?tv . ?tv wikibase:timeValue ?time ; wikibase:timePrecision ?prec . '
            f'BIND("{p}" AS ?prop) }}' for p in props)
        return self.select(f"""SELECT ?item ?prop ?time ?prec WHERE {{ VALUES ?item {{ {self._values(qids)} }}
            {parts} }}""")

    def types(self, qids: list[str], classes: list[str]) -> list[dict]:
        """К каким из сопоставленных классов Wikidata относится объект (экземпляр подкласса … подкласса)."""
        return self.select(f"""SELECT ?item ?cls WHERE {{ VALUES ?item {{ {self._values(qids)} }}
            VALUES ?cls {{ {self._values(classes)} }} ?item wdt:P31/wdt:P279* ?cls . }}""")

    def children(self, parent: str, limit: int) -> list[str]:
        """Естественные спутники тела, по известности."""
        rows = self.select(f"""SELECT DISTINCT ?c ?sl WHERE {{ ?c wdt:P397 wd:{parent} ;
            wdt:P31/wdt:P279* wd:Q2537 ; wikibase:sitelinks ?sl . ?c rdfs:label ?l FILTER(lang(?l) = "ru") }}
            ORDER BY DESC(?sl) LIMIT {limit}""")
        return [qid(r["c"]) for r in rows]

    def members(self, cls: str, limit: int, pattern: str = "") -> list[str]:
        """Самые известные объекты класса Wikidata (с русским названием)."""
        where = pattern or f"?x wdt:P31/wdt:P279* wd:{cls} ."
        rows = self.select(f"""SELECT DISTINCT ?x ?sl WHERE {{ {where} ?x wikibase:sitelinks ?sl .
            FILTER(?sl >= {CONFIG.min_sitelinks}) ?x rdfs:label ?l FILTER(lang(?l) = "ru") }}
            ORDER BY DESC(?sl) LIMIT {limit}""", timeout=12)
        return [qid(r["x"]) for r in rows]

    def find_by_label(self, ru: str, en: str = "") -> str | None:
        """Объект по точному названию (для элементов базы знаний без идентификатора Wikidata)."""
        names = " ".join(f'"{n}"@{lang}' for n, lang in ((ru, "ru"), (en, "en")) if n)
        rows = self.select(f"""SELECT ?x ?sl WHERE {{ VALUES ?n {{ {names} }} ?x rdfs:label ?n ;
            wikibase:sitelinks ?sl . }} ORDER BY DESC(?sl) LIMIT 1""")
        return qid(rows[0]["x"]) if rows else None
