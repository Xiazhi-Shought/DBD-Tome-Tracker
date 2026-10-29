"""Explicit packaged-runtime smoke test; never runs during normal startup."""
from pathlib import Path
import json

def check(report: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont
    from PySide6.QtWidgets import QApplication
    from desktranslate.ui.tome_overlay import TomeOverlay
    from desktranslate.ocr import RapidEngine
    app = QApplication([])
    overlay = TomeOverlay()
    overlay.display_task(None)
    overlay.set_acrylic_opacity(55)
    app.processEvents()
    overlay.dismiss()
    overlay.display_task(None)
    assert not overlay.isVisible()
    overlay.reopen()
    assert overlay.isVisible()
    image = Image.new('RGB', (900, 300), 'white')
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 44)
    ImageDraw.Draw(image).text((30, 30), '工程师协会\n修理10台发电机\n2/10', font=font, fill='black')
    engine = RapidEngine('zh-CN')
    result = engine.recognize(image, 'zh-CN')
    text = result.text
    engine.close()
    assert '工程师协会' in text and '10' in text, text
    overlay.close()
    report.write_text(json.dumps({'status': 'PASS', 'ocr': text, 'qt': 'show/opacity/dismiss/reopen passed'}, ensure_ascii=False), encoding='utf-8')
