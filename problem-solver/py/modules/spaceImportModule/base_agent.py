"""Базовый класс агентов импорта «Космоса» (встроены в программу обработки сообщения, аргумент rrel_1 —
сообщение). Агент сам проверяет класс сообщения: чужое сообщение — действие завершается без изменений."""
from __future__ import annotations

import logging
import time

from sc_client.models import ScAddr
from sc_kpm import ScAgentClassic, ScResult
from sc_kpm.utils.action_utils import finish_action_with_status, generate_action_result, get_action_arguments

from .pipeline import ImportPipeline, ImportReport

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s", datefmt="[%d-%b-%y %H:%M:%S]")


class SpaceImportAgentBase(ScAgentClassic):
    action_class = ""

    def __init__(self) -> None:
        super().__init__(self.action_class)
        self._pipeline: ImportPipeline | None = None

    @property
    def pipeline(self) -> ImportPipeline:
        if self._pipeline is None:
            self._pipeline = ImportPipeline()
        return self._pipeline

    def on_event(self, event_element: ScAddr, event_edge: ScAddr, action_element: ScAddr) -> ScResult:
        started = time.monotonic()
        try:
            args = get_action_arguments(action_element, 1)
            message = args[0] if args else ScAddr(0)
            if not message.is_valid():
                finish_action_with_status(action_element, False)
                return ScResult.ERROR
            self.pipeline.writer._qids = None        # база знаний могла измениться с прошлого сообщения
            report = self.process(message, started)
        except Exception:
            self.logger.exception("%s завершился с ошибкой", type(self).__name__)
            finish_action_with_status(action_element, False)
            return ScResult.ERROR
        if report is not None:
            generate_action_result(action_element, self.pipeline.kb.new_link(report.text()),
                                   *[w.node for w in report.written])
        finish_action_with_status(action_element, True)
        return ScResult.OK

    def process(self, message: ScAddr, started: float) -> ImportReport | None:
        raise NotImplementedError
