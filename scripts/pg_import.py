"""
SIMRA CSV → POSTGRESQL IMPORT
==============================
Lit tous les fichiers *_rides.csv et *_incidents.csv dans converted_csv/
et les importe dans les tables gps_traces et incidents.

Prerequis:
    pip install psycopg2-binary pandas python-dotenv

Fichier .env a la racine du projet:
    DB_HOST=localhost
    DB_NAME=simra_berlin
    DB_USER=votre_admin
    DB_PASSWORD=votre_mot_de_passe

Lancement:
    python pg_import.py
"""


import os
import re
import io
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
from dotenv import load_dotenv

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

DB_CONFIG = {
    'host':     os.getenv('DB_HOST',     'localhost'),
    'database': os.getenv('DB_NAME',     'simra_berlin'),
    'user':     os.getenv('DB_USER',     'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
}

# Dossier contenant les CSV convertis (structure: converted_csv/ANNEE/MOIS/*.csv)
CSV_DIR = Path(os.getenv('CSV_DIR', 'C:/Users/PC/Documents/Projekt_Geodaten_haltung_Vernetzung/data/converted_csv'))

# Fichier de progression pour la reprise après interruption
PROGRESS_FILE = Path('progress.log')

# Bounding box Berlin — seuls les points dans cette zone sont importés
BERLIN = {
    'min_lon': 13.0884, 'max_lon': 13.7611,
    'min_lat': 52.3383, 'max_lat': 52.6755,
}

# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================
def load_progress():
    if not PROGRESS_FILE.exists():
        return set()
    with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())

def mark_done(filename):
    with open(PROGRESS_FILE, 'a', encoding='utf-8') as f:
        f.write(filename + '\n')

def in_berlin(lat, lon):
    """Retourne True si les coordonnées sont dans Berlin."""
    if pd.isna(lat) or pd.isna(lon):
        return False
    return (BERLIN['min_lon'] <= lon <= BERLIN['max_lon'] and
            BERLIN['min_lat'] <= lat <= BERLIN['max_lat'])


def extract_ride_id(filename):
    """
    Extrait l'identifiant de trajet depuis le nom de fichier.
    Ex: 'VM2_-11801195_rides.csv' → '-11801195'
        'VM2_18666164_incidents.csv' → '18666164'
    """
    stem = re.sub(r'_(incidents|rides)$', '', Path(filename).stem)
    parts = stem.split('_', 1)
    return parts[1] if len(parts) > 1 else stem


def to_int(val):
    return int(val) if pd.notna(val) else None

def to_float(val):
    return float(val) if pd.notna(val) else None

def to_bool(val):
    if pd.isna(val):
        return None
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ('true', '1', 'yes')

# ============================================================
# IMPORT GPS_TRACES (_rides.csv)
# ============================================================

def import_rides(conn, csv_file, year, month):
    """
    Importe les points GPS d'un fichier _rides.csv dans la table gps_traces.
    - Seules les lignes avec lat/lon valides et dans Berlin sont importées.
    - La géométrie est créée directement en SQL avec ST_MakePoint.
    """
    df = pd.read_csv(csv_file)

    if 'lat' not in df.columns or 'lon' not in df.columns:
        print(f"      ⚠ Colonnes lat/lon absentes : {csv_file.name}")
        return 0

    ride_id = extract_ride_id(csv_file.name)

    # Filtrer : coordonnées valides + dans Berlin
    df = df.dropna(subset=['lat', 'lon'])
    df = df[df.apply(lambda r: in_berlin(r['lat'], r['lon']), axis=1)]

    if df.empty:
        return 0

    # Construire les tuples à insérer.
    # lon et lat sont répétés en fin de tuple pour ST_MakePoint(lon, lat).
    args = [
        (
            ride_id,
            to_float(r.get('lat')),
            to_float(r.get('lon')),
            to_int(r.get('timeStamp')),
            to_float(r.get('acc')),
            to_bool(r.get('is_interpolated')),
            year, month,
            csv_file.name,
            to_float(r.get('lon')),   # pour ST_MakePoint
            to_float(r.get('lat')),
        )
        for _, r in df.iterrows()
    ]

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO gps_traces
                (ride_id, lat, lon, "timeStamp", acc, is_interpolated,
                 year, month, source_file, geom)
            VALUES %s
            ON CONFLICT (ride_id, "timeStamp", source_file) DO NOTHING
        """, args, template="""(
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            ST_SetSRID(ST_MakePoint(%s, %s), 4326)
        )""")
        conn.commit()

    return len(args)

# ============================================================
# IMPORT INCIDENTS (_incidents.csv)
# ============================================================

def import_incidents(conn, csv_file, year, month):
    """
    Importe les incidents d'un fichier _incidents.csv dans la table incidents.

    Deux cas possibles dans les fichiers SimRa :
    - Ligne AVEC lat/lon  → filtre Berlin appliqué, géométrie créée
    - Ligne SANS lat/lon  → importée avec geom = NULL (entrée technique, incident = -5)
    """
    df = pd.read_csv(csv_file)

    if 'incident' not in df.columns or 'bike' not in df.columns:
        print(f"      ⚠ Colonnes incident/bike absentes : {csv_file.name}")
        return 0

    ride_id = extract_ride_id(csv_file.name)

    # Lignes avec coordonnées : filtre Berlin
    has_coords = df['lat'].notna() & df['lon'].notna()
    df_avec    = df[has_coords].copy()
    df_avec    = df_avec[df_avec.apply(lambda r: in_berlin(r['lat'], r['lon']), axis=1)]

    # Lignes sans coordonnées : importées telles quelles (geom = NULL)
    df_sans = df[~has_coords].copy()

    df_all = pd.concat([df_avec, df_sans], ignore_index=True)

    if df_all.empty:
        return 0

    # lon/lat apparaissent 4× en fin de tuple pour le CASE WHEN + ST_MakePoint :
    # CASE WHEN lon IS NOT NULL AND lat IS NOT NULL
    #      THEN ST_SetSRID(ST_MakePoint(lon, lat), 4326)
    #      ELSE NULL END
    args = [
        (
            ride_id,
            to_float(r.get('lat')),
            to_float(r.get('lon')),
            to_int(r.get('ts')),
            to_int(r.get('bike')),
            to_int(r.get('incident')),
            to_int(r.get('scary')),
            year, month,
            csv_file.name,
            to_float(r.get('lon')),   # WHEN condition
            to_float(r.get('lat')),
            to_float(r.get('lon')),   # ST_MakePoint
            to_float(r.get('lat')),
        )
        for _, r in df_all.iterrows()
    ]

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO incidents
                (ride_id, lat, lon, ts, bike, incident, scary,
                 year, month, source_file, geom)
            VALUES %s
            ON CONFLICT (ride_id, ts, incident, source_file) DO NOTHING
        """, args, template="""(
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            CASE WHEN %s IS NOT NULL AND %s IS NOT NULL
                 THEN ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                 ELSE NULL
            END
        )""")
        conn.commit()

    return len(args)

# ============================================================
# FONCTION PRINCIPALE
# ============================================================

def main():
    print("\n" + "=" * 55)
    print("  SIMRA → POSTGRESQL IMPORT")
    print("=" * 55)
    print(f"  Base     : {DB_CONFIG['database']} @ {DB_CONFIG['host']}")
    print(f"  CSV dir  : {CSV_DIR}")
    print("=" * 55)

    # Vérification du dossier CSV
    if not CSV_DIR.exists():
        print(f"\n❌ Dossier introuvable : {CSV_DIR}")
        print("   Vérifiez CSV_DIR dans votre fichier .env ou la config.")
        return

    already_done = load_progress()
    if already_done:
        print(f"\n⏭️  Reprise : {len(already_done)} fichier(s) déjà traités, ignorés.")

    # Connexion à la base
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("\n✅ Connexion PostgreSQL établie")
    except Exception as e:
        print(f"\n❌ Connexion échouée : {e}")
        return

    total_gps = total_inc = errors = skipped = 0

    # Parcourir la structure converted_csv/ANNEE/MOIS/
    for year_dir in sorted(CSV_DIR.iterdir()):
        if not year_dir.is_dir() or year_dir.name == 'unknown':
            continue
        year = year_dir.name
        print(f"\n📁 Année {year}")

        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            month = month_dir.name
            csv_files = list(month_dir.glob("*.csv"))
            if not csv_files:
                continue
            print(f"   📁 Mois {month}  ({len(csv_files)} fichiers)")

            for csv_file in sorted(csv_files):
                if csv_file.name in already_done:
                    skipped += 1
                    continue
                try:
                    if csv_file.name.endswith('_rides.csv'):
                        n = import_rides(conn, csv_file, year, month)
                        total_gps += n
                        if n > 0:
                            print(f"      ✅ {csv_file.name} → {n} points GPS")
                        mark_done(csv_file.name)  # ← juste après le print ✅

                    elif csv_file.name.endswith('_incidents.csv'):
                        n = import_incidents(conn, csv_file, year, month)
                        total_inc += n
                        if n > 0:
                            print(f"      ✅ {csv_file.name} → {n} incidents")
                        mark_done(csv_file.name)  # ← juste après le print ✅
                        
                except Exception as e:
                    errors += 1
                    conn.rollback()
                    print(f"      ❌ Erreur dans {csv_file.name} : {e}")
                    if errors >= 20:
                        print("\n⛔ Trop d'erreurs (20+), import interrompu.")
                        conn.close()
                        return

    conn.close()

    print("\n" + "=" * 55)
    print("  RÉSULTATS")
    print("=" * 55)
    print(f"  Points GPS importés  : {total_gps:>10,}")
    print(f"  Incidents importés   : {total_inc:>10,}")
    print(f"  Fichiers ignorés     : {skipped:>10,}")
    print(f"  Erreurs              : {errors:>10}")
    print("=" * 55)

    if errors == 0 and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        print(f"\n🧹 Import complet — '{PROGRESS_FILE}' supprimé automatiquement.")


if __name__ == "__main__":
    main()
