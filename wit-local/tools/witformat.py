"""Помощники для генераторов обучающих фраз: склонение названий и запись экспорта в формате Wit.ai.

Фразы строятся по шаблонам вида «Какие симптомы у {e:gent}?»: вместо {e:gent}
подставляется название понятия в нужном падеже, а позиция подстановки
сохраняется как размеченная сущность (start/end/body/value) — так же, как её
разметил бы человек в разделе Understanding на wit.ai.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil

import pymorphy3

morph = pymorphy3.MorphAnalyzer()

CASES = {"nomn", "gent", "datv", "accs", "ablt", "loct"}


def _keep_case(src: str, dst: str) -> str:
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[:1].isupper():
        return dst[:1].upper() + dst[1:]
    return dst


def _inflect_word(word: str, case: str, want: set[str] | None = None, pos: tuple = ("NOUN",)) -> str | None:
    for p in morph.parse(word.lower()):
        if p.tag.POS in pos and "nomn" in p.tag and (not want or want <= p.tag.grammemes | {p.tag.number or ""}):
            f = p.inflect({case} | (want or set()))
            if f:
                return _keep_case(word, f.word)
    return None


# False — названия с заглавной буквы считаются торговыми и не склоняются («Комирнати»); для имён собственных,
# которые склоняются («Марс», «Луна»), генератор устанавливает True.
INFLECT_CAPITALIZED = False


def _is_brand(phrase: str) -> bool:
    """Торговые названия («Комирнати», «Ваксигрип Тетра»), аббревиатуры и латиница не склоняются."""
    if not re.search(r"[а-яё]", phrase.lower()) or phrase.split(" ")[0].isupper():
        return True
    return not INFLECT_CAPITALIZED and phrase[:1].isupper() and not phrase[:2].isupper()


def _head(words: list[str]):
    """Главное слово: первое слово, наиболее вероятный разбор которого — существительное в им. п."""
    cands = []
    for i, w in enumerate(words):
        if re.search(r"[0-9A-Za-z(«\"]", w):
            continue
        last = w.split("-")[-1].lower()
        ps = morph.parse(last)
        if ps and ps[0].tag.POS == "NOUN" and "nomn" in ps[0].tag:
            return i, ps[0]
        nouns = [p for p in ps if p.tag.POS == "NOUN" and "nomn" in p.tag]
        if nouns:
            cands.append((i, nouns[0]))
    return cands[-1] if cands else None


def inflect(phrase: str, case: str, overrides: dict | None = None) -> str:
    """Склоняет именную группу в именительном падеже: главное существительное и согласованные
    с ним прилагательные слева. Всё, что правее главного слова («инфаркт миокарда»,
    «боль за грудиной»), не меняется. Торговые названия не склоняются.
    Падеж можно дополнить числом: "nomn+plur" — «вирусы», "gent+plur" — «вирусов»."""
    case, _, want_number = case.partition("+")
    if case == "nomn" and not want_number:
        return phrase
    if overrides and (phrase, case) in overrides:
        return overrides[(phrase, case)]
    if _is_brand(phrase):
        return phrase
    words = phrase.split(" ")
    head = _head(words)
    if head is None:
        return phrase
    hi, hp = head
    number = want_number or hp.tag.number or "sing"
    gender = hp.tag.gender
    animacy = hp.tag.animacy or "inan"
    out = list(words)
    # главное слово (у составных через дефис склоняются все части-существительные: врач-терапевт)
    parts = words[hi].split("-")
    new_parts = []
    for part in parts:
        f = None
        if re.fullmatch(r"[а-яё]+", part.lower()) and not (part.isupper() and len(part) > 1):
            for p in morph.parse(part.lower()):
                if p.tag.POS == "NOUN" and "nomn" in p.tag:
                    g = p.inflect({case, number})
                    if g:
                        f = _keep_case(part, g.word)
                    break
        new_parts.append(f or part)
    out[hi] = "-".join(new_parts)
    # согласованные определения слева от главного слова (у «РНК-содержащий» склоняется последняя часть)
    for i in range(hi):
        w = words[i]
        if not re.search(r"[А-Яа-яЁё]$", w):
            continue
        prefix, _, last = w.rpartition("-")
        for p in morph.parse(last.lower()):
            if p.tag.POS in ("ADJF", "PRTF", "NUMR") and "nomn" in p.tag:
                want = {case, number} | ({gender} if number == "sing" and gender else set())
                if case == "accs" and (number == "plur" or gender == "masc"):
                    want |= {animacy}
                f = p.inflect(want)
                if f:
                    new = _keep_case(last, f.word)
                    out[i] = f"{prefix}-{new}" if prefix else new
                break
    return " ".join(out)


# ---------------------------------------------------------------------- шаблоны → размеченные фразы
SLOT_RE = re.compile(r"\{(\w+)(?::([\w+]+))?\}")


def render(template: str, slots: dict[str, str], values: dict[str, str] | None = None,
           overrides: dict | None = None) -> dict:
    """«Какие симптомы у {d:gent}?» + {"d": "грипп"} → текст и размеченные сущности."""
    text, ents, pos = "", [], 0
    for m in SLOT_RE.finditer(template):
        text += template[pos:m.start()]
        name, case = m.group(1), m.group(2) or "nomn"
        base = slots[name]
        surface = inflect(base, case, overrides)
        # «о» перед гласной → «об»: «об инфаркте», «об отношении»
        if re.search(r"(^|\s)[Оо] $", text) and surface[:1].lower() in "аоуэиы":
            text = text[:-1] + "б "
        start = len(text)
        text += surface
        ents.append({"entity": "rrel_entity:rrel_entity", "start": start, "end": len(text),
                     "body": surface, "value": (values or {}).get(name, base), "entities": []})
        pos = m.end()
    text += template[pos:]
    text = text[:1].upper() + text[1:]
    for e in ents:
        e["body"] = text[e["start"]:e["end"]]
    return {"text": text, "entities": ents}


POLITE_PREFIX = ["Подскажите, пожалуйста, ", "Скажите, пожалуйста, ", "Будьте добры, подскажите, ",
                 "Извините, а ", "Не могли бы вы подсказать, ", "Здравствуйте! Подскажите, "]
POLITE_SUFFIX = [", пожалуйста", ", буду благодарна", ", заранее спасибо", ", спасибо"]
RUDE_PREFIX = ["Ну и ", "Слушай, быстро: ", "Отвечай уже, ", "Ну давай, говори, ", "Эй, ",
               "Сколько можно ждать, "]
RUDE_SUFFIX = [", долго ещё ждать?", ", отвечай быстрее", ", ну же", "?! Не тормози"]


def with_coloring(item: dict, coloring: str, rnd: random.Random) -> dict:
    """Добавляет вежливую или грубую рамку и сдвигает разметку сущностей."""
    text, ents = item["text"], [dict(e) for e in item["entities"]]
    if coloring == "neutral":
        return {"text": text, "entities": ents, "coloring": coloring}
    pre = rnd.choice(POLITE_PREFIX if coloring == "positive" else RUDE_PREFIX)
    use_suffix = rnd.random() < 0.4
    if use_suffix:
        suf = rnd.choice(POLITE_SUFFIX if coloring == "positive" else RUDE_SUFFIX)
        body = text.rstrip("?.!")
        end_punct = text[len(body):] if not suf.endswith("?") else ""
        text = body + suf + (end_punct if coloring == "positive" else "")
        if coloring == "positive" and not text.endswith(("?", ".", "!")):
            text += "?"
        shift = 0
    else:
        starts_with_entity = any(e["start"] == 0 for e in ents)
        first_word = text.split(" ")[0]
        acronym = len(first_word) > 1 and first_word.isupper()
        first = text[:1] if acronym or starts_with_entity else text[:1].lower()
        text = pre + first + text[1:]
        shift = len(pre)
    for e in ents:
        e["start"] += shift
        e["end"] += shift
    return {"text": text, "entities": ents, "coloring": coloring}


# ---------------------------------------------------------------------- запись экспорта
def write_export(out_dir: str, app_name: str, intents: list[str], utterances: list[dict],
                 test: list[dict] | None = None, entity_keywords: dict[str, list[str]] | None = None,
                 traits: dict[str, list[str]] | None = None, dev: list[dict] | None = None) -> None:
    """Записывает каталог classification/ в структуре экспорта Wit.ai."""
    for sub in ("intents", "entities", "traits", "utterances", "test"):
        shutil.rmtree(os.path.join(out_dir, sub), ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)

    def dump(rel: str, data) -> None:
        path = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    dump("app.json", {"name": app_name, "lang": "ru", "private": True,
                      "description": "Экспорт обучающих данных локального Wit.ai-совместимого классификатора"})
    for i in intents:
        dump(f"intents/{i}.json", {"name": i})
    if entity_keywords is not None:
        dump("entities/rrel_entity.json", {
            "name": "rrel_entity", "roles": ["rrel_entity"], "lookups": ["keywords", "free-text"],
            "keywords": [{"keyword": k, "synonyms": sorted(set([k] + v))} for k, v in sorted(entity_keywords.items())]})
    for name, values in (traits or {}).items():
        dump(f"traits/{name}.json", {"name": name, "values": [{"value": v} for v in values]})

    def wit(u: dict) -> dict:
        d = {"text": u["text"], "intent": u.get("intent"), "entities": u.get("entities", []),
             "traits": [{"trait": k, "value": v} for k, v in u.get("traits", {}).items()]}
        if d["intent"] in (None, "none"):
            d.pop("intent")
        return d

    dump("utterances/utterances-1.json", {"utterances": [wit(u) for u in utterances]})
    if dev:
        dump("test/utterances-dev.json", {"utterances": [wit(u) for u in dev]})
    if test:
        dump("test/utterances-test.json", {"utterances": [wit(u) for u in test]})
