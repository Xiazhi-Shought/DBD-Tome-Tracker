from __future__ import annotations

import json
import multiprocessing
import sys
from dataclasses import replace
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from desktranslate.capture import MSSCapture, enable_dpi_awareness
from desktranslate.hotkeys import Hotkeys
from desktranslate.ocr import ModelManager, RapidEngine
from desktranslate.settings import data_dir
from desktranslate.tome_config import TomeConfig, TomeConfigStore
from desktranslate.tome_service import TomeService


def main() -> int:
    multiprocessing.freeze_support()
    enable_dpi_awareness()
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    # The control window is intentionally hidden while the full-screen selector
    # is active. Closing the selector must not make Qt quit just because no
    # visible top-level window remains for a moment.
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("DBD 古书任务追踪器")
    from PySide6.QtGui import QIcon
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets/tome-logo.png")))
    app.setOrganizationName("DBD Tome Tracker")
    window = TomeControlWindow(data_dir() / "dbd-tome-tracker")
    window.show()
    return app.exec()


class TomeControlWindow:
    """Composition wrapper kept importable before Qt is initialized."""

    def __new__(cls, directory: Path):  # type: ignore[no-untyped-def]
        from PySide6.QtCore import QTimer, Qt, QEvent
        from PySide6.QtWidgets import (
            QApplication,
            QComboBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPushButton,
            QSlider,
            QSpinBox,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

        from desktranslate.ui.selection import RegionSelector
        from desktranslate.ui.tome_overlay import TomeOverlay

        class Window(QWidget):
            def __init__(self) -> None:
                super().__init__()
                directory.mkdir(parents=True, exist_ok=True)
                self.setWindowTitle("DBD 古书任务追踪器")
                self.resize(620, 560)
                self.config_store = TomeConfigStore(directory / "config.json")
                try:
                    self.config = self.config_store.load()
                except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                    self.config = TomeConfig()
                self.config = replace(
                    self.config, notification_region=self.fixed_notification_region()
                )
                self.config_store.save(self.config)
                self.results: Queue[tuple[str, object]] = Queue()
                self.selector = None
                self.overlay = TomeOverlay()
                self.overlay.set_acrylic_opacity(self.config.overlay_opacity)
                self.hotkeys = Hotkeys({"capture_task": self.select_task})
                QApplication.instance().installNativeEventFilter(self.hotkeys)
                self.hotkey_conflicts = self.hotkeys.register(
                    {"capture_task": self.config.capture_hotkey}
                )
                self.service = TomeService(
                    MSSCapture,
                    lambda: RapidEngine("zh-CN"),
                    directory / "active-task.json",
                )

                layout = QVBoxLayout(self)
                title = QLabel("DBD 古书任务追踪器")
                title.setStyleSheet("font-size:22px;font-weight:700")
                layout.addWidget(title)
                self.status = QLabel("正在检查中文 OCR 模型…")
                self.status.setWordWrap(True)
                layout.addWidget(self.status)
                shortcut_row = QHBoxLayout()
                shortcut = QLabel("截图快捷键（点击更改后按键，Esc 取消）：")
                self.hotkey_edit = QLineEdit(self.config.capture_hotkey)
                self.hotkey_edit.setReadOnly(True)
                self.hotkey_edit.installEventFilter(self)
                self.recording_hotkey = False
                self.pending_hotkey = None
                shortcut_row.addWidget(self.hotkey_edit)
                hotkey_save = QPushButton("更改快捷键")
                self.hotkey_save = hotkey_save
                hotkey_save.clicked.connect(self.begin_hotkey_recording)
                shortcut_row.addWidget(hotkey_save)
                layout.addLayout(shortcut_row)
                shortcut.setStyleSheet("color:#7fdcc0")
                layout.addWidget(shortcut)

                role_row = QHBoxLayout()
                role_row.addWidget(QLabel("任务阵营"))
                self.role = QComboBox()
                self.role.addItem("逃生者", "survivor")
                self.role.addItem("杀手", "killer")
                index = self.role.findData(self.config.role)
                self.role.setCurrentIndex(max(0, index))
                self.role.currentIndexChanged.connect(self.save_role)
                role_row.addWidget(self.role)
                role_row.addStretch()
                layout.addLayout(role_row)

                opacity_row = QHBoxLayout()
                opacity_row.addWidget(QLabel("悬浮窗透明度"))
                self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
                self.opacity_slider.setRange(30, 95)
                self.opacity_slider.setValue(self.config.overlay_opacity)
                self.opacity_value = QLabel(f"{self.config.overlay_opacity}%")
                self.opacity_slider.valueChanged.connect(self.save_overlay_opacity)
                opacity_row.addWidget(self.opacity_slider, 1)
                opacity_row.addWidget(self.opacity_value)
                layout.addLayout(opacity_row)

                layout.addWidget(QLabel("任务名称"))
                self.task_title = QLineEdit()
                self.task_title.setPlaceholderText("识别后会自动填入，可在这里修改")
                layout.addWidget(self.task_title)
                layout.addWidget(QLabel("任务详情"))
                self.task_description = QTextEdit()
                self.task_description.setPlaceholderText("任务要求会自动填入，可在这里修改")
                self.task_description.setMaximumHeight(105)
                layout.addWidget(self.task_description)
                progress_row = QHBoxLayout()
                progress_row.addWidget(QLabel("当前进度"))
                self.task_current = QSpinBox()
                self.task_current.setRange(0, 9999)
                progress_row.addWidget(self.task_current)
                progress_row.addWidget(QLabel("目标进度"))
                self.task_target = QSpinBox()
                self.task_target.setRange(1, 9999)
                progress_row.addWidget(self.task_target)
                progress_row.addStretch()
                layout.addLayout(progress_row)
                self.editor_loading = False
                self.editor_dirty = False
                self.editor_save_timer = QTimer(self)
                self.editor_save_timer.setSingleShot(True)
                self.editor_save_timer.setInterval(500)
                self.editor_save_timer.timeout.connect(self.save_editor_task)
                self.task_title.textEdited.connect(self.queue_editor_save)
                self.task_description.textChanged.connect(self.queue_editor_save)
                self.task_current.valueChanged.connect(self.queue_editor_save)
                self.task_target.valueChanged.connect(self.queue_editor_save)
                self.save_task_button = QPushButton("立即保存（修改后也会自动保存）")
                self.save_task_button.clicked.connect(self.save_editor_task)
                layout.addWidget(self.save_task_button)

                self.task_button = QPushButton("① 框选任务卡并识别名称和详情")
                self.task_button.clicked.connect(self.select_task)
                layout.addWidget(self.task_button)
                self.notice_button = QPushButton("② 使用固定右侧任务进度区域")
                self.notice_button.clicked.connect(self.use_fixed_notification_region)
                layout.addWidget(self.notice_button)
                self.start_button = QPushButton("③ 开始自动追踪")
                self.start_button.clicked.connect(self.toggle_monitor)
                layout.addWidget(self.start_button)
                extra_row = QHBoxLayout()
                show_overlay = QPushButton("显示悬浮窗")
                show_overlay.clicked.connect(self.overlay.reopen)
                extra_row.addWidget(show_overlay)
                hide_overlay = QPushButton("关闭悬浮窗")
                hide_overlay.clicked.connect(self.overlay.dismiss)
                extra_row.addWidget(hide_overlay)
                about_button = QPushButton("关于")
                about_button.clicked.connect(self.show_about)
                extra_row.addWidget(about_button)
                layout.addLayout(extra_row)

                self.timer = QTimer(self)
                self.timer.timeout.connect(self.poll)
                self.timer.start(100)
                self.ensure_models()
                if self.hotkey_conflicts:
                    self.status.setText(
                        f"快捷键 {self.config.capture_hotkey} 已被占用，请修改快捷键。"
                    )
                if self.service.tracker.task:
                    task = self.service.tracker.task
                    self.load_task_into_editor(task)
                    if task.current is not None and task.target is not None:
                        self.overlay.display_task(task)
                    else:
                        self.status.setText(
                            f"旧任务没有初始进度，请按 {self.config.capture_hotkey} 重新框选标题和进度数字。"
                        )

            def ensure_models(self) -> None:
                manager = ModelManager()
                if manager.installed("zh-CN", verify=True):
                    self.status.setText("中文 OCR 已就绪。任务进度将自动读取右侧固定区域。")
                    return
                self.set_controls(False)

                def install() -> None:
                    try:
                        manager.install("zh-CN", Event(), lambda *_: None)
                        self.results.put(("models", True))
                    except Exception as error:
                        self.results.put(("error", f"中文 OCR 模型准备失败：{error}"))

                Thread(target=install, name="dbd-tome-model-install", daemon=True).start()

            def set_controls(self, enabled: bool) -> None:
                for button in (self.task_button, self.notice_button, self.start_button):
                    button.setEnabled(enabled)

            def begin_hotkey_recording(self) -> None:
                self.hotkeys.close()
                self.recording_hotkey = True
                self.pending_hotkey = None
                self.hotkey_edit.setText("请按下按键…")
                self.hotkey_save.setEnabled(False)
                self.hotkey_edit.setFocus()
                self.hotkey_edit.grabKeyboard()

            def finish_hotkey_recording(self, value=None) -> None:
                self.recording_hotkey = False
                self.pending_hotkey = None
                self.hotkey_edit.releaseKeyboard()
                self.hotkey_save.setEnabled(True)
                self.hotkey_edit.setText(value or self.config.capture_hotkey)
                if value:
                    self.save_hotkey()
                    self.hotkey_edit.setText(self.config.capture_hotkey)
                else:
                    self.hotkeys.register({"capture_task": self.config.capture_hotkey})
                    self.status.setText("已取消更改快捷键。")

            def eventFilter(self, obj, event):
                if obj is self.hotkey_edit and self.recording_hotkey:
                    if event.type() == QEvent.Type.KeyPress:
                        if event.isAutoRepeat():
                            return True
                        key = event.key()
                        if key == Qt.Key.Key_Escape:
                            self.finish_hotkey_recording()
                            return True
                        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                            return True
                        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
                            name = chr(key)
                        elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
                            name = f"F{key - Qt.Key.Key_F1 + 1}"
                        else:
                            self.status.setText("请按字母、数字或 F1–F12，可搭配 Ctrl、Alt、Shift、Win。")
                            return True
                        mods = event.modifiers()
                        names = [n for flag, n in ((Qt.KeyboardModifier.ControlModifier, "Ctrl"), (Qt.KeyboardModifier.AltModifier, "Alt"), (Qt.KeyboardModifier.ShiftModifier, "Shift"), (Qt.KeyboardModifier.MetaModifier, "Win")) if mods & flag]
                        self.pending_hotkey = (key, "+".join(names + [name]))
                        self.hotkey_edit.setText(self.pending_hotkey[1])
                        return True
                    if event.type() == QEvent.Type.KeyRelease:
                        if not event.isAutoRepeat() and self.pending_hotkey and event.key() == self.pending_hotkey[0]:
                            self.finish_hotkey_recording(self.pending_hotkey[1])
                        return True
                    if event.type() == QEvent.Type.FocusOut:
                        self.finish_hotkey_recording()
                return super().eventFilter(obj, event)

            def save_hotkey(self) -> None:
                from desktranslate.shortcuts import parse_hotkey
                value = self.hotkey_edit.text().strip().replace(" ", "")
                old = self.config.capture_hotkey
                try:
                    parse_hotkey(value)
                except ValueError:
                    self.status.setText("格式错误：请使用 Ctrl、Alt、Shift 或 Win 加字母、数字或 F1–F12，例如 Ctrl+Shift+T。")
                    return
                conflicts = self.hotkeys.register({"capture_task": value})
                if conflicts:
                    self.hotkeys.register({"capture_task": old})
                    self.status.setText(f"快捷键 {value} 已被占用，保留原快捷键 {old}。")
                    return
                try:
                    updated = replace(self.config, capture_hotkey=value)
                    self.config_store.save(updated)
                except OSError:
                    self.hotkeys.register({"capture_task": old})
                    self.status.setText("保存失败，已恢复原快捷键。")
                    return
                self.config = updated
                self.status.setText(f"截图快捷键已更新为 {value}，重启后仍有效。")

            def save_role(self) -> None:
                self.config = replace(self.config, role=str(self.role.currentData()))
                self.config_store.save(self.config)

            def save_overlay_opacity(self, value: int) -> None:
                self.config = replace(self.config, overlay_opacity=value)
                self.config_store.save(self.config)
                self.opacity_value.setText(f"{value}%")
                self.overlay.set_acrylic_opacity(value)

            def fixed_notification_region(self):  # type: ignore[no-untyped-def]
                """DBD's right-side challenge progress card, relative to the primary display."""
                screen = QApplication.primaryScreen()
                geometry = screen.geometry()
                ratio = screen.devicePixelRatio()
                left = round(geometry.x() * ratio)
                top = round(geometry.y() * ratio)
                width = round(geometry.width() * ratio)
                height = round(geometry.height() * ratio)
                from desktranslate.models import Rect

                return Rect(
                    left + round(width * 0.74),
                    top + round(height * 0.29),
                    max(1, round(width * 0.26)),
                    max(1, round(height * 0.16)),
                )

            def use_fixed_notification_region(self) -> None:
                self.config = replace(
                    self.config, notification_region=self.fixed_notification_region()
                )
                self.config_store.save(self.config)
                region = self.config.notification_region
                self.status.setText(
                    f"已使用固定任务进度区域：{region.x}, {region.y}, "
                    f"{region.width} × {region.height}。"
                )

            def queue_editor_save(self, *_args) -> None:
                if not self.editor_loading:
                    self.editor_dirty = True
                    self.editor_save_timer.start()

            def load_task_into_editor(self, task) -> None:  # type: ignore[no-untyped-def]
                self.editor_loading = True
                self.task_title.setText(task.title)
                self.task_description.setPlainText(task.description)
                self.task_current.setValue(task.current if task.current is not None else 0)
                self.task_target.setValue(task.target if task.target is not None else 1)
                self.editor_loading = False

            def save_editor_task(self) -> None:
                title = self.task_title.text().strip()
                if not title:
                    self.status.setText("任务名称不能为空。")
                    return
                try:
                    task = self.service.set_manual_task(
                        title,
                        self.task_current.value(),
                        self.task_target.value(),
                        str(self.role.currentData()),
                        self.service.tracker.task.confidence if self.service.tracker.task else 0.0,
                        self.task_description.toPlainText(),
                    )
                except ValueError as error:
                    self.status.setText(str(error))
                    return
                self.editor_dirty = False
                self.status.setText("任务修改已自动保存，重启后会恢复。")
                self.overlay.display_task(task)

            def choose(self, callback, capture_callback=None) -> None:  # type: ignore[no-untyped-def]
                if self.selector is not None and not self.selector.closed:
                    return
                self.hide()
                self.overlay.hide()
                QApplication.processEvents()

                def start_selector() -> None:
                    self.selector = RegionSelector()
                    self.selector.selected.connect(callback)
                    if capture_callback is not None:
                        self.selector.selected_capture.connect(capture_callback)
                    self.selector.cancelled.connect(self.show)
                    self.selector.start()

                # Give Windows DWM enough time to remove our windows before the
                # selector freezes the desktop image.
                QTimer.singleShot(180, start_selector)

            def select_task(self) -> None:
                self.choose(lambda _region: None, self.task_selected)

            def task_selected(self, region, image) -> None:  # type: ignore[no-untyped-def]
                self.config = replace(self.config, task_region=region)
                self.config_store.save(self.config)
                self.status.setText("正在识别任务卡…")
                role = str(self.role.currentData())

                def recognize() -> None:
                    try:
                        task = self.service.recognize_task_details_image(image, role)
                        self.results.put(("task_details", task))
                    except Exception as error:
                        self.results.put(("error", f"任务卡识别失败：{error}"))

                Thread(target=recognize, name="dbd-tome-card", daemon=True).start()

            def show_about(self) -> None:
                QMessageBox.about(self, "关于 DBD 古书任务追踪器",
                    "<h3>DBD 古书任务追踪器</h3><p>版本 1.0.0</p>"
                    "<p>作者：Lohick</p>"
                    "<p>© 2026 Lohick。本项目原创内容及修改部分。</p>"
                    "<p>第三方代码与组件版权归各自权利人所有，详见随附许可证。</p>"
                    "<p>《黎明杀机》相关名称与商标归其权利人所有。<br>本工具为非官方项目，与游戏官方无关联。</p>")

            def toggle_monitor(self) -> None:
                if self.service.thread and self.service.thread.is_alive():
                    self.service.stop()
                    self.start_button.setText("③ 开始自动追踪")
                    self.status.setText("自动追踪已停止。")
                    return
                self.use_fixed_notification_region()
                self.service.start(self.config.notification_region)
                self.start_button.setText("停止自动追踪")
                self.status.setText("正在监控右上角任务进度提示。")
                self.overlay.display_task(self.service.tracker.task)

            def poll(self) -> None:
                while True:
                    try:
                        kind, payload = self.results.get_nowait()
                    except Empty:
                        break
                    if kind == "models":
                        self.set_controls(True)
                        self.status.setText("中文 OCR 已就绪。任务卡需框选一次；进度使用固定区域。")
                    elif kind == "task":
                        self.status.setText("任务已识别并保存。")
                        self.overlay.display_task(payload)
                    elif kind == "task_details":
                        recognized = payload
                        self.show()
                        self.raise_()
                        self.activateWindow()
                        current = recognized.current if recognized.current is not None else 0
                        target = recognized.target if recognized.target is not None else max(1, current)
                        try:
                            task = self.service.set_manual_task(
                                recognized.title,
                                current,
                                target,
                                recognized.role,
                                recognized.confidence,
                                recognized.description,
                            )
                        except ValueError as error:
                            self.status.setText(str(error))
                            continue
                        self.load_task_into_editor(task)
                        self.status.setText("识别完成，已直接生成悬浮窗；可在本页面修改。")
                        self.overlay.display_task(task)
                    else:
                        self.show()
                        self.set_controls(True)
                        self.status.setText(str(payload))
                task = self.service.next_task()
                while task is not None:
                    if not self.editor_dirty:
                        self.load_task_into_editor(task)
                    self.overlay.display_task(task)
                    task = self.service.next_task()

            def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
                self.editor_save_timer.stop()
                if self.editor_dirty:
                    self.save_editor_task()
                self.service.stop()
                self.hotkeys.close()
                QApplication.instance().removeNativeEventFilter(self.hotkeys)
                self.overlay.close()
                event.accept()

        return Window()


if __name__ == "__main__":
    raise SystemExit(main())
