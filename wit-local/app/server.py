"""Локальный Wit.ai-совместимый классификатор сообщений для NIKA.

Агент MessageTopicClassificationAgent отправляет текст сообщения запросом
GET <url>?q=<текст> с заголовком Authorization и разбирает JSON-ответ с полями
intents / entities / traits (см. WitAiClient.cpp). Этот сервис отвечает в том же
формате, поэтому для подключения достаточно указать его адрес в nika.ini:

    [wit-ai]
    url = http://wit-local:8095/message

Конфигурация — переменными окружения:
    KB_DIR            каталог knowledge-base (читаются extra/*/classification)
    SC_SERVER_URL     адрес sc-server для словаря сущностей (ws://problem-solver:8090)
    DATA_DIR          куда сохранять кэш словаря и метрики (/data)
    REFRESH_SECONDS   период сверки словаря с базой знаний (300)
    INTENT_THRESHOLD  минимальная уверенность намерения (0.35)
"""
from __future__ import annotations

import collections
import json
import logging
import os
import threading
import time

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from . import dataset as dataset_mod
from .gazetteer import Gazetteer, load_from_sc_memory
from .nlu import NLU

KB_DIR = os.environ.get("KB_DIR", "/kb")
SC_SERVER_URL = os.environ.get("SC_SERVER_URL", "ws://problem-solver:8090")
DATA_DIR = os.environ.get("DATA_DIR", "/data")
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "300"))
THRESHOLD = float(os.environ.get("INTENT_THRESHOLD", "0.35"))
CACHE = os.path.join(DATA_DIR, "gazetteer.json")
STATIC = os.path.join(os.path.dirname(__file__), "static")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("wit-local")

app = FastAPI(title="wit-local", description="Локальный Wit.ai-совместимый классификатор сообщений NIKA")


class State:
    def __init__(self) -> None:
        self.nlu = NLU(THRESHOLD)
        self.lock = threading.Lock()
        self.sc_status = "не подключались"
        self.metrics: dict = {}
        self.metrics_status = "не считались"
        self.history: collections.deque = collections.deque(maxlen=100)
        # сущности, переданные агентами через /api/entities: добавляются в любой словарь, построенный позже
        # (фоновое переобучение на словаре, прочитанном раньше, не должно их терять)
        self.pushed: dict = {}
        # момент начала обучения текущей модели: модель, начавшая обучаться раньше, не заменяет более свежую
        # (иначе фоновое обучение на старом кэше словаря после перезапуска затирает свежий словарь)
        self.model_started = 0.0


state = State()


def _signature(g: Gazetteer) -> tuple:
    return tuple(sorted((e.value, e.top, len(e.names)) for e in g.entities))


def with_pushed(g: Gazetteer) -> Gazetteer:
    """Словарь g плюс сущности, переданные агентами и ещё отсутствующие в нём."""
    known = {e.addr for e in g.entities}
    extra = [e for a, e in list(state.pushed.items()) if a not in known]
    return Gazetteer(g.entities + extra, g.source, g.loaded_at) if extra else g


def retrain(gazetteer: Gazetteer, reason: str) -> None:
    started = time.time()
    gazetteer = with_pushed(gazetteer)
    ds = dataset_mod.load(KB_DIR)
    nlu = NLU(THRESHOLD)
    t = time.time()
    nlu.fit(ds, gazetteer)
    with state.lock:
        if started < state.model_started:
            log.info("обучение (%s) устарело — модель, начавшая обучаться позже, уже готова", reason)
            return
        nlu.gazetteer = with_pushed(nlu.gazetteer)      # за время обучения агенты могли передать ещё сущности
        state.nlu = nlu
        state.model_started = started
    log.info("обучено (%s): %d фраз, %d намерений, %d сущностей словаря, %.2f с",
             reason, len(ds.train), len(ds.intents), len(gazetteer.entities), time.time() - t)
    threading.Thread(target=compute_metrics, args=(nlu,), daemon=True).start()


def compute_metrics(nlu: NLU) -> None:
    state.metrics_status = "считаются"
    try:
        m = {"trained_at": nlu.trained_at, "cv": nlu.cross_validate()}
        for split in ("dev", "test"):
            part = [u for u in (nlu.dataset.test if nlu.dataset else []) if u.split == split]
            if part:
                m[split] = nlu.evaluate(part)
                m[split]["by_domain"] = {}
                for dom in sorted({u.source for u in part}):
                    dm = nlu.evaluate([u for u in part if u.source == dom])
                    m[split]["by_domain"][dom] = {k: dm[k] for k in ("n", "intent_accuracy", "intent_macro_f1",
                                                                     "entity_accuracy", "trait_accuracy")}
        for part in ("cv", "dev", "test"):
            if part in m:
                m[part].pop("rows", None)
        if state.nlu is nlu:
            state.metrics = m
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(os.path.join(DATA_DIR, "metrics.json"), "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False, indent=1)
        state.metrics_status = "готово"
    except Exception as exc:  # метрики — справочные, сервис без них работает
        log.exception("метрики не посчитаны")
        state.metrics_status = f"ошибка: {exc}"


# Обновления словаря не должны идти одновременно: клиент sc-server один на процесс.
_refresh_lock = threading.Lock()


def _load_gazetteer() -> Gazetteer | None:
    with _refresh_lock:
        try:
            return load_from_sc_memory(SC_SERVER_URL)
        except Exception as exc:
            state.sc_status = f"недоступен ({type(exc).__name__}: {exc})"
            log.warning("словарь из sc-memory не загружен: %s", exc)
            return None


def refresh_from_kb(force: bool = False) -> bool:
    g = _load_gazetteer()
    if g is None:
        return False
    state.sc_status = f"загружено {len(g.entities)} сущностей в {time.strftime('%H:%M:%S')}"
    if force or _signature(g) != _signature(state.nlu.gazetteer) or state.nlu.gazetteer.source == "cache":
        g.save(CACHE)
        retrain(g, "словарь из базы знаний")
    return True


def background() -> None:
    cached = Gazetteer.load(CACHE)
    retrain(cached or Gazetteer(), "кэш словаря" if cached else "без словаря")
    delay = 5
    while not refresh_from_kb():
        time.sleep(delay)
        delay = min(delay * 2, 60)
    while True:
        time.sleep(REFRESH_SECONDS)
        refresh_from_kb()


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=background, daemon=True).start()


# ---------------------------------------------------------------------- API в формате Wit.ai
@app.get("/message")
def message(request: Request, q: str = Query(..., description="текст сообщения"), explain: bool = False):
    t = time.time()
    r = state.nlu.parse(q, explain=explain)
    state.history.appendleft({
        "time": time.strftime("%H:%M:%S"),
        "client": request.headers.get("user-agent", "")[:40],
        "text": q,
        "intent": r["intents"][0]["name"] if r["intents"] else None,
        "confidence": r["intents"][0]["confidence"] if r["intents"] else None,
        "entities": [e["value"] for e in r["entities"].get("rrel_entity:rrel_entity", [])],
        "traits": {k: v[0]["value"] for k, v in r["traits"].items()},
        "ms": round((time.time() - t) * 1000, 1),
    })
    if not explain:
        for e in r["entities"].get("rrel_entity:rrel_entity", []):
            e.pop("kb", None)
    return JSONResponse(r)


# ---------------------------------------------------------------------- служебные методы
@app.get("/health")
def health():
    return {"status": "ok", "trained": state.nlu.intent_model is not None,
            "entities": len(state.nlu.gazetteer.entities), "sc_server": state.sc_status}


@app.get("/api/info")
def info():
    nlu = state.nlu
    ds = nlu.dataset
    counts = collections.Counter(u.intent for u in ds.train) if ds else {}
    test_counts = collections.Counter(u.intent for u in ds.test if u.split == "test") if ds else {}
    dev_counts = collections.Counter(u.intent for u in ds.test if u.split == "dev") if ds else {}
    by_domain = collections.defaultdict(collections.Counter)
    if ds:
        for u in ds.train:
            by_domain[u.intent][u.source] += 1
    return {
        "apps": [{k: v for k, v in a.items() if k != "path"} for a in (ds.apps if ds else [])],
        "intents": [{"name": i, "train": counts.get(i, 0), "dev": dev_counts.get(i, 0), "test": test_counts.get(i, 0),
                     "domains": dict(by_domain.get(i, {}))} for i in sorted(set(counts) | set(test_counts) | set(dev_counts))],
        "traits": ds.traits if ds else {},
        "train_size": len(ds.train) if ds else 0,
        "dev_size": sum(u.split == "dev" for u in ds.test) if ds else 0,
        "test_size": sum(u.split == "test" for u in ds.test) if ds else 0,
        "gazetteer": {"source": nlu.gazetteer.source, "entities": len(nlu.gazetteer.entities),
                      "loaded_at": nlu.gazetteer.loaded_at},
        "sc_server": state.sc_status,
        "threshold": nlu.threshold,
        "trained_at": nlu.trained_at,
        "context_lemmas": sorted(nlu.context_lemmas),
        "metrics_status": state.metrics_status,
        "metrics": state.metrics,
    }


@app.get("/api/entities")
def entities(q: str = ""):
    qn = q.lower().strip()
    out = []
    for e in state.nlu.gazetteer.entities:
        names = [n[0] for n in e.names]
        if qn and not any(qn in n.lower() for n in names) and qn not in e.sys_idtf.lower():
            continue
        out.append({"value": e.value, "sys_idtf": e.sys_idtf, "kind": e.kind, "top": e.top,
                    "top_name": e.top_name, "names": names, "type_token": e.type_token})
    out.sort(key=lambda x: (x["top"], x["value"].lower()))
    return {"total": len(state.nlu.gazetteer.entities), "items": out}


@app.get("/api/history")
def history():
    return list(state.history)


@app.post("/api/reload")
def reload(entities_only: bool = False):
    """Перечитать словарь из sc-памяти и переобучить модели.
    entities_only=true — быстрый режим для агентов, которые только что добавили сущности в базу знаний:
    если новых типов сущностей нет, модели намерений не зависят от изменения, поэтому словарь подменяется
    сразу, а полное переобучение идёт в фоне."""
    if entities_only:
        g = _load_gazetteer()
        if g is not None:
            old_types = {e.type_token for e in state.nlu.gazetteer.entities}
            if {e.type_token for e in g.entities} <= old_types:
                g = with_pushed(g)
                with state.lock:
                    state.nlu.gazetteer = g
                g.save(CACHE)
                state.sc_status = f"загружено {len(g.entities)} сущностей в {time.strftime('%H:%M:%S')} (словарь подменён)"
                threading.Thread(target=retrain, args=(g, "словарь из базы знаний, фоновое переобучение"),
                                 daemon=True).start()
                return {"sc_server": state.sc_status, "entities": len(g.entities)}
    ok = refresh_from_kb(force=True)
    if not ok:
        retrain(state.nlu.gazetteer, "повторное обучение без обновления словаря")
    return {"sc_server": state.sc_status, "entities": len(state.nlu.gazetteer.entities)}


@app.post("/api/entities")
def add_entities(payload: dict):
    """Добавить в словарь сущности, которые агент только что создал в базе знаний (ЛР4: импорт лекарств).
    Формат элемента — как у Entity: addr, value, sys_idtf, kind, classes, top, top_name, names=[[текст, язык, вид]].
    Если тип (top) не указан, он берётся у уже известной сущности того же класса. Модели не переобучаются:
    тип сущности уже встречался в обучающих фразах, поэтому новые названия распознаются сразу."""
    from .gazetteer import Entity
    with state.lock:
        old = state.nlu.gazetteer
        by_addr = {e.addr: e for e in old.entities}
        top_of_class: dict[str, tuple[str, str]] = {}
        for e in old.entities:
            for c in e.classes:
                top_of_class.setdefault(c, (e.top, e.top_name))
            if e.kind == "class" and e.sys_idtf:
                top_of_class.setdefault(e.sys_idtf, (e.top, e.top_name))
        added = 0
        for raw in payload.get("entities", []):
            e = Entity(**raw)
            if not e.top:
                e.top, e.top_name = next((top_of_class[c] for c in e.classes if c in top_of_class), ("", ""))
            added += e.addr not in by_addr
            by_addr[e.addr] = e
            state.pushed[e.addr] = e
        g = Gazetteer(list(by_addr.values()), "база знаний + сущности от агентов", time.time())
        state.nlu.gazetteer = g
    g.save(CACHE)
    return {"added": added, "entities": len(g.entities)}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))
