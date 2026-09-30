"""Режим 2 (Переверзев М. А.): наполнение базы знаний космическими объектами из Wikidata.

Условие: сообщение класса «о наполнении базы знаний космическими объектами». Тип можно не указывать
(«Наполни базу знаний космическими объектами из Wikidata») — тогда берутся все классы базы знаний, которым
сопоставлен класс Wikidata, в первую очередь классы без экземпляров; можно указать класс («…небесными
телами», «…космическими миссиями») — берутся его подклассы; можно указать объект («…спутниками Юпитера»)
— загружаются его естественные спутники.
"""
from __future__ import annotations

import concurrent.futures as cf

from sc_client.constants import sc_type
from sc_client.models import ScAddr

from . import mapping as M
from .base_agent import SpaceImportAgentBase
from .config import CONFIG
from .pipeline import ImportReport
from .sources import SourceError

MESSAGE_CLASS = "concept_message_about_kb_filling_with_space_objects"
BY_TYPE_CLASS = "concept_message_about_kb_filling_with_space_objects_by_type"


class SpaceKbFillAgent(SpaceImportAgentBase):
    action_class = "action_fill_kb_with_space_objects"

    def process(self, message: ScAddr, started: float) -> ImportReport | None:
        p = self.pipeline
        if not p.message_has_class(message, MESSAGE_CLASS):
            return None
        root = p.kb.find("concept_space_object")
        classes = {c.value for c in p.space_classes()}
        entities = [e for e in p.entities(message) if e.value != root.value]
        type_classes = [e for e in entities if e.value in classes]
        objects = [e for e in entities if e.value not in classes and p.is_space_instance(e)]
        mapped = p.writer.wd_classes()                  # Q… → (узел, класс базы знаний)
        if type_classes or objects:
            p.kb.add_to_class(p.kb.keynode(BY_TYPE_CLASS, sc_type.CONST_NODE_CLASS), message)
        if objects:                                     # «…спутниками Юпитера»
            qids = []
            for o in objects:
                q = p.qid_of(o)
                if q:
                    try:
                        qids += p.collector.wd.children(q, CONFIG.fill_by_type * 2)
                    except SourceError:
                        pass
            qids = [q for q in qids if q not in p.writer.qid_map()][: CONFIG.fill_by_type]
            self.logger.info("Режим 2 (спутники объекта): %s", qids)
            return p.run(qids, message, started)
        if type_classes:                                # «…небесными телами», «…космическими миссиями»
            wanted = {c.value for t in type_classes for c in p.kb.subclasses(t)}
            groups = [q for q, (_, kb_cls) in mapped.items() if kb_cls.value in wanted]
            limit, per_group = CONFIG.fill_by_type, CONFIG.fill_by_type
        else:                                           # без типа — все сопоставленные классы, пустые первыми
            count = {q: len(p.kb.instances_deep(kb_cls)) for q, (_, kb_cls) in mapped.items()}
            groups = sorted(mapped, key=lambda q: (count[q], q))
            limit, per_group = CONFIG.fill_total, CONFIG.fill_per_class
        with cf.ThreadPoolExecutor(max_workers=8) as pool:
            lists = list(pool.map(self._members, groups))
        known = p.writer.qid_map()
        qids: list[str] = []
        for round_ in range(per_group):                 # по кругу: по одному объекту из каждого класса
            for group, members in zip(groups, lists):
                fresh = [q for q in members if q not in known and q not in qids]
                if len(fresh) > 0 and sum(1 for q in qids if q in members) <= round_:
                    qids.append(fresh[0])
        qids = qids[:limit]
        self.logger.info("Режим 2: классы %s, объекты %s", groups, qids)
        report = p.run(qids, message, started, limit=limit)
        if not qids:
            report.note = "В Wikidata не нашлось новых объектов этого типа — возможно, все они уже загружены."
            p.kb.add_text(message, "nrel_space_import_report", report.note, unique=False)
        return report

    def _members(self, q: str) -> list[str]:
        """Самые известные объекты класса Wikidata; для классов со списком известных объектов в базе знаний
        (звёзды) — этот список."""
        p = self.pipeline
        node = p.writer.wd_classes()[q][0]
        seeds = p.kb.texts(node, "nrel_known_wikidata_member")
        if seeds:                                   # порядок — по известности (числу статей в Википедиях)
            try:
                sl = {r["item"].rsplit("/", 1)[-1]: int(r.get("sl", 0) or 0) for r in p.collector.wd.labels(seeds)}
                return sorted(seeds, key=lambda x: -sl.get(x, 0))
            except SourceError:
                return seeds
        c = M.BY_QID.get(q)
        try:
            return p.collector.wd.members(q, 12, c.pattern if c and c.pattern != "SEED" else "")
        except SourceError:
            return []
