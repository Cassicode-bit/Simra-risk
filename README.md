# SimRa Risk Berlin

SimRa Risk Berlin is a data-driven project for analyzing cycling movements, reported incidents, and incident rates in Berlin from 2021 to 2024 using data from the SimRa app. The project combines geospatial processing, PostgreSQL/PostGIS storage, routing workflows, and an interactive Streamlit dashboard.

## Project overview

This repository contains:

- a Streamlit application for visualizing cycling flows and incidents in Berlin
- data processing scripts for importing and preparing SimRa data
- routing scripts for building bike-compatible networks from OpenStreetMap
- PostgreSQL/PostGIS SQL scripts for spatial analysis and risk calculations

The main goal is to explore how cycling behavior and reported safety incidents relate across Berlin districts.

## Features

- Interactive map view of cycling trips and incidents
- District-level incident rate analysis
- Support for German and English UI text
- PostgreSQL/PostGIS integration for geospatial queries
- Routing workflow based on OSMnx and NetworkX

## Repository structure

- app/ – Streamlit application
- data/ – input and generated geospatial data
- scripts/ – data import, preprocessing, and routing scripts
- cache/ – cached routing graph data

## Requirements

The project depends on Python packages listed in requirements.txt. A typical setup includes:

- Streamlit
- PyDeck
- pandas
- geopandas
- networkx
- osmnx
- psycopg2-binary
- python-dotenv
- requests
- shapely
- tqdm

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/Cassicode-bit/Simra-risk.git
   cd Simra-risk
   ```

2. Create and activate a Python environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate

   On Windows PowerShell:

   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create a local environment file:

   Copy [.env.example](.env.example) to .env and replace the placeholder values with your own local settings.

## Downloading the sample data

The project includes a sample GPS dataset (`data/sample_2024/gps_traces_2024.csv`) directly in the repository. No additional download is required.

## Environment variables

The project uses a local .env file for database configuration. Sensitive values should never be committed to GitHub.

Required variables:

- DB_HOST
- DB_NAME
- DB_USER
- DB_PASSWORD

Example values are provided in [.env.example](.env.example).

## Running the app

Start the Streamlit dashboard locally:

```bash
streamlit run app/app_improved.py
```

## Data workflow

A typical workflow is:

1. Prepare or import the raw SIMRA data
2. Load the data into PostgreSQL/PostGIS
3. Download the Berlin bike network per district
4. Run the routing and analysis scripts
5. Open the Streamlit app to explore results

## GitHub and secrets

When publishing this project on GitHub:

- do not commit your real .env file
- keep secrets such as database passwords out of the repository
- use [.env.example](.env.example) as a template for collaborators
- if needed, add a GitHub repository secret or use a deployment environment for production credentials

## German version

### SimRa Risk Berlin

SimRa Risk Berlin ist ein datengetriebenes Projekt zur Analyse von Fahrradbewegungen, gemeldeten Unfällen und Unfallraten in Berlin auf Basis der SimRa-App. Das Projekt kombiniert Geodatenverarbeitung, PostgreSQL/PostGIS, Routing-Workflows und ein interaktives Streamlit-Dashboard.

### Überblick

Dieses Repository enthält:

- eine Streamlit-Anwendung zur Visualisierung von Fahrradströmen und Unfällen in Berlin
- Datenverarbeitungs-Skripte für den Import und die Aufbereitung von SimRa-Daten
- Routing-Skripte zur Erstellung eines fahrradfreundlichen Netzwerks aus OpenStreetMap
- PostgreSQL/PostGIS-SQL-Skripte für räumliche Analysen und Risikoberechnungen

### Funktionen

- Interaktive Kartenansicht von Fahrradfahrten und Unfällen
- Analyse der Unfallrate pro Bezirk
- Unterstützung für deutsche und englische UI-Texte
- PostgreSQL/PostGIS-Integration für räumliche Abfragen
- Routing-Workflow mit OSMnx und NetworkX

### Installation

1. Repository klonen:

   ```bash
   git clone https://github.com/Cassicode-bit/Simra-risk.git
   cd Simra-risk
   ```

2. Virtuelle Umgebung anlegen und aktivieren:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

   In PowerShell unter Windows:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Abhängigkeiten installieren:

   ```bash
   pip install -r requirements.txt
   ```

4. Lokale Konfigurationsdatei anlegen:

   Kopiere [.env.example](.env.example) nach .env und ersetze die Platzhalterwerte durch eigene lokale Einstellungen.

## Beispieldaten

Das Projekt enthält einen Beispiel-GPS-Datensatz (`data/sample_2024/gps_traces_2024.csv`) direkt im Repository. Ein separater Download ist nicht erforderlich.

### Umgebungsvariablen

Das Projekt verwendet eine lokale .env-Datei für die Datenbankkonfiguration. Sensitive Werte sollten niemals in GitHub hochgeladen werden.

Benötigte Variablen:

- DB_HOST
- DB_NAME
- DB_USER
- DB_PASSWORD

Beispielwerte finden sich in [.env.example](.env.example).

### Start der App

```bash
streamlit run app/app_improved.py
```

## License

This project is intended for research and personal analysis purposes. Please adapt the license according to your own needs before publishing publicly.
