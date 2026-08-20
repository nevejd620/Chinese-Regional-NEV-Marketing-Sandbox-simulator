"""
ensure_db.py — guarantee nev.db exists AND is usable before the app reads it.

nev.db is .gitignore'd, so on a fresh Streamlit Cloud container it won't exist
unless you either (A) force-add it to Git, or (B) regenerate it on first boot.
This module implements (B) and falls back to the mock so the skeleton always
renders. If you force-add a *healthy* nev.db (option A), this module no-ops.

Phase 5 fix: "file exists" is not the same as "database works". A 0-byte
placeholder, an LFS pointer, or an empty shell (0 tables) all pass exists()
and then blow up downstream in calibration.py with `no such table`. The
criterion is now: exists + non-trivial size + contains the tables we actually
read.
"""
from pathlib import Path
import sqlite3
import subprocess, sys

ROOT = Path(__file__).resolve().parent
DB   = ROOT / "nev.db"

# Tables calibration.py actually queries. The criterion is "does this DB
# support what we read", not "does it have all 6 Phase-0 tables".
REQUIRED_TABLES = {
    "sales_transactions",
    "model_dim",
    "supply_chain_costs",
    "macro_shocks_log",
    "financial_snapshots",
}

# Set by ensure_db(): True when the app is running on mock/regenerated data
# rather than the real Phase-0 nev.db. app.py can read this to show a banner.
IS_FALLBACK = False


def db_usable(path: Path = DB) -> bool:
    """exists + non-trivial size + has the tables we read."""
    if not path.exists() or path.stat().st_size < 1024:
        return False
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as con:
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.DatabaseError:
        return False          # corrupt / not actually a SQLite file
    missing = REQUIRED_TABLES - tables
    if missing:
        print(f"[ensure_db] nev.db present but unusable, missing tables: {sorted(missing)}")
        return False
    return True


def ensure_db() -> Path:
    global IS_FALLBACK
    if db_usable(DB):
        IS_FALLBACK = False
        return DB

    # An unusable file would block the mock writer below — clear it first.
    if DB.exists():
        DB.unlink()

    # ── OPTION B: regenerate from your Phase-0 DGP ───────────────────────
    # generate_data.build() returns (tables, ground_truth) IN MEMORY — it does
    # not write anything to disk. So the bootstrap has to persist them itself.
    try:
        import generate_data
        tables, truth = generate_data.build()
        with sqlite3.connect(DB) as con:
            for name, df in tables.items():
                df.to_sql(name, con, if_exists="replace", index=False)
        import json
        (ROOT / "ground_truth.json").write_text(
            json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
        if db_usable(DB):
            IS_FALLBACK = True     # regenerated, not the shipped Phase-0 DB
            return DB
    except Exception as e:  # noqa: BLE001
        print("[ensure_db] generate_data bootstrap failed:", e)

    # ── last resort: mock DB so the app still comes up ───────────────────
    try:
        subprocess.run([sys.executable, str(ROOT / "test" / "make_mock_db.py")],
                       check=True)
    except Exception as e:  # noqa: BLE001
        print("[ensure_db] mock bootstrap failed:", e)
    IS_FALLBACK = True
    return DB


if __name__ == "__main__":
    p = ensure_db()
    print("nev.db ready at:", p, "| usable:", db_usable(p), "| fallback:", IS_FALLBACK)
