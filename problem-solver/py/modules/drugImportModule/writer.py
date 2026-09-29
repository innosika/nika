"""Погружение собранных сведений о препарате в базу знаний."""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field

from sc_client.constants import sc_type
from sc_client.models import ScAddr

from .collector import DrugRecord
from .config import CONFIG
from .dictionaries import Term
from .kb import Kb

logger = logging.getLogger(__name__)

SOURCE_RXNAV = "information_source_rxnav"
SOURCE_OPENFDA = "information_source_openfda"


@dataclass
class AtcGroup:
    node: ScAddr
    code: str
    name_ru: str
    drug_class: ScAddr


@dataclass
class WriteResult:
    drug: ScAddr
    created: bool
    facts: int = 0
    dropped_confounded: list[str] = field(default_factory=list)


class DrugWriter:
    def __init__(self, kb: Kb) -> None:
        self.kb = kb
        self._groups: list[AtcGroup] | None = None

    # --- знания базы, на которые опирается импорт
    def atc_groups(self) -> list[AtcGroup]:
        """Группы ATC, описанные в базе знаний: код, русское название, соответствующий класс лекарств."""
        if self._groups is None:
            self._groups = []
            for g in self.kb.members(self.kb.keynode("concept_atc_group", sc_type.CONST_NODE_CLASS)):
                codes = self.kb.texts(g, "nrel_atc_code")
                classes = self.kb.targets(g, "nrel_corresponding_drug_class")
                if codes and classes:
                    self._groups.append(AtcGroup(g, codes[0], self.kb.main_idtf(g), classes[0]))
            self._groups.sort(key=lambda x: -len(x.code))       # сначала более узкие группы
        return self._groups

    def group_for(self, atc_code: str) -> AtcGroup | None:
        return next((g for g in self.atc_groups() if atc_code.startswith(g.code)), None)

    def disease_symptoms(self, diseases: list[ScAddr]) -> set[str]:
        """Системные идентификаторы симптомов заболеваний (для фильтра искажения по показанию)."""
        out: set[str] = set()
        for d in diseases:
            for s in self.kb.targets(d, "nrel_symptom"):
                idtf = self._sys_idtf(s)
                if idtf:
                    out.add(idtf)
        return out

    def _sys_idtf(self, addr: ScAddr) -> str:
        names = self.kb.texts(addr, "nrel_system_identifier")
        return names[0] if names else ""

    # --- запись
    def _term_node(self, term: Term) -> ScAddr:
        addr, created = self.kb.ensure_node(term.sys_id, term.cls, term.ru, term.source.capitalize()
                                            if term.kind == "symptom" else term.source)
        if term.kind == "disease":
            self.kb.add_text(addr, "nrel_mesh_heading", term.source, lang=None)
        return addr

    def write(self, rec: DrugRecord) -> WriteResult:
        kb, n = self.kb, rec.name
        groups = [g for code, _ in rec.atc if (g := self.group_for(code))]
        drug = kb.find(n.sys_id)
        created = not drug.is_valid()
        if created:
            # Новый препарат сначала — экземпляр класса «лекарственное средство»; конкретный класс
            # (антигистаминное, сахароснижающее…) выводит правило по группе ATC.
            drug, _ = kb.ensure_node(n.sys_id, "concept_drug", n.ru, n.rx_name,
                                     synonyms_ru=n.synonyms, synonyms_en=rec.brands)
        res = WriteResult(drug, created)

        f = 0
        f += kb.add_text(drug, "nrel_rxcui", rec.rxcui, lang=None) if rec.rxcui else 0
        for code, _ in rec.atc:
            f += kb.add_text(drug, "nrel_atc_code", code, lang=None)
        for g in {g.node.value: g for g in groups}.values():
            f += kb.add_relation(drug, "nrel_atc_group", g.node)
        disease_nodes = []
        for t in rec.indications:
            d = self._term_node(t)
            disease_nodes.append(d)
            f += kb.add_relation(drug, "nrel_indication", d)
        for t in rec.relieved:
            f += kb.add_relation(drug, "nrel_relieved_symptom", self._term_node(t))
        # искажение по показанию: симптомы всех заболеваний, при которых препарат показан по базе знаний
        # (и загруженных сейчас, и заданных раньше — например, в ЛР1)
        indicated = {d.value: d for d in disease_nodes + kb.targets(drug, "nrel_indication")}
        res.dropped_confounded = rec.drop_confounded(self.disease_symptoms(list(indicated.values())))
        for t, _ in rec.side_effects[: CONFIG.side_effects]:
            f += kb.add_relation(drug, "nrel_side_effect", self._term_node(t))
        for brand in rec.brands:
            kb.add_text(drug, "nrel_idtf", brand, "en")
        if created or not kb.texts(drug, "nrel_definition"):
            kb.add_text(drug, "nrel_definition", self._definition(rec, groups))
        kb.add_relation(drug, "nrel_information_source", kb.keynode(SOURCE_RXNAV, sc_type.CONST_NODE))
        kb.add_relation(drug, "nrel_information_source", kb.keynode(SOURCE_OPENFDA, sc_type.CONST_NODE))
        kb.add_text(drug, "nrel_import_note", self._note(rec, res), unique=False)
        res.facts = f
        return res

    @staticmethod
    def _definition(rec: DrugRecord, groups: list[AtcGroup]) -> str:
        codes = ", ".join(code for code, _ in rec.atc)
        if groups:
            return (f"лекарственное средство группы «{groups[0].name_ru}» (код ATC {codes}); "
                    f"международное непатентованное название — {rec.name.rx_name}")
        return f"лекарственное средство, международное непатентованное название — {rec.name.rx_name}" + \
            (f" (код ATC {codes})" if codes else "")

    @staticmethod
    def _note(rec: DrugRecord, res: WriteResult) -> str:
        date = datetime.date.today().strftime("%d.%m.%Y")
        parts = [f"сведения загружены {date}: RxNav/RxClass (rxcui {rec.rxcui or '—'}, классы ATC, показания MED-RT)"]
        if rec.side_effects:
            se = ", ".join(f"{t.ru} — {c}" for t, c in rec.side_effects[:6])
            parts.append(f"openFDA FAERS (число сообщений о нежелательных реакциях: {se})")
        if res.dropped_confounded:
            parts.append("не записаны как побочные эффекты (симптомы самого показания): "
                         + ", ".join(res.dropped_confounded))
        if rec.unmapped_indications or rec.unmapped_reactions:
            parts.append(f"без русского названия пропущено показаний: {rec.unmapped_indications}, "
                         f"реакций: {rec.unmapped_reactions}")
        return "; ".join(parts)
