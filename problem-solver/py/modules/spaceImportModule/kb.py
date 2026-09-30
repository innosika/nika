"""Чтение и запись sc-памяти для модуля импорта: поиск элементов, создание узлов, связей и ссылок."""
from __future__ import annotations

from sc_client import client
from sc_client.constants import sc_type
from sc_client.models import (ScAddr, ScConstruction, ScIdtfResolveParams, ScLinkContent, ScLinkContentType,
                              ScTemplate)

LANG = {"ru": "lang_ru", "en": "lang_en"}


class Kb:
    def __init__(self) -> None:
        self._keynodes: dict[str, ScAddr] = {}
        self.created: list[dict] = []     # созданные сущности — для словаря классификатора (wit-local)

    # --- ключевые узлы
    def find(self, idtf: str) -> ScAddr:
        """Элемент по системному идентификатору (недействительный адрес, если его нет)."""
        if idtf in self._keynodes:
            return self._keynodes[idtf]
        addr = client.resolve_keynodes(ScIdtfResolveParams(idtf=idtf, type=None))[0]
        if addr.is_valid():
            self._keynodes[idtf] = addr
        return addr

    def keynode(self, idtf: str, node_type=sc_type.CONST_NODE_NON_ROLE) -> ScAddr:
        """Ключевой узел; создаётся с указанным типом, если его ещё нет в памяти."""
        addr = self.find(idtf)
        if not addr.is_valid():
            addr = client.resolve_keynodes(ScIdtfResolveParams(idtf=idtf, type=node_type))[0]
            self._keynodes[idtf] = addr
        return addr

    # --- поиск
    def is_member(self, cls: ScAddr, element: ScAddr) -> bool:
        t = ScTemplate()
        t.triple(cls, sc_type.VAR_PERM_POS_ARC, element)
        return bool(client.search_by_template(t))

    def members(self, cls: ScAddr) -> list[ScAddr]:
        t = ScTemplate()
        t.triple(cls, sc_type.VAR_PERM_POS_ARC, (sc_type.VAR_NODE, "_x"))
        return [r.get("_x") for r in client.search_by_template(t)]

    def classes_of(self, element: ScAddr) -> list[ScAddr]:
        t = ScTemplate()
        t.triple((sc_type.VAR_NODE_CLASS, "_c"), sc_type.VAR_PERM_POS_ARC, element)
        return [r.get("_c") for r in client.search_by_template(t)]

    def targets(self, src: ScAddr, rel: str | ScAddr) -> list[ScAddr]:
        rel_addr = self.find(rel) if isinstance(rel, str) else rel
        if not rel_addr.is_valid():
            return []
        t = ScTemplate()
        t.quintuple(src, sc_type.VAR_COMMON_ARC, (sc_type.VAR, "_x"), sc_type.VAR_PERM_POS_ARC, rel_addr)
        return [r.get("_x") for r in client.search_by_template(t)]

    def texts(self, src: ScAddr, rel: str, lang: str | None = None) -> list[str]:
        out = []
        for link in self.targets(src, rel):
            if lang and not self.is_member(self.keynode(LANG[lang], sc_type.CONST_NODE_CLASS), link):
                continue
            content = client.get_link_content(link)[0]
            if content and content.data is not None:
                out.append(str(content.data))
        return out

    def main_idtf(self, node: ScAddr, lang: str = "ru") -> str:
        names = self.texts(node, "nrel_main_idtf", lang)
        return names[0] if names else ""

    def subclasses(self, cls: ScAddr) -> list[ScAddr]:
        """Класс и все его подклассы (надкласс =>nrel_inclusion: подкласс)."""
        out, stack, seen = [], [cls], set()
        while stack:
            c = stack.pop()
            if c.value in seen:
                continue
            seen.add(c.value)
            out.append(c)
            stack.extend(self.targets(c, "nrel_inclusion"))
        return out

    def instances_deep(self, cls: ScAddr) -> list[ScAddr]:
        seen: dict[int, ScAddr] = {}
        for c in self.subclasses(cls):
            for x in self.members(c):
                seen.setdefault(x.value, x)
        return list(seen.values())

    def has_relation(self, src: ScAddr, rel: str, trg: ScAddr) -> bool:
        return any(x == trg for x in self.targets(src, rel))

    # --- запись
    def add_to_class(self, cls: ScAddr, element: ScAddr) -> bool:
        if self.is_member(cls, element):
            return False
        c = ScConstruction()
        c.generate_connector(sc_type.CONST_PERM_POS_ARC, cls, element)
        client.generate_elements(c)
        return True

    def add_relation(self, src: ScAddr, rel: str, trg: ScAddr) -> bool:
        """src =>rel: trg, если такой пары ещё нет. Возвращает True, если факт добавлен."""
        if self.has_relation(src, rel, trg):
            return False
        c = ScConstruction()
        c.generate_connector(sc_type.CONST_COMMON_ARC, src, trg, "arc")
        c.generate_connector(sc_type.CONST_PERM_POS_ARC, self.keynode(rel), "arc")
        client.generate_elements(c)
        return True

    def add_text(self, src: ScAddr, rel: str, text: str, lang: str | None = "ru", unique: bool = True) -> bool:
        if unique and text in self.texts(src, rel):
            return False
        c = ScConstruction()
        c.generate_link(sc_type.CONST_NODE_LINK, ScLinkContent(text, ScLinkContentType.STRING), "link")
        c.generate_connector(sc_type.CONST_COMMON_ARC, src, "link", "arc")
        c.generate_connector(sc_type.CONST_PERM_POS_ARC, self.keynode(rel), "arc")
        if lang:
            c.generate_connector(sc_type.CONST_PERM_POS_ARC, self.keynode(LANG[lang], sc_type.CONST_NODE_CLASS),
                                 "link")
        client.generate_elements(c)
        return True

    def new_link(self, text: str) -> ScAddr:
        c = ScConstruction()
        c.generate_link(sc_type.CONST_NODE_LINK, ScLinkContent(text, ScLinkContentType.STRING))
        return client.generate_elements(c)[0]

    def new_set(self, elements: list[ScAddr]) -> ScAddr:
        c = ScConstruction()
        c.generate_node(sc_type.CONST_NODE, "set")
        for e in elements:
            c.generate_connector(sc_type.CONST_PERM_POS_ARC, "set", e)
        return client.generate_elements(c)[0]

    def ensure_node(self, sys_id: str, cls: str, ru: str, en: str = "", synonyms_ru: list[str] = (),
                    synonyms_en: list[str] = (), wit_entity: bool = True) -> tuple[ScAddr, bool]:
        """Узел с системным идентификатором; если его нет — создаётся в классе cls с именами.
        Возвращает (адрес, создан_ли)."""
        addr = self.find(sys_id)
        if addr.is_valid():
            return addr, False
        addr = self.keynode(sys_id, sc_type.CONST_NODE)
        self.add_to_class(self.keynode(cls, sc_type.CONST_NODE_CLASS), addr)
        if wit_entity:   # сущность распознаётся классификатором сообщений (wit-local)
            self.add_to_class(self.keynode("concept_wit_entity", sc_type.CONST_NODE_CLASS), addr)
        self.add_text(addr, "nrel_main_idtf", ru, "ru", unique=False)
        if en:
            self.add_text(addr, "nrel_main_idtf", en, "en", unique=False)
        for s in synonyms_ru:
            self.add_text(addr, "nrel_idtf", s, "ru")
        for s in synonyms_en:
            self.add_text(addr, "nrel_idtf", s, "en")
        if wit_entity:
            names = [[ru, "ru", "main"]] + ([[en, "en", "main"]] if en else [])
            names += [[x, "ru", "idtf"] for x in synonyms_ru] + [[x, "en", "idtf"] for x in synonyms_en]
            self.created.append({"addr": addr.value, "value": ru, "sys_idtf": sys_id, "kind": "instance",
                                 "classes": [cls], "names": names})
        return addr, True
