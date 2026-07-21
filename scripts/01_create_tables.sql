-- ============================================================
-- SIMRA BERLIN -- TABELLENSTRUKTUR
-- Voraussetzung: PostGIS muss aktiviert sein
-- Ausfuehren: In VSCode mit SQLTools, oder:
--   psql -U ihr_admin -d simra_berlin -f 01_create_tables.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- TABELLE 1: GPS_TRACES
-- Quelle: *_rides.csv
-- Eine Zeile pro GPS-Messpunkt
-- ============================================================

DROP TABLE IF EXISTS gps_traces CASCADE;

CREATE TABLE gps_traces (
    id              SERIAL          PRIMARY KEY,
    ride_id         TEXT            NOT NULL,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    "timeStamp"     BIGINT,
    acc             DOUBLE PRECISION,
    is_interpolated BOOLEAN         DEFAULT FALSE,
    year            TEXT            NOT NULL,
    month           TEXT            NOT NULL,
    source_file     TEXT,
    geom            GEOMETRY(Point, 4326)
);

CREATE UNIQUE INDEX uq_gps_traces ON gps_traces(ride_id, "timeStamp", source_file);

CREATE INDEX idx_gps_geom    ON gps_traces USING GIST(geom);
CREATE INDEX idx_gps_ride    ON gps_traces(ride_id);
CREATE INDEX idx_gps_year    ON gps_traces(year, month);

-- ============================================================
-- TABELLE 2: INCIDENTS
-- Quelle: *_incidents.csv
-- Eine Zeile pro gemeldeten Vorfall
-- Zeilen ohne Koordinaten werden mit geom=NULL importiert
-- ============================================================

DROP TABLE IF EXISTS incidents CASCADE;

CREATE TABLE incidents (
    id          SERIAL          PRIMARY KEY,
    ride_id     TEXT            NOT NULL,
    lat         DOUBLE PRECISION,
    lon         DOUBLE PRECISION,
    ts          BIGINT,
    bike        INTEGER,
    incident    INTEGER,
    scary       INTEGER,
    year        TEXT            NOT NULL,
    month       TEXT            NOT NULL,
    source_file TEXT,
    geom        GEOMETRY(Point, 4326)
);

CREATE UNIQUE INDEX uq_incidents ON incidents(ride_id, ts, incident, source_file);

CREATE INDEX idx_inc_geom    ON incidents USING GIST(geom);
CREATE INDEX idx_inc_ride    ON incidents(ride_id);
CREATE INDEX idx_inc_year    ON incidents(year, month);
CREATE INDEX idx_inc_type    ON incidents(incident);

-- ============================================================
-- PRUEFABFRAGE: Tabellen bestaetigen
-- ============================================================

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('gps_traces', 'incidents')
ORDER BY table_name;

