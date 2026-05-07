#!/usr/bin/env python3
"""Delete dated tmp run directories older than the retention window.

Only directories named YYYY-MM-DD are eligible. Other tmp files or folders are
left untouched so this script cannot accidentally delete unrelated scratch data.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path


def parse_day(name: str) -> date | None:
    try:
        return datetime.strptime(name, "%Y-%m-%d").date()
    except ValueError:
        return None


def cleanup(root: Path, retention_days: int, today: date, dry_run: bool) -> list[Path]:
    tmp = root / "tmp"
    if not tmp.exists():
        return []

    cutoff = today - timedelta(days=retention_days)
    deleted: list[Path] = []
    for child in sorted(tmp.iterdir()):
        if not child.is_dir():
            continue
        child_day = parse_day(child.name)
        if child_day is None:
            continue
        if child_day < cutoff:
            deleted.append(child)
            if not dry_run:
                shutil.rmtree(child)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--retention-days", type=int, default=7)
    parser.add_argument("--today", help="Override current date as YYYY-MM-DD for testing")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.retention_days < 1:
        raise SystemExit("--retention-days must be >= 1")

    today = parse_day(args.today) if args.today else date.today()
    if today is None:
        raise SystemExit("--today must be YYYY-MM-DD")

    deleted = cleanup(args.root, args.retention_days, today, args.dry_run)
    action = "would delete" if args.dry_run else "deleted"
    for path in deleted:
        print(f"{action}: {path}")
    print(f"{action}_count={len(deleted)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
