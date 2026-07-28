"""
ensure_db.py — guarantee nev.db exists before the app reads it.

nev.db is .gitignore'd, so on a fresh Streamlit Cloud container it won't exist
unless you either (A) force-add it to Git, or (B) regenerate it on first boot.
This module implements (B) and falls back to the mock so the skeleton always
renders. If you force-add nev.db (option A), this module simply no-ops.
"""
from pathlib import Path
import subprocess, sys

ROOT = Path(__file__).resolve().parent
DB   = ROOT / "nev.db"


def ensure_db() -> Path:
    if DB.exists():
        return DB

    # ── OPTION B: regenerate from your Phase-0 DGP ───────────────────────
    # Wire this to generate_data.py's REAL entry point. I don't know its
    # function name, so it tries the common ones — replace with the true one.
    try:
        import generate_data  # your Phase-0 module (repo root)
        for fn in ("build_database", "build", "main", "generate", "run"):
            if hasattr(generate_data, fn):
                getattr(generate_data, fn)()
                break
        if DB.exists():
            return DB
    except Exception as e:  # noqa: BLE001
        print("[ensure_db] generate_data bootstrap failed:", e)

    # ── last resort: mock DB so the app still comes up ───────────────────
    try:
        subprocess.run([sys.executable, str(ROOT / "test" / "make_mock_db.py")],
                       check=True)
    except Exception as e:  # noqa: BLE001
        print("[ensure_db] mock bootstrap failed:", e)
    return DB


if __name__ == "__main__":
    print("nev.db ready at:", ensure_db())
