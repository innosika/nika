"""Общий конвейер агентов импорта «Космоса»: загрузить из Wikidata → погрузить → вывести новые знания → отчёт."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests
from sc_client import client
from sc_client.constants import sc_type
from sc_client.models import ScAddr, ScTemplate
from sc_kpm.utils.action_utils import execute_agent, get_action_result

from .collector import Collector, SpaceRecord
from .config import CONFIG
from .kb import Kb
from .writer import SpaceWriter, WriteResult

logger = logging.getLogger(__name__)


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    return few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


@dataclass
class ImportReport:
    records: list[SpaceRecord] = field(default_factory=list)
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
            return self.note or "Wikidata не сообщила новых сведений — база знаний не изменилась."
        n = len(self.written)
        s = (f"Из Wikidata загружены сведения о {n} {plural(n, 'объекте', 'объектах', 'объектах')} "
             f"(новых в базе знаний — {self.created}), погружено фактов: {self.facts}")
        return s + (f"; логический вывод добавил ещё {self.derived}." if self.derived else ".")


class ImportPipeline:
    def __init__(self) -> None:
        self.kb = Kb()
        self.collector = Collector()
        self.writer = SpaceWriter(self.kb)

    # --- сведения о сообщении
    def message_has_class(self, message: ScAddr, cls: str) -> bool:
        c = self.kb.find(cls)
        return c.is_valid() and self.kb.is_member(c, message)

    def entities(self, message: ScAddr) -> list[ScAddr]:
        t = ScTemplate()
        t.quintuple(message, sc_type.VAR_PERM_POS_ARC, (sc_type.VAR, "_e"), sc_type.VAR_PERM_POS_ARC,
                    self.kb.find("rrel_entity"))
        return [r.get("_e") for r in client.search_by_template(t)]

    def space_classes(self) -> list[ScAddr]:
        roots = [self.kb.find(c) for c in ("concept_space_object", "concept_space_mission", "concept_constellation",
                                           "concept_cosmodrome", "concept_space_agency", "concept_cosmonaut")]
        out = []
        for r in roots:
            if r.is_valid():
                out += self.kb.subclasses(r)
        return out

    def is_space_instance(self, node: ScAddr) -> bool:
        return any(self.kb.is_member(c, node) for c in self.space_classes())

    def qid_of(self, node: ScAddr) -> str | None:
        """Идентификатор Wikidata объекта базы знаний; если его нет — поиск по названию."""
        ids = self.kb.texts(node, "nrel_wikidata_id")
        if ids:
            return ids[0]
        return self.collector.wd.find_by_label(self.kb.main_idtf(node, "ru"), self.kb.main_idtf(node, "en"))

    def was_imported(self, node: ScAddr) -> bool:
        return bool(self.kb.targets(node, "nrel_space_data_source"))

    # --- импорт
    def run(self, qids: list[str], message: ScAddr, started: float, with_children: bool = False,
            kb_nodes: dict[str, ScAddr] | None = None, limit: int | None = None) -> ImportReport:
        rep = ImportReport()
        budget = max(5.0, CONFIG.time_budget - (time.monotonic() - started))
        rep.records = self.collector.collect(qids, with_children=with_children, budget=budget)
        if limit:
            main = [r for r in rep.records if not r.parent][:limit]
            rep.records = main + [r for r in rep.records if r.parent]
        # сначала родительские объекты, затем спутники (им нужен узел родителя)
        for rec in sorted(rep.records, key=lambda r: bool(r.parent)):
            try:
                rep.written.append(self.writer.write(rec, (kb_nodes or {}).get(rec.qid)))
            except Exception:
                logger.exception("Не удалось погрузить сведения о %s", rec.qid)
        if rep.written:
            rep.derived = self.infer([w.node for w in rep.written])
            self.push_entities()
        rep.seconds = round(time.monotonic() - started, 1)
        rep.http = dict(self.collector.wd.stats)
        for w in rep.written:
            self.kb.add_relation(message, "nrel_imported_space_object", w.node)
        self.kb.add_text(message, "nrel_space_import_report", rep.text(), unique=False)
        logger.info("Импорт: %s за %.1f с, запросы %s", rep.text(), rep.seconds, rep.http)
        return rep

    def infer(self, nodes: list[ScAddr]) -> int:
        """Инициирует действие вывода новых знаний (агент SpaceKnowledgeInferenceAgent, C++)."""
        action, ok = execute_agent({self.kb.new_set(nodes): False}, ["action", "action_infer_space_knowledge"],
                                   wait_time=CONFIG.inference_wait)
        if not ok:
            logger.warning("Вывод новых знаний не завершился успешно")
            return 0
        t = ScTemplate()
        t.triple(get_action_result(action), sc_type.VAR_PERM_POS_ARC, (sc_type.VAR_NODE_LINK, "_link"))
        for r in client.search_by_template(t):
            content = str(client.get_link_content(r.get("_link"))[0].data)
            if content.isdigit():
                return int(content)
        return 0

    def push_entities(self) -> None:
        """Новые объекты — в словарь классификатора wit-local: распознаются в следующем сообщении."""
        entities, self.kb.created = self.kb.created, []
        if entities:
            try:
                logger.info("wit-local: %s", requests.post(CONFIG.wit_entities_url, json={"entities": entities},
                                                           timeout=10).json())
            except (requests.RequestException, ValueError) as e:
                logger.warning("wit-local не принял новые сущности: %s", e)
