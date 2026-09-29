"""Настройки модуля импорта сведений о лекарствах (переменные окружения контейнера py-sc-server)."""
from __future__ import annotations

import os
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(int(default))).lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    cache_dir: str = os.environ.get("DRUG_IMPORT_CACHE_DIR", "/data/drug-import-cache")
    snapshot_path: str = os.path.join(HERE, "data", "offline_snapshot.json")
    data_dir: str = os.path.join(HERE, "data")
    offline: bool = _env_bool("DRUG_IMPORT_OFFLINE", False)          # только кэш и снимок, без сети
    on_demand: bool = _env_bool("DRUG_IMPORT_ON_DEMAND", True)        # режим 1 можно отключить для регрессии ЛР3
    request_timeout: float = float(os.environ.get("DRUG_IMPORT_REQUEST_TIMEOUT", "12"))
    time_budget: float = float(os.environ.get("DRUG_IMPORT_TIME_BUDGET", "26"))   # секунд на загрузку
    workers: int = int(os.environ.get("DRUG_IMPORT_WORKERS", "24"))
    fill_total: int = int(os.environ.get("DRUG_IMPORT_FILL_TOTAL", "12"))        # режим 2: всего препаратов
    fill_per_class: int = int(os.environ.get("DRUG_IMPORT_FILL_PER_CLASS", "2"))  # режим 2: на класс
    fill_by_type: int = int(os.environ.get("DRUG_IMPORT_FILL_BY_TYPE", "6"))      # режим 3: препаратов
    side_effects: int = int(os.environ.get("DRUG_IMPORT_SIDE_EFFECTS", "6"))      # побочных эффектов на препарат
    min_reports: int = int(os.environ.get("DRUG_IMPORT_MIN_REPORTS", "20"))      # порог числа сообщений FAERS
    wit_entities_url: str = os.environ.get("WIT_ENTITIES_URL", "http://wit-local:8095/api/entities")
    inference_wait: float = float(os.environ.get("DRUG_IMPORT_INFERENCE_WAIT", "12"))


CONFIG = Config()
