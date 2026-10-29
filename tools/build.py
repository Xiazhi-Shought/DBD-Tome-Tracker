from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', 'DBD-Tome-Tracker.spec'], cwd=root, check=True)
import PySide6
qt = Path(PySide6.__file__).parent
out = root / 'dist/DBD-Tome-Tracker'
for pattern in ('msvcp140*.dll', 'vcruntime140*.dll'):
    for path in qt.glob(pattern):
        shutil.copy2(path, out / '_internal' / path.name)
shutil.copy2(root / 'LICENSE', out / 'LICENSE.txt')
shutil.copy2(root / 'COPYRIGHT.txt', out / 'COPYRIGHT.txt')
print(out / 'DBD-Tome-Tracker.exe')
