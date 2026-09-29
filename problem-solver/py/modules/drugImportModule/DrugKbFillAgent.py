"""Режим 2 (Сергиевич Д.): стартовое наполнение базы знаний лекарствами из внешнего источника.

Условие: сообщение класса «сообщение о наполнении базы знаний лекарственными средствами» без
указания типа лекарств («Наполни базу знаний лекарствами из openFDA»). Агент берёт из базы знаний
группы ATC, сопоставленные классам лекарств, — в первую очередь классы, у которых ещё нет экземпляров, —
запрашивает у RxClass состав каждой группы и загружает самые распространённые препараты.
"""
from __future__ import annotations

import concurrent.futures as cf

from sc_client.models import ScAddr

from .base_agent import DrugImportAgentBase
from .config import CONFIG
from .dictionaries import DICTS
from .pipeline import ImportReport
from .sources import SourceError

MESSAGE_CLASS = "concept_message_about_kb_filling_with_drugs"


class DrugKbFillAgent(DrugImportAgentBase):
    action_class = "action_fill_kb_with_drugs"

    def process(self, message: ScAddr, started: float) -> ImportReport | None:
        p = self.pipeline
        if not p.message_has_class(message, MESSAGE_CLASS) or p.type_entities(message):
            return None                       # тип лекарств указан — это сообщение агента режима 3
        groups = p.writer.atc_groups()
        # сначала пустые классы, затем — с наименьшим числом экземпляров
        filled = {g.code: len(p.kb.instances_deep(g.drug_class)) for g in groups}
        groups = sorted(groups, key=lambda g: (filled[g.code], g.code))
        with cf.ThreadPoolExecutor(max_workers=len(groups) or 1) as pool:
            members = dict(zip([g.code for g in groups], pool.map(self._members, [g.code for g in groups])))
        names, per_class = [], {}
        # по кругу: из каждой группы по одному препарату, пока не наберётся лимит
        for round_ in range(CONFIG.fill_per_class):
            for g in groups:
                fresh = [d for d in DICTS.ranked(members[g.code]) if not p.exists(d) and d not in names]
                if fresh and per_class.get(g.code, 0) <= round_:
                    names.append(fresh[0])
                    per_class[g.code] = per_class.get(g.code, 0) + 1
        names = names[: CONFIG.fill_total]
        self.logger.info("Режим 2: группы %s, кандидаты %s", [g.code for g in groups], [n.rx_name for n in names])
        return p.run(names, limit=CONFIG.fill_total, message=message, started=started)

    def _members(self, code: str) -> list[str]:
        try:
            return self.pipeline.collector.rxnav.atc_members(code)
        except SourceError:
            return []
