"""Оценка качества классификатора без запуска сервиса.

    python3 evaluate.py [--kb ../../knowledge-base] [--sc ws://localhost:8090] [--domain section_...] [--json out.json]

Словарь сущностей берётся из sc-memory (если sc-server доступен) или из кэша
wit-local/data/gazetteer.json. Печатает:
  * 5-кратную перекрёстную проверку на обучающих фразах;
  * качество на валидационной (dev) и итоговой тестовой (test) выборках, по всем
    областям и по выбранной (--domain);
  * ошибки распознавания.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from app import dataset as dataset_mod  # noqa: E402
from app.gazetteer import Gazetteer, load_from_sc_memory  # noqa: E402
from app.nlu import NLU  # noqa: E402


def table(m: dict) -> str:
    lines = [f"  фраз: {m['n']}, точность намерения: {m['intent_accuracy']:.3f}, macro-F1: {m['intent_macro_f1']:.3f}, "
             f"сущности (точное совпадение набора): {m['entity_accuracy']:.3f}"
             + (f", признак wit$sentiment: {m['trait_accuracy']:.3f}" if m.get("trait_accuracy") is not None else "")]
    for k, v in sorted(m["per_intent"].items()):
        if v["support"]:
            lines.append(f"    {k:28s} P={v['precision']:.2f} R={v['recall']:.2f} F1={v['f1']:.2f} n={v['support']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", default=os.path.join(HERE, "..", "..", "knowledge-base"))
    ap.add_argument("--sc", default="ws://localhost:8090")
    ap.add_argument("--cache", default=os.path.join(HERE, "..", "data", "gazetteer.json"))
    ap.add_argument("--domain", default=None, help="каталог extra/<domain> для отдельной оценки")
    ap.add_argument("--json", default=None)
    ap.add_argument("--no-cv", action="store_true")
    ap.add_argument("--splits", default="dev", help="какие выборки оценивать: dev, test или dev,test")
    a = ap.parse_args()

    try:
        g = load_from_sc_memory(a.sc)
        g.save(a.cache)
        print(f"словарь: {len(g.entities)} сущностей из {a.sc}")
    except Exception as exc:
        g = Gazetteer.load(a.cache)
        if g is None:
            sys.exit(f"sc-server недоступен ({exc}) и кэша словаря нет")
        print(f"словарь: {len(g.entities)} сущностей из кэша (sc-server: {exc})")

    ds = dataset_mod.load(a.kb)
    nlu = NLU()
    nlu.fit(ds, g)
    print(f"обучено: {len(ds.train)} фраз, {len(ds.intents)} намерений, тестовых фраз: {len(ds.test)}")
    out = {}
    if not a.no_cv:
        cv = nlu.cross_validate()
        print(f"\nПерекрёстная проверка ({cv['folds']} блоков):\n" + table(cv))
        out["cv"] = {k: v for k, v in cv.items() if k != "rows"}
    for split in a.splits.split(","):
        part = [u for u in ds.test if u.split == split]
        if not part:
            continue
        m = nlu.evaluate(part)
        name = {"dev": "Валидационная выборка", "test": "Итоговая тестовая выборка"}[split]
        print(f"\n{name}, все области:\n" + table(m))
        out[split] = m
        if a.domain:
            dm = nlu.evaluate([u for u in part if u.source == a.domain])
            print(f"\n{name}, {a.domain}:\n" + table(dm))
            out[split + "_domain"] = dm
        print(f"\nОшибки ({name.lower()}):")
        for r in m["errors"]:
            print(f"  «{r['text']}»: {r['gold']} → {r['pred']}; сущности {r['gold_entities']} → {r['pred_entities']}")
        for r in m["rows"]:
            for t, (g_, p_) in r.get("traits", {}).items():
                if g_ != p_:
                    print(f"  признак {t}: «{r['text']}»: {g_} → {p_}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
