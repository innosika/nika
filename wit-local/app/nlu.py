"""Классификатор намерений, признаков и выделение сущностей.

Порядок разбора сообщения (повторяет то, что делает Wit.ai):
  1. сущности ищутся словарём, построенным по базе знаний (gazetteer.py);
  2. найденные упоминания заменяются типом сущности — максимальным классом её ветки
     иерархии: «Какие симптомы у гриппа?» → «какие симптомы у ent_concept_disease»;
     так модель учит конструкцию вопроса, а не конкретные названия, и новое понятие,
     добавленное в базу знаний, распознаётся без переобучения;
  3. намерение (intent) и признак (trait) определяются логистической регрессией
     по TF-IDF словесных n-грамм лемм и символьных n-грамм (устойчивость к опечаткам);
  4. если уверенность ниже порога или предсказан класс «none», намерение не
     возвращается — NIKA отнесёт сообщение к concept_not_classified_by_intent_message.
"""
from __future__ import annotations

import collections
import time

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import FeatureUnion, Pipeline

from .dataset import Dataset, Utterance
from .gazetteer import Gazetteer
from .text import lemma, normalize, tokenize

ENTITY_KEY = "rrel_entity:rrel_entity"


def _word_analyzer(text: str) -> list[str]:
    toks = [t.text if t.text.startswith("ent_") else lemma(t.text) for t in tokenize(text)]
    toks = [t for t in toks if t != "*"]
    # Структурный признак — какие типы сущностей встретились вместе: вопрос
    # «Помогает ли ибупрофен при гриппе?» отличается от «Опасен ли ибупрофен?»
    # именно наличием второй сущности-заболевания.
    types = sorted({t for t in toks if t.startswith("ent_")})
    structure = ["ENTS=" + ("+".join(types) if types else "none")]
    return toks + [f"{a} {b}" for a, b in zip(toks, toks[1:])] + structure


def _features() -> FeatureUnion:
    return FeatureUnion([
        ("words", TfidfVectorizer(analyzer=_word_analyzer, sublinear_tf=True)),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True,
                                  preprocessor=lambda s: normalize(s))),
    ])


def _clf(class_weight="balanced", C: float = 10.0) -> LogisticRegression:
    return LogisticRegression(C=C, max_iter=5000, class_weight=class_weight)


def intent_weights(y: list[str], none_factor: float) -> dict[str, float]:
    """Сбалансированные веса классов; вес «none» дополнительно умножается на none_factor.

    Фраз «Что такое …» в обучении в разы больше, чем фраз других намерений, поэтому
    классы взвешиваются обратно их частоте. Класс «none» при этом не должен
    перетягивать непривычные, но осмысленные формулировки вопросов, поэтому его вес
    уменьшен."""
    cnt = collections.Counter(y)
    n, k = len(y), len(cnt)
    w = {c: n / (k * v) for c, v in cnt.items()}
    if "none" in w:
        w["none"] *= none_factor
    return w


class NLU:
    def __init__(self, threshold: float = 0.35, none_factor: float = 1.0, C: float = 10.0):
        self.threshold = threshold
        self.none_factor = none_factor
        self.C = C
        self.gazetteer = Gazetteer()
        self.intent_model: Pipeline | None = None
        self.trait_models: dict[str, Pipeline] = {}
        self.trait_defaults: dict[str, str] = {}
        self.context_lemmas: set[str] = set()
        self.dataset: Dataset | None = None
        self.trained_at = 0.0
        self.metrics: dict = {}

    # ------------------------------------------------------------------ обучение
    def _delex_train(self, u: Utterance) -> str:
        """Размеченные сущности плюс то, что словарь найдёт при распознавании, —
        чтобы обучающий текст преобразовывался так же, как входящее сообщение."""
        spans = [dict(e) for e in u.entities]
        for m in self.entities(u.text):
            if not any(m["start"] < e["end"] and e["start"] < m["end"] for e in u.entities):
                spans.append(m)
        return self.gazetteer.delexicalize(u.text, spans)

    def _context(self, utts: list[Utterance]) -> set[str]:
        """Леммы, которые в обучающих фразах встречаются вне размеченных сущностей.

        Это слова конструкции вопроса («симптом», «врач», «лечение»). Если совпадение с
        понятием базы знаний состоит только из таких слов, а в сообщении есть и другая
        сущность, оно не выделяется: в «Какие симптомы у гриппа?» сущность — грипп, а не
        симптом; в «Назови естественные спутники Сатурна» — Сатурн.
        """
        cnt = collections.Counter()
        for u in utts:
            covered = [(e["start"], e["end"]) for e in u.entities]
            for t in tokenize(u.text):
                if not any(s <= t.start < e for s, e in covered):
                    cnt[lemma(t.text)] += 1
        return {w for w, n in cnt.items() if n >= 3}

    def fit(self, dataset: Dataset, gazetteer: Gazetteer) -> None:
        self.dataset = dataset
        self.gazetteer = gazetteer
        utts = dataset.train
        self.context_lemmas = self._context(utts)
        X = [self._delex_train(u) for u in utts]
        y = [u.intent for u in utts]
        clf = _clf(intent_weights(y, self.none_factor), self.C)
        self.intent_model = Pipeline([("f", _features()), ("clf", clf)]).fit(X, y)
        self.trait_models, self.trait_defaults = {}, {}
        for trait, values in dataset.traits.items():
            default = "neutral" if "neutral" in values else values[0]
            self.trait_defaults[trait] = default
            ty = [u.traits.get(trait, default) for u in utts]
            if len(set(ty)) > 1:
                self.trait_models[trait] = Pipeline([("f", _features()), ("clf", _clf())]).fit(X, ty)
        self.trained_at = time.time()

    # ------------------------------------------------------------------ разбор
    def entities(self, text: str) -> list[dict]:
        found = self.gazetteer.find(text)
        if len(found) > 1:
            # Приложение «класс + экземпляр этого класса» («чёрной дыры Стрелец A*»): выделяется экземпляр.
            drop = set()
            for a, b in zip(found, found[1:]):
                ea, eb = a["kb_entity"], b["kb_entity"]
                if ea.kind == "class" and not text[a["end"]:b["start"]].strip() and ea.sys_idtf in eb.classes:
                    drop.add(id(a))
            found = [m for m in found if id(m) not in drop]
        if len(found) > 1:
            keep = []
            for m in found:
                toks = tokenize(m["body"])
                # все слова совпадения — слова конструкции вопроса («симптомы», «естественные спутники»)
                if toks and all(lemma(t.text) in self.context_lemmas for t in toks):
                    continue
                keep.append(m)
            found = keep or found
        return found

    def parse(self, text: str, explain: bool = False) -> dict:
        spans = self.entities(text)
        delex = self.gazetteer.delexicalize(text, spans)
        result: dict = {"text": text, "intents": [], "entities": {}, "traits": {}}
        if self.intent_model is not None:
            proba = self.intent_model.predict_proba([delex])[0]
            classes = self.intent_model.classes_
            order = np.argsort(-proba)
            best, conf = classes[order[0]], float(proba[order[0]])
            if best != "none" and conf >= self.threshold:
                result["intents"].append({"id": best, "name": best, "confidence": round(conf, 4)})
            if explain:
                result["_alternatives"] = [{"name": classes[i], "confidence": round(float(proba[i]), 4)}
                                           for i in order[:5]]
        if spans:
            result["entities"][ENTITY_KEY] = [{
                "id": s["kb_entity"].sys_idtf or str(s["kb_entity"].addr),
                "name": "rrel_entity", "role": "rrel_entity",
                "start": s["start"], "end": s["end"], "body": s["body"], "value": s["value"],
                "confidence": s["confidence"], "type": "value", "entities": {},
                "kb": {"sys_idtf": s["kb_entity"].sys_idtf, "kind": s["kb_entity"].kind,
                       "classes": s["kb_entity"].classes, "top": s["kb_entity"].top, "top_name": s["kb_entity"].top_name},
            } for s in spans]
        for trait, default in self.trait_defaults.items():
            model = self.trait_models.get(trait)
            if model is None:
                value, conf = default, 1.0
            else:
                p = model.predict_proba([delex])[0]
                i = int(np.argmax(p))
                value, conf = model.classes_[i], float(p[i])
            result["traits"][trait] = [{"id": f"{trait}:{value}", "value": value, "confidence": round(conf, 4)}]
        if explain:
            result["_delexicalized"] = " ".join(delex.split())
        return result

    # ------------------------------------------------------------------ оценка качества
    def evaluate(self, utts: list[Utterance]) -> dict:
        rows = []
        for u in utts:
            r = self.parse(u.text)
            pred = r["intents"][0]["name"] if r["intents"] else "none"
            gold_e = sorted(e.get("value", e.get("body")) for e in u.entities)
            pred_e = sorted(e["value"] for e in r["entities"].get(ENTITY_KEY, []))
            row = {"text": u.text, "gold": u.intent, "pred": pred,
                   "gold_entities": gold_e, "pred_entities": pred_e,
                   "intent_ok": pred == u.intent, "entities_ok": gold_e == pred_e}
            for trait, value in u.traits.items():
                row.setdefault("traits", {})[trait] = (value, r["traits"].get(trait, [{}])[0].get("value"))
            rows.append(row)
        return summarize(rows)

    def cross_validate(self, folds: int = 5, seed: int = 0) -> dict:
        """k-кратная перекрёстная проверка на обучающих фразах (разбор — полный, со словарём)."""
        assert self.dataset is not None
        utts = self.dataset.train
        y = [u.intent for u in utts]
        min_count = min(collections.Counter(y).values())
        k = max(2, min(folds, min_count))
        skf = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed)
        rows = []
        full = self.dataset
        for tr, te in skf.split(utts, y):
            sub = NLU(self.threshold, self.none_factor, self.C)
            sub.fit(Dataset(train=[utts[i] for i in tr], intents=full.intents, traits=full.traits), self.gazetteer)
            rows.extend(sub.evaluate([utts[i] for i in te])["rows"])
        res = summarize(rows)
        res["folds"] = k
        return res


def summarize(rows: list[dict]) -> dict:
    labels = sorted({r["gold"] for r in rows} | {r["pred"] for r in rows})
    per = {}
    for lab in labels:
        tp = sum(r["gold"] == lab and r["pred"] == lab for r in rows)
        fp = sum(r["gold"] != lab and r["pred"] == lab for r in rows)
        fn = sum(r["gold"] == lab and r["pred"] != lab for r in rows)
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * rc / (p + rc) if p + rc else 0.0
        per[lab] = {"precision": round(p, 4), "recall": round(rc, 4), "f1": round(f, 4), "support": tp + fn}
    gold_labels = [lab for lab in labels if per[lab]["support"]]
    n = len(rows) or 1
    trait_rows = [v for r in rows for v in r.get("traits", {}).values()]
    return {
        "n": len(rows),
        "intent_accuracy": round(sum(r["intent_ok"] for r in rows) / n, 4),
        "intent_macro_f1": round(sum(per[l]["f1"] for l in gold_labels) / (len(gold_labels) or 1), 4),
        "entity_accuracy": round(sum(r["entities_ok"] for r in rows) / n, 4),
        "trait_accuracy": round(sum(a == b for a, b in trait_rows) / len(trait_rows), 4) if trait_rows else None,
        "per_intent": per,
        "errors": [r for r in rows if not (r["intent_ok"] and r["entities_ok"])],
        "rows": rows,
    }
