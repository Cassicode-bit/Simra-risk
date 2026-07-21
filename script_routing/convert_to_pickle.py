"""
ROUTING — CONVERT EXISTING GRAPHML FILES TO PICKLE
=====================================================
One-time conversion of the 12 already-downloaded Bezirk .graphml
files into .pkl (pickle) files, which load MUCH faster (often 10-20x)
since GraphML is a slow-to-parse XML format.

Only needs to run once. Safe to re-run — existing .pkl files are
skipped.

Usage:
    python convert_to_pickle.py
"""

import osmnx as ox
import pickle
from pathlib import Path
import time

BEZIRKE_DIR = Path("data/routing/bezirke")


def main():
    print("\n" + "=" * 55)
    print("  CONVERT — GraphML to pickle (faster loading)")
    print("=" * 55)

    graphml_files = sorted(BEZIRKE_DIR.glob("*.graphml"))
    print(f"\n  Found {len(graphml_files)} GraphML files\n")

    for graphml_file in graphml_files:
        pickle_file = graphml_file.with_suffix(".pkl")

        if pickle_file.exists():
            print(f"  {graphml_file.stem}: already converted, skipping")
            continue

        print(f"  Converting: {graphml_file.stem}")
        t0 = time.time()
        G = ox.load_graphml(graphml_file)
        load_time = time.time() - t0

        with open(pickle_file, "wb") as f:
            pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

        size_mb = pickle_file.stat().st_size / (1024 * 1024)
        print(f"    Loaded GraphML in {load_time:.1f}s, "
              f"saved pickle ({size_mb:.1f} MB)")

    print("\n" + "=" * 55)
    print("  DONE")
    print("=" * 55)


if __name__ == "__main__":
    main()
