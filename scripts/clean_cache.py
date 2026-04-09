from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]

for pyc_file in root.rglob("*.pyc"):
    pyc_file.unlink()

for cache_dir in sorted(root.rglob("__pycache__"), reverse=True):
    shutil.rmtree(cache_dir, ignore_errors=True)

print(root)
