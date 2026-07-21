"""
SIMRA CSV KONVERTER
Konvertiert alle SimRa-Rohdateien in echte CSV-Dateien.
Jede Eingabedatei erzeugt zwei CSV-Dateien:
- <name>_incidents.csv
- <name>_rides.csv

Ausgabe sortiert nach Jahr und Monat:
  converted_csv/2022/01/VM2_..._incidents.csv

Konfiguration:
    Die Pfade werden relativ zum Projekt-Root aufgeloest (dieses Skript
    liegt in scripts/, das Projekt-Root ist der Ordner darueber). Das
    macht das Skript auf jedem Rechner lauffaehig, ohne einen fest
    einprogrammierten Windows-Pfad wie in einer frueheren Version.
    Optional koennen SIMRA_BASE_DIR / SIMRA_RAW_DIR / CSV_DIR ueber
    Umgebungsvariablen (siehe .env.example) ueberschrieben werden.

Requirements:
    pip install pandas python-dotenv

Usage:
    python scripts/Automation_Simra_CSV_Converter.py
"""

import os
import re
import io
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# KONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

BASE_DIR   = Path(os.getenv("SIMRA_BASE_DIR", str(PROJECT_ROOT)))
RAW_DIR    = Path(os.getenv("SIMRA_RAW_DIR", str(BASE_DIR / "data" / "raw")))
OUTPUT_DIR = Path(os.getenv("CSV_DIR", str(BASE_DIR / "data" / "converted_csv")))

# Exakter Separator wie in den Dateien (25 Gleichheitszeichen)
SEPARATOR = "========================="

# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def extract_year_month_from_path(file_path):
    path_parts = Path(file_path).parts
    year, month = None, None
    for part in path_parts:
        if re.match(r'^20\d{2}$', part):
            year = part
        if re.match(r'^(0[1-9]|1[0-2])$', part):
            month = part
    return year, month


def get_output_path(file_path, suffix):
    year, month = extract_year_month_from_path(file_path)
    target_dir = OUTPUT_DIR / year / month if (year and month) else OUTPUT_DIR / "unknown"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{Path(file_path).stem}{suffix}"


def fill_missing_coordinates(rides_df):
    if rides_df is not None and not rides_df.empty:
        if 'lat' in rides_df.columns and 'lon' in rides_df.columns:
            rides_df['is_interpolated'] = rides_df['lat'].isna()
            rides_df['lat'] = rides_df['lat'].ffill()
            rides_df['lon'] = rides_df['lon'].ffill()
    return rides_df  # toujours retourner le df


# ============================================================
# KONVERTIERUNGSFUNKTION
# ============================================================

def convert_simra_file(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    if SEPARATOR not in content:
        return None, None

    parts = content.split(SEPARATOR)
    if len(parts) < 2:
        return None, None

    incidents_part = parts[0].strip()
    rides_part     = parts[1].strip()

    # === 1. INCIDENTS ===
    incidents_df = None
    if incidents_part:
        lines, data_lines, header = incidents_part.split('\n'), [], None

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Überspringe Block-Kopfzeilen wie "73#1" oder "100#1#0"
            if re.match(r'^\d+#\d+(#\d+)?$', line):
                continue
            if line.startswith('key,lat,lon,ts,bike'):
                header = line
                continue
            # FIX: Datenzeile kann mit Ziffer ODER Komma beginnen (leere key-Felder)
            if header and ',' in line and (line[0].isdigit() or line[0] == ','):
                data_lines.append(line)

        if header and data_lines:
            fake_file = io.StringIO(header + '\n' + '\n'.join(data_lines) + '\n')
            try:
                incidents_df = pd.read_csv(fake_file)
            except Exception:
                incidents_df = None

    # === 2. RIDES ===
    rides_df = None
    if rides_part:
        lines, data_lines, header = rides_part.split('\n'), [], None

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if re.match(r'^\d+#\d+(#\d+)?$', line):
                continue
            # FIX: Header ohne espaces — "lat,lon,X,Y,Z,timeStamp"
            if line.startswith('lat,lon,'):
                header = line
                continue
            if header and ',' in line and (line[0].isdigit() or line[0] == ','):
                data_lines.append(line)

        if header and data_lines:
            fake_file = io.StringIO(header + '\n' + '\n'.join(data_lines) + '\n')
            try:
                rides_df = pd.read_csv(fake_file)
                rides_df = fill_missing_coordinates(rides_df)
            except Exception:
                rides_df = None

    return incidents_df, rides_df


# ============================================================
# HAUPTFUNKTION
# ============================================================

def main():
    print("\n" + "=" * 60)
    print("SIMRA → CSV KONVERTER")
    print("=" * 60)
    print(f"\nRAW_DIR    = {RAW_DIR}")
    print(f"OUTPUT_DIR = {OUTPUT_DIR}")

    if not RAW_DIR.exists():
        print(f"\n❌ RAW_DIR nicht gefunden: {RAW_DIR}")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    simra_files = [
        Path(root) / fn
        for root, _, filenames in os.walk(RAW_DIR)
        for fn in filenames
        if 'VM2_' in fn
    ]
    print(f"\n📄 {len(simra_files)} Datei(en) gefunden\n")

    if not simra_files:
        print("❌ Keine Dateien mit 'VM2_' gefunden. Bitte Pfad und Dateinamen prüfen.")
        return

    incidents_saved = rides_saved = errors = 0

    for i, file_path in enumerate(simra_files):
        if (i + 1) % 1000 == 0:
            print(f"  Fortschritt: {i+1}/{len(simra_files)}")
        try:
            incidents_df, rides_df = convert_simra_file(file_path)

            if incidents_df is not None and not incidents_df.empty:
                incidents_df.to_csv(get_output_path(file_path, '_incidents.csv'), index=False)
                incidents_saved += 1

            if rides_df is not None and not rides_df.empty:
                rides_df.to_csv(get_output_path(file_path, '_rides.csv'), index=False)
                rides_saved += 1

        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"❌ Fehler in {file_path.name}: {e}")

    print("\n" + "=" * 60)
    print("ERGEBNISSE")
    print("=" * 60)
    print(f"Verarbeitete Dateien:     {len(simra_files)}")
    print(f"Incident-CSV gespeichert: {incidents_saved}")
    print(f"Ride-CSV gespeichert:     {rides_saved}")
    print(f"Fehler:                   {errors}")

    print("\n📁 Ordnerstruktur:")
    for year_dir in sorted(OUTPUT_DIR.iterdir()):
        if year_dir.is_dir():
            print(f"   📁 {year_dir.name}/")
            for month_dir in sorted(year_dir.iterdir()):
                if month_dir.is_dir():
                    n = len(list(month_dir.glob("*.csv")))
                    print(f"      📁 {month_dir.name}/ ({n} CSV-Dateien)")


if __name__ == "__main__":
    main()
