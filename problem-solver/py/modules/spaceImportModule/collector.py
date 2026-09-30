"""Сбор сведений о космических объектах из Wikidata и их нормализация (процедурная часть модуля).

Результат — SpaceRecord: русское название, класс по типу Wikidata, значения отношений в формате базы
знаний. Объекты без русского названия отбрасываются (в базе знаний «Космос» все имена русские).
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import time
from dataclasses import dataclass, field

from . import mapping as M
from .config import CONFIG
from .sources import SourceError, Wikidata, qid

logger = logging.getLogger(__name__)


@dataclass
class Target:
    """Объект — значение связи (родительское тело, созвездие, оператор, экипаж…)."""
    qid: str
    ru: str
    default_class: str | None
    wd_class: M.WdClass | None = None


@dataclass
class SpaceRecord:
    qid: str
    ru: str = ""
    en: str = ""
    descr: str = ""
    sitelinks: int = 0
    wd_class: M.WdClass | None = None
    nodes: dict[str, list[Target]] = field(default_factory=dict)     # отношение → объекты
    texts: dict[str, list[str]] = field(default_factory=dict)        # отношение → тексты
    parent: str = ""                                                   # для спутников, добавленных к планете

    @property
    def facts(self) -> int:
        return sum(len(v) for v in self.nodes.values()) + sum(len(v) for v in self.texts.values())


class Collector:
    def __init__(self) -> None:
        self.wd = Wikidata()

    def _batch(self, qids: list[str]) -> dict[str, SpaceRecord]:
        recs = {q: SpaceRecord(q) for q in qids}
        with cf.ThreadPoolExecutor(max_workers=4) as pool:
            f_lab = pool.submit(self.wd.labels, qids)
            f_links = pool.submit(self.wd.links, qids, list(M.NODE_PROPS) + list(M.LABEL_PROPS))
            f_qty = pool.submit(self.wd.quantities, qids, list(M.QUANTITY_PROPS))
            f_time = pool.submit(self.wd.times, qids, list(M.TIME_PROPS))
            labels, links, qty, times = f_lab.result(), f_links.result(), f_qty.result(), f_time.result()
        for r in labels:
            rec = recs[qid(r["item"])]
            rec.ru = rec.ru or r.get("ru", "")
            rec.en = rec.en or r.get("en", "")
            rec.descr = rec.descr or r.get("descr", "")
            rec.sitelinks = max(rec.sitelinks, int(r.get("sl", 0) or 0))
        targets: dict[str, Target] = {}
        for r in links:
            rec, prop = recs[qid(r["item"])], qid(r["prop"])
            label = r.get("valLabel", "")
            if not label or label.startswith("Q") and label[1:].isdigit():
                continue                                   # у значения нет ни русского, ни английского названия
            if prop in M.LABEL_PROPS:
                rel = M.LABEL_PROPS[prop]
                if label not in rec.texts.setdefault(rel, []):
                    rec.texts[rel].append(label)
            else:
                rel, default = M.NODE_PROPS[prop]
                t = targets.setdefault(qid(r["val"]), Target(qid(r["val"]), label, default))
                if all(x.qid != t.qid for x in rec.nodes.setdefault(rel, [])):
                    rec.nodes[rel].append(t)
        seen: set[tuple[str, str]] = set()
        for r in qty:
            key = (qid(r["item"]), r["prop"])
            if key in seen:
                continue                                   # первое значение лучшего ранга
            seen.add(key)
            rel = M.QUANTITY_PROPS[r["prop"]]
            try:
                if float(r["amount"]) > 0:
                    recs[key[0]].texts[rel] = [M.FORMAT[rel](float(r["amount"]))]
            except (ValueError, OverflowError):
                pass                                       # величина в неожиданном формате не погружается
        best: dict[tuple[str, str], tuple[int, str]] = {}
        for r in times:
            key = (qid(r["item"]), r["prop"])
            prec = int(r["prec"])
            if key not in best or prec > best[key][0]:
                best[key] = (prec, r["time"])
        for (item, prop), (prec, t) in best.items():
            if (value := M.date(t, prec)):
                recs[item].texts[M.TIME_PROPS[prop]] = [value]
        # классы объектов и значений-объектов — одним запросом
        all_qids = list(recs) + [t for t in targets if t not in recs]
        found: dict[str, set[str]] = {}
        for r in self.wd.types(all_qids, [c.qid for c in M.CLASSES]):
            found.setdefault(qid(r["item"]), set()).add(qid(r["cls"]))
        pick = lambda q: next((c for c in M.CLASSES if c.qid in found.get(q, ())), None)
        for rec in recs.values():
            rec.wd_class = pick(rec.qid)
        for t in targets.values():
            t.wd_class = pick(t.qid)
        return recs

    def collect(self, qids: list[str], with_children: bool = False, budget: float | None = None) -> list[SpaceRecord]:
        """Сведения об объектах (одна пачка запросов); для планет — и об их естественных спутниках."""
        deadline = time.monotonic() + (CONFIG.time_budget if budget is None else budget)
        qids = list(dict.fromkeys(qids))
        if not qids:
            return []
        try:
            recs = self._batch(qids)
        except SourceError as e:
            logger.warning("Источник недоступен: %s", e)
            return []
        out = [r for q in qids if (r := recs[q]).ru]
        if with_children and time.monotonic() < deadline:
            kids: dict[str, str] = {}
            for rec in out:
                if rec.wd_class and rec.wd_class.kb_class in ("concept_gas_giant", "concept_terrestrial_planet",
                                                              "concept_planet", "concept_dwarf_planet"):
                    try:
                        for c in self.wd.children(rec.qid, CONFIG.children):
                            kids.setdefault(c, rec.qid)
                    except SourceError:
                        pass
            kids = {c: p for c, p in kids.items() if c not in recs}
            if kids and time.monotonic() < deadline:
                try:
                    child_recs = self._batch(list(kids))
                    for c, p in kids.items():
                        if child_recs[c].ru:
                            child_recs[c].parent = p
                            out.append(child_recs[c])
                except SourceError as e:
                    logger.warning("Спутники не загружены: %s", e)
        return out
