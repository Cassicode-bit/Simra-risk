"""
PHASE 3 — DOWNLOAD AND IMPORT OF BERLIN BEZIRKE
=================================================
Official source : Geoportal Berlin / GDI-BE
Service         : WFS ALKIS Berlin (OGC WFS 2.0.0)
Endpoint        : https://gdi.berlin.de/services/wfs/alkis_bezirke
License         : Datenlizenz Deutschland Zero 2.0

This script:
1. Queries the official WFS (OGC standard GetFeature request)
2. Retrieves the 12 Berlin Bezirke geometries in GeoJSON
3. Saves the file locally for reuse
4. Imports the geometries into a PostgreSQL/PostGIS table

Requirements:
    pip install geopandas requests psycopg2-binary python-dotenv

Usage:
    python phase3_bezirke.py
"""

import os
import json
import requests
import geopandas as gpd
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from shapely.geometry import MultiPolygon, Polygon
from io import BytesIO

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

# OGC WFS endpoint — Geoportal Berlin / GDI-BE
WFS_URL = "https://gdi.berlin.de/services/wfs/alkis_bezirke"

# WFS GetFeature parameters
# outputFormat=application/json returns GeoJSON directly
WFS_PARAMS = {
    "SERVICE":      "WFS",
    "VERSION":      "2.0.0",
    "REQUEST":      "GetFeature",
    "TYPENAMES":    "alkis_bezirke:bezirksgrenzen",
    "SRSNAME":      "EPSG:4326",       # Request WGS84 directly
    "outputFormat": "application/json",
    "COUNT":        "50",              # Max features (12 Bezirke)
}

# Local save paths
DATA_DIR     = Path("data/bezirke")
GEOJSON_PATH = DATA_DIR / "berlin_bezirke.geojson"

# Real column names, confirmed by manual inspection in Jupyter
NAME_COLUMN = "namgem"
ID_COLUMN   = "gem"


# ============================================================
# STEP 1 — WFS GetFeature REQUEST
# ============================================================

def fetch_bezirke_wfs():
    """
    Sends an OGC WFS 2.0.0 GetFeature request to the Geoportal Berlin.
    Returns a GeoDataFrame if successful, None otherwise.

    If the local GeoJSON already exists, it is loaded directly
    to avoid unnecessary network requests.
    """
    print("\n" + "=" * 55)
    print("  STEP 1 — WFS GetFeature Request")
    print("=" * 55)
    print(f"  Endpoint : {WFS_URL}")
    print(f"  TypeName : {WFS_PARAMS['TYPENAMES']}")
    print(f"  SRS      : {WFS_PARAMS['SRSNAME']}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Use cached file if available
    if GEOJSON_PATH.exists():
        print(f"\n  Cached file found: {GEOJSON_PATH}")
        print("  Loading from disk (delete to force re-download)")
        gdf = gpd.read_file(GEOJSON_PATH)
        return gdf

    print("\n  Sending WFS GetFeature request...")
    try:
        response = requests.get(WFS_URL, params=WFS_PARAMS, timeout=60)
        response.raise_for_status()

        # Check content type
        content_type = response.headers.get("Content-Type", "")
        print(f"  Response content-type: {content_type}")

        if "json" in content_type or response.content.strip().startswith(b"{"):
            # GeoJSON response
            gdf = gpd.read_file(BytesIO(response.content))
        else:
            # Fallback: try GML/XML parsing via GeoPandas
            print("  Non-JSON response — attempting GML parsing...")
            gdf = gpd.read_file(BytesIO(response.content))

        # Save locally for reuse
        gdf.to_file(GEOJSON_PATH, driver="GeoJSON")
        size_kb = GEOJSON_PATH.stat().st_size / 1024
        print(f"  Saved to: {GEOJSON_PATH} ({size_kb:.1f} KB)")
        return gdf

    except Exception as e:
        print(f"\n  WFS request failed: {e}")
        return None

# ============================================================
# STEP 2 — INSPECTION AND VALIDATION
# ============================================================

def inspect_bezirke(gdf):
    """
    Validates the downloaded GeoDataFrame:
    - Checks projection (must be WGS84 / EPSG:4326)
    - Lists available columns
    - Prints each Bezirk name
    Reprojects to WGS84 if needed.
    """
    print("\n" + "=" * 55)
    print("  STEP 2 — Inspection and validation")
    print("=" * 55)

    print(f"\n  Features retrieved : {len(gdf)}")
    print(f"  Projection         : {gdf.crs}")
    print(f"  Columns            : {list(gdf.columns)}")

    # Reproject to WGS84 if needed
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        print(f"\n  Reprojecting from {gdf.crs} to WGS84 (EPSG:4326)...")
        gdf = gdf.to_crs(epsg=4326)
        print("  Reprojection done")
    else:
        print("\n  WGS84 (EPSG:4326) confirmed — compatible with OSM and PostGIS")

    # Find name column
    print(f"\n  {'#':<4} {'Bezirk name'}")
    print("  " + "-" * 35)
    for i, (_, row) in enumerate(gdf.iterrows(), 1):
        print(f"  {i:<4} {row[NAME_COLUMN]}")
    return gdf

# ============================================================
# STEP 3 — CREATE POSTGRESQL TABLE
# ============================================================

def create_bezirke_table(conn):
    """
    Creates the bezirke table in PostgreSQL/PostGIS.
    Drops and recreates the table if it already exists.
    Adds spatial index (GIST) and name index.
    """
    print("\n" + "=" * 55)
    print("  STEP 3 — Creating bezirke table in PostgreSQL")
    print("=" * 55)

    with conn.cursor() as cur:
        cur.execute("""
            DROP TABLE IF EXISTS bezirke CASCADE;

            CREATE TABLE bezirke (
                id          SERIAL PRIMARY KEY,
                bezirk_id   TEXT,
                name        TEXT NOT NULL,
                geom        GEOMETRY(MultiPolygon, 4326)
            );

            CREATE INDEX idx_bezirke_geom ON bezirke USING GIST(geom);
            CREATE INDEX idx_bezirke_name ON bezirke(name);
        """)
        conn.commit()
    print("  Table bezirke created with GIST spatial index")

# ============================================================
# STEP 4 — IMPORT INTO POSTGRESQL
# ============================================================

def import_bezirke(conn, gdf):
    """
    Imports Bezirke geometries into PostgreSQL.
    Each geometry is cast to MultiPolygon for type consistency,
    then inserted via ST_GeomFromText with SRID 4326.
    """
    print("\n" + "=" * 55)
    print("  STEP 4 — Importing into PostgreSQL")
    print("=" * 55)

    print(f"  Using name column : '{NAME_COLUMN}'")
    print(f"  Using ID column   : '{ID_COLUMN}'")

    # Ensure all geometries are MultiPolygon
    gdf = gdf.copy()
    def to_multipolygon(geom):
        if isinstance(geom, Polygon):
            return MultiPolygon([geom])
        return geom
    gdf['geometry'] = gdf['geometry'].apply(to_multipolygon)

    count = 0
    with conn.cursor() as cur:
        for _, row in gdf.iterrows():
            bezirk_id = str(row[ID_COLUMN])
            name      = str(row[NAME_COLUMN])
            wkt       = row['geometry'].wkt
            cur.execute("""
                INSERT INTO bezirke (bezirk_id, name, geom)
                VALUES (%s, %s, ST_Multi(ST_GeomFromText(%s, 4326)))
            """, (bezirk_id, name, wkt))
            count += 1
        conn.commit()

    print(f"  {count} Bezirke imported into PostgreSQL")
    return count

# ============================================================
# STEP 5 — FINAL VERIFICATION
# ============================================================

def verify_import(conn):
    """
    Runs a verification query listing all imported Bezirke
    with their area in km² computed by PostGIS.
    """
    print("\n" + "=" * 55)
    print("  STEP 5 — Verifying import")
    print("=" * 55)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT name,
                   ROUND((ST_Area(geom::geography) / 1000000)::numeric, 2) AS area_km2
            FROM bezirke
            ORDER BY name;
        """)
        rows = cur.fetchall()

    print(f"\n  {'Bezirk':<32} {'Area (km2)':>10}")
    print("  " + "-" * 43)
    for name, area in rows:
        print(f"  {name:<32} {area:>10}")
    print(f"\n  Total: {len(rows)} Bezirke in database")

# ============================================================
# MAIN
# ============================================================

def main():
    print("\n" + "=" * 55)
    print("  PHASE 3 — BERLIN BEZIRKE (WFS OGC)")
    print("  Source : Geoportal Berlin / GDI-BE / ALKIS")
    print("  License: Datenlizenz Deutschland Zero 2.0")
    print("=" * 55)

    # Step 1: WFS GetFeature
    gdf = fetch_bezirke_wfs()
    if gdf is None or len(gdf) == 0:
        print("\n  No data retrieved — aborting.")
        return

    # Step 2: Inspect and validate
    gdf = inspect_bezirke(gdf)

    # Connect to PostgreSQL
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("\n  PostgreSQL connection established")
    except Exception as e:
        print(f"\n  Connection failed: {e}")
        return

    # Step 3: Create table
    create_bezirke_table(conn)

    # Step 4: Import
    n = import_bezirke(conn, gdf)

    # Step 5: Verify
    if n > 0:
        verify_import(conn)

    conn.close()
    print("\n" + "=" * 55)
    print("  PHASE 3 COMPLETE")
    print("=" * 55)


if __name__ == "__main__":
    main()
