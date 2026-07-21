"""
SIMRA RISK BERLIN — STREAMLIT APP
===================================
Interactive visualization of cycling GPS flows, incidents, and
incident rates per Bezirk in Berlin, based on SimRa data (2021-2024).

Tabs:
    1. Flux / Flows      — animated ride paths (TripsLayer)
    2. Incidents         — scatterplot of reported incidents
    3. Taux / Rate       — choropleth of incident rate per Bezirk

Requirements:
    pip install streamlit pydeck psycopg2-binary pandas python-dotenv

Usage:
    streamlit run app.py
"""

import streamlit as st
import streamlit.components.v1 as components
import pydeck as pdk
import pandas as pd
import psycopg2
import json
import time
import os
from pathlib import Path
from dotenv import load_dotenv

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()


def resolve_repo_paths():
    """
    Finds the project's root folder by walking UPWARD from wherever
    this app.py file happens to live, looking for a 'data/bezirke'
    folder. This makes the app work no matter which subfolder it's
    placed in (scripts/, app/, routing/, project root, or any future
    reorganization) — instead of assuming a fixed, hardcoded folder
    name like the previous version did (which broke the moment the
    file was moved anywhere other than exactly one level under a
    folder literally named "scripts").
    """
    current = Path(__file__).resolve().parent

    # Climb up at most 6 levels — enough for any reasonable project
    # depth, while avoiding an unbounded search if something's wrong.
    for _ in range(6):
        if (current / "data" / "bezirke").is_dir():
            return current
        parent = current.parent
        if parent == current:  # reached the filesystem root — stop
            break
        current = parent

    # Fallback: if no 'data/bezirke' folder was found anywhere above,
    # assume the project root is this file's own folder (previous
    # default behaviour), so the app still starts rather than crashing.
    return Path(__file__).resolve().parent


DB_CONFIG = {
    'host':     os.getenv('DB_HOST',     'localhost'),
    'database': os.getenv('DB_NAME',     'simra_inspired'),
    'user':     os.getenv('DB_USER',     'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
}

MAP_STYLE_OPTIONS = {
    "dark": {
        "label": "Dark",
        "pydeck": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        "tile_url": "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
    },
    "osm": {
        "label": "OSM",
        "pydeck": None,
        "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    },
    "satellite": {
        "label": "Satellite",
        "pydeck": "satellite",
        "tile_url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    },
}

BERLIN_LAT = 52.52
BERLIN_LON = 13.405

st.set_page_config(
    page_title="SimRa Risk Berlin",
    page_icon="🚴",
    layout="wide",
)

# ============================================================
# GLOBAL VISUAL POLISH
# ============================================================
# Custom CSS for a more intentional look: a cleaner font, an accent
# color consistent with the orange used for ride paths on the map,
# rounded metric cards, and a tidier sidebar/tabs styling.

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

html, body, [class*="css"]  {
    font-family: 'Inter', sans-serif;
}

h1, h2, h3 {
    color: #1c1c1c;
}

div[data-testid="stMetric"] {
    background: rgba(255, 120, 60, 0.07);
    border: 1px solid rgba(255, 120, 60, 0.30);
    border-radius: 10px;
    padding: 12px 16px;
}
div[data-testid="stMetricValue"] {
    color: #ff783c;
}

section[data-testid="stSidebar"] {
    background: #f7f7f9;
    border-right: 1px solid rgba(0,0,0,0.06);
}

button[data-baseweb="tab"] {
    font-weight: 600;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #ff783c !important;
    border-bottom-color: #ff783c !important;
}

div[role="radiogroup"] {
    gap: 4px;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# LANGUAGE / TRANSLATIONS
# ============================================================
# All user-facing text lives in this dictionary, keyed by language code.
# Adding a new language later only means adding one more key here.

TEXTS = {
    "de": {
        "sidebar_title": "🚴 SimRa Risk Berlin",
        "sidebar_intro": "Analyse von Fahrradströmen und Unfällen in Berlin (SimRa, 2021-2024)",
        "data_source_csv": "📁 Lokale Beispieldaten (Januar 2024) — keine Datenbank erforderlich",
        "data_source_db": "🗄️ Verbunden mit PostgreSQL-Datenbank",
        "language_label": "Sprache",
        "year_label": "Jahr",
        "month_label": "Monat",
        "day_label": "Tag",
        "no_days": "Keine Tage für diesen Monat gefunden.",
        "click_hint": "💡 Klicke auf eine Spur, um Details zur Fahrt zu sehen.",
        "markers_legend": "🟢 Start der Fahrt  |  🔴 Ende der Fahrt",
        "granularity_label": "Zeitraum",
        "granularity_month": "Monat",
        "granularity_week": "Woche",
        "granularity_day": "Tag",
        "week_label": "Woche (Start)",
        "no_weeks": "Keine Wochen für diesen Monat gefunden.",
        "anim_mode_label": "Anzeige",
        "anim_mode_static": "Statisch (alle Fahrten)",
        "anim_mode_all": "Alle Fahrten animieren",
        "anim_mode_single": "Eine Fahrt animieren",
        "select_ride_label": "Fahrt auswählen",
        "filter_note": "Die Filter Jahr/Monat gelten für die Tabs **Bewegungsströme** und "
                        "**Unfälle**. Der Tab **Unfallrate** zeigt immer die Daten "
                        "über den gesamten Zeitraum.",
        "app_title": "SimRa Risk Berlin",
        "app_intro": "Visualisierung der Fahrradbewegungen, gemeldeten Unfälle und "
                     "der Unfallrate pro Berliner Bezirk, basierend auf Daten der "
                     "**SimRa**-App (TU Berlin, 2021-2024).",
        "tab_flows": "🚴 Bewegungsströme",
        "tab_incidents": "⚠️ Unfälle",
        "tab_rate": "📊 Unfallrate",
        "flows_subheader": "Animierte Fahrradbewegungen",
        "no_gps_data": "Keine GPS-Daten für diesen Zeitraum.",
        "rides_loaded": "Geladene Fahrten (Stichprobe)",
        "rides_total": "Fahrten insgesamt (Monat)",
        "play_button": "▶️ Abspielen",
        "reset_button": "⏹️ Zurücksetzen",
        "time_slider": "Zeitpunkt",
        "trail_length_label": "Spurlänge (Sekunden)",
        "speed_label": "Animationsgeschwindigkeit (×)",
        "incidents_subheader": "Gemeldete Unfälle",
        "no_incidents": "Keine Unfälle für diesen Zeitraum.",
        "total_incidents": "Unfälle gesamt",
        "scary_incidents": "davon 'scary'",
        "scary_caption": "🔴 Rot = als gefährlich empfunden (scary)  |  🟠 Orange = nicht gefährlich",
        "rate_subheader": "Unfallrate pro Bezirk (gesamter Zeitraum 2021-2024)",
        "rate_caption": "🔴 Dunkelrot = hohe Unfallrate  |  ⚫ Grau/dunkel = niedrige Rate",
        "basemap_label": "Hintergrundkarte",
        "basemap_dark": "Dunkel",
        "basemap_osm": "OSM",
        "basemap_satellite": "Satellit",
        "map_legend": "🟠 Orange Linien = Fahrradtouren  |  Berlin-Bezirke in hellblau",
        "incident_hover_hint": "💡 Klicke auf einen Unfall, um die Adresse zu sehen.",
        "table_title": "Details pro Bezirk",
        "col_bezirk": "Bezirk",
        "col_incidents": "Unfälle",
        "col_km": "Gefahrene km",
        "col_rate": "Rate (Unfälle/km)",
    },
    "en": {
        "sidebar_title": "🚴 SimRa Risk Berlin",
        "sidebar_intro": "Analysis of cycling flows and incidents in Berlin (SimRa, 2021-2024)",
        "data_source_csv": "📁 Local sample data (January 2024) — no database required",
        "data_source_db": "🗄️ Connected to PostgreSQL database",
        "language_label": "Language",
        "year_label": "Year",
        "month_label": "Month",
        "day_label": "Day",
        "no_days": "No days found for this month.",
        "click_hint": "💡 Click a trace to see trip details.",
        "markers_legend": "🟢 Ride start  |  🔴 Ride end",
        "granularity_label": "Time range",
        "granularity_month": "Month",
        "granularity_week": "Week",
        "granularity_day": "Day",
        "week_label": "Week (starting)",
        "no_weeks": "No weeks found for this month.",
        "anim_mode_label": "Display",
        "anim_mode_static": "Static (all rides)",
        "anim_mode_all": "Animate all rides",
        "anim_mode_single": "Animate one ride",
        "select_ride_label": "Select ride",
        "filter_note": "The Year/Month filters apply to the **Flows** and "
                        "**Incidents** tabs. The **Incident rate** tab always "
                        "shows data aggregated over the full period.",
        "app_title": "SimRa Risk Berlin",
        "app_intro": "Visualization of cycling movements, reported incidents, "
                     "and the incident rate per Berlin district, based on data "
                     "collected by the **SimRa** app (TU Berlin, 2021-2024).",
        "tab_flows": "🚴 Flows",
        "tab_incidents": "⚠️ Incidents",
        "tab_rate": "📊 Incident rate",
        "flows_subheader": "Animated cycling flows",
        "no_gps_data": "No GPS data for this period.",
        "rides_loaded": "Rides loaded (sample)",
        "rides_total": "Total rides (month)",
        "play_button": "▶️ Play",
        "reset_button": "⏹️ Reset",
        "time_slider": "Time",
        "trail_length_label": "Trail length (seconds)",
        "speed_label": "Animation speed (×)",
        "incidents_subheader": "Reported incidents",
        "no_incidents": "No incidents for this period.",
        "total_incidents": "Total incidents",
        "scary_incidents": "Of which scary",
        "scary_caption": "🔴 Red = perceived as dangerous (scary)  |  🟠 Orange = not dangerous",
        "rate_subheader": "Incident rate per Bezirk (full period 2021-2024)",
        "rate_caption": "🔴 Dark red = high incident rate  |  ⚫ Grey/dark = low rate",
        "basemap_label": "Basemap",
        "basemap_dark": "Dark",
        "basemap_osm": "OSM",
        "basemap_satellite": "Satellite",
        "map_legend": "🟠 Orange lines = bike rides  |  Berlin districts in light blue",
        "incident_hover_hint": "💡 Click an incident to see its address.",
        "table_title": "Details per Bezirk",
        "col_bezirk": "Bezirk",
        "col_incidents": "Incidents",
        "col_km": "Km travelled",
        "col_rate": "Rate (incidents/km)",
    },
}

# Language selector — placed first, before anything else is rendered
lang = st.sidebar.selectbox("🌐 Sprache / Language", ["de", "en"], format_func=lambda l: "Deutsch" if l == "de" else "English")
t = TEXTS[lang]
selected_basemap = st.sidebar.selectbox(
    t["basemap_label"],
    ["dark", "osm", "satellite"],
    format_func=lambda key: {
        "dark": t["basemap_dark"],
        "osm": t["basemap_osm"],
        "satellite": t["basemap_satellite"],
    }[key],
)

# ============================================================
# DATABASE CONNECTION (cached)
# ============================================================

@st.cache_resource
def get_connection():
    return psycopg2.connect(**DB_CONFIG)


# ============================================================
# CSV SAMPLE DATA — optional, checked before falling back to the DB
# ============================================================
# If a `data/sample_2024/` folder with the expected CSV files exists
# (produced by export_sample_2024.py), the app uses those directly —
# no PostgreSQL setup required. This lets someone (e.g. a grader)
# test the app immediately with a self-contained 2024 sample, while
# the full multi-year experience still works normally against a real
# database if one is configured instead. Every load_* function below
# checks USE_CSV_DATA and branches accordingly.

SAMPLE_DIR = resolve_repo_paths() / "data" / "sample_2024"
USE_CSV_DATA = (SAMPLE_DIR / "gps_traces_2024.csv").exists()


@st.cache_data
def load_csv_gps():
    return pd.read_csv(
        SAMPLE_DIR / "gps_traces_2024.csv",
        dtype={"ride_id": str, "year": str, "month": str},
    )


@st.cache_data
def load_csv_incidents_raw():
    return pd.read_csv(
        SAMPLE_DIR / "incidents_2024.csv",
        dtype={"ride_id": str, "year": str, "month": str},
    )


@st.cache_data
def load_csv_ride_stats():
    return pd.read_csv(
        SAMPLE_DIR / "ride_stats_2024.csv",
        dtype={"ride_id": str, "year": str, "month": str},
    )


@st.cache_data
def load_csv_bezirk_risk_raw():
    return pd.read_csv(SAMPLE_DIR / "bezirk_risk.csv")


@st.cache_data
def load_available_years():
    if USE_CSV_DATA:
        return sorted(load_csv_gps()["year"].unique().tolist())
    conn = get_connection()
    df = pd.read_sql("SELECT DISTINCT year FROM gps_traces ORDER BY year", conn)
    return df['year'].tolist()


@st.cache_data
def load_available_months(year):
    if USE_CSV_DATA:
        df = load_csv_gps()
        return sorted(df.loc[df["year"] == year, "month"].unique().tolist())
    conn = get_connection()
    df = pd.read_sql(
        "SELECT DISTINCT month FROM gps_traces WHERE year = %s ORDER BY month",
        conn, params=(year,)
    )
    return df['month'].tolist()


@st.cache_data
def load_available_days(year, month):
    """
    Returns the sorted list of calendar days present in gps_traces
    for a given year/month, derived from the timeStamp column
    (epoch milliseconds converted to a real date).
    """
    if USE_CSV_DATA:
        df = load_csv_gps()
        sub = df[(df["year"] == year) & (df["month"] == month)]
        days = pd.to_datetime(sub["timeStamp"], unit="ms").dt.date.astype(str)
        return sorted(days.unique().tolist())

    conn = get_connection()
    df = pd.read_sql("""
        SELECT DISTINCT DATE(to_timestamp("timeStamp" / 1000.0)) AS day
        FROM gps_traces
        WHERE year = %s AND month = %s
        ORDER BY day
    """, conn, params=(year, month))
    return df['day'].astype(str).tolist()


@st.cache_data
def load_available_weeks(year, month):
    """
    Returns the sorted list of week start dates (Monday) present in
    gps_traces for a given year/month. Matches PostgreSQL's
    date_trunc('week', ...), which also uses Monday as the ISO week
    start — pandas' `.dt.weekday` (Monday=0) gives the same result.
    """
    if USE_CSV_DATA:
        df = load_csv_gps()
        sub = df[(df["year"] == year) & (df["month"] == month)]
        dates = pd.to_datetime(sub["timeStamp"], unit="ms")
        week_start = (dates - pd.to_timedelta(dates.dt.weekday, unit="D")).dt.date
        return sorted(week_start.astype(str).unique().tolist())

    conn = get_connection()
    df = pd.read_sql("""
        SELECT DISTINCT date_trunc('week', to_timestamp("timeStamp" / 1000.0))::date AS week_start
        FROM gps_traces
        WHERE year = %s AND month = %s
        ORDER BY week_start
    """, conn, params=(year, month))
    return df['week_start'].astype(str).tolist()


@st.cache_data
def load_total_ride_count(year, month):
    """Returns the real total number of distinct rides for the period,
    regardless of how many are actually loaded/displayed."""
    if USE_CSV_DATA:
        df = load_csv_gps()
        sub = df[(df["year"] == year) & (df["month"] == month)]
        return int(sub["ride_id"].nunique())

    conn = get_connection()
    df = pd.read_sql("""
        SELECT COUNT(DISTINCT ride_id) AS n
        FROM gps_traces
        WHERE year = %s AND month = %s
    """, conn, params=(year, month))
    return int(df['n'].iloc[0])


def _build_ride_paths(points_df, distance_map, point_step):
    """
    Shared path-building logic used by both the CSV and database
    branches of load_ride_paths, so the two stay perfectly consistent
    (downsampling, rounding, distance/duration computation).
    """
    paths = []
    for ride_id, group in points_df.groupby('ride_id'):
        group = group.iloc[::point_step]
        if len(group) < 2:
            continue
        t0 = group['timeStamp'].iloc[0]
        t_last = group['timeStamp'].iloc[-1]
        path = [[round(lon, 5), round(lat, 5)] for lon, lat in group[['lon', 'lat']].values]
        timestamps = [round(ts, 1) for ts in ((group['timeStamp'] - t0) / 1000.0).tolist()]
        duration_min = round((t_last - t0) / 1000.0 / 60.0, 1)
        distance_km = round(float(distance_map.get(ride_id, 0)), 2)

        paths.append({
            "path": path,
            "timestamps": timestamps,
            "ride_id": str(ride_id),
            "distance_km": distance_km,
            "duration_min": duration_min,
        })
    return paths


@st.cache_data
def load_ride_paths(year, month, granularity, day=None, week_start=None,
                     max_rides=None, point_step=3):
    """
    Loads rides for the flow map, at one of three granularities:
        - "day"   : all rides that started on a specific calendar day
        - "week"  : rides that started within a specific Mon-Sun week
        - "month" : rides that started anywhere in the selected month

    Day-level naturally has few rides, so all of them are loaded.
    Week and month level can have far more rides, so `max_rides`
    caps the sample size to keep the payload manageable (a random
    sample still preserves the overall spatial pattern).

    point_step keeps only every Nth GPS point per ride (SimRa records
    a point roughly every 250ms — far more detail than needed to see
    the shape and direction of a ride's path).

    Returns a list of dicts, one per ride:
        {
            "path": [[lon, lat], ...],
            "timestamps": [0, 1.2, 2.5, ...],
            "ride_id": "...",
            "distance_km": 4.72,
            "duration_min": 18.3
        }
    """
    if USE_CSV_DATA:
        df = load_csv_gps()
        sub = df[(df["year"] == year) & (df["month"] == month)].copy()
        if sub.empty:
            return []

        start_ts = sub.groupby("ride_id")["timeStamp"].min()

        if granularity == "day":
            match_dates = pd.to_datetime(start_ts, unit="ms").dt.date.astype(str)
            valid_rides = start_ts.index[match_dates == day]
        elif granularity == "week":
            week_start_dt = pd.to_datetime(week_start)
            week_end_dt = week_start_dt + pd.Timedelta(days=7)
            start_dates = pd.to_datetime(start_ts, unit="ms")
            valid_rides = start_ts.index[
                (start_dates >= week_start_dt) & (start_dates < week_end_dt)
            ]
        else:  # month
            valid_rides = start_ts.index

        if max_rides and len(valid_rides) > max_rides:
            valid_rides = pd.Index(valid_rides).to_series().sample(
                n=max_rides, random_state=None
            ).values

        if len(valid_rides) == 0:
            return []

        points_df = sub[sub["ride_id"].isin(valid_rides)].sort_values(
            ["ride_id", "timeStamp"]
        )

        stats_df = load_csv_ride_stats()
        distance_map = dict(zip(stats_df["ride_id"], stats_df["distance_km"]))

        return _build_ride_paths(points_df, distance_map, point_step)

    # -------------------- database branch --------------------
    conn = get_connection()

    if granularity == "day":
        date_filter = 'DATE(to_timestamp(start_ts / 1000.0)) = %s'
        date_param = (day,)
    elif granularity == "week":
        date_filter = (
            "to_timestamp(start_ts / 1000.0) >= %s::date "
            "AND to_timestamp(start_ts / 1000.0) < %s::date + INTERVAL '7 days'"
        )
        date_param = (week_start, week_start)
    else:
        date_filter = 'TRUE'
        date_param = ()

    limit_clause = "LIMIT %s" if max_rides else ""
    limit_param = (max_rides,) if max_rides else ()
    order_clause = "ORDER BY random()" if max_rides else ""

    query = f"""
        SELECT ride_id
        FROM (
            SELECT ride_id, MIN("timeStamp") AS start_ts
            FROM gps_traces
            WHERE year = %s AND month = %s
            GROUP BY ride_id
        ) sub
        WHERE {date_filter}
        {order_clause}
        {limit_clause}
    """
    ride_ids_df = pd.read_sql(
        query, conn, params=(year, month) + date_param + limit_param
    )

    if ride_ids_df.empty:
        return []

    ride_ids = tuple(ride_ids_df['ride_id'].tolist())

    points_df = pd.read_sql("""
        SELECT ride_id, lat, lon, "timeStamp"
        FROM gps_traces
        WHERE ride_id IN %s
        ORDER BY ride_id, "timeStamp"
    """, conn, params=(ride_ids,))

    distances_df = pd.read_sql("""
        SELECT ride_id, distance_km
        FROM ride_stats
        WHERE ride_id IN %s
    """, conn, params=(ride_ids,))
    distance_map = dict(zip(distances_df['ride_id'], distances_df['distance_km']))

    return _build_ride_paths(points_df, distance_map, point_step)


@st.cache_data
def load_incidents(year, month):
    if USE_CSV_DATA:
        df = load_csv_incidents_raw()
        sub = df[(df["year"] == year) & (df["month"] == month)]
        return sub[["lat", "lon", "incident", "scary"]].reset_index(drop=True)

    conn = get_connection()
    query = """
        SELECT lat, lon, incident, scary
        FROM incidents
        WHERE geom IS NOT NULL
          AND incident NOT IN (-5, -2)
          AND year = %s AND month = %s
    """
    return pd.read_sql(query, conn, params=(year, month))


@st.cache_data
def load_bezirk_risk():
    if USE_CSV_DATA:
        # Geometries come from the local Bezirke GeoJSON (already on
        # disk from Phase 3, no DB needed); stats come from the
        # exported bezirk_risk.csv. Matched by Bezirk name.
        boundaries = load_berlin_boundaries()
        risk_df = load_csv_bezirk_risk_raw()
        risk_map = risk_df.set_index("bezirk_name").to_dict(orient="index")

        rows = []
        for feature in boundaries.get("features", []):
            props = feature.get("properties", {})
            name = props.get("namgem") or props.get("name")
            stats = risk_map.get(name, {})
            rows.append({
                "name": name,
                "geojson": json.dumps(feature["geometry"]),
                "total_incidents": stats.get("total_incidents", 0),
                "total_km": stats.get("total_km", 0),
                "incident_rate": stats.get("incident_rate", 0),
            })
        return pd.DataFrame(rows).sort_values("name").reset_index(drop=True)

    conn = get_connection()
    query = """
        SELECT
            b.name,
            ST_AsGeoJSON(b.geom)   AS geojson,
            r.total_incidents,
            r.total_km,
            r.incident_rate
        FROM bezirke b
        LEFT JOIN bezirk_risk r ON b.name = r.bezirk_name
        ORDER BY b.name
    """
    return pd.read_sql(query, conn)


@st.cache_data
def load_berlin_boundaries():
    repo_root = resolve_repo_paths()
    boundaries_file = repo_root / "data" / "bezirke" / "berlin_bezirke.geojson"

    if not boundaries_file.exists():
        return {"type": "FeatureCollection", "features": []}

    with boundaries_file.open("r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# SIDEBAR — FILTERS
# ============================================================

st.sidebar.title(t["sidebar_title"])
st.sidebar.markdown(t["sidebar_intro"])

if USE_CSV_DATA:
    st.sidebar.success(t["data_source_csv"])
else:
    st.sidebar.info(t["data_source_db"])

st.sidebar.markdown("---")

years = load_available_years()
selected_year = st.sidebar.selectbox(t["year_label"], years, index=len(years) - 1)

months = load_available_months(selected_year)
selected_month = st.sidebar.selectbox(t["month_label"], months)

st.sidebar.markdown("---")
st.sidebar.caption(t["filter_note"])

# ============================================================
# MAIN — TABS
# ============================================================

st.title(t["app_title"])
st.markdown(t["app_intro"])

tab_flows, tab_incidents, tab_rate = st.tabs([
    t["tab_flows"], t["tab_incidents"], t["tab_rate"]
])

# ------------------------------------------------------------
# TAB 1 — FLOWS (animated TripsLayer)
# ------------------------------------------------------------
with tab_flows:
    st.subheader(f"{t['flows_subheader']} — {selected_month}/{selected_year}")

    # ------------------------------------------------------------
    # Granularity: Month / Week / Day
    # ------------------------------------------------------------
    granularity = st.radio(
        t["granularity_label"],
        ["month", "week", "day"],
        format_func=lambda g: {
            "month": t["granularity_month"],
            "week": t["granularity_week"],
            "day": t["granularity_day"],
        }[g],
        horizontal=True,
    )

    ride_paths = []

    if granularity == "day":
        available_days = load_available_days(selected_year, selected_month)
        if not available_days:
            st.warning(t["no_days"])
        else:
            selected_day = st.selectbox(t["day_label"], available_days, index=len(available_days) - 1)
            # A single day naturally has few rides — load all of them.
            ride_paths = load_ride_paths(
                selected_year, selected_month, "day", day=selected_day
            )

    elif granularity == "week":
        available_weeks = load_available_weeks(selected_year, selected_month)
        if not available_weeks:
            st.warning(t["no_weeks"])
        else:
            selected_week = st.selectbox(t["week_label"], available_weeks, index=len(available_weeks) - 1)
            # A week can have more rides than a day — sample to stay light.
            ride_paths = load_ride_paths(
                selected_year, selected_month, "week", week_start=selected_week, max_rides=200
            )

    else:  # month
        # A full month can have thousands of rides — sample for performance.
        ride_paths = load_ride_paths(
            selected_year, selected_month, "month", max_rides=150
        )

    if not ride_paths:
        st.warning(t["no_gps_data"])
    else:
        total_rides = load_total_ride_count(selected_year, selected_month)
        col_m1, col_m2 = st.columns(2)
        col_m1.metric(t["rides_total"], f"{total_rides:,}")
        col_m2.metric(t["rides_loaded"], f"{len(ride_paths):,}")

        # ------------------------------------------------------------
        # Two ways to animate: a button to animate ALL rides at once,
        # or clicking a single ride on the map to animate just that
        # one. Clicking a ride while "animate all" is active switches
        # to single-ride mode for that ride instead.
        # ------------------------------------------------------------
        animate_all = st.toggle(t["anim_mode_all"], value=False)

        trail_length = st.slider(t["trail_length_label"], 10, 300, 80)
        animation_speed = st.slider(t["speed_label"], 20, 900, 400)

        st.caption(t["click_hint"])
        st.caption(t["map_legend"])

        max_duration = max(p["timestamps"][-1] for p in ride_paths)

        all_rides_data = ride_paths

        all_rides_json = json.dumps(all_rides_data)
        berlin_boundaries_json = json.dumps(load_berlin_boundaries())
        basemap_tile_url = MAP_STYLE_OPTIONS[selected_basemap]["tile_url"]

        # ------------------------------------------------------------
        # Client-side rendering (deck.gl, running entirely in the browser)
        # ------------------------------------------------------------
        # No animation loop runs until the user actually clicks a ride —
        # the map starts fully static (fastest, lightest state), and an
        # animation only starts for the one specific ride that was
        # clicked, via requestAnimationFrame, entirely in the browser.
        html_code = f"""
        <div id="deck-container" style="height:600px; width:100%; position:relative; background:#111;"></div>
        <div id="deck-error" style="color:#ff6b6b; font-family:monospace; padding:8px;"></div>
        <div id="trip-info" style="
            display:none; position:absolute; z-index:10;
            background:rgba(20,20,20,0.92); color:#fff;
            border:1px solid #ff9933; border-radius:6px;
            padding:10px 14px; font-family:sans-serif; font-size:13px;
            pointer-events:none;
        "></div>
        <script src="https://unpkg.com/deck.gl@8.9.34/dist.min.js" id="deckgl-script"></script>
        <script>
        function initDeck() {{
            try {{
                const {{DeckGL, TripsLayer, PathLayer, TileLayer, BitmapLayer, ScatterplotLayer, GeoJsonLayer}} = deck;

                const allRidesData = {all_rides_json};
                const berlinBoundariesData = {berlin_boundaries_json};
                const loopLength = {max_duration};
                const trailLength = {trail_length};
                const animationSpeed = {animation_speed};
                const animateAll = {str(animate_all).lower()};

                const infoBox = document.getElementById('trip-info');
                const geocodeCache = {{}};
                let animationFrameId = null;
                let animatedRideId = null;

                async function getLocationName(lon, lat) {{
                    const key = `${{lat.toFixed(5)}},${{lon.toFixed(5)}}`;
                    if (geocodeCache[key]) return geocodeCache[key];

                    const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${{lat.toFixed(5)}}&lon=${{lon.toFixed(5)}}&zoom=18&addressdetails=1`;
                    try {{
                        const response = await fetch(url);
                        const data = await response.json();
                        const address = data.address || {{}};
                        const parts = [];
                        if (address.road) parts.push(address.road);
                        if (address.house_number) parts.push(address.house_number);
                        if (address.suburb && !parts.includes(address.suburb)) parts.push(address.suburb);
                        if (address.city_district && !parts.includes(address.city_district)) parts.push(address.city_district);
                        if (address.city && !parts.includes(address.city)) parts.push(address.city);
                        const name = parts.length ? parts.join(', ') : (data.display_name || null);
                        geocodeCache[key] = name;
                        return name;
                    }} catch (err) {{
                        geocodeCache[key] = null;
                        return null;
                    }}
                }}

                const tileLayer = new TileLayer({{
                    data: '{basemap_tile_url}',
                    minZoom: 0,
                    maxZoom: 19,
                    tileSize: 256,
                    renderSubLayers: props => {{
                        const {{boundingBox}} = props.tile;
                        return new BitmapLayer(props, {{
                            data: null,
                            image: props.data,
                            bounds: [
                                boundingBox[0][0], boundingBox[0][1],
                                boundingBox[1][0], boundingBox[1][1]
                            ]
                        }});
                    }}
                }});

                const berlinFillLayer = new GeoJsonLayer({{
                    id: 'berlin-fill',
                    data: berlinBoundariesData,
                    filled: true,
                    stroked: false,
                    getFillColor: [28, 61, 95, 34],
                    pickable: false
                }});

                const berlinBorderLayer = new GeoJsonLayer({{
                    id: 'berlin-borders',
                    data: berlinBoundariesData,
                    filled: false,
                    stroked: true,
                    getLineColor: [255, 255, 255, 220],
                    lineWidthMinPixels: 2.2,
                    pickable: false
                }});

                function buildStaticPathLayer(excludeRideId) {{
                    const data = excludeRideId
                        ? allRidesData.filter(d => d.ride_id !== excludeRideId)
                        : allRidesData;
                    return new PathLayer({{
                        id: 'static-paths',
                        data: data,
                        getPath: d => d.path,
                        getColor: [255, 120, 60, 200],
                        getWidth: 4,
                        widthMinPixels: 3,
                        pickable: true,
                        autoHighlight: true,
                        highlightColor: [255, 255, 0, 255]
                    }});
                }}

                function stopAnimation() {{
                    if (animationFrameId !== null) {{
                        cancelAnimationFrame(animationFrameId);
                        animationFrameId = null;
                    }}
                    animatedRideId = null;
                }}

                function renderStatic() {{
                    stopAnimation();
                    deckgl.setProps({{
                        layers: [
                            tileLayer, berlinFillLayer, berlinBorderLayer,
                            buildStaticPathLayer(null)
                        ]
                    }});
                }}

                function startRideAnimation(rideData) {{
                    stopAnimation();
                    animatedRideId = rideData.ride_id;
                    const rideDuration = rideData.timestamps[rideData.timestamps.length - 1];
                    const startTime = Date.now();
                    const staticOthers = buildStaticPathLayer(rideData.ride_id);

                    function animate() {{
                        const elapsed = ((Date.now() - startTime) / 1000) * animationSpeed;
                        const currentTime = elapsed % rideDuration;

                        const tripsLayer = new TripsLayer({{
                            id: 'trips',
                            data: [rideData],
                            getPath: d => d.path,
                            getTimestamps: d => d.timestamps,
                            getColor: [255, 120, 60],
                            opacity: 0.95,
                            widthMinPixels: 4,
                            rounded: true,
                            trailLength: trailLength * animationSpeed,
                            currentTime: currentTime,
                            pickable: true,
                            autoHighlight: true,
                            highlightColor: [255, 255, 0, 255]
                        }});

                        deckgl.setProps({{
                            layers: [
                                tileLayer, berlinFillLayer, berlinBorderLayer,
                                staticOthers, tripsLayer
                            ]
                        }});
                        animationFrameId = requestAnimationFrame(animate);
                    }}
                    animate();
                }}

                function startAllAnimation() {{
                    stopAnimation();
                    animatedRideId = 'ALL';

                    const startTime = Date.now();

                    function animate() {{
                        const elapsed = ((Date.now() - startTime) / 1000) * animationSpeed;
                        const currentTime = elapsed % loopLength;

                        const tripsLayer = new TripsLayer({{
                            id: 'trips',
                            data: allRidesData,
                            getPath: d => d.path,
                            getTimestamps: d => d.timestamps,
                            getColor: [255, 120, 60],
                            opacity: 0.95,
                            widthMinPixels: 3,
                            rounded: true,
                            trailLength: trailLength * animationSpeed,
                            currentTime: currentTime,
                            pickable: true,
                            autoHighlight: true,
                            highlightColor: [255, 255, 0, 255]
                        }});

                        deckgl.setProps({{
                            layers: [
                                tileLayer, berlinFillLayer, berlinBorderLayer,
                                tripsLayer
                            ]
                        }});
                        animationFrameId = requestAnimationFrame(animate);
                    }}
                    animate();
                }}

                const deckgl = new DeckGL({{
                    container: 'deck-container',
                    initialViewState: {{
                        longitude: {BERLIN_LON},
                        latitude: {BERLIN_LAT},
                        zoom: 10,
                        pitch: 0
                    }},
                    controller: true,
                    layers: [],
                    onClick: async (info) => {{
                        if (info.object && info.object.ride_id) {{
                            const d = info.object;
                            const startPoint = d.path[0];
                            const endPoint = d.path[d.path.length - 1];

                            infoBox.innerHTML = 'Loading location…';
                            infoBox.style.left = info.x + 'px';
                            infoBox.style.top = info.y + 'px';
                            infoBox.style.display = 'block';

                            const [startLabel, endLabel] = await Promise.all([
                                getLocationName(startPoint[0], startPoint[1]),
                                getLocationName(endPoint[0], endPoint[1]),
                            ]);

                            infoBox.innerHTML =
                                '<b>Start:</b> ' + (startLabel || 'Location unavailable') + '<br/>' +
                                '<b>End:</b> ' + (endLabel || 'Location unavailable') + '<br/>' +
                                '<b>Ride ID:</b> ' + d.ride_id + '<br/>' +
                                '<b>Distance:</b> ' + d.distance_km + ' km<br/>' +
                                '<b>Duration:</b> ' + d.duration_min + ' min';

                            // Clicking the ride that's already animating alone
                            // stops it (back to static, or back to "animate
                            // all" if that toggle is on). Clicking any other
                            // ride switches the animation to that one instead,
                            // overriding "animate all" for as long as it's active.
                            if (animatedRideId === d.ride_id) {{
                                animateAll ? startAllAnimation() : renderStatic();
                            }} else {{
                                startRideAnimation(d);
                            }}
                        }} else {{
                            infoBox.style.display = 'none';
                            animateAll ? startAllAnimation() : renderStatic();
                        }}
                    }}
                }});

                animateAll ? startAllAnimation() : renderStatic();
            }} catch (err) {{
                document.getElementById('deck-error').innerText = 'deck.gl error: ' + err.message;
            }}
        }}

        if (typeof deck !== 'undefined') {{
            initDeck();
        }} else {{
            document.getElementById('deckgl-script').addEventListener('load', initDeck);
            document.getElementById('deckgl-script').addEventListener('error', function() {{
                document.getElementById('deck-error').innerText =
                    'Failed to load deck.gl from CDN — check your internet connection.';
            }});
        }}
        </script>
        """

        components.html(html_code, height=650)

# ------------------------------------------------------------
# TAB 2 — INCIDENTS (Scatterplot)
# ------------------------------------------------------------
with tab_incidents:
    st.subheader(f"{t['incidents_subheader']} — {selected_month}/{selected_year}")

    df_inc = load_incidents(selected_year, selected_month)

    if df_inc.empty:
        st.warning(t["no_incidents"])
    else:
        col1, col2 = st.columns(2)
        col1.metric(t["total_incidents"], f"{len(df_inc):,}")
        col2.metric(t["scary_incidents"], f"{(df_inc['scary'] == 1).sum():,}")

        df_inc = df_inc.copy()
        df_inc['lon'] = df_inc['lon'].round(5)
        df_inc['lat'] = df_inc['lat'].round(5)
        df_inc['severity_text'] = df_inc['scary'].apply(
            lambda s: 'scary' if s == 1 else 'not scary'
        )
        df_inc['color'] = df_inc['scary'].apply(
            lambda s: [220, 30, 30, 180] if s == 1 else [255, 165, 0, 160]
        )

        st.caption(t["incident_hover_hint"])

        incidents_json = json.dumps(
            df_inc[['lon', 'lat', 'severity_text', 'color']].to_dict('records')
        )
        berlin_boundaries_json = json.dumps(load_berlin_boundaries())
        basemap_tile_url = MAP_STYLE_OPTIONS[selected_basemap]["tile_url"]

        # ------------------------------------------------------------
        # Client-side rendering (deck.gl), mirroring the Flows tab.
        # A native pydeck tooltip can only template existing columns —
        # it can't make an async network call — so reverse-geocoding
        # the incident's address on hover requires this custom
        # deck.gl component instead of st.pydeck_chart.
        # ------------------------------------------------------------
        html_code = f"""
        <div id="deck-container-inc" style="height:600px; width:100%; position:relative; background:#111;"></div>
        <div id="deck-error-inc" style="color:#ff6b6b; font-family:monospace; padding:8px;"></div>
        <div id="incident-info" style="
            display:none; position:absolute; z-index:10;
            background:rgba(20,20,20,0.92); color:#fff;
            border:1px solid #ff9933; border-radius:6px;
            padding:10px 14px; font-family:sans-serif; font-size:13px;
            pointer-events:none;
        "></div>
        <script src="https://unpkg.com/deck.gl@8.9.34/dist.min.js" id="deckgl-script-inc"></script>
        <script>
        function initDeckIncidents() {{
            try {{
                const {{DeckGL, TileLayer, BitmapLayer, ScatterplotLayer, GeoJsonLayer}} = deck;

                const incidentsData = {incidents_json};
                const berlinBoundariesData = {berlin_boundaries_json};

                const infoBox = document.getElementById('incident-info');
                const geocodeCache = {{}};
                let hoverToken = 0;

                async function getLocationName(lon, lat) {{
                    const key = `${{lat.toFixed(5)}},${{lon.toFixed(5)}}`;
                    if (geocodeCache[key]) return geocodeCache[key];

                    const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${{lat.toFixed(5)}}&lon=${{lon.toFixed(5)}}&zoom=18&addressdetails=1`;
                    try {{
                        const response = await fetch(url);
                        const data = await response.json();
                        const address = data.address || {{}};
                        const parts = [];
                        if (address.road) parts.push(address.road);
                        if (address.house_number) parts.push(address.house_number);
                        if (address.suburb && !parts.includes(address.suburb)) parts.push(address.suburb);
                        if (address.city_district && !parts.includes(address.city_district)) parts.push(address.city_district);
                        if (address.city && !parts.includes(address.city)) parts.push(address.city);
                        const name = parts.length ? parts.join(', ') : (data.display_name || null);
                        geocodeCache[key] = name;
                        return name;
                    }} catch (err) {{
                        geocodeCache[key] = null;
                        return null;
                    }}
                }}

                const tileLayer = new TileLayer({{
                    data: '{basemap_tile_url}',
                    minZoom: 0,
                    maxZoom: 19,
                    tileSize: 256,
                    renderSubLayers: props => {{
                        const {{boundingBox}} = props.tile;
                        return new BitmapLayer(props, {{
                            data: null,
                            image: props.data,
                            bounds: [
                                boundingBox[0][0], boundingBox[0][1],
                                boundingBox[1][0], boundingBox[1][1]
                            ]
                        }});
                    }}
                }});

                const berlinFillLayer = new GeoJsonLayer({{
                    id: 'berlin-fill-inc',
                    data: berlinBoundariesData,
                    filled: true,
                    stroked: false,
                    getFillColor: [28, 61, 95, 34],
                    pickable: false
                }});

                const berlinBorderLayer = new GeoJsonLayer({{
                    id: 'berlin-borders-inc',
                    data: berlinBoundariesData,
                    filled: false,
                    stroked: true,
                    getLineColor: [255, 255, 255, 220],
                    lineWidthMinPixels: 2.2,
                    pickable: false
                }});

                const scatterLayer = new ScatterplotLayer({{
                    id: 'incidents',
                    data: incidentsData,
                    getPosition: d => [d.lon, d.lat],
                    getFillColor: d => d.color,
                    // radiusUnits: 'pixels' keeps dots a consistent small
                    // size on screen regardless of zoom level. Without this,
                    // deck.gl treats getRadius as METRES by default, which
                    // makes points grow larger and larger (in screen space)
                    // the more you zoom in — exactly the "huge dots" issue.
                    radiusUnits: 'pixels',
                    getRadius: 6,
                    radiusMinPixels: 4,
                    radiusMaxPixels: 10,
                    pickable: true,
                    autoHighlight: true,
                    highlightColor: [255, 255, 0, 220]
                }});

                const deckglIncidents = new DeckGL({{
                    container: 'deck-container-inc',
                    initialViewState: {{
                        longitude: {BERLIN_LON},
                        latitude: {BERLIN_LAT},
                        zoom: 10,
                        pitch: 0
                    }},
                    controller: true,
                    layers: [tileLayer, berlinFillLayer, berlinBorderLayer, scatterLayer],
                    // Click-triggered popup instead of hover: hovering used to
                    // fire a network geocoding request on every mouse movement
                    // over a point, which made the map feel sluggish. A single
                    // request per click is far lighter and matches the Flows tab.
                    onClick: async (info) => {{
                        if (info.object) {{
                            const d = info.object;
                            const myToken = ++hoverToken;

                            infoBox.innerHTML = '<b>' + d.severity_text + '</b><br/>Loading address…';
                            infoBox.style.left = info.x + 'px';
                            infoBox.style.top = info.y + 'px';
                            infoBox.style.display = 'block';

                            const address = await getLocationName(d.lon, d.lat);
                            if (myToken !== hoverToken) return;

                            infoBox.innerHTML =
                                '<b>' + d.severity_text + '</b><br/>' +
                                (address || 'Address unavailable');
                        }} else {{
                            hoverToken++;
                            infoBox.style.display = 'none';
                        }}
                    }}
                }});
            }} catch (err) {{
                document.getElementById('deck-error-inc').innerText = 'deck.gl error: ' + err.message;
            }}
        }}

        if (typeof deck !== 'undefined') {{
            initDeckIncidents();
        }} else {{
            document.getElementById('deckgl-script-inc').addEventListener('load', initDeckIncidents);
            document.getElementById('deckgl-script-inc').addEventListener('error', function() {{
                document.getElementById('deck-error-inc').innerText =
                    'Failed to load deck.gl from CDN — check your internet connection.';
            }});
        }}
        </script>
        """

        components.html(html_code, height=650)

        st.caption(t["scary_caption"])

# ------------------------------------------------------------
# TAB 3 — INCIDENT RATE (Choropleth)
# ------------------------------------------------------------
with tab_rate:
    st.subheader(t["rate_subheader"])

    df_risk = load_bezirk_risk()

    features = []
    for _, row in df_risk.iterrows():
        geom = json.loads(row['geojson'])
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "name": row['name'],
                "total_incidents": int(row['total_incidents']) if pd.notna(row['total_incidents']) else 0,
                "total_km": float(row['total_km']) if pd.notna(row['total_km']) else 0,
                "incident_rate": float(row['incident_rate']) if pd.notna(row['incident_rate']) else 0,
            }
        })
    geojson_data = {"type": "FeatureCollection", "features": features}

    max_rate = df_risk['incident_rate'].max()

    def rate_to_color(rate):
        if pd.isna(rate) or max_rate == 0:
            return [100, 100, 100, 100]
        ratio = rate / max_rate
        return [int(255 * ratio), int(80 * (1 - ratio)), 40, 180]

    for f in features:
        f['properties']['fill_color'] = rate_to_color(f['properties']['incident_rate'])

    geojson_layer = pdk.Layer(
        "GeoJsonLayer",
        data=geojson_data,
        get_fill_color="properties.fill_color",
        get_line_color=[255, 255, 255, 100],
        line_width_min_pixels=1,
        pickable=True,
        stroked=True,
        filled=True,
    )

    if selected_basemap == "osm":
        basemap_layer = pdk.Layer(
            "TileLayer",
            data=MAP_STYLE_OPTIONS[selected_basemap]["tile_url"],
            min_zoom=0,
            max_zoom=19,
            tile_size=256,
        )
        layers = [basemap_layer, geojson_layer]
        map_style = None
    else:
        layers = [geojson_layer]
        map_style = MAP_STYLE_OPTIONS[selected_basemap]["pydeck"]

    view_state = pdk.ViewState(
        latitude=BERLIN_LAT, longitude=BERLIN_LON, zoom=9.5, pitch=0,
    )

    st.pydeck_chart(pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style=map_style,
        tooltip={
            "html": "<b>{name}</b><br/>"
                    "Incidents: {total_incidents}<br/>"
                    "Km: {total_km}<br/>"
                    "Rate: {incident_rate}",
            "style": {"backgroundColor": "steelblue", "color": "white"}
        },
    ))

    st.caption(t["rate_caption"])

    st.markdown(f"### {t['table_title']}")
    st.dataframe(
        df_risk[['name', 'total_incidents', 'total_km', 'incident_rate']]
        .sort_values('incident_rate', ascending=False)
        .rename(columns={
            'name': t['col_bezirk'],
            'total_incidents': t['col_incidents'],
            'total_km': t['col_km'],
            'incident_rate': t['col_rate'],
        }),
        width="stretch",
        hide_index=True,
    )
