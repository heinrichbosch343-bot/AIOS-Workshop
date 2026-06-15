"""
Build (or refresh) the Knowledge Pool from the client Drive folders.

  python scripts/backfill_pool.py --dry-run          # show what WOULD be indexed (free, instant)
  python scripts/backfill_pool.py --client "Acme"    # index just one company folder
  python scripts/backfill_pool.py                    # index every selected company folder

A dry run never calls Voyage or downloads files — it only lists the folders/files that match,
so you can confirm the selection before spending any embedding budget.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import indexer  # noqa: E402


def _dry_run(client: str | None) -> None:
    plan = indexer.discover(client)
    if not plan:
        print("No company folders matched. Set POOL_CLIENT_ROOTS or check the folder name.")
        return
    grand = 0
    for company, files in plan.items():
        print(f"\n{company}: {len(files)} files to index")
        by_project: dict[str, list[str]] = {}
        for f in files:
            by_project.setdefault(f.get("project") or "(top level)", []).append(f["name"])
        for proj, names in by_project.items():
            print(f"  {proj}: {len(names)}")
            for nm in names[:10]:
                print(f"      - {nm}")
            if len(names) > 10:
                print(f"      ... +{len(names) - 10} more")
        grand += len(files)
    print(f"\nTotal: {grand} file(s) across {len(plan)} company folder(s). "
          f"Run without --dry-run to index them.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="list what would be indexed; no embedding")
    ap.add_argument("--client", default=None, help="limit to one company folder (name or id)")
    args = ap.parse_args()

    if args.dry_run:
        _dry_run(args.client)
    else:
        print(f"\nDone. {indexer.reindex_all(args.client)}")


if __name__ == "__main__":
    main()
