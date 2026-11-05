#!/usr/bin/env python3
"""Rebuild everything the research put into Harties Board's seed, in the right order, in one go.

  python scripts/harties_refresh.py [--seed PATH]

Order matters: the directory first (events look their organisers up there), then the help numbers, then the events, then the pictures
(which only fill in listings that are already in the seed), then the duplicates are removed (outputs/community-app/directory/dupes.json).
Each step replaces only what it put there itself (the `origin` tag), so running it twice gives the same seed.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SEED = "C:/Users/gamin/BoschAI/harties-board/data/seed.local.json"

ap = argparse.ArgumentParser()
ap.add_argument("--seed", default=DEFAULT_SEED)
seed = ap.parse_args().seed
for step in (["harties_directory.py", "prepare"], ["harties_directory.py", "apply"], ["harties_directory.py", "merge", "--seed", seed],
             ["harties_numbers.py", "merge", "--seed", seed], ["harties_events.py", "merge", "--seed", seed],
             ["harties_pictures.py", "apply", "--seed", seed], ["harties_dedupe.py", "--seed", seed]):
    print("==", " ".join(step))
    done = subprocess.run([sys.executable, str(HERE / step[0]), *step[1:]], check=False)
    if done.returncode != 0:
        sys.exit(f"step failed: {' '.join(step)}")
