import os, tempfile
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from desktranslate.tome_app import TomeControlWindow
from desktranslate.tome_config import TomeConfigStore
app=QApplication([])
with tempfile.TemporaryDirectory() as d, patch('desktranslate.tome_app.ModelManager') as mm, patch('desktranslate.tome_app.Hotkeys') as hk:
 mm.return_value.installed.return_value=True
 hk.return_value.register.return_value=[]
 with patch.object(QApplication,'installNativeEventFilter'),patch.object(QApplication,'removeNativeEventFilter'):
  w=TomeControlWindow(Path(d))
  w.hotkey_edit.setText('Ctrl+Alt+F8');w.save_hotkey()
  assert TomeConfigStore(Path(d)/'config.json').load().capture_hotkey=='Ctrl+Alt+F8'
  w.hotkey_edit.setText('bad');w.save_hotkey();assert w.config.capture_hotkey=='Ctrl+Alt+F8'
  hk.return_value.register.side_effect=[['Ctrl+Alt+F9'],[]]
  w.hotkey_edit.setText('Ctrl+Alt+F9');w.save_hotkey();assert w.config.capture_hotkey=='Ctrl+Alt+F8'
  assert not w.overlay.icon.pixmap().isNull()
  hk.return_value.register.side_effect=None
  hk.return_value.register.return_value=[]
  from PySide6.QtTest import QTest
  from PySide6.QtCore import Qt
  w.begin_hotkey_recording()
  QTest.keyClick(w.hotkey_edit, Qt.Key.Key_F8)
  assert w.config.capture_hotkey == 'F8'
  w.begin_hotkey_recording()
  QTest.keyClick(w.hotkey_edit, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
  assert w.config.capture_hotkey == 'Ctrl+Shift+K'
  w.begin_hotkey_recording()
  QTest.keyClick(w.hotkey_edit, Qt.Key.Key_Escape)
  assert w.config.capture_hotkey == 'Ctrl+Shift+K'
  assert not w.recording_hotkey
  print('PASS: F8, Ctrl+Shift+K auto-save; Esc cancel')
  w.overlay.dismiss()
  w.overlay.display_task(None)
  assert not w.overlay.isVisible()
  w.overlay.reopen()
  assert w.overlay.isVisible()
  from unittest.mock import patch as mock_patch
  with mock_patch('PySide6.QtWidgets.QMessageBox.about') as about:
   w.show_about()
   assert about.called
  print('PASS: overlay stays closed on updates, reopens, About dialog')
  w.task_title.setText('自动保存测试')
  w.task_description.setPlainText('修理发电机')
  w.task_target.setValue(10)
  w.task_current.setValue(3)
  QTest.qWait(650)
  w.close()
  w2=TomeControlWindow(Path(d))
  assert w2.task_title.text() == '自动保存测试'
  assert w2.task_current.value() == 3 and w2.task_target.value() == 10
  assert w2.config.capture_hotkey == 'Ctrl+Shift+K'
  w2.close()
  print('PASS: automatic task save and restart restores task and hotkey')
print('PASS: UI startup, logo, hotkey persistence, invalid input, conflict rollback')
