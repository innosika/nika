"""Настройки модуля импорта сведений о космических объектах (переменные окружения контейнера py-sc-server)."""
from __future__ import annotations

import os
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(int(default))).lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    cache_dir: str = os.environ.get("SPACE_IMPORT_CACHE_DIR", "/data/space-import-cache")
    snapshot_path: str = os.path.join(HERE, "data", "offline_snapshot.json")
    offline: bool = _env_bool("SPACE_IMPORT_OFFLINE", False)        # только кэш и снимок, без сети
    on_demand: bool = _env_bool("SPACE_IMPORT_ON_DEMAND", True)      # режим 1 можно отключить
    endpoint: str = os.environ.get("WIKIDATA_ENDPOINT", "https://query.wikidata.org/sparql")
    user_agent: str = "NIKA-knowledge-import/1.0 (BSUIR student lab work; https://github.com/innosika/nika)"
    request_timeout: float = float(os.environ.get("SPACE_IMPORT_REQUEST_TIMEOUT", "20"))
    time_budget: float = float(os.environ.get("SPACE_IMPORT_TIME_BUDGET", "26"))   # секунд на загрузку
    fill_total: int = int(os.environ.get("SPACE_IMPORT_FILL_TOTAL", "12"))         # режим 2: всего объектов
    fill_per_class: int = int(os.environ.get("SPACE_IMPORT_FILL_PER_CLASS", "2"))   # режим 2: на класс
    fill_by_type: int = int(os.environ.get("SPACE_IMPORT_FILL_BY_TYPE", "6"))       # режим 2 с типом
    children: int = int(os.environ.get("SPACE_IMPORT_CHILDREN", "8"))               # спутников у планеты
    min_sitelinks: int = int(os.environ.get("SPACE_IMPORT_MIN_SITELINKS", "15"))    # «известность» объекта
    wit_entities_url: str = os.environ.get("WIT_ENTITIES_URL", "http://wit-local:8095/api/entities")
    inference_wait: float = float(os.environ.get("SPACE_IMPORT_INFERENCE_WAIT", "12"))


CONFIG = Config()
