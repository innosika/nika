"""Режим 3 (Рублевская Е.): наполнение базы знаний лекарствами определённого типа.

Условие: сообщение класса «сообщение о наполнении базы знаний лекарственными средствами заданного
типа» с сущностью. Тип задаётся:
* классом лекарств («Наполни БЗ антигистаминными средствами») — берутся группы ATC этого класса
  и его подклассов;
* заболеванием или классом заболеваний («…лекарствами от аллергии», «…от сахарного диабета 2 типа») —
  берутся рубрики MeSH заболевания (для класса — всех его заболеваний) и лекарства, которые по MED-RT
  «may_treat» эти заболевания.
"""
from __future__ import annotations

import concurrent.futures as cf

from sc_client.constants import sc_type
from sc_client.models import ScAddr

from .base_agent import DrugImportAgentBase
from .config import CONFIG
from .dictionaries import DICTS
from .pipeline import ImportReport
from .sources import SourceError

MESSAGE_CLASS = "concept_message_about_kb_filling_with_drugs"
BY_TYPE_CLASS = "concept_message_about_kb_filling_with_drugs_by_type"


class DrugKbFillByTypeAgent(DrugImportAgentBase):
    action_class = "action_fill_kb_with_drugs_by_type"

    def process(self, message: ScAddr, started: float) -> ImportReport | None:
        p = self.pipeline
        types = p.type_entities(message) if p.message_has_class(message, MESSAGE_CLASS) else []
        if not types:
            return None
        p.kb.add_to_class(p.kb.keynode(BY_TYPE_CLASS, sc_type.CONST_NODE_CLASS), message)
        source_names: list[str] = []
        what = ""
        for entity in types:
            drug_classes = {c.value for c in p.drug_classes()}
            if entity.value in drug_classes:
                subclasses = {c.value for c in p.kb.subclasses(entity)}
                codes = [g.code for g in p.writer.atc_groups() if g.drug_class.value in subclasses]
                source_names += self._parallel(p.collector.rxnav.atc_members, codes)
                what = f"класс лекарств, группы ATC {', '.join(codes)}"
            else:
                headings = self.mesh_headings(entity)
                source_names += self._parallel(p.collector.rxnav.drugs_for_disease, headings)
                what = f"заболевания, рубрики MeSH: {'; '.join(headings)}"
        candidates = [d for d in DICTS.ranked(source_names)
                      if not (p.exists(d) and p.was_imported(p.kb.find(d.sys_id)))]
        self.logger.info("Режим 3: %s; кандидаты %s", what, [d.rx_name for d in candidates])
        report = p.run(candidates, limit=CONFIG.fill_by_type, message=message, started=started)
        if not candidates:
            report.note = ("Во внешних источниках не нашлось новых препаратов этого типа с русскими названиями — "
                           "возможно, все они уже загружены.")
            p.kb.add_text(message, "nrel_knowledge_import_report", report.note, unique=False)
        return report

    def mesh_headings(self, entity: ScAddr) -> list[str]:
        """Рубрики MeSH заболевания; для класса заболеваний — всех его заболеваний (включая подклассы)."""
        kb = self.pipeline.kb
        nodes = [entity] + kb.instances_deep(entity)
        out: list[str] = []
        for n in nodes:
            for h in kb.texts(n, "nrel_mesh_heading"):
                if h not in out:
                    out.append(h)
        return out

    def _parallel(self, fn, args: list[str]) -> list[str]:
        def safe(a: str) -> list[str]:
            try:
                return fn(a)
            except SourceError:
                return []
        with cf.ThreadPoolExecutor(max_workers=max(1, min(8, len(args)))) as pool:
            return [x for res in pool.map(safe, args) for x in res]
