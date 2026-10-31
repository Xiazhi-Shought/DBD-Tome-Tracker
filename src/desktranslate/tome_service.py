from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import replace
from collections.abc import Callable
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread

from PIL import Image

from desktranslate.algorithms import FrameGate
from desktranslate.models import CaptureProvider, OCREngine, Rect
from desktranslate.tome import TomeTask, TomeTaskTracker, parse_task_card
from desktranslate.tome_catalog import TomeCatalog
from desktranslate.tome_runtime import ProgressStabilizer


class TomeService:
    """Low-impact capture → OCR → persistent Tome progress service."""

    def __init__(
        self,
        capture_factory: Callable[[], CaptureProvider],
        ocr_factory: Callable[[], OCREngine],
        store: Path,
        language: str = "zh-CN",
        cadence: float = 0.20,
        frame_settle: float = 0.15,
        catalog: TomeCatalog | None = None,
    ) -> None:
        self.capture_factory = capture_factory
        self.ocr_factory = ocr_factory
        self.store = store
        self.language = language
        self.cadence = cadence
        self.tracker = TomeTaskTracker.load(store)
        self.stabilizer = ProgressStabilizer(confirmations=2)
        self.frame_gate = FrameGate(settle=frame_settle, threshold=1.2, motion_interval=0.45)
        self.events: Queue[TomeTask] = Queue(maxsize=8)
        self.stop_event = Event()
        self.thread: Thread | None = None
        self.lock = Lock()
        self.capture: CaptureProvider | None = None
        self.ocr: OCREngine | None = None
        self.notification_region: Rect | None = None
        self.ocr_runs = 0
        self.captures = 0
        self.catalog = catalog

    def recognize_task_card(
        self, region: Rect, role: str = "unknown", require_progress: bool = False
    ) -> TomeTask:
        capture = self.capture_factory()
        ocr = self.ocr_factory()
        try:
            result = ocr.recognize(capture.capture(region), self.language)
            task = parse_task_card(result.text, role, result.confidence)
            if require_progress and (task.current is None or task.target is None):
                raise ValueError(
                    "未识别到任务进度。请重新框选，并把任务标题和 0/3、2/5 一类进度数字一起框入。"
                )
            with self.lock:
                self.tracker.task = task
                self.tracker.save(self.store)
            self._publish(task)
            return task
        finally:
            ocr.close()
            capture.close()

    def recognize_task_name(self, region: Rect) -> tuple[str, float]:
        """OCR a task card and return a catalog-normalized title without requiring progress."""
        capture = self.capture_factory()
        ocr = self.ocr_factory()
        try:
            result = ocr.recognize(capture.capture(region), self.language)
            parsed = parse_task_card(result.text, confidence=result.confidence)
            matched = self.catalog.match(parsed.title) if self.catalog else None
            return (matched.chinese_name if matched else parsed.title, result.confidence)
        finally:
            ocr.close()
            capture.close()

    def recognize_task_details(self, region: Rect, role: str = "unknown") -> TomeTask:
        """OCR the title, description and optional progress directly from a task card."""
        capture = self.capture_factory()
        ocr = self.ocr_factory()
        try:
            result = ocr.recognize(capture.capture(region), self.language)
            return parse_task_card(result.text, role, result.confidence)
        finally:
            ocr.close()
            capture.close()

    def recognize_task_details_image(self, image: Image.Image, role: str = "unknown") -> TomeTask:
        """OCR the frozen picker crop so hover-only task text cannot disappear."""
        ocr = self.ocr_factory()
        try:
            result = ocr.recognize(image, self.language)
            return parse_task_card(result.text, role, result.confidence)
        finally:
            ocr.close()

    def set_manual_task(
        self,
        title: str,
        current: int,
        target: int,
        role: str,
        confidence: float = 0.0,
        description: str = "",
    ) -> TomeTask:
        if current < 0 or target <= 0 or current > target:
            raise ValueError("进度必须满足 0 ≤ 当前进度 ≤ 目标进度")
        task = TomeTask(
            title=title.strip(),
            description=description.strip(),
            current=current,
            target=target,
            role=role,
            completed=current >= target,
            confidence=confidence,
            updated_at=time.time(),
        )
        with self.lock:
            self.tracker.task = task
            self.tracker.save(self.store)
        self._publish(task)
        return task

    def adjust_progress(self, delta: int = 0, complete: bool = False) -> TomeTask | None:
        """Adjust the active task from overlay controls and persist it immediately."""

        with self.lock:
            task = self.tracker.task
            if task is None or task.current is None or task.target is None:
                return None
            current = task.target if complete else max(0, min(task.target, task.current + int(delta)))
            if current == task.current and task.completed == (current >= task.target):
                return task
            task = replace(
                task,
                current=current,
                completed=current >= task.target,
                display_progress="",
                updated_at=time.time(),
            )
            self.tracker.task = task
            self.tracker.save(self.store)
        self._publish(task)
        return task

    def start(self, notification_region: Rect) -> None:
        if self.thread and self.thread.is_alive():
            raise RuntimeError("Tome notification monitoring is already running")
        self.notification_region = notification_region
        self.stop_event.clear()
        self.thread = Thread(target=self._run, name="dbd-tome-monitor", daemon=True)
        self.thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout)
        self._close_workers()

    def process_frame(self, image: Image.Image, now: float | None = None) -> bool:
        """Process one captured notification frame; exposed for diagnostics and tests."""

        moment = time.monotonic() if now is None else now
        decision = self.frame_gate.observe(image, moment)
        if not decision.ready:
            return False
        if self.ocr is None:
            self.ocr = self.ocr_factory()
        result = self.ocr.recognize(image, self.language)
        self.ocr_runs += 1
        confirmed = self.stabilizer.observe(result.text, result.confidence, moment)
        if confirmed is None:
            return False
        with self.lock:
            changed = self.tracker.apply_notification(
                confirmed.text, confirmed.confidence
            )
            if not changed or self.tracker.task is None:
                return False
            self.tracker.save(self.store)
            task = self.tracker.task
        self._publish(task)
        return True

    def next_task(self) -> TomeTask | None:
        try:
            return self.events.get_nowait()
        except Empty:
            return None

    def _run(self) -> None:
        if self.notification_region is None:
            return
        try:
            self.capture = self.capture_factory()
            while not self.stop_event.is_set():
                started = time.monotonic()
                image = self.capture.capture(self.notification_region)
                self.captures += 1
                self.process_frame(image, started)
                self.stop_event.wait(max(0.01, self.cadence - (time.monotonic() - started)))
        except Exception:
            logging.exception("DBD Tome notification monitor stopped after an error")
        finally:
            self._close_workers()

    def _publish(self, task: TomeTask) -> None:
        while self.events.full():
            with contextlib.suppress(Empty):
                self.events.get_nowait()
        self.events.put_nowait(task)

    def _close_workers(self) -> None:
        if self.ocr is not None:
            self.ocr.close()
            self.ocr = None
        if self.capture is not None:
            self.capture.close()
            self.capture = None
