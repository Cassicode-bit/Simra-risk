"""
ROUTING — EXTRACT DEDICATED CYCLEWAYS FOR MAP DISPLAY
=========================================================
Extracts ONLY the dedicated cycleway segments (highway=cycleway)
from the 12 Bezirk .graphml files, and saves them as a single
lightweight GeoJSON file for display on the Streamlit map.

This is separate from the stripped .pkl files used for routing
(which no longer carry the 'highway' tag needed to filter here).
The .graphml files still have full attributes, so we read from
those instead.

Why not display the full rideable network on the map: it includes
residential streets, footways, tracks — hundreds of thousands of
segments citywide. Showing all of that as a background layer would
be both misleading (not "pistes cyclables") and too heavy for the
browser to render smoothly. Dedicated cycleways are a much smaller,
semantically correct subset.

This is a one-time preprocessing step — run once, reused by the app
afterwards without needing to touch the graphml files again.

Requirements:
    pip install osmnx networkx

Usage:
    python extract_cycleways.py
"""

import osmnx as ox
import json
import time
from pathlib import Path


def resolve_repo_paths():
    """Return absolute paths to the Berlin bezirk graph files and output GeoJSON."""
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "data" / "routing" / "bezirke", repo_root / "data" / "routing" / "cycleways.geojson"


BEZIRKE_DIR, OUTPUT_FILE = resolve_repo_paths()


def extract_cycleways_from_graph(G):
    """
    Returns a list of [[lon, lat], [lon, lat]] segments for every
    edge tagged as a dedicated cycleway in this graph.
    """
    segments = []
    for u, v, data in G.edges(data=True):
        highway = data.get('highway', '')
        # highway can be a string or a list of strings in OSM data
        is_cycleway = (
            highway == 'cycleway'
            or (isinstance(highway, list) and 'cycleway' in highway)
        )
        if not is_cycleway:
            continue

        u_data = G.nodes[u]
        v_data = G.nodes[v]
        segment = [
            [u_data['x'], u_data['y']],
            [v_data['x'], v_data['y']],
        ]
        segments.append(segment)

    return segments


def main():
    print("\n" + "=" * 55)
    print("  EXTRACT — Dedicated cycleways for map display")
    print("=" * 55)

    graphml_files = sorted(BEZIRKE_DIR.glob("*.graphml"))
    print(f"\n  Found {len(graphml_files)} Bezirk network files\n")

    all_segments = []

    for graphml_file in graphml_files:
        print(f"  Processing: {graphml_file.stem}")
        t0 = time.time()
        G = ox.load_graphml(graphml_file)

        segments = extract_cycleways_from_graph(G)
        all_segments.extend(segments)

        print(f"    {len(segments):,} cycleway segments "
              f"({time.time() - t0:.1f}s)")

        del G  # free memory before loading the next Bezirk

    print(f"\n  Total cycleway segments across Berlin: {len(all_segments):,}")

    # Save as a simple GeoJSON FeatureCollection of LineStrings
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": seg},
            "properties": {}
        }
        for seg in all_segments
    ]
    geojson = {"type": "FeatureCollection", "features": features}

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)

    size_mb = OUTPUT_FILE.stat().st_size / (1024 * 1024)
    print(f"\n  Saved: {OUTPUT_FILE} ({size_mb:.1f} MB)")
    print("\n" + "=" * 55)
    print("  DONE")
    print("=" * 55)


if __name__ == "__main__":
    main()
