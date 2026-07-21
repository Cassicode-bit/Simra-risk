-- ============================================================
-- PHASE 4 — DISTANCE CALCULATION PER RIDE
-- ============================================================
-- Computes the total distance travelled per ride_id
-- using GPS trace points stored in gps_traces.
--
-- Method:
--   1. Reproject geometries from EPSG:4326 to EPSG:25833 (UTM Zone 33N)
--      → gives coordinates in metres, suitable for metric calculations
--   2. Order points by timeStamp to reconstruct the ride path
--   3. Build a LineString from the ordered points (ST_MakeLine)
--   4. Compute its length in metres (ST_Length)
--   5. Convert to kilometres and store in ride_stats
--
-- Result table: ride_stats (ride_id, distance_km, year, month)
-- ============================================================


-- ============================================================
-- STEP 1 — Create ride_stats table
-- ============================================================

DROP TABLE IF EXISTS ride_stats;

CREATE TABLE ride_stats (
    ride_id      TEXT PRIMARY KEY,
    distance_km  DOUBLE PRECISION,
    year         TEXT,
    month        TEXT
);

CREATE INDEX idx_ride_stats_year ON ride_stats(year, month);


-- ============================================================
-- STEP 2 — Compute and insert distances
-- ============================================================
-- ST_Transform(geom, 25833) : reprojects each point from WGS84 to UTM 33N
-- ST_MakeLine(...ORDER BY)  : connects the points in chronological order
--                             to form the ride path as a LineString
-- ST_Length(...)            : computes the length of the LineString in metres
--                             (metric unit since we are in EPSG:25833)
-- / 1000.0                  : converts metres to kilometres
-- ============================================================

INSERT INTO ride_stats (ride_id, distance_km, year, month)
SELECT
    ride_id,
    ST_Length(
        ST_MakeLine(
            ST_Transform(geom, 25833)
            ORDER BY "timeStamp"
        )
    ) / 1000.0  AS distance_km,
    MIN(year)   AS year,
    MIN(month)  AS month
FROM gps_traces
WHERE geom IS NOT NULL
GROUP BY ride_id;


-- ============================================================
-- STEP 3 — Verification
-- ============================================================

-- Total number of rides processed
SELECT COUNT(*) AS total_rides FROM ride_stats;

-- Distribution of distances
SELECT
    MIN(distance_km)                          AS min_km,
    ROUND(AVG(distance_km)::numeric, 2)       AS avg_km,
    ROUND(PERCENTILE_CONT(0.5)
          WITHIN GROUP (ORDER BY distance_km)
          ::numeric, 2)                        AS median_km,
    MAX(distance_km)                          AS max_km
FROM ride_stats
WHERE distance_km > 0;

-- Top 10 longest rides (sanity check)
SELECT ride_id, ROUND(distance_km::numeric, 2) AS distance_km, year, month
FROM ride_stats
ORDER BY distance_km DESC
LIMIT 10;

-- Rides with suspicious distance (> 100 km — likely GPS errors)
SELECT COUNT(*) AS suspicious_rides
FROM ride_stats
WHERE distance_km > 100;

-- Rides with zero or near-zero distance (single GPS point)
SELECT COUNT(*) AS empty_rides
FROM ride_stats
WHERE distance_km < 0.01;
