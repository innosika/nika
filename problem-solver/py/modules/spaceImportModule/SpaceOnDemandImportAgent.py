"""Режим 1 (Пикта И. Д.): дозагрузка сведений о космическом объекте по запросу пользователя.

Условие: сообщение ЛР2 о физических характеристиках, об орбите, о спутниках, об открытии, о созвездии или
о космической миссии; среди сущностей есть объект базы знаний, у которого нет запрошенных сведений и который
ещё не загружался. Агент находит объект в Wikidata (по идентификатору из базы знаний или по названию),
погружает сведения (для вопроса о спутниках — и сами спутники) и выводит новые знания; затем стандартный
агент ответа отвечает по пополненной базе знаний.
"""
from __future__ import annotations

from sc_client.models import ScAddr

from .base_agent import SpaceImportAgentBase
from .config import CONFIG
from .pipeline import ImportReport

# класс сообщения → отношения, наличие любого из которых означает «сведения уже есть»
ASKED = {
    "concept_message_about_physical_parameters": ("nrel_mass", "nrel_equatorial_radius"),
    "concept_message_about_orbit": ("nrel_orbit",),
    "concept_message_about_satellites": ("nrel_natural_satellite",),
    "concept_message_about_discovery": ("nrel_discoverer",),
    "concept_message_about_constellation": ("nrel_located_in_constellation",),
    "concept_message_about_space_mission": ("nrel_start_date", "nrel_launch_date"),
}


class SpaceOnDemandImportAgent(SpaceImportAgentBase):
    action_class = "action_import_space_knowledge_on_demand"

    def process(self, message: ScAddr, started: float) -> ImportReport | None:
        if not CONFIG.on_demand:
            return None
        p = self.pipeline
        asked = [cls for cls in ASKED if p.message_has_class(message, cls)]
        if not asked:
            return None
        relations = ASKED[asked[0]]
        qids, nodes = [], {}
        for entity in p.entities(message):
            if not p.is_space_instance(entity) or p.was_imported(entity):
                continue            # не объект базы знаний или уже загружался
            if all(p.kb.targets(entity, rel) for rel in relations):
                continue            # запрошенные сведения уже есть
            q = p.qid_of(entity)
            if q:
                qids.append(q)
                nodes[q] = entity
        if not qids:
            self.logger.info("Режим 1: загрузка не нужна")
            return None
        self.logger.info("Режим 1: дозагрузка сведений о %s", qids)
        return p.run(qids, message, started, with_children=asked[0] == "concept_message_about_satellites",
                     kb_nodes=nodes)
