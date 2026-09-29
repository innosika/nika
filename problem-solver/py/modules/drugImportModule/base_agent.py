"""Базовый класс агентов импорта сведений о лекарствах.

Все три агента встроены в программу обработки сообщения (message_processing_program) и получают
сообщение первым аргументом (rrel_1). Агент сам проверяет класс сообщения: если сообщение не его,
действие завершается успешно без изменений, и программа переходит к следующему агенту.
"""
from __future__ import annotations

import logging
import time

from sc_client.models import ScAddr
from sc_kpm import ScAgentClassic, ScResult
from sc_kpm.utils.action_utils import finish_action_with_status, generate_action_result, get_action_arguments

from .pipeline import ImportPipeline, ImportReport

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s", datefmt="[%d-%b-%y %H:%M:%S]")


class DrugImportAgentBase(ScAgentClassic):
    action_class = ""

    def __init__(self) -> None:
        super().__init__(self.action_class)
        self._pipeline: ImportPipeline | None = None

    @property
    def pipeline(self) -> ImportPipeline:
        if self._pipeline is None:          # создаётся после подключения к sc-серверу
            self._pipeline = ImportPipeline()
        return self._pipeline

    def on_event(self, event_element: ScAddr, event_edge: ScAddr, action_element: ScAddr) -> ScResult:
        started = time.monotonic()
        try:
            args = get_action_arguments(action_element, 1)
            message = args[0] if args else ScAddr(0)
            if not message.is_valid():
                self.logger.warning("%s: нет сообщения в аргументе rrel_1", type(self).__name__)
                finish_action_with_status(action_element, False)
                return ScResult.ERROR
            report = self.process(message, started)
        except Exception:
            self.logger.exception("%s завершился с ошибкой", type(self).__name__)
            finish_action_with_status(action_element, False)
            return ScResult.ERROR
        if report is not None:
            link = self.pipeline.kb.new_link(report.text())
            generate_action_result(action_element, link, *[w.drug for w in report.written])
        finish_action_with_status(action_element, True)
        return ScResult.OK

    def process(self, message: ScAddr, started: float) -> ImportReport | None:
        """Возвращает отчёт импорта или None, если сообщение не относится к агенту."""
        raise NotImplementedError
