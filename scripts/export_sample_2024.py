"""
EXPORT — SAMPLE DATA FOR JANUARY 2024 (CSV)
============================================
Exports a self-contained set of CSV files covering January 2024 only,
so the app can be tested WITHOUT setting up a full PostgreSQL
database or re-running the whole import pipeline. One month keeps
the sample small and fast to load while still exercising every part
of the app (flows, incidents, rate).

Produces, in data/sample_2024/:
    gps_traces_2024.csv   — GPS points for January 2024 rides
    incidents_2024.csv    — real incidents for January 2024 (technical rows excluded)
    ride_stats_2024.csv   — precomputed distance per January 2024 ride
    bezirk_risk.csv       — Bezirk-level incident rates (full 2021-2024
                             period — this table is NOT year-specific,
                             so it's exported in full regardless)

The app (app_improved.py) checks for these files first and only
falls back to a live database connection if they're missing — see
the corresponding change in the app's data-loading section.

Requirements:
    pip install psycopg2-binary pandas python-dotenv

Usage:
    python export_sample_2024.py
"""

import os
import pandas as pd
import psycopg2
from pathlib import Path
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

SAMPLE_YEAR = '2024'
SAMPLE_MONTH = '01'


def resolve_repo_paths():
    """Same upward-search logic as the app, so this script also works
    regardless of which subfolder it's placed in."""
    current = Path(__file__).resolve().parent
    for _ in range(6):
        if (current / "data" / "bezirke").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return Path(__file__).resolve().parent


REPO_ROOT = resolve_repo_paths()
OUTPUT_DIR = REPO_ROOT / "data" / "sample_2024"


def main():
    print("\n" + "=" * 55)
    print(f"  EXPORT — Sample data for year {SAMPLE_YEAR}")
    print("=" * 55)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("\n  PostgreSQL connection established")
    except Exception as e:
        print(f"\n  Connection failed: {e}")
        return

    # --------------------------------------------------------
    # 1. GPS traces for the sample year
    # --------------------------------------------------------
    print(f"\n  Exporting gps_traces ({SAMPLE_YEAR}-{SAMPLE_MONTH})...")
    df_gps = pd.read_sql("""
        SELECT ride_id, lat, lon, "timeStamp", year, month
        FROM gps_traces
        WHERE year = %(year)s AND month = %(month)s
    """, conn, params={"year": SAMPLE_YEAR, "month": SAMPLE_MONTH})
    gps_path = OUTPUT_DIR / "gps_traces_2024.csv"
    df_gps.to_csv(gps_path, index=False)
    print(f"    {len(df_gps):,} rows -> {gps_path.name} "
          f"({gps_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # --------------------------------------------------------
    # 2. Incidents for the sample year
    #    (technical rows -5/-2 excluded at export time — they're
    #    never used by the app anyway, so this also shrinks the file)
    # --------------------------------------------------------
    print(f"\n  Exporting incidents ({SAMPLE_YEAR}-{SAMPLE_MONTH})...")
    df_inc = pd.read_sql("""
        SELECT ride_id, lat, lon, incident, scary, year, month
        FROM incidents
        WHERE year = %(year)s AND month = %(month)s
          AND geom IS NOT NULL
          AND incident NOT IN (-5, -2)
    """, conn, params={"year": SAMPLE_YEAR, "month": SAMPLE_MONTH})
    inc_path = OUTPUT_DIR / "incidents_2024.csv"
    df_inc.to_csv(inc_path, index=False)
    print(f"    {len(df_inc):,} rows -> {inc_path.name} "
          f"({inc_path.stat().st_size / 1024:.1f} KB)")

    # --------------------------------------------------------
    # 3. Ride stats (distance) for the sample year
    # --------------------------------------------------------
    print(f"\n  Exporting ride_stats ({SAMPLE_YEAR}-{SAMPLE_MONTH})...")
    df_stats = pd.read_sql("""
        SELECT ride_id, distance_km, year, month
        FROM ride_stats
        WHERE year = %(year)s AND month = %(month)s
    """, conn, params={"year": SAMPLE_YEAR, "month": SAMPLE_MONTH})
    stats_path = OUTPUT_DIR / "ride_stats_2024.csv"
    df_stats.to_csv(stats_path, index=False)
    print(f"    {len(df_stats):,} rows -> {stats_path.name} "
          f"({stats_path.stat().st_size / 1024:.1f} KB)")

    # --------------------------------------------------------
    # 4. Bezirk risk table — full period, NOT year-specific
    #    (only 12 rows, trivial size, needed for the Rate tab
    #    regardless of which year is selected elsewhere)
    # --------------------------------------------------------
    print("\n  Exporting bezirk_risk (full period, all years)...")
    df_risk = pd.read_sql("SELECT * FROM bezirk_risk", conn)
    risk_path = OUTPUT_DIR / "bezirk_risk.csv"
    df_risk.to_csv(risk_path, index=False)
    print(f"    {len(df_risk):,} rows -> {risk_path.name}")

    conn.close()

    print("\n" + "=" * 55)
    print("  DONE")
    print("=" * 55)
    print(f"\n  All files saved under: {OUTPUT_DIR}")
    print("  These files travel WITH the project folder — no")
    print("  database setup needed to test the app with this sample.")


if __name__ == "__main__":
    main()
