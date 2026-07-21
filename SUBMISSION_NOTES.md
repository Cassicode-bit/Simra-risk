# Hinweis zur Abgabe / Submission note

Aus Groessengruenden wurden zwei generierte/abgeleitete Datensaetze aus diesem
Paket entfernt (sie sind ohnehin ueber `.gitignore` von Git ausgeschlossen und
lassen sich vollstaendig neu erzeugen):

- `data/routing/` (Bezirks-Graphen, .graphml/.pkl, ~680 MB)
  → neu erzeugen mit `script_routing/download_bike_network.py` und
    `script_routing/convert_to_pickle.py`
- `data/sample_2024/gps_traces_2024.csv` (~132 MB)
  → neu erzeugen mit `scripts/export_sample_2024.py` (benoetigt eine
    laufende PostgreSQL/PostGIS-Datenbank mit importierten SimRa-Daten)

Alle uebrigen Beispieldaten (Bezirksgrenzen, Incidents, Ride-Stats,
Risikoraten) sind enthalten, sodass die App-Struktur nachvollziehbar bleibt,
auch ohne die volle Datenbank aufzusetzen.

---

For size reasons, two generated/derived datasets were removed from this
package (they are already excluded from Git via `.gitignore` and can be
fully regenerated):

- `data/routing/` (per-district road network graphs, .graphml/.pkl, ~680 MB)
  → regenerate with `script_routing/download_bike_network.py` and
    `script_routing/convert_to_pickle.py`
- `data/sample_2024/gps_traces_2024.csv` (~132 MB)
  → regenerate with `scripts/export_sample_2024.py` (requires a running
    PostgreSQL/PostGIS database with imported SimRa data)

All other sample data (district boundaries, incidents, ride stats, risk
rates) is included so the app's structure can be followed without setting
up the full database.
