"""Клиенты внешних источников сведений о лекарственных средствах.

* RxNav / RxClass (Национальная медицинская библиотека США, https://rxnav.nlm.nih.gov):
  нормализация названия (rxcui), классы ATC, показания MED-RT (may_treat, имена MeSH),
  члены класса ATC и лекарства, которые «may_treat» заболевание.
* openFDA (Управление по санитарному надзору за качеством пищевых продуктов и медикаментов США,
  https://open.fda.gov): FAERS drug/event — нежелательные реакции нормализованными терминами MedDRA
  с числом сообщений; drug/label — торговые названия и фармакологический класс (EPC).

Все ответы — JSON. Каждый ответ кэшируется на диске (ключ — URL), поэтому повторный запрос
идёт без сети. Если сеть недоступна, используется резервный снимок ответов (data/offline_snapshot.json).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import urllib.parse
from typing import Any

import requests

from .config import CONFIG

logger = logging.getLogger(__name__)

RXNAV = "https://rxnav.nlm.nih.gov/REST"
OPENFDA = "https://api.fda.gov/drug"

# Термины FAERS, которые описывают не реакцию организма, а обстоятельства применения.
NON_CLINICAL_TERMS = {
    "DRUG INEFFECTIVE", "OFF LABEL USE", "PRODUCT USE IN UNAPPROVED INDICATION", "DRUG INTERACTION",
    "INAPPROPRIATE SCHEDULE OF PRODUCT ADMINISTRATION", "PRODUCT DOSE OMISSION ISSUE", "DEATH",
    "INTENTIONAL OVERDOSE", "OVERDOSE", "TOXICITY TO VARIOUS AGENTS", "COMPLETED SUICIDE",
    "PRODUCT USE ISSUE", "WRONG TECHNIQUE IN PRODUCT USAGE PROCESS", "DRUG ABUSE", "NO ADVERSE EVENT",
    "CONDITION AGGRAVATED", "DRUG HYPERSENSITIVITY", "MALAISE", "INTENTIONAL PRODUCT MISUSE",
    "EXPOSURE DURING PREGNANCY", "MATERNAL EXPOSURE DURING PREGNANCY", "INCORRECT DOSE ADMINISTERED",
    "PRODUCT QUALITY ISSUE", "ADVERSE DRUG REACTION", "ADVERSE EVENT", "DRUG DEPENDENCE",
    "THERAPEUTIC RESPONSE DECREASED", "TREATMENT FAILURE", "DISEASE PROGRESSION", "HOSPITALISATION",
    "INTENTIONAL PRODUCT USE ISSUE", "PRODUCT PRESCRIBING ERROR", "ACCIDENTAL OVERDOSE",
    "DRUG WITHDRAWAL SYNDROME", "PREMATURE BABY", "FOETAL EXPOSURE DURING PREGNANCY", "SUICIDE ATTEMPT",
}


class SourceError(Exception):
    """Источник недоступен и в кэше нет ответа."""


class JsonHttp:
    """GET-запросы с дисковым кэшем и резервным снимком."""

    def __init__(self) -> None:
        self.cache_dir = CONFIG.cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self.session = requests.Session()
        self._lock = threading.Lock()
        self.stats = {"network": 0, "cache": 0, "snapshot": 0, "failed": 0}
        self.snapshot: dict[str, Any] = {}
        if os.path.exists(CONFIG.snapshot_path):
            with open(CONFIG.snapshot_path, encoding="utf-8") as f:
                self.snapshot = json.load(f)

    def _path(self, url: str) -> str:
        return os.path.join(self.cache_dir, hashlib.sha1(url.encode()).hexdigest() + ".json")

    def _count(self, key: str) -> None:
        with self._lock:
            self.stats[key] += 1

    def get(self, url: str) -> Any:
        path = self._path(url)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cached = json.load(f)
            self._count("cache")
            return cached["data"] if isinstance(cached, dict) and "url" in cached else cached
        if not CONFIG.offline:
            try:
                r = self.session.get(url, timeout=CONFIG.request_timeout)
                if r.status_code == 404:          # openFDA отвечает 404, если ничего не найдено
                    data: Any = None
                else:
                    r.raise_for_status()
                    data = r.json()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"url": url, "data": data}, f, ensure_ascii=False)
                self._count("network")
                return data
            except (requests.RequestException, ValueError) as e:
                logger.warning("Источник не ответил: %s (%s)", url, e)
        if url in self.snapshot:
            self._count("snapshot")
            return self.snapshot[url]
        self._count("failed")
        raise SourceError(url)


def q(value: str) -> str:
    return urllib.parse.quote(value, safe="")


class RxNavClient:
    def __init__(self, http: JsonHttp) -> None:
        self.http = http

    def rxcui(self, name: str) -> str | None:
        data = self.http.get(f"{RXNAV}/rxcui.json?name={q(name)}&search=2") or {}
        ids = data.get("idGroup", {}).get("rxnormId") or []
        return ids[0] if ids else None

    def _classes(self, rxcui: str, source: str, relas: str = "") -> list[dict]:
        url = f"{RXNAV}/rxclass/class/byRxcui.json?rxcui={rxcui}&relaSource={source}"
        if relas:
            url += f"&relas={relas}"
        data = self.http.get(url) or {}
        return data.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", []) or []

    def atc_codes(self, rxcui: str) -> list[tuple[str, str]]:
        """Классы ATC 4-го уровня: [(код, английское название)]."""
        out = {}
        for item in self._classes(rxcui, "ATC"):
            c = item["rxclassMinConceptItem"]
            out[c["classId"]] = c["className"]
        return sorted(out.items())

    def may_treat(self, rxcui: str) -> list[str]:
        """Показания MED-RT: имена рубрик MeSH (заболевания и симптомы)."""
        names = {item["rxclassMinConceptItem"]["className"] for item in self._classes(rxcui, "MEDRT", "may_treat")}
        return sorted(names)

    def atc_members(self, code: str) -> list[str]:
        data = self.http.get(f"{RXNAV}/rxclass/classMembers.json?classId={q(code)}&relaSource=ATC&ttys=IN") or {}
        members = data.get("drugMemberGroup", {}).get("drugMember", []) or []
        return [m["minConcept"]["name"] for m in members]

    def mesh_class_id(self, mesh_name: str) -> str | None:
        data = self.http.get(f"{RXNAV}/rxclass/class/byName.json?className={q(mesh_name)}&classTypes=DISEASE") or {}
        items = data.get("rxclassMinConceptList", {}).get("rxclassMinConcept", []) or []
        return items[0]["classId"] if items else None

    def drugs_for_disease(self, mesh_name: str) -> list[str]:
        """Лекарства, которые по MED-RT «may_treat» заболевание (включая подрубрики MeSH)."""
        class_id = self.mesh_class_id(mesh_name)
        if not class_id:
            return []
        data = self.http.get(f"{RXNAV}/rxclass/classMembers.json?classId={class_id}&relaSource=MEDRT"
                             f"&rela=may_treat&ttys=IN&trans=1") or {}
        members = data.get("drugMemberGroup", {}).get("drugMember", []) or []
        return [m["minConcept"]["name"] for m in members]


class OpenFdaClient:
    def __init__(self, http: JsonHttp) -> None:
        self.http = http

    def reactions(self, generic_name: str, limit: int = 30) -> list[tuple[str, int]]:
        """Нежелательные реакции из FAERS: [(термин MedDRA, число сообщений)] по убыванию."""
        url = (f"{OPENFDA}/event.json?search=patient.drug.openfda.generic_name:%22{q(generic_name)}%22"
               f"&count=patient.reaction.reactionmeddrapt.exact&limit={limit}")
        data = self.http.get(url) or {}
        return [(r["term"], r["count"]) for r in data.get("results", []) if r["term"] not in NON_CLINICAL_TERMS]

    def label_summary(self, generic_name: str) -> dict:
        """Торговые названия и фармакологические классы EPC из инструкций (drug/label)."""
        url = f"{OPENFDA}/label.json?search=openfda.generic_name:%22{q(generic_name)}%22&limit=20"
        data = self.http.get(url) or {}
        brands: dict[str, int] = {}
        epc: set[str] = set()
        name = generic_name.lower()
        for res in data.get("results", []):
            fda = res.get("openfda", {})
            generics = [g.lower() for g in fda.get("generic_name", [])]
            # только однокомпонентные препараты: у комбинаций чужие классы и торговые названия
            if len(generics) != 1 or name not in generics[0] or any(x in generics[0] for x in (" and ", ",", "/")):
                continue
            for b in fda.get("brand_name", []):
                b = b.strip()
                if b and name not in b.lower() and len(b) <= 30:
                    brands[b.title()] = brands.get(b.title(), 0) + 1
            epc.update(fda.get("pharm_class_epc", []))
        top = [b for b, _ in sorted(brands.items(), key=lambda x: -x[1])[:3]]
        return {"brands": top, "epc": sorted(epc)}
