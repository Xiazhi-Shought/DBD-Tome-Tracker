from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from desktranslate.tome import TomeTaskTracker, parse_progress, parse_task_card
from desktranslate.tome_runtime import ProgressStabilizer, overlay_text


class TomeParserTests(unittest.TestCase):
    def test_parses_chinese_task_card_and_full_width_progress(self) -> None:
        task = parse_task_card("患难与共\n安全救下 4 名逃生者\n进度：2／4", "survivor", 0.91)
        self.assertEqual(task.title, "患难与共")
        self.assertEqual(task.description, "安全救下 4 名逃生者")
        self.assertEqual((task.current, task.target), (2, 4))
        self.assertFalse(task.completed)

    def test_rejects_impossible_progress(self) -> None:
        self.assertIsNone(parse_progress("任务进度 7/4"))

    def test_tracker_ignores_duplicate_and_regression(self) -> None:
        tracker = TomeTaskTracker(parse_task_card("患难与共\n安全救下 4 名逃生者\n1/4"))
        self.assertFalse(tracker.apply(parse_progress("1/4")))
        self.assertTrue(tracker.apply(parse_progress("2/4", 0.8)))
        self.assertFalse(tracker.apply(parse_progress("1/4")))
        self.assertEqual(tracker.task.current, 2)

    def test_percentage_notification_updates_fraction_task_and_overlay(self) -> None:
        tracker = TomeTaskTracker(parse_task_card("工程师协会\n协同修理10台发电机\n2/10"))
        self.assertTrue(tracker.apply_notification("工程师协会\n37%", 0.91))
        self.assertEqual((tracker.task.current, tracker.task.target), (3, 10))
        self.assertEqual(tracker.task.display_progress, "37%（约 3 / 10）")
        self.assertIn("37%", overlay_text(tracker.task))

    def test_tracker_persists_completed_task(self) -> None:
        tracker = TomeTaskTracker(parse_task_card("治疗者\n治疗 3 次\n2/3", "survivor"))
        self.assertTrue(tracker.apply(parse_progress("3/3", 0.95)))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "task.json"
            tracker.save(path)
            loaded = TomeTaskTracker.load(path)
        self.assertTrue(loaded.task.completed)
        self.assertEqual((loaded.task.current, loaded.task.target), (3, 3))

    def test_notification_requires_matching_title_when_present(self) -> None:
        tracker = TomeTaskTracker(parse_task_card("患难与共\n安全救下 4 名逃生者\n1/4"))
        self.assertFalse(tracker.apply_notification("另一项任务\n2/4", 0.9))
        self.assertTrue(tracker.apply_notification("患难与共\n2/4", 0.9))

    def test_stabilizer_confirms_two_frames_and_suppresses_duplicates(self) -> None:
        stabilizer = ProgressStabilizer(confirmations=2)
        self.assertIsNone(stabilizer.observe("患难与共 2/4", 0.7, 10.0))
        confirmed = stabilizer.observe("患难与共 2／4", 0.9, 10.2)
        self.assertEqual((confirmed.current, confirmed.target), (2, 4))
        self.assertIsNone(stabilizer.observe("患难与共 2/4", 0.9, 10.4))
        self.assertIsNone(stabilizer.observe("患难与共 2/4", 0.9, 10.6))

    def test_overlay_text_contains_role_description_and_progress(self) -> None:
        task = parse_task_card("患难与共\n安全救下 4 名逃生者\n2/4", "survivor")
        self.assertEqual(overlay_text(task), "逃生者任务 · 患难与共\n安全救下 4 名逃生者\n2 / 4")

    def test_tome_metadata_is_not_used_as_task_description(self) -> None:
        task = parse_task_card("工程师协会\n古书第10册-电锯惊魂-等级4\n0/3", "survivor")
        self.assertEqual(task.title, "工程师协会")
        self.assertEqual(task.description, "")
        self.assertEqual((task.current, task.target), (0, 3))

    def test_task_category_and_reward_are_not_used_as_description(self) -> None:
        task = parse_task_card(
            "启蒙\n逃生者大师挑战\n致盲杀手2次。\n在单场对局中完成这项挑战。\n0/1\n35 000",
            "survivor",
        )
        self.assertEqual(task.title, "启蒙")
        self.assertEqual(
            task.description, "致盲杀手2次。 在单场对局中完成这项挑战。"
        )
        self.assertEqual((task.current, task.target), (0, 1))

    def test_task_details_automatically_parse_editable_progress(self) -> None:
        task = parse_task_card(
            "工程师协会\n逃生者挑战\n与其他逃生者协同修理累计10台发电机。\n2/10\n45 000",
            "survivor",
        )
        self.assertEqual(task.title, "工程师协会")
        self.assertEqual(task.description, "与其他逃生者协同修理累计10台发电机。")
        self.assertEqual((task.current, task.target), (2, 10))

    def test_task_role_is_detected_from_challenge_subtitle(self) -> None:
        survivor = parse_task_card("工程师协会\n逃生者大师挑战\n修理发电机\n2/10", "killer")
        killer = parse_task_card("阴森恐怖\n杀手挑战\n钩住逃生者\n1/8", "survivor")
        both = parse_task_card("黄金时代\n挑战\n获得徽章\n3/20", "killer")
        self.assertEqual(survivor.role, "survivor")
        self.assertEqual(killer.role, "killer")
        self.assertEqual(both.role, "both")


if __name__ == "__main__":
    unittest.main()
