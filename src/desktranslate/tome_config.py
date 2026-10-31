from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from desktranslate.models import Rect


@dataclass(frozen=True)
class TomeConfig:
    task_region: Rect | None = None
    notification_region: Rect | None = None
    role: str = "unknown"
    overlay_opacity: int = 72
    capture_hotkey: str = "Ctrl+Shift+T"

    def __post_init__(self) -> None:
        from desktranslate.shortcuts import parse_hotkey
        parse_hotkey(self.capture_hotkey)
        if self.role not in {"survivor", "killer", "both", "unknown"}:
            raise ValueError("invalid Tome role")
        if not 30 <= self.overlay_opacity <= 95:
            raise ValueError("overlay opacity must be between 30 and 95")


class TomeConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.last_payload = None

    def load(self) -> TomeConfig:
        if not self.path.exists():
            return TomeConfig()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.last_payload = payload.copy()
        return TomeConfig(
            task_region=Rect(**payload["task_region"]) if payload.get("task_region") else None,
            notification_region=(
                Rect(**payload["notification_region"])
                if payload.get("notification_region")
                else None
            ),
            role=payload.get("role", "unknown"),
            overlay_opacity=payload.get("overlay_opacity", 72),
            capture_hotkey=payload.get("capture_hotkey", "Ctrl+Shift+T"),
        )

    def save(self, config: TomeConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "task_region": asdict(config.task_region) if config.task_region else None,
            "notification_region": (
                asdict(config.notification_region) if config.notification_region else None
            ),
            "role": config.role,
            "overlay_opacity": config.overlay_opacity,
            "capture_hotkey": config.capture_hotkey,
        }
        if self.last_payload is not None and self.path.exists():
            latest = json.loads(self.path.read_text(encoding="utf-8"))
            changes = {k: v for k, v in payload.items() if v != self.last_payload.get(k)}
            latest.update(changes)
            payload = latest
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        # Keep this instance baseline, so unrelated changes never overwrite another instance.
        self.last_payload = {
            "task_region": asdict(config.task_region) if config.task_region else None,
            "notification_region": asdict(config.notification_region) if config.notification_region else None,
            "role": config.role, "overlay_opacity": config.overlay_opacity,
            "capture_hotkey": config.capture_hotkey,
        }
