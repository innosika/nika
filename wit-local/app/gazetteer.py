"""Словарь сущностей классификатора, построенный по базе знаний NIKA.

Словарь не дублирует базу знаний: при запуске сервис обращается к sc-server и
забирает элементы множества concept_wit_entity вместе с их идентификаторами
(основной и дополнительные, русские и английские), классами и системными
идентификаторами. Агент классификации NIKA (MessageTopicClassifier) затем
сопоставляет выделенную сущность с элементами того же множества по основному
идентификатору на русском языке, поэтому в ответе сервиса значение (value)
сущности — всегда её основной русский идентификатор, даже если пользователь
написал синоним, другой падеж или английское название.

Последний успешно загруженный словарь сохраняется в JSON: сервис поднимается и
тогда, когда sc-server ещё не готов (база знаний пересобирается).
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field

from .text import Token, edit_distance_le1, norm_forms, normalize, tokenize

log = logging.getLogger("wit-local.gazetteer")

# Слова, которые не могут быть однословной сущностью, даже если совпали с идентификатором.
STOP_SINGLE = {"что", "как", "такое", "такой", "такая", "кто", "это", "бывает", "какой", "ли", "а", "и", "в", "у", "о"}

NODE_CLASS = 0x800
NODE_NON_ROLE = 0x400
NODE_ROLE = 0x200


@dataclass
class Entity:
    addr: int
    value: str                      # основной идентификатор на русском языке
    sys_idtf: str = ""
    kind: str = "instance"          # class | relation | role | instance
    classes: list[str] = field(default_factory=list)   # системные идтф. классов (для экземпляров)
    top: str = ""                   # максимальный класс ветки иерархии — тип сущности
    top_name: str = ""
    names: list[list[str]] = field(default_factory=list)  # [текст, язык, вид]

    @property
    def type_token(self) -> str:
        """Токен, которым сущность заменяется в тексте для классификатора намерений."""
        if self.kind in ("relation", "role"):
            return "ent_relation"
        return "ent_" + (self.top or self.kind)


@dataclass
class _Entry:
    tokens: list[str]               # нормализованные токены варианта имени
    forms: list[frozenset[str]]     # нормальные формы каждого токена
    entity: Entity
    exact: bool                     # вариант — основной идентификатор
    tail: str = ""                  # знаки после последнего токена: «)» в «грипп A(H1N1)»


class Gazetteer:
    def __init__(self, entities: list[Entity] | None = None, source: str = "empty", loaded_at: float = 0.0):
        self.entities: list[Entity] = entities or []
        self.source = source
        self.loaded_at = loaded_at
        self.by_value: dict[str, Entity] = {}
        self._index: dict[str, list[_Entry]] = {}
        self._build()

    # ------------------------------------------------------------------ построение индекса
    def _variants(self, e: Entity) -> list[tuple[str, bool]]:
        out = []
        for text, lang, kind in e.names:
            out.append((text, kind == "main" and lang == "ru"))
            if e.kind in ("relation", "role"):
                bare = text.rstrip("*'").strip()
                out.append((f"отношение {bare}", False))
        return out

    def _build(self) -> None:
        self.by_value = {}
        self._index = {}
        for e in self.entities:
            self.by_value.setdefault(e.value, e)
            for text, exact in self._variants(e):
                toks = [t.lower for t in tokenize(text)]
                if not toks:
                    continue
                if len(toks) == 1 and toks[0] in STOP_SINGLE:
                    continue
                last = tokenize(text)[-1]
                entry = _Entry(toks, [norm_forms(t) for t in toks], e, exact, text[last.end:].strip())
                for f in entry.forms[0]:
                    self._index.setdefault(f, []).append(entry)

    # ------------------------------------------------------------------ поиск в тексте
    def _match_at(self, tokens: list[Token], i: int, fuzzy: bool) -> list[tuple[_Entry, float]]:
        found = []
        first_forms = norm_forms(tokens[i].text)
        cands: list[_Entry] = []
        for f in first_forms:
            cands.extend(self._index.get(f, ()))
        for entry in cands:
            n = len(entry.tokens)
            if i + n > len(tokens):
                continue
            if all(entry.forms[j] & norm_forms(tokens[i + j].text) for j in range(n)):
                found.append((entry, 1.0))
        if found or not fuzzy:
            return found
        # Опечатка в однословном имени длиной от 6 букв: «туберкулоз», «пнемония».
        w = tokens[i].lower
        if len(w) < 6 or not w.isalpha():
            return found
        for entries in self._index.values():
            for entry in entries:
                if len(entry.tokens) != 1 or len(entry.tokens[0]) < 6:
                    continue
                if any(edit_distance_le1(w, f) for f in entry.forms[0] if abs(len(f) - len(w)) <= 1):
                    found.append((entry, 0.8))
        return found

    def find(self, text: str, fuzzy: bool = True) -> list[dict]:
        """Упоминания сущностей: самые длинные непересекающиеся совпадения."""
        tokens = tokenize(text)
        spans = []
        for i in range(len(tokens)):
            for entry, conf in self._match_at(tokens, i, fuzzy):
                j = i + len(entry.tokens) - 1
                spans.append((i, j, entry, conf))
        # приоритет: длина, точность совпадения, основной идентификатор
        spans.sort(key=lambda s: (-(s[1] - s[0]), -s[3], not s[2].exact, s[0]))
        taken: set[int] = set()
        chosen = []
        seen_entities: set[int] = set()
        for i, j, entry, conf in spans:
            if any(k in taken for k in range(i, j + 1)):
                continue
            if entry.entity.addr in seen_entities:
                continue
            taken.update(range(i, j + 1))
            seen_entities.add(entry.entity.addr)
            end = tokens[j].end
            if entry.tail and text.startswith(entry.tail, end):
                end += len(entry.tail)
            chosen.append({
                "start": tokens[i].start,
                "end": end,
                "body": text[tokens[i].start:end],
                "value": entry.entity.value,
                "confidence": conf,
                "kb_entity": entry.entity,
            })
        chosen.sort(key=lambda m: m["start"])
        return chosen

    def delexicalize(self, text: str, spans: list[dict]) -> str:
        """Замена упоминаний сущностей их типом: «Какие симптомы у ent_concept_disease»."""
        out, pos = [], 0
        for s in sorted(spans, key=lambda s: s["start"]):
            out.append(text[pos:s["start"]])
            ent = s.get("kb_entity") or self.by_value.get(s["value"])
            out.append(f" {ent.type_token if ent else 'ent_entity'} ")
            pos = s["end"]
        out.append(text[pos:])
        return "".join(out)

    # ------------------------------------------------------------------ сериализация
    def to_json(self) -> dict:
        return {"source": self.source, "loaded_at": self.loaded_at, "entities": [asdict(e) for e in self.entities]}

    @classmethod
    def from_json(cls, data: dict) -> "Gazetteer":
        return cls([Entity(**e) for e in data["entities"]], data.get("source", "cache"), data.get("loaded_at", 0.0))

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str) -> "Gazetteer | None":
        try:
            with open(path, encoding="utf-8") as f:
                g = cls.from_json(json.load(f))
            g.source = "cache"
            return g
        except (OSError, ValueError, KeyError, TypeError):
            return None


# ---------------------------------------------------------------------- загрузка из sc-memory
def load_from_sc_memory(url: str, timeout: float = 20.0) -> Gazetteer:
    """Читает множество concept_wit_entity из sc-memory через sc-server (py-sc-client)."""
    from sc_client import client
    from sc_client.constants import sc_type
    from sc_client.models import ScIdtfResolveParams, ScTemplate

    if client.is_connected():
        client.disconnect()
    client.connect(url)
    if not client.is_connected():
        raise ConnectionError(f"sc-server {url} недоступен")
    try:
        names = ["concept_wit_entity", "nrel_main_idtf", "nrel_idtf", "nrel_system_identifier",
                 "lang_ru", "lang_en", "nrel_inclusion"]
        kn = dict(zip(names, client.resolve_keynodes(*[ScIdtfResolveParams(idtf=n, type=None) for n in names])))
        if not kn["concept_wit_entity"].is_valid():
            raise LookupError("в базе знаний нет concept_wit_entity")

        def members() -> list:
            t = ScTemplate()
            t.triple(kn["concept_wit_entity"], sc_type.VAR_PERM_POS_ARC, (sc_type.VAR_NODE, "_e"))
            return [r.get("_e") for r in client.search_by_template(t)]

        def idtfs(rel: str, lang: str | None) -> list[tuple]:
            t = ScTemplate()
            t.triple(kn["concept_wit_entity"], sc_type.VAR_PERM_POS_ARC, (sc_type.VAR_NODE, "_e"))
            t.quintuple("_e", sc_type.VAR_COMMON_ARC, (sc_type.VAR_NODE_LINK, "_l"), sc_type.VAR_PERM_POS_ARC, kn[rel])
            if lang:
                t.triple(kn[lang], sc_type.VAR_PERM_POS_ARC, "_l")
            res = client.search_by_template(t)
            if not res:
                return []
            contents = client.get_link_content(*[r.get("_l") for r in res])
            return [(r.get("_e").value, str(c.data)) for r, c in zip(res, contents)]

        def sys_idtf_one(a) -> str:
            t = ScTemplate()
            t.quintuple(a, sc_type.VAR_COMMON_ARC, (sc_type.VAR_NODE_LINK, "_l"), sc_type.VAR_PERM_POS_ARC,
                        kn["nrel_system_identifier"])
            res = client.search_by_template(t)
            return str(client.get_link_content(res[0].get("_l"))[0].data) if res else ""

        def main_ru_one(a) -> str:
            t = ScTemplate()
            t.quintuple(a, sc_type.VAR_COMMON_ARC, (sc_type.VAR_NODE_LINK, "_l"), sc_type.VAR_PERM_POS_ARC,
                        kn["nrel_main_idtf"])
            t.triple(kn["lang_ru"], sc_type.VAR_PERM_POS_ARC, "_l")
            res = client.search_by_template(t)
            return str(client.get_link_content(res[0].get("_l"))[0].data) if res else ""

        addrs = members()
        types = client.get_elements_types(*addrs) if addrs else []
        ents: dict[int, Entity] = {}
        for a, ty in zip(addrs, types):
            v = ty.value
            kind = ("class" if v & NODE_CLASS == NODE_CLASS else
                    "relation" if v & NODE_NON_ROLE == NODE_NON_ROLE else
                    "role" if v & NODE_ROLE == NODE_ROLE else "instance")
            ents[a.value] = Entity(addr=a.value, value="", kind=kind)

        for rel, lang, kind in [("nrel_main_idtf", "lang_ru", "main"), ("nrel_idtf", "lang_ru", "idtf"),
                                ("nrel_main_idtf", "lang_en", "main"), ("nrel_idtf", "lang_en", "idtf")]:
            for addr, text in idtfs(rel, lang):
                e = ents.get(addr)
                if e is None or not text.strip():
                    continue
                e.names.append([text.strip(), lang[-2:], kind])
                if rel == "nrel_main_idtf" and lang == "lang_ru" and not e.value:
                    e.value = text.strip()

        # Классы экземпляров и иерархия включения — для типа сущности (ветки иерархии).
        t = ScTemplate()
        t.triple(kn["concept_wit_entity"], sc_type.VAR_PERM_POS_ARC, (sc_type.VAR_NODE, "_e"))
        t.triple((sc_type.VAR_NODE_CLASS, "_c"), sc_type.VAR_PERM_POS_ARC, "_e")
        member_of: dict[int, set[int]] = {}
        class_addrs = {}
        for r in client.search_by_template(t):
            c = r.get("_c")
            if c.value == kn["concept_wit_entity"].value:
                continue
            member_of.setdefault(r.get("_e").value, set()).add(c.value)
            class_addrs[c.value] = c

        t = ScTemplate()
        t.quintuple((sc_type.VAR_NODE_CLASS, "_sup"), sc_type.VAR_COMMON_ARC, (sc_type.VAR_NODE_CLASS, "_sub"),
                    sc_type.VAR_PERM_POS_ARC, kn["nrel_inclusion"])
        parent: dict[int, set[int]] = {}
        for r in client.search_by_template(t):
            parent.setdefault(r.get("_sub").value, set()).add(r.get("_sup").value)
            class_addrs[r.get("_sub").value] = r.get("_sub")
            class_addrs[r.get("_sup").value] = r.get("_sup")

        def roots(c: int, seen=None) -> set[int]:
            seen = seen or set()
            if c in seen:
                return set()
            seen.add(c)
            ps = parent.get(c)
            if not ps:
                return {c}
            out = set()
            for p in ps:
                out |= roots(p, seen)
            return out

        # Системные идентификаторы сущностей и их классов — двумя шаблонными запросами.
        sys_of: dict[int, str] = {a: v for a, v in idtfs("nrel_system_identifier", None)}
        t = ScTemplate()
        t.triple(kn["concept_wit_entity"], sc_type.VAR_PERM_POS_ARC, (sc_type.VAR_NODE, "_e"))
        t.triple((sc_type.VAR_NODE_CLASS, "_c"), sc_type.VAR_PERM_POS_ARC, "_e")
        t.quintuple("_c", sc_type.VAR_COMMON_ARC, (sc_type.VAR_NODE_LINK, "_l"), sc_type.VAR_PERM_POS_ARC,
                    kn["nrel_system_identifier"])
        res = client.search_by_template(t)
        if res:
            for r, c in zip(res, client.get_link_content(*[r.get("_l") for r in res])):
                sys_of[r.get("_c").value] = str(c.data)
        # Служебные классы NIKA/OSTIS не являются ветками предметной области.
        service = {"class", "sc_node_class", "concept_wit_entity", "concept_entity_possible_class"}
        root_cache: dict[int, str] = {}
        top_names: dict[str, str] = {}
        for e in ents.values():
            start = {e.addr} if e.kind == "class" else member_of.get(e.addr, set())
            e.classes = sorted({sys_of.get(c, "") for c in member_of.get(e.addr, set())} - service - {""})
            tops = set()
            for c in start:
                tops |= roots(c)
            named = []
            for c in tops:
                if c not in root_cache:
                    root_cache[c] = sys_of.get(c) or sys_idtf_one(class_addrs.get(c) or c)
                if root_cache[c] and root_cache[c] not in service:
                    named.append((root_cache[c], c))
            if named:
                e.top, c = sorted(named)[0]
                if e.top not in top_names:
                    top_names[e.top] = main_ru_one(class_addrs[c]) if c in class_addrs else ""
                e.top_name = top_names[e.top]
        for e in ents.values():
            e.sys_idtf = sys_of.get(e.addr, "")

        result = [e for e in ents.values() if e.value]
        return Gazetteer(result, source=url, loaded_at=time.time())
    finally:
        client.disconnect()
