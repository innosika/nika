"""Погружение сведений о космических объектах в базу знаний «Космос»."""
from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass, field

from sc_client import client
from sc_client.constants import sc_type
from sc_client.models import ScAddr, ScTemplate

from .collector import SpaceRecord, Target
from .kb import Kb
from .mapping import WdClass

logger = logging.getLogger(__name__)

SOURCE = "information_source_wikidata"
ROOT = "concept_space_object"
NATURAL = {"nrel_orbit", "nrel_located_in_constellation", "nrel_discoverer", "nrel_discovery_date",
           "nrel_spectral_class", "nrel_mass", "nrel_equatorial_radius", "nrel_orbital_period"}
# какие отношения погружаются для объектов каждого класса (как в описании предметной области ЛР1)
ALLOWED = {
    **{c: NATURAL for c in ("concept_planet", "concept_gas_giant", "concept_terrestrial_planet", "concept_dwarf_planet",
                            "concept_natural_satellite", "concept_asteroid", "concept_comet", "concept_star",
                            "concept_galaxy", "concept_nebula", "concept_black_hole")},
    **{c: {"nrel_launch_date", "nrel_operator", "nrel_orbit"} for c in (
        "concept_space_station", "concept_interplanetary_probe", "concept_artificial_satellite")},
    "concept_space_mission": {"nrel_start_date", "nrel_mission_crew", "nrel_launch_site", "nrel_used_launch_vehicle",
                              "nrel_operator"},
    "concept_launch_vehicle": {"nrel_operator"},
}
# у миссий дата запуска записывается как дата начала (как в ЛР1)
MISSION_DATE = {"nrel_launch_date": "nrel_start_date"}
# классы, которые не являются подклассами «космического объекта»: новые узлы создаются прямо в них
TOP_LEVEL = {"concept_space_mission", "concept_constellation", "concept_cosmodrome", "concept_space_agency",
             "concept_cosmonaut", "concept_planetary_system"}


@dataclass
class WriteResult:
    node: ScAddr
    created: bool
    facts: int = 0
    kept_lr1: list[str] = field(default_factory=list)


class SpaceWriter:
    def __init__(self, kb: Kb) -> None:
        self.kb = kb
        self._qids: dict[str, ScAddr] | None = None
        self._wd_classes: dict[str, ScAddr] | None = None

    # --- знания базы, на которые опирается импорт
    def qid_map(self) -> dict[str, ScAddr]:
        """Идентификатор Wikidata → элемент базы знаний (по отношению nrel_wikidata_id)."""
        if self._qids is None:
            self._qids = {}
            rel = self.kb.find("nrel_wikidata_id")
            if rel.is_valid():
                t = ScTemplate()
                t.quintuple((sc_type.VAR_NODE, "_x"), sc_type.VAR_COMMON_ARC, (sc_type.VAR_NODE_LINK, "_l"),
                            sc_type.VAR_PERM_POS_ARC, rel)
                for r in client.search_by_template(t):
                    content = client.get_link_content(r.get("_l"))[0].data
                    self._qids[str(content)] = r.get("_x")
        return self._qids

    def wd_classes(self) -> dict[str, tuple[ScAddr, ScAddr]]:
        """Класс Wikidata (Q…) → (его узел в базе знаний, соответствующий класс базы знаний)."""
        if self._wd_classes is None:
            self._wd_classes = {}
            for node in self.kb.members(self.kb.keynode("concept_wikidata_class", sc_type.CONST_NODE_CLASS)):
                ids = self.kb.texts(node, "nrel_wikidata_id")
                classes = self.kb.targets(node, "nrel_corresponding_space_class")
                if ids and classes:
                    self._wd_classes[ids[0]] = (node, classes[0])
        return self._wd_classes

    def sys_idtf(self, addr: ScAddr) -> str:
        names = self.kb.texts(addr, "nrel_system_identifier")
        return names[0] if names else ""

    # --- запись
    def _new_sys_id(self, en: str, ru: str, q: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "_", (en or "").lower()).strip("_") or f"wd_{q.lower()}"
        sid = base
        if self.kb.find(sid).is_valid():
            sid = f"{base}_{q.lower()}"
        return sid

    def _creation_class(self, wd: WdClass | None, default: str | None) -> str:
        if wd:
            return wd.kb_class if wd.kb_class in TOP_LEVEL else ROOT     # точный класс выведет правило 1
        return default or ROOT

    def _ensure(self, q: str, ru: str, en: str, wd: WdClass | None, default: str | None,
                descr: str = "") -> tuple[ScAddr, bool]:
        qids = self.qid_map()
        if q in qids:
            return qids[q], False
        node, created = self.kb.ensure_node(self._new_sys_id(en, ru, q), self._creation_class(wd, default), ru, en)
        self.kb.add_text(node, "nrel_wikidata_id", q, lang=None)
        if wd and wd.qid in self.wd_classes():
            self.kb.add_relation(node, "nrel_wikidata_type", self.wd_classes()[wd.qid][0])
        if created and descr:
            self.kb.add_text(node, "nrel_definition", descr)
        qids[q] = node
        return node, created

    def _target(self, t: Target) -> ScAddr:
        node, _ = self._ensure(t.qid, t.ru, "", t.wd_class, t.default_class)
        return node

    def write(self, rec: SpaceRecord, kb_node: ScAddr | None = None) -> WriteResult:
        kb = self.kb
        if kb_node is not None and kb_node.is_valid():
            node, created = kb_node, False
            kb.add_text(node, "nrel_wikidata_id", rec.qid, lang=None)
            self.qid_map()[rec.qid] = node
        else:
            node, created = self._ensure(rec.qid, rec.ru, rec.en, rec.wd_class, None, rec.descr)
        res = WriteResult(node, created)
        if rec.wd_class and rec.wd_class.qid in self.wd_classes():
            res.facts += kb.add_relation(node, "nrel_wikidata_type", self.wd_classes()[rec.wd_class.qid][0])
        kb_class = rec.wd_class.kb_class if rec.wd_class else ""
        allowed = ALLOWED.get(kb_class, NATURAL)
        for rel, values in rec.texts.items():
            if kb_class == "concept_space_mission":
                rel = MISSION_DATE.get(rel, rel)
            if rel not in allowed:
                continue
            if kb.targets(node, rel):
                res.kept_lr1.append(rel)          # сведения уже есть (например, из ЛР1) — не дублируются
                continue
            for v in values:
                res.facts += kb.add_text(node, rel, v)
        for rel, targets in rec.nodes.items():
            if rel not in allowed:
                continue
            for t in targets:
                res.facts += kb.add_relation(node, rel, self._target(t))
        kb.add_relation(node, "nrel_space_data_source", kb.keynode(SOURCE, sc_type.CONST_NODE))
        kb.add_text(node, "nrel_space_import_note", self._note(rec, res), unique=False)
        return res

    @staticmethod
    def _note(rec: SpaceRecord, res: WriteResult) -> str:
        date = datetime.date.today().strftime("%d.%m.%Y")
        s = f"сведения загружены {date} из Wikidata ({rec.qid}"
        s += f", класс Wikidata «{rec.wd_class.ru}»" if rec.wd_class else ""
        s += f", статей в Википедиях: {rec.sitelinks})"
        if res.kept_lr1:
            s += "; не заменены сведения, которые уже были в базе знаний: " + ", ".join(sorted(set(res.kept_lr1)))
        return s
