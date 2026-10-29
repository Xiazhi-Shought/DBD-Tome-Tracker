from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from desktranslate.models import OCRResult, Rect
from desktranslate.tome import TomeTaskTracker, parse_task_card
from desktranslate.tome_service import TomeService
from desktranslate.tome_catalog import CatalogTask, TomeCatalog


class FakeCapture:
    def __init__(self, image: Image.Image) -> None:
        self.image = image
        self.closed = False

    def capture(self, region: Rect) -> Image.Image:
        return self.image

    def close(self) -> None:
        self.closed = True


class FakeOCR:
    def __init__(self, results: list[OCRResult]) -> None:
        self.results = results
        self.closed = False

    def recognize(self, image: Image.Image, language: str, vertical: bool = False) -> OCRResult:
        return self.results.pop(0)

    def close(self) -> None:
        self.closed = True


class TomeServiceTests(unittest.TestCase):
    def test_legacy_title_only_capture_can_still_match_catalog(self) -> None:
        image = Image.new("RGB", (640, 120), "black")
        capture = FakeCapture(image)
        ocr = FakeOCR([OCRResult("工程师协今\n古书第10册-电锯惊魂-等级4", confidence=0.91)])
        catalog = TomeCatalog([CatalogTask(
            "The Engineer's Guild", "工程师协会",
            "合作修理发电机，总计完成相当于 {{target}} 台发电机的进度。",
            "survivor", ("工程师协今",)
        )])
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / "task.json"
            service = TomeService(lambda: capture, lambda: ocr, store, catalog=catalog)
            title, confidence = service.recognize_task_name(Rect(0, 0, 640, 120))
            task = service.set_manual_task(title, 1, 4, "unknown", confidence)
            loaded = TomeTaskTracker.load(store).task
        self.assertEqual(title, "工程师协会")
        self.assertEqual((task.current, task.target), (1, 4))
        self.assertEqual(task.description, "")
        self.assertEqual(loaded.role, "unknown")

    def test_recognizes_details_and_manual_save_keeps_them(self) -> None:
        image = Image.new("RGB", (640, 400), "black")
        capture = FakeCapture(image)
        ocr = FakeOCR([OCRResult(
            "启蒙\n逃生者大师挑战\n致盲杀手2次。\n在单场对局中完成这项挑战。\n0/1",
            confidence=0.94,
        )])
        with tempfile.TemporaryDirectory() as folder:
            service = TomeService(lambda: capture, lambda: ocr, Path(folder) / "task.json")
            recognized = service.recognize_task_details(Rect(0, 0, 640, 400), "survivor")
            saved = service.set_manual_task(
                recognized.title,
                0,
                1,
                recognized.role,
                recognized.confidence,
                recognized.description,
            )
        self.assertEqual(saved.title, "启蒙")
        self.assertIn("致盲杀手2次", saved.description)
        self.assertEqual((saved.current, saved.target), (0, 1))

    def test_recognizes_and_persists_task_card(self) -> None:
        image = Image.new("RGB", (320, 120), "black")
        capture = FakeCapture(image)
        ocr = FakeOCR([OCRResult("患难与共\n安全救下 4 名逃生者\n1/4", confidence=0.93)])
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / "task.json"
            service = TomeService(lambda: capture, lambda: ocr, store)
            task = service.recognize_task_card(Rect(0, 0, 320, 120), "survivor")
            loaded = TomeTaskTracker.load(store).task
        self.assertEqual(task.title, "患难与共")
        self.assertEqual(loaded.current, 1)
        self.assertTrue(capture.closed)
        self.assertTrue(ocr.closed)

    def test_changed_frames_confirm_and_publish_progress(self) -> None:
        first = Image.new("RGB", (100, 40), "black")
        second = first.copy()
        for point in ((5, 5), (6, 5), (5, 6), (6, 6)):
            second.putpixel(point, (255, 255, 255))
        ocr = FakeOCR(
            [
                OCRResult("患难与共\n2/4", confidence=0.82),
                OCRResult("患难与共\n2／4", confidence=0.94),
            ]
        )
        with tempfile.TemporaryDirectory() as folder:
            service = TomeService(
                lambda: FakeCapture(first), lambda: ocr, Path(folder) / "task.json", frame_settle=0
            )
            service.tracker.task = parse_task_card("患难与共\n安全救下 4 名逃生者\n1/4")
            self.assertFalse(service.process_frame(first, 1.0))
            self.assertTrue(service.process_frame(second, 1.1))
            event = service.next_task()
        self.assertEqual((event.current, event.target), (2, 4))
        self.assertEqual(service.ocr_runs, 2)

    def test_static_frame_does_not_repeat_ocr(self) -> None:
        frame = Image.new("RGB", (100, 40), "black")
        ocr = FakeOCR([OCRResult("患难与共\n2/4", confidence=0.9)])
        with tempfile.TemporaryDirectory() as folder:
            service = TomeService(
                lambda: FakeCapture(frame), lambda: ocr, Path(folder) / "task.json", frame_settle=0
            )
            service.tracker.task = parse_task_card("患难与共\n安全救下 4 名逃生者\n1/4")
            service.process_frame(frame, 1.0)
            service.process_frame(frame, 2.0)
        self.assertEqual(service.ocr_runs, 1)

    def test_initial_capture_requires_progress_when_requested(self) -> None:
        image = Image.new("RGB", (320, 120), "black")
        capture = FakeCapture(image)
        ocr = FakeOCR([OCRResult("工程师协会\n古书第10册-电锯惊魂-等级4", confidence=0.93)])
        with tempfile.TemporaryDirectory() as folder:
            service = TomeService(lambda: capture, lambda: ocr, Path(folder) / "task.json")
            with self.assertRaisesRegex(ValueError, "未识别到任务进度"):
                service.recognize_task_card(
                    Rect(0, 0, 320, 120), "survivor", require_progress=True
                )


if __name__ == "__main__":
    unittest.main()
