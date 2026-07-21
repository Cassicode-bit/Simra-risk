"""
ROUTING — STEP 2: DOWNLOAD BERLIN CYCLING-COMPATIBLE NETWORK
================================================================
Downloads the road network for Berlin from OpenStreetMap via OSMnx,
ONE BEZIRK AT A TIME, and saves each Bezirk's network as its own
GraphML file in data/routing/bezirke/.

Why per-Bezirk instead of one city-wide file: a single query for all
of Berlin (even excluding motorways) returns a response too large to
parse in memory on a typical machine. Downloading 12 smaller networks
(one per official Bezirk polygon, from Phase 3's `bezirke` table) and
NEVER merging them into one giant in-memory graph avoids that failure
entirely. During routing, only the 1-2 Bezirk graphs relevant to a
given ride are loaded at a time.

Network scope: instead of restricting to dedicated cycleways only,
this uses a custom filter that includes residential streets, tertiary
roads, service roads, tracks, footways and cycleways — everything a
real cyclist could realistically ride on (including e.g. shared paths
through parks) — while excluding motorways/trunk roads (illegal for
cyclists) and purely pedestrian-only infrastructure irrelevant to
riding (stairs, elevators, escalators, indoor corridors — e.g. inside
a U-Bahn station, which a cyclist would walk through, not ride).

Requirements:
    pip install osmnx networkx psycopg2-binary geopandas shapely python-dotenv

Usage:
    python download_bike_network.py
"""

import os
import time
import osmnx as ox
import pandas as pd
import psycopg2
import networkx as nx
from pathlib import Path
from shapely import wkt as shapely_wkt
from dotenv import load_dotenv

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

DB_CONFIG = {
    'host':     os.getenv('DB_HOST',     'localhost'),
    'database': os.getenv('DB_NAME',     'simra_inspired'),
    'user':     os.getenv('DB_USER',     'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
}

OUTPUT_DIR = Path("data/routing/bezirke")

CUSTOM_FILTER = (
    '["highway"]["area"!~"yes"]["access"!~"private"]'
    '["highway"!~"motorway|motorway_link|trunk|trunk_link|'
    'steps|elevator|escalator|corridor|bus_guideway|'
    'proposed|construction|abandoned|platform|raceway"]'
)

MAX_RETRIES = 2


def get_bezirke():
    """Loads the official Bezirke polygons from PostgreSQL (Phase 3)."""
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql("SELECT name, ST_AsText(geom) AS wkt FROM bezirke ORDER BY name", conn)
    conn.close()
    return df


def download_one_bezirk(name, polygon):
    """
    Downloads the network for a single Bezirk polygon, retrying once
    on failure (Overpass can time out transiently on large/complex
    polygons). Returns the graph, or None if all attempts fail.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            G = ox.graph_from_polygon(polygon, custom_filter=CUSTOM_FILTER)
            return G
        except Exception as e:
            print(f"    Attempt {attempt}/{MAX_RETRIES} failed: "
                  f"{type(e).__name__}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(5)
    return None


def main():
    print("\n" + "=" * 55)
    print("  DOWNLOAD — Berlin cycling-compatible network (per Bezirk)")
    print("=" * 55)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    bezirke_df = get_bezirke()
    print(f"\n  {len(bezirke_df)} Bezirke found in database")

    succeeded = []
    failed = []

    for _, row in bezirke_df.iterrows():
        name = row['name']
        output_file = OUTPUT_DIR / f"{name}.graphml"

        if output_file.exists():
            print(f"\n  {name}: already downloaded, skipping")
            succeeded.append(name)
            continue

        print(f"\n  Downloading: {name}")
        polygon = shapely_wkt.loads(row['wkt'])

        t0 = time.time()
        G = download_one_bezirk(name, polygon)
        elapsed = time.time() - t0

        if G is None:
            print(f"    FAILED after {MAX_RETRIES} attempts — skipping {name}")
            failed.append(name)
            continue

        print(f"    {len(G.nodes):,} nodes, {len(G.edges):,} edges "
              f"({elapsed:.1f}s)")

        # Save immediately — this Bezirk's graph is now off the Python
        # heap and safely on disk before moving to the next one, so
        # memory never accumulates across Bezirke.
        ox.save_graphml(G, filepath=str(output_file))
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"    Saved: {output_file} ({size_mb:.1f} MB)")
        succeeded.append(name)

        del G  # free memory explicitly before the next iteration

    print("\n" + "=" * 55)
    print("  RESULTS")
    print("=" * 55)
    print(f"  Succeeded : {len(succeeded)} — {succeeded}")
    print(f"  Failed    : {len(failed)} — {failed}")

    if failed:
        print("\n  Re-run this script to retry the failed Bezirke —")
        print("  already-downloaded ones will be skipped automatically.")
    else:
        print("\n  All Bezirke downloaded successfully.")


if __name__ == "__main__":
    main()
