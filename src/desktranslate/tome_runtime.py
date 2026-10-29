from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from desktranslate.tome import ProgressObservation, TomeTask, parse_progress


@dataclass(frozen=True)
class TimedObservation:
    observation: ProgressObservation
    seen_at: float


class ProgressStabilizer:
    """Confirm short-lived OCR notifications without counting every captured frame."""

    def __init__(self, confirmations: int = 2, window_seconds: float = 1.25) -> None:
        if confirmations < 1:
            raise ValueError("confirmations must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.confirmations = confirmations
        self.window_seconds = window_seconds
        self.pending: deque[TimedObservation] = deque()
        self.last_emitted: tuple[int, int] | None = None

    def observe(
        self, text: str, confidence: float, now: float
    ) -> ProgressObservation | None:
        parsed = parse_progress(text, confidence)
        while self.pending and now - self.pending[0].seen_at > self.window_seconds:
            self.pending.popleft()
        if parsed is None:
            return None
        key = (parsed.current, parsed.target)
        self.pending.append(TimedObservation(parsed, now))
        matches = [item for item in self.pending if (item.observation.current, item.observation.target) == key]
        if len(matches) < self.confirmations or key == self.last_emitted:
            return None
        self.last_emitted = key
        self.pending.clear()
        best = max(matches, key=lambda item: item.observation.confidence)
        return best.observation


def overlay_text(task: TomeTask | None) -> str:
    if task is None:
        return "尚未识别古书任务"
    role = {"survivor": "逃生者", "killer": "杀手", "unknown": "古书"}[task.role]
    progress = task.display_progress or (
        f"{task.current} / {task.target}"
        if task.current is not None and task.target is not None
        else "等待进度提示"
    )
    marker = "✓ 已完成" if task.completed else progress
    description = f"\n{task.description}" if task.description else ""
    return f"{role}任务 · {task.title}{description}\n{marker}"
