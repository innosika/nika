from sc_kpm import ScModule

from .SpaceKbFillAgent import SpaceKbFillAgent
from .SpaceOnDemandImportAgent import SpaceOnDemandImportAgent


class SpaceImportModule(ScModule):
    """Модуль адаптации знаний: импорт сведений о космических объектах из Wikidata (ЛР4, вариант «Космос»)."""

    def __init__(self):
        super().__init__(SpaceOnDemandImportAgent(), SpaceKbFillAgent())
