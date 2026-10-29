from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path


_PROGRESS_PATTERNS = (
    re.compile(r"(?P<current>\d{1,4})\s*[/／]\s*(?P<target>\d{1,4})"),
    re.compile(r"进度\s*[:：]?\s*(?P<current>\d{1,4})\s*(?:/|／|共)\s*(?P<target>\d{1,4})"),
)
_PERCENT_PATTERN = re.compile(r"(?P<percent>\d{1,3})\s*[%％]")


def normalize_ocr_text(text: str) -> str:
    """Normalize punctuation and whitespace without destroying Chinese task text."""

    normalized = unicodedata.normalize("NFKC", text).replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in normalized.splitlines()]
    return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class TomeTask:
    title: str
    description: str = ""
    current: int | None = None
    target: int | None = None
    role: str = "unknown"
    completed: bool = False
    confidence: float = 0.0
    updated_at: float = 0.0
    display_progress: str = ""

    def __post_init__(self) -> None:
        if self.role not in {"survivor", "killer", "unknown"}:
            raise ValueError("role must be survivor, killer, or unknown")
        if not self.title.strip():
            raise ValueError("task title cannot be empty")
        if self.current is not None and self.current < 0:
            raise ValueError("current progress cannot be negative")
        if self.target is not None and self.target <= 0:
            raise ValueError("target progress must be positive")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class ProgressObservation:
    current: int
    target: int
    text: str
    confidence: float = 0.0


def title_similarity(expected: str, observed: str) -> float:
    """Return an OCR-tolerant similarity score for a task title."""

    left = re.sub(r"[^\w\u3400-\u9fff]", "", normalize_ocr_text(expected)).casefold()
    right = re.sub(r"[^\w\u3400-\u9fff]", "", normalize_ocr_text(observed)).casefold()
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return min(len(left), len(right)) / max(len(left), len(right))
    return SequenceMatcher(None, left, right).ratio()


def parse_progress(text: str, confidence: float = 0.0) -> ProgressObservation | None:
    normalized = normalize_ocr_text(text)
    for pattern in _PROGRESS_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue
        current = int(match.group("current"))
        target = int(match.group("target"))
        if target <= 0 or current > target:
            continue
        return ProgressObservation(current, target, normalized, confidence)
    percent = _PERCENT_PATTERN.search(normalized)
    if percent:
        value = int(percent.group("percent"))
        if 0 <= value <= 100:
            return ProgressObservation(value, 100, normalized, confidence)
    return None


def parse_task_card(text: str, role: str = "unknown", confidence: float = 0.0) -> TomeTask:
    normalized = normalize_ocr_text(text)
    lines = normalized.splitlines()
    if not lines:
        raise ValueError("OCR result did not contain task text")
    observation = parse_progress(normalized, confidence)
    progress_line = next((line for line in lines if parse_progress(line)), "")
    content = [
        line
        for line in lines
        if line != progress_line
        and not re.search(r"古书\s*第?\s*\d+\s*册|等级\s*\d+", line)
        and not re.fullmatch(r"(?:逃生者|杀手)?(?:大师)?挑战", line)
        and not re.fullmatch(r"[\d\s,，]+", line)
    ]
    title = content[0] if content else lines[0]
    description = " ".join(content[1:])
    current = observation.current if observation else None
    target = observation.target if observation else None
    return TomeTask(
        title=title,
        description=description,
        current=current,
        target=target,
        role=role,
        completed=current is not None and target is not None and current >= target,
        confidence=confidence,
        updated_at=time.time(),
    )


class TomeTaskTracker:
    """Own the persistent task displayed by the future DBD overlay."""

    def __init__(self, task: TomeTask | None = None) -> None:
        self.task = task

    def apply(self, observation: ProgressObservation) -> bool:
        if self.task is None:
            return False
        if self.task.target is not None and observation.target != self.task.target:
            return False
        if self.task.current is not None and observation.current < self.task.current:
            return False
        if self.task.current == observation.current and self.task.target == observation.target:
            return False
        self.task = replace(
            self.task,
            current=observation.current,
            target=observation.target,
            completed=observation.current >= observation.target,
            display_progress="",
            confidence=max(self.task.confidence, observation.confidence),
            updated_at=time.time(),
        )
        return True

    def apply_notification(
        self,
        text: str,
        confidence: float = 0.0,
        minimum_title_similarity: float = 0.55,
    ) -> bool:
        if self.task is None:
            return False
        observation = parse_progress(text, confidence)
        if observation is None:
            return False
        without_progress = normalize_ocr_text(text)
        for pattern in _PROGRESS_PATTERNS:
            without_progress = pattern.sub("", without_progress)
        without_progress = _PERCENT_PATTERN.sub("", without_progress)
        if without_progress.strip() and title_similarity(self.task.title, without_progress) < minimum_title_similarity:
            return False
        percent = _PERCENT_PATTERN.search(normalize_ocr_text(text))
        if percent and self.task.target is not None:
            value = int(percent.group("percent"))
            mapped = min(self.task.target, value * self.task.target // 100)
            if self.task.current is not None:
                mapped = max(self.task.current, mapped)
            label = f"{value}%（约 {mapped} / {self.task.target}）"
            if self.task.display_progress == label:
                return False
            self.task = replace(
                self.task,
                current=mapped,
                completed=value >= 100,
                display_progress=label,
                confidence=max(self.task.confidence, confidence),
                updated_at=time.time(),
            )
            return True
        return self.apply(observation)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self.task) if self.task else None
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def load(cls, path: Path) -> TomeTaskTracker:
        if not path.exists():
            return cls()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(TomeTask(**payload) if payload else None)
