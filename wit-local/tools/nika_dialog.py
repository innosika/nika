"""Диалог с NIKA из командной строки — так же, как это делает веб-интерфейс (порт 3033).

Для каждой фразы создаётся действие action_reply_to_message (rrel_1 — sc-ссылка с текстом,
rrel_2 — диалог, nrel_authors — пользователь), после его завершения из sc-памяти
читаются: ответ системы, классы, к которым отнесено сообщение, выделенные сущности
(роль rrel_entity) и признак. То есть проверяется вся цепочка: классификация
(правилами базы знаний или сервисом wit-local) → правило ответа → фраза ответа.

    python3 nika_dialog.py "Привет" "Что такое грипп?"            печать таблицы
    python3 nika_dialog.py --file phrases.txt --json out.json      фразы из файла, результат в JSON
    python3 nika_dialog.py --name msg_symptoms "Какие симптомы у гриппа?"
        сообщению присваивается системный идентификатор — его можно открыть в sc-web:
        http://localhost:8000/?sys_id=msg_symptoms
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time

from sc_client import client
from sc_client.constants import sc_type
from sc_client.models import ScConstruction, ScIdtfResolveParams, ScLinkContent, ScLinkContentType, ScTemplate

KEYNODES = ["action", "action_initiated", "action_finished", "action_finished_successfully", "action_reply_to_message",
            "rrel_1", "rrel_2", "nrel_authors", "concept_text_file", "lang_ru", "concept_user", "concept_dialogue",
            "rrel_dialog_participant", "nrel_reply", "nrel_sc_text_translation", "rrel_entity", "nrel_main_idtf",
            "nrel_system_identifier", "concept_message", "concept_atomic_message"]
kn: dict = {}


# Узлы, которые веб-интерфейс создаёт при первом входе, если их ещё нет (resolveUserAgent.ts).
CREATE_IF_MISSING = {"concept_user": sc_type.CONST_NODE_CLASS, "concept_dialogue": sc_type.CONST_NODE_CLASS,
                     "rrel_dialog_participant": sc_type.CONST_NODE_ROLE}


def resolve():
    addrs = client.resolve_keynodes(*[ScIdtfResolveParams(idtf=k, type=CREATE_IF_MISSING.get(k)) for k in KEYNODES])
    kn.update(zip(KEYNODES, addrs))


def link_text(addr) -> str:
    return str(client.get_link_content(addr)[0].data)


def sys_idtf(addr) -> str:
    t = ScTemplate()
    t.quintuple(addr, sc_type.VAR_COMMON_ARC, (sc_type.VAR_NODE_LINK, "_l"), sc_type.VAR_PERM_POS_ARC,
                kn["nrel_system_identifier"])
    r = client.search_by_template(t)
    return link_text(r[0].get("_l")) if r else ""


def main_idtf(addr) -> str:
    t = ScTemplate()
    t.quintuple(addr, sc_type.VAR_COMMON_ARC, (sc_type.VAR_NODE_LINK, "_l"), sc_type.VAR_PERM_POS_ARC,
                kn["nrel_main_idtf"])
    t.triple(kn["lang_ru"], sc_type.VAR_PERM_POS_ARC, "_l")
    r = client.search_by_template(t)
    return link_text(r[0].get("_l")) if r else ""


def user_and_dialog():
    t = ScTemplate()
    t.triple(kn["concept_user"], sc_type.VAR_PERM_POS_ARC, (sc_type.VAR_NODE, "_user"))
    t.triple(kn["concept_dialogue"], sc_type.VAR_PERM_POS_ARC, (sc_type.VAR_NODE, "_dialog"))
    t.quintuple("_dialog", sc_type.VAR_PERM_POS_ARC, "_user", sc_type.VAR_PERM_POS_ARC, kn["rrel_dialog_participant"])
    r = client.search_by_template(t)
    if r:
        return r[0].get("_user"), r[0].get("_dialog")
    g = client.generate_by_template(t, {})
    return g.get("_user"), g.get("_dialog")


def plain(text: str) -> str:
    text = re.sub(r"<img[^>]*>", " [изображение] ", text)
    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(html.unescape(text).split())


def message_info(msg) -> dict:
    t = ScTemplate()
    t.triple((sc_type.VAR_NODE_CLASS, "_c"), sc_type.VAR_PERM_POS_ARC, msg)
    classes = sorted({sys_idtf(r.get("_c")) for r in client.search_by_template(t)} - {"", "concept_message"})
    t = ScTemplate()
    t.quintuple(msg, sc_type.VAR_PERM_POS_ARC, (sc_type.VAR_NODE, "_e"), sc_type.VAR_PERM_POS_ARC, kn["rrel_entity"])
    ents = []
    for r in client.search_by_template(t):
        e = r.get("_e")
        ents.append({"sys_idtf": sys_idtf(e), "main_idtf": main_idtf(e)})
    return {"classes": classes, "entities": ents}


def send(text: str, user, dialog, timeout: float = 40.0, name: str | None = None) -> dict:
    c = ScConstruction()
    c.generate_link(sc_type.CONST_NODE_LINK, ScLinkContent(text, ScLinkContentType.STRING), "link")
    link = client.generate_elements(c)[0]
    t = ScTemplate()
    t.triple(kn["action"], sc_type.VAR_PERM_POS_ARC, (sc_type.VAR_NODE, "_a"))
    t.triple(kn["action_reply_to_message"], sc_type.VAR_PERM_POS_ARC, "_a")
    t.quintuple("_a", sc_type.VAR_PERM_POS_ARC, link, sc_type.VAR_PERM_POS_ARC, kn["rrel_1"])
    t.quintuple("_a", sc_type.VAR_PERM_POS_ARC, dialog, sc_type.VAR_PERM_POS_ARC, kn["rrel_2"])
    t.quintuple("_a", sc_type.VAR_COMMON_ARC, user, sc_type.VAR_PERM_POS_ARC, kn["nrel_authors"])
    t.triple(kn["concept_text_file"], sc_type.VAR_PERM_POS_ARC, link)
    t.triple(kn["lang_ru"], sc_type.VAR_PERM_POS_ARC, link)
    action = client.generate_by_template(t, {}).get("_a")
    t0 = time.time()
    c = ScConstruction()
    c.generate_connector(sc_type.CONST_PERM_POS_ARC, kn["action_initiated"], action)
    client.generate_elements(c)

    done = ScTemplate()
    done.triple(kn["action_finished"], sc_type.VAR_PERM_POS_ARC, action)
    while not client.search_by_template(done):
        if time.time() - t0 > timeout:
            return {"text": text, "error": "истекло время ожидания ответа"}
        time.sleep(0.15)
    elapsed = time.time() - t0

    t = ScTemplate()
    t.quintuple((sc_type.VAR_NODE, "_t"), sc_type.VAR_COMMON_ARC, (sc_type.VAR_NODE, "_msg"), sc_type.VAR_PERM_POS_ARC,
                kn["nrel_sc_text_translation"])
    t.triple("_t", sc_type.VAR_PERM_POS_ARC, link)
    r = client.search_by_template(t)
    if not r:
        return {"text": text, "error": "сообщение не создано"}
    msg = r[0].get("_msg")
    out = {"text": text, "seconds": round(elapsed, 2), **message_info(msg)}
    t = ScTemplate()
    t.quintuple(msg, sc_type.VAR_COMMON_ARC, (sc_type.VAR_NODE, "_reply"), sc_type.VAR_PERM_POS_ARC, kn["nrel_reply"])
    t.quintuple((sc_type.VAR_NODE, "_t"), sc_type.VAR_COMMON_ARC, "_reply", sc_type.VAR_PERM_POS_ARC,
                kn["nrel_sc_text_translation"])
    t.triple("_t", sc_type.VAR_PERM_POS_ARC, (sc_type.VAR_NODE_LINK, "_l"))
    r = client.search_by_template(t)
    if r:
        raw = link_text(r[0].get("_l"))
        out["reply"] = plain(raw)
        out["reply_has_image"] = "<img" in raw
    else:
        out["reply"] = None
    if name:
        c = ScConstruction()
        c.generate_link(sc_type.CONST_NODE_LINK, ScLinkContent(name, ScLinkContentType.STRING), "l")
        idl = client.generate_elements(c)[0]
        c = ScConstruction()
        c.generate_connector(sc_type.CONST_COMMON_ARC, msg, idl, "arc")
        c.generate_connector(sc_type.CONST_PERM_POS_ARC, kn["nrel_system_identifier"], "arc")
        client.generate_elements(c)
        out["sys_idtf"] = name
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phrases", nargs="*")
    ap.add_argument("--file")
    ap.add_argument("--url", default="ws://localhost:8090")
    ap.add_argument("--json")
    ap.add_argument("--name", action="append", default=[], help="системный идентификатор сообщения (по порядку фраз)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    phrases = list(a.phrases)
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            phrases += [s.strip() for s in f if s.strip() and not s.startswith("#")]
    client.connect(a.url)
    resolve()
    user, dialog = user_and_dialog()
    results = []
    for i, p in enumerate(phrases):
        r = send(p, user, dialog, name=a.name[i] if i < len(a.name) else None)
        results.append(r)
        if not a.quiet:
            print(f"\n> {p}")
            if "error" in r:
                print(f"  ОШИБКА: {r['error']}")
                continue
            print(f"  классы:   {', '.join(r['classes'])}")
            print(f"  сущности: {', '.join(e['sys_idtf'] or e['main_idtf'] for e in r['entities']) or '—'}")
            print(f"  ответ ({r['seconds']} с): {r['reply']}")
    client.disconnect()
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
    return results


if __name__ == "__main__":
    sys.exit(0 if main() is not None else 1)
