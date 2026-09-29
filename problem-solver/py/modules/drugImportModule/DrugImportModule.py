from sc_kpm import ScModule

from .DrugKbFillAgent import DrugKbFillAgent
from .DrugKbFillByTypeAgent import DrugKbFillByTypeAgent
from .DrugOnDemandImportAgent import DrugOnDemandImportAgent


class DrugImportModule(ScModule):
    """Модуль адаптации знаний: импорт сведений о лекарствах из openFDA и RxNav (ЛР4, вариант «Медицина»)."""

    def __init__(self):
        super().__init__(DrugOnDemandImportAgent(), DrugKbFillAgent(), DrugKbFillByTypeAgent())
