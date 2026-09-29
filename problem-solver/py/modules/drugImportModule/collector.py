"""Сбор сведений о препаратах из внешних источников и их нормализация (процедурная часть модуля).

Результат — DrugRecord: только то, что удалось сопоставить со словарями базы знаний
(русские названия есть). Всё, что сопоставить не удалось, считается и попадает в отчёт.
"""
from __future__ import annotations

import concurrent.futures as cf
import copy
import logging
import time
from dataclasses import dataclass, field

from .config import CONFIG
from .dictionaries import DICTS, DrugName, Term
from .sources import JsonHttp, OpenFdaClient, RxNavClient, SourceError

logger = logging.getLogger(__name__)


@dataclass
class DrugRecord:
    name: DrugName
    rxcui: str = ""
    atc: list[tuple[str, str]] = field(default_factory=list)       # [(код ATC, название)]
    indications: list[Term] = field(default_factory=list)          # заболевания
    relieved: list[Term] = field(default_factory=list)             # устраняемые симптомы
    side_effects: list[tuple[Term, int]] = field(default_factory=list)   # (симптом, число сообщений FAERS)
    brands: list[str] = field(default_factory=list)
    epc: list[str] = field(default_factory=list)
    unmapped_indications: int = 0
    unmapped_reactions: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def facts(self) -> int:
        """Число содержательных фактов (показания, устраняемые симптомы, побочные эффекты)."""
        return len(self.indications) + len(self.relieved) + len(self.side_effects)

    def drop_confounded(self, extra_symptoms: set[str] = frozenset()) -> list[str]:
        """Убирает из побочных эффектов симптомы, ради устранения которых препарат и принимают
        (искажение по показанию: в сообщения FAERS попадает сам симптом болезни)."""
        own = {t.sys_id for t in self.relieved} | set(extra_symptoms)
        dropped = [t.ru for t, _ in self.side_effects if t.sys_id in own]
        self.side_effects = [(t, n) for t, n in self.side_effects if t.sys_id not in own]
        return dropped


class Collector:
    def __init__(self) -> None:
        self.http = JsonHttp()
        self.rxnav = RxNavClient(self.http)
        self.fda = OpenFdaClient(self.http)

    # Сведения о препарате собираются тремя независимыми запросами, которые идут параллельно.
    def _part_rxnav(self, rec: DrugRecord) -> None:
        rec.rxcui = self.rxnav.rxcui(rec.name.rx_name) or ""
        if not rec.rxcui:
            return
        rec.atc = self.rxnav.atc_codes(rec.rxcui)
        seen: set[str] = set()
        for mesh in self.rxnav.may_treat(rec.rxcui):
            t = DICTS.indications.get(mesh)
            if t is None:
                rec.unmapped_indications += 1
            elif t.sys_id not in seen:
                seen.add(t.sys_id)
                (rec.indications if t.kind == "disease" else rec.relieved).append(t)

    def _part_faers(self, rec: DrugRecord) -> None:
        seen: set[str] = set()
        for term, count in self.fda.reactions(rec.name.openfda):
            t = DICTS.reactions.get(term)
            if t is None:
                rec.unmapped_reactions += 1
                continue
            if count < CONFIG.min_reports or t.sys_id in seen:
                continue
            seen.add(t.sys_id)
            rec.side_effects.append((t, count))
            if len(rec.side_effects) >= CONFIG.side_effects + 3:   # запас на фильтр искажения по показанию
                break

    def _part_label(self, rec: DrugRecord) -> None:
        lab = self.fda.label_summary(rec.name.openfda)
        rec.brands, rec.epc = lab["brands"], lab["epc"]

    def _run_part(self, part, rec: DrugRecord) -> None:
        try:
            part(rec)
        except SourceError as e:
            rec.errors.append(str(e))
        except Exception as e:  # ответ неожиданного формата не должен ронять весь импорт
            logger.exception("Ошибка разбора ответа источника")
            rec.errors.append(repr(e))

    def collect(self, name: DrugName) -> DrugRecord:
        return self.collect_many([name], limit=1)[0] if name else DrugRecord(name)

    def collect_many(self, names: list[DrugName], limit: int, budget: float | None = None) -> list[DrugRecord]:
        """Собирает сведения параллельно, не дольше budget секунд. Возвращает первые limit препаратов
        (в порядке списка), о которых источники что-то сообщили; незавершённые запросы отбрасываются."""
        budget = CONFIG.time_budget if budget is None else budget
        deadline = time.monotonic() + budget
        candidates = names[: limit + 3]     # запас: о части препаратов источники не знают ничего
        recs = [DrugRecord(n) for n in candidates]
        pool = cf.ThreadPoolExecutor(max_workers=CONFIG.workers)
        futures = {}
        for rec in recs:
            for part in (self._part_rxnav, self._part_faers, self._part_label):
                futures[pool.submit(self._run_part, part, rec)] = rec
        pending_recs: set[int] = set()
        try:
            for _ in cf.as_completed(futures, timeout=max(1.0, deadline - time.monotonic())):
                pass
        except cf.TimeoutError:
            pending_recs = {id(r) for f, r in futures.items() if not f.done()}
            logger.warning("Время на загрузку истекло, не завершено запросов: %d",
                           sum(1 for f in futures if not f.done()))
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        ready = [r for r in recs if id(r) not in pending_recs and r.facts]
        if len(ready) < limit:     # частично собранные тоже годятся, если в них есть факты
            ready += [r for r in recs if id(r) in pending_recs and r.facts][: limit - len(ready)]
            ready.sort(key=lambda r: candidates.index(r.name))
        # незавершённые потоки ещё могут дописывать записи — отдаём копии
        return [copy.deepcopy(r) for r in ready[:limit]]
