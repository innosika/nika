"""Режим 1 (Банкевич Я.): дозагрузка сведений о препарате по запросу пользователя.

Условие: сообщение о побочных эффектах, о показаниях или о применении лекарства при заболевании;
среди сущностей есть препарат базы знаний, у которого нет запрошенных сведений и который ещё не
загружался из внешних источников. Агент загружает сведения о препарате, погружает их и выводит новые
знания; затем стандартный агент ответа отвечает уже по пополненной базе знаний.
"""
from __future__ import annotations

from sc_client.models import ScAddr

from .base_agent import DrugImportAgentBase
from .config import CONFIG
from .pipeline import ImportReport

# класс сообщения → отношение, наличие которого означает «сведения уже есть»
# (для «помогает ли X при Y» — None: проверяется только, загружался ли препарат)
ASKED_RELATION = {
    "concept_message_about_drug_side_effects": "nrel_side_effect",
    "concept_message_about_drug_indications": "nrel_indication",
    "concept_message_about_drug_for_disease": None,
}


class DrugOnDemandImportAgent(DrugImportAgentBase):
    action_class = "action_import_drug_knowledge_on_demand"

    def process(self, message: ScAddr, started: float) -> ImportReport | None:
        if not CONFIG.on_demand:
            return None
        p = self.pipeline
        asked = [cls for cls in ASKED_RELATION if p.message_has_class(message, cls)]
        if not asked:
            return None
        relation = ASKED_RELATION[asked[0]]
        names = []
        for entity in p.entities(message):
            if not p.is_drug(entity) or p.was_imported(entity):
                continue            # не препарат или сведения уже загружались
            if relation and p.kb.targets(entity, relation):
                continue            # запрошенные сведения в базе знаний уже есть
            name = p.drug_name(entity)
            if name:
                names.append(name)
        if not names:
            self.logger.info("Режим 1: загрузка не нужна (сведения есть или препарат неизвестен словарю)")
            return None
        self.logger.info("Режим 1: дозагрузка сведений о %s", [n.rx_name for n in names])
        return p.run(names, limit=len(names), message=message, started=started)
