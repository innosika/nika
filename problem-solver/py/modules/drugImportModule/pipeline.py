"""Общий конвейер трёх агентов импорта: загрузить → погрузить в БЗ → вывести новые знания → отчёт."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests
from sc_client import client
from sc_client.constants import sc_type
from sc_client.models import ScAddr, ScTemplate
from sc_kpm.utils.action_utils import execute_agent, get_action_result

from .collector import Collector, DrugRecord
from .config import CONFIG
from .dictionaries import DICTS, DrugName
from .kb import Kb
from .writer import DrugWriter, WriteResult

logger = logging.getLogger(__name__)


@dataclass
class ImportReport:
    requested: int = 0
    records: list[DrugRecord] = field(default_factory=list)
    written: list[WriteResult] = field(default_factory=list)
    derived: int = 0
    seconds: float = 0.0
    http: dict = field(default_factory=dict)
    note: str = ""

    @property
    def created(self) -> int:
        return sum(1 for w in self.written if w.created)

    @property
    def facts(self) -> int:
        return sum(w.facts for w in self.written)

    def text(self) -> str:
        if not self.written:
            return self.note or ("Внешние источники не сообщили новых сведений о препаратах "
                                 "с русскими названиями — база знаний не изменилась.")
        drugs = len(self.written)
        s = (f"Из openFDA и RxNav загружены сведения о {drugs} {plural(drugs, 'препарате', 'препаратах', 'препаратах')}"
             f" (новых в базе знаний — {self.created}), погружено фактов: {self.facts}")
        s += f"; логический вывод добавил ещё {self.derived}." if self.derived else "."
        return s


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    return few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


class ImportPipeline:
    def __init__(self) -> None:
        self.kb = Kb()
        self.collector = Collector()
        self.writer = DrugWriter(self.kb)

    # --- сведения о сообщении
    def message_has_class(self, message: ScAddr, cls: str) -> bool:
        c = self.kb.find(cls)
        return c.is_valid() and self.kb.is_member(c, message)

    def entities(self, message: ScAddr) -> list[ScAddr]:
        rrel = self.kb.find("rrel_entity")
        t = ScTemplate()
        t.quintuple(message, sc_type.VAR_PERM_POS_ARC, (sc_type.VAR, "_e"), sc_type.VAR_PERM_POS_ARC, rrel)
        return [r.get("_e") for r in client.search_by_template(t)]

    def drug_classes(self) -> list[ScAddr]:
        return self.kb.subclasses(self.kb.find("concept_drug"))

    def type_entities(self, message: ScAddr) -> list[ScAddr]:
        """Сущности, задающие тип лекарств: класс лекарств (кроме самого «лекарственного средства»),
        заболевание или класс заболеваний."""
        drug_root = self.kb.find("concept_drug")
        drug_classes = {c.value for c in self.drug_classes()} - {drug_root.value}
        disease_classes = self.kb.subclasses(self.kb.find("concept_disease"))
        disease_class_ids = {c.value for c in disease_classes}
        out = []
        for e in self.entities(message):
            if e.value in drug_classes or e.value in disease_class_ids \
                    or any(self.kb.is_member(c, e) for c in disease_classes):
                out.append(e)
        return out

    def is_drug(self, node: ScAddr) -> bool:
        return any(self.kb.is_member(c, node) for c in self.drug_classes())

    def drug_name(self, node: ScAddr) -> DrugName | None:
        """Препарат базы знаний → запись словаря (по системному идентификатору или названиям)."""
        sys_id = self.writer._sys_idtf(node)
        for d in DICTS.drugs.values():
            if d.sys_id == sys_id:
                return d
        for en in self.kb.texts(node, "nrel_main_idtf", "en"):
            if (d := DICTS.drug(en)):
                return d
        for ru in self.kb.texts(node, "nrel_main_idtf", "ru"):
            if (d := DICTS.drug_by_ru(ru)):
                return d
        return None

    def was_imported(self, drug: ScAddr) -> bool:
        return bool(self.kb.targets(drug, "nrel_information_source"))

    def exists(self, name: DrugName) -> bool:
        return self.kb.find(name.sys_id).is_valid()

    # --- импорт
    def run(self, names: list[DrugName], limit: int, message: ScAddr, started: float | None = None) -> ImportReport:
        started = started or time.monotonic()
        rep = ImportReport(requested=len(names))
        budget = CONFIG.time_budget - (time.monotonic() - started)
        if names:
            rep.records = self.collector.collect_many(names, limit, budget=max(4.0, budget))
        for rec in rep.records:
            try:
                rep.written.append(self.writer.write(rec))
            except Exception:
                logger.exception("Не удалось погрузить сведения о %s", rec.name.rx_name)
        if rep.written:
            rep.derived = self.infer([w.drug for w in rep.written])
            self.reload_classifier()
        rep.seconds = round(time.monotonic() - started, 1)
        rep.http = dict(self.collector.http.stats)
        self.attach_to_message(message, rep)
        logger.info("Импорт: %s за %.1f с, запросы %s", rep.text(), rep.seconds, rep.http)
        return rep

    def infer(self, drugs: list[ScAddr]) -> int:
        """Инициирует действие вывода новых знаний (агент DrugKnowledgeInferenceAgent, C++)."""
        drugs_set = self.kb.new_set(drugs)
        action, ok = execute_agent({drugs_set: False}, ["action", "action_infer_drug_knowledge"],
                                   wait_time=CONFIG.inference_wait)
        if not ok:
            logger.warning("Вывод новых знаний не завершился успешно")
            return 0
        result = get_action_result(action)
        t = ScTemplate()
        t.triple(result, sc_type.VAR_PERM_POS_ARC, (sc_type.VAR_NODE_LINK, "_link"))
        for r in client.search_by_template(t):
            content = client.get_link_content(r.get("_link"))[0].data
            if str(content).isdigit():
                return int(content)
        return 0

    def reload_classifier(self) -> None:
        """Передаёт wit-local созданные сущности — новые препараты, заболевания и симптомы распознаются
        в следующем же сообщении (перечитывать всю sc-память не нужно)."""
        entities, self.kb.created = self.kb.created, []
        if not entities:
            return
        try:
            r = requests.post(CONFIG.wit_entities_url, json={"entities": entities}, timeout=10)
            logger.info("wit-local: %s", r.json())
        except (requests.RequestException, ValueError) as e:
            logger.warning("wit-local не принял новые сущности: %s", e)

    def attach_to_message(self, message: ScAddr, rep: ImportReport) -> None:
        """Итог импорта записывается в сообщение: его читают правило и фраза ответа."""
        kb = self.kb
        for w in rep.written:
            kb.add_relation(message, "nrel_imported_drug", w.drug)
        kb.add_text(message, "nrel_knowledge_import_report", rep.text(), unique=False)
