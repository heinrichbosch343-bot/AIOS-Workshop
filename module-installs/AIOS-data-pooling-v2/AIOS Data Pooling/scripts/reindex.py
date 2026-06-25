"""
Refresh the pool from Google Drive — the command you run after adding or editing files.

Incremental + idempotent: only new or changed files are re-embedded (unchanged files are
skipped via their content hash), so re-running is always safe and usually fast.

CLI:
    python reindex.py                  # refresh every client folder
    python reindex.py "Acme Corp"      # refresh one client only
    python reindex.py --dry-run        # show what WOULD be indexed, without embedding
"""
import argparse

from indexer import discover, reindex_all


def main() -> None:
    p = argparse.ArgumentParser(description="Refresh the data pool from Google Drive.")
    p.add_argument("client", nargs="?", default=None,
                   help="One client folder name (or id); omit to refresh everything")
    p.add_argument("--dry-run", action="store_true",
                   help="List the files that would be indexed, without embedding anything")
    a = p.parse_args()

    if a.dry_run:
        plan = discover(a.client)
        total = 0
        for company, files in plan.items():
            print(f"\n[{company}] {len(files)} candidate files")
            for f in files:
                print(f"  - {f['name']}" + (f"  (project: {f['project']})" if f.get("project") else ""))
            total += len(files)
        print(f"\n{total} files across {len(plan)} client folder(s). Run without --dry-run to index.")
        return

    totals = reindex_all(a.client)
    print(f"\nDone: {totals['indexed']} indexed ({totals['chunks']} chunks), "
          f"{totals['skipped']} unchanged/skipped, {totals['errors']} errors "
          f"out of {totals['files']} files.")


if __name__ == "__main__":
    main()
