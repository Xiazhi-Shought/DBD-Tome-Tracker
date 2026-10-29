import multiprocessing
import traceback
from pathlib import Path
import os

if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        import sys
        if '--self-test' in sys.argv:
            from desktranslate.release_check import check
            check(Path(sys.argv[sys.argv.index('--self-test') + 1]))
            raise SystemExit(0)
        from desktranslate.tome_app import main
        raise SystemExit(main())
    except Exception:
        log = Path(os.environ.get('LOCALAPPDATA', '.')) / 'DeskTranslate' / 'dbd-tome-tracker' / 'startup-error.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding='utf-8')
        raise
