"""Обучающие фразы в формате экспорта Wit.ai.

Каталог classification/ устроен так же, как архив, который Wit.ai выдаёт по
Settings → Export your data:

    classification/
      app.json                   название приложения, язык
      intents/<name>.json        {"name": ...}
      entities/<name>.json       {"name", "roles", "lookups", "keywords": [{"keyword", "synonyms"}]}
      traits/<name>.json         {"name", "values": [{"value"}]}
      utterances/*.json          {"utterances": [{"text", "intent", "entities": [...], "traits": [...]}]}
      test/utterances-dev.json   валидационная выборка (по ней настраивались шаблоны и параметры)
      test/utterances-test.json  итоговая тестовая выборка (при настройке не использовалась)

Отличие от экспорта Wit.ai одно: у размеченной сущности кроме body хранится value —
основной идентификатор элемента базы знаний, к которому относится фрагмент.
Сервис читает все каталоги knowledge-base/extra/*/classification, поэтому один
классификатор обслуживает все подключённые предметные области.
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field


@dataclass
class Utterance:
    text: str
    intent: str                                   # "none" — фраза вне всех намерений
    entities: list[dict] = field(default_factory=list)   # {"entity", "start", "end", "body", "value"}
    traits: dict[str, str] = field(default_factory=dict)
    source: str = ""
    split: str = "train"                          # train | dev | test


@dataclass
class Dataset:
    train: list[Utterance] = field(default_factory=list)
    test: list[Utterance] = field(default_factory=list)
    intents: set[str] = field(default_factory=set)
    traits: dict[str, list[str]] = field(default_factory=dict)
    apps: list[dict] = field(default_factory=list)


def _read_utterances(path: str, domain: str, split: str = "train") -> list[Utterance]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for u in data.get("utterances", []):
        out.append(Utterance(
            text=u["text"],
            intent=u.get("intent") or "none",
            entities=[dict(e) for e in u.get("entities", [])],
            traits={t["trait"]: t["value"] for t in u.get("traits", [])},
            source=domain,
            split=split,
        ))
    return out


def load(kb_dir: str) -> Dataset:
    ds = Dataset()
    for cls_dir in sorted(glob.glob(os.path.join(kb_dir, "extra", "*", "classification"))):
        domain = os.path.basename(os.path.dirname(cls_dir))
        app = {"domain": domain, "path": cls_dir}
        try:
            with open(os.path.join(cls_dir, "app.json"), encoding="utf-8") as f:
                app.update(json.load(f))
        except OSError:
            pass
        ds.apps.append(app)
        for p in sorted(glob.glob(os.path.join(cls_dir, "intents", "*.json"))):
            with open(p, encoding="utf-8") as f:
                ds.intents.add(json.load(f)["name"])
        for p in sorted(glob.glob(os.path.join(cls_dir, "traits", "*.json"))):
            with open(p, encoding="utf-8") as f:
                t = json.load(f)
            vals = ds.traits.setdefault(t["name"], [])
            for v in t.get("values", []):
                if v["value"] not in vals:
                    vals.append(v["value"])
        for p in sorted(glob.glob(os.path.join(cls_dir, "utterances", "*.json"))):
            ds.train.extend(_read_utterances(p, domain))
        for p in sorted(glob.glob(os.path.join(cls_dir, "test", "*.json"))):
            split = "dev" if p.endswith("-dev.json") else "test"
            ds.test.extend(_read_utterances(p, domain, split))
    ds.intents |= {u.intent for u in ds.train if u.intent != "none"}
    return ds
