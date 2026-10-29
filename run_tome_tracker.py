import multiprocessing
import traceback
from pathlib import Path
import os

if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        from desktranslate.tome_app import main
        raise SystemExit(main())
    except Exception:
        log = Path(os.environ.get('LOCALAPPDATA', '.')) / 'DeskTranslate' / 'dbd-tome-tracker' / 'startup-error.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding='utf-8')
        raise
