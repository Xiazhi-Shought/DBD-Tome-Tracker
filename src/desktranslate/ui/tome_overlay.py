from __future__ import annotations

import ctypes
import os
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal, QElapsedTimer, QTimer
from PySide6.QtGui import (
    QPixmap, QColor, QFont, QLinearGradient, QMouseEvent, QPainter, QPainterPath,
    QPaintEvent, QRegion, QResizeEvent
)
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget
)

from desktranslate.tome import TomeTask


class TomeOverlay(QWidget):
    """Always-on-top task card that can be dragged and position-locked."""

    progress_delta_requested = Signal(int)
    completion_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.dismissed = False
        self.setWindowTitle("DBD 古书任务追踪器")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setMinimumSize(380, 150)
        self.resize(480, 188)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 17, 18, 15)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(12)
        self.icon = QLabel("◈")
        self.icon.setFixedSize(38, 38)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet(
            "color:#60cdff;background:rgba(96,205,255,28);border:1px solid rgba(96,205,255,95);"
            "border-radius:9px;font-size:22px;font-weight:700;"
        )
        self.icon.setPixmap(QPixmap(str(Path(__file__).parents[1] / "assets/tome-logo.png")).scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header.addWidget(self.icon)
        heading = QVBoxLayout()
        heading.setSpacing(1)
        self.eyebrow = QLabel("DBD · 古书任务")
        self.eyebrow.setStyleSheet(
            "color:rgba(255,255,255,150);font-family:'Segoe UI';font-size:11px;font-weight:600;"
        )
        heading.addWidget(self.eyebrow)
        self.label = QLabel("尚未识别古书任务")
        self.label.setStyleSheet(
            "color:#ffffff;background:transparent;font-family:'Segoe UI';font-size:17px;font-weight:600;"
        )
        heading.addWidget(self.label)
        header.addLayout(heading, 1)
        layout.addLayout(header)

        self.description = QLabel("")
        self.description.setWordWrap(True)
        self.description.setStyleSheet(
            "color:rgba(255,255,255,205);background:transparent;font-family:'Microsoft YaHei UI';"
            "font-size:13px;"
        )
        layout.addWidget(self.description)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(10)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setStyleSheet(
            "QProgressBar{background:rgba(255,255,255,28);border:0;border-radius:2px;}"
            "QProgressBar::chunk{background:#60cdff;border-radius:2px;}"
        )
        progress_row.addWidget(self.progress_bar, 1)
        self.progress = QLabel("等待进度")
        self.progress.setStyleSheet(
            "color:#ffffff;font-family:'Segoe UI';font-size:13px;font-weight:600;"
        )
        progress_row.addWidget(self.progress)
        layout.addLayout(progress_row)

        self.minus_button = QPushButton("−")
        self.plus_button = QPushButton("+")
        self.complete_button = QPushButton("✓")
        self._repeat_timer = QTimer(self)
        self._repeat_timer.timeout.connect(self._repeat_progress_change)
        self._repeat_elapsed = QElapsedTimer()
        self._repeat_direction = 0

        self.lock_button = QPushButton("🔓")
        self.lock_button.setToolTip("锁定位置")
        self.lock_button.setFixedSize(30, 26)
        self.lock_button.setStyleSheet(
            "QPushButton{color:#ffffff;background:rgba(255,255,255,18);"
            "border:1px solid rgba(255,255,255,45);border-radius:7px;font-size:14px;}"
            "QPushButton:hover{background:rgba(255,255,255,35);border-color:rgba(255,255,255,75);}"
        )
        self.lock_button.clicked.connect(self.toggle_locked)
        footer = QHBoxLayout()
        for button, tip, direction in (
            (self.minus_button, "减少进度（长按加速）", -1),
            (self.plus_button, "增加进度（长按加速）", 1),
        ):
            button.setToolTip(tip)
            button.setFixedSize(30, 26)
            button.setStyleSheet(self.lock_button.styleSheet())
            button.pressed.connect(lambda direction=direction: self._start_progress_change(direction))
            button.released.connect(self._stop_progress_change)
            footer.addWidget(button)
        self.complete_button.setToolTip("标记为已完成")
        self.complete_button.setFixedSize(34, 26)
        self.complete_button.setStyleSheet(self.lock_button.styleSheet())
        self.complete_button.clicked.connect(self.completion_requested.emit)
        footer.addWidget(self.complete_button)
        footer.addStretch()
        footer.addWidget(self.lock_button)
        self.dismiss_button = QPushButton("×")
        self.dismiss_button.setToolTip("关闭悬浮窗（主界面可重新显示）")
        self.dismiss_button.setFixedSize(30, 26)
        self.dismiss_button.setStyleSheet(self.lock_button.styleSheet())
        self.dismiss_button.clicked.connect(self.dismiss)
        footer.addWidget(self.dismiss_button)
        layout.addLayout(footer)
        for widget in (self.icon, self.eyebrow, self.label, self.description, self.progress, self.progress_bar):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.placed = False
        self.locked = False
        self.drag_offset: QPoint | None = None
        self.opacity_percent = 72
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._apply_rounded_mask()

    def _start_progress_change(self, direction: int) -> None:
        self._repeat_direction = direction
        self._repeat_elapsed.start()
        self.progress_delta_requested.emit(direction)
        self._repeat_timer.start(420)

    def _repeat_progress_change(self) -> None:
        elapsed = self._repeat_elapsed.elapsed()
        if elapsed < 1400:
            step, interval = 1, 180
        elif elapsed < 2800:
            step, interval = 2, 105
        else:
            step, interval = 5, 60
        self.progress_delta_requested.emit(self._repeat_direction * step)
        self._repeat_timer.setInterval(interval)

    def _stop_progress_change(self) -> None:
        self._repeat_timer.stop()
        self._repeat_direction = 0

    def set_acrylic_opacity(self, percent: int) -> None:
        self.opacity_percent = max(30, min(95, int(percent)))
        self._enable_windows_acrylic()
        self.update()
        # Child widgets must be repainted against the newly cleared backing store.
        for child in self.findChildren(QWidget):
            child.update()

    def _apply_rounded_mask(self) -> None:
        self.clearMask()

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._apply_rounded_mask()
        if hasattr(self, "opacity_percent"):
            self._enable_windows_acrylic()
        super().resizeEvent(event)

    def _enable_windows_acrylic(self) -> None:
        if os.name != "nt":
            return

        class AccentPolicy(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_int),
            ]

        class WindowCompositionAttributeData(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t),
            ]

        alpha = round(1 + (self.opacity_percent - 30) / 65 * 253)
        red, green, blue = 28, 40, 58
        color = (alpha << 24) | (blue << 16) | (green << 8) | red
        policy = AccentPolicy(4, 0, color, 0)  # ACCENT_ENABLE_ACRYLICBLURBEHIND
        data = WindowCompositionAttributeData(
            19, ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p), ctypes.sizeof(policy)
        )
        setter = ctypes.windll.user32.SetWindowCompositionAttribute
        setter.argtypes = [ctypes.c_void_p, ctypes.POINTER(WindowCompositionAttributeData)]
        setter.restype = ctypes.c_int
        self.acrylic_result = setter(ctypes.c_void_p(int(self.winId())), ctypes.byref(data))
        # Ask DWM for native rounded corners as well; the Qt mask clips the
        # acrylic surface itself so no rectangular blur leaks outside.
        corner = ctypes.c_int(2)  # DWMWCP_ROUND; match the painted 8-DIP corner
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(int(self.winId())), 33, ctypes.byref(corner), ctypes.sizeof(corner)
        )

        border = ctypes.c_uint(0xFFFFFFFE)  # DWMWA_COLOR_NONE
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(int(self.winId())), 34, ctypes.byref(border), ctypes.sizeof(border)
        )

        class Margins(ctypes.Structure):
            _fields_ = [(key, ctypes.c_int) for key in ("left", "right", "top", "bottom")]
        margins = Margins(-1, -1, -1, -1)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
            ctypes.c_void_p(int(self.winId())), ctypes.byref(margins)
        )

    def toggle_locked(self) -> None:
        self.locked = not self.locked
        self.lock_button.setText("🔒" if self.locked else "🔓")
        self.lock_button.setToolTip("解锁位置" if self.locked else "锁定位置")
        self.setCursor(Qt.CursorShape.ArrowCursor if self.locked else Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.locked and event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.locked and self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.drag_offset = None
        super().mouseReleaseEvent(event)

    def place_default(self) -> None:
        """Place away from DBD's top-right notification feed."""

        bounds = QApplication.primaryScreen().availableGeometry()
        self.move(bounds.left() + 24, bounds.top() + 96)
        self.placed = True

    def dismiss(self) -> None:
        self.dismissed = True
        self.hide()

    def reopen(self) -> None:
        self.dismissed = False
        self.show()

    def display_task(self, task: TomeTask | None) -> None:
        if task is None:
            self.eyebrow.setText("DBD · 古书任务")
            self.label.setText("尚未识别古书任务")
            self.description.setText("")
            self.progress.setText("等待进度")
            self.progress_bar.setValue(0)
            self.minus_button.setEnabled(False)
            self.plus_button.setEnabled(False)
            self.complete_button.setEnabled(False)
        else:
            role = {"survivor": "逃生者", "killer": "杀手", "both": "双阵营", "unknown": "古书"}[task.role]
            self.eyebrow.setText(f"DBD · {role}任务")
            self.label.setText(task.title)
            self.description.setText(task.description)
            if task.completed:
                self.progress.setText("✓ 已完成")
                self.progress_bar.setValue(1000)
            elif task.display_progress:
                self.progress.setText(task.display_progress)
                percent = int(task.display_progress.split("%", 1)[0])
                self.progress_bar.setValue(max(0, min(1000, percent * 10)))
            elif task.current is not None and task.target:
                self.progress.setText(f"{task.current} / {task.target}")
                self.progress_bar.setValue(round(task.current / task.target * 1000))
            else:
                self.progress.setText("等待进度")
                self.progress_bar.setValue(0)
            editable = task.current is not None and task.target is not None
            self.minus_button.setEnabled(editable and task.current > 0)
            self.plus_button.setEnabled(editable and task.current < task.target)
            self.complete_button.setEnabled(editable and not task.completed)
        if not self.placed:
            self.place_default()
        if not self.isVisible() and not self.dismissed:
            self.show()
        self._enable_windows_acrylic()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        # WA_NoSystemBackground leaves the backing store untouched. Explicitly
        # replace old pixels before alpha painting, otherwise every slider tick
        # blends onto the previous frame and brightens text/control edges.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = self.rect().adjusted(1, 1, -1, -1)
        gradient = QLinearGradient(card.topLeft(), card.bottomRight())
        # A wide alpha range makes the UI slider visibly affect the acrylic card.
        veil = 8
        gradient.setColorAt(0, QColor(28, 40, 58, veil))
        gradient.setColorAt(1, QColor(20, 29, 43, max(4, veil - 8)))
        painter.setPen(QColor(255, 255, 255, 48))
        painter.setBrush(gradient)
        painter.drawRoundedRect(card, 8, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#60cdff"))
        painter.drawRoundedRect(1, 22, 3, self.height() - 44, 2, 2)
