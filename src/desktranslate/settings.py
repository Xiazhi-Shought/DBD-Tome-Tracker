from pathlib import Path
import os
import sys

# Preserve legacy storage paths for existing tasks and OCR models.
def data_dir() -> Path:
    if override := os.environ.get("DESKTRANSLATE_DATA_DIR"):
        return Path(override)
    executable_dir = Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False) and (executable_dir / "portable-mode").is_file():
        return executable_dir / "DeskTranslateData"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "DeskTranslate"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "desktranslate"

