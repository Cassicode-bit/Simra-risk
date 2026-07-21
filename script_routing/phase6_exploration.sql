-- ============================================================
-- PHASE 6 — EXPLORATION QUERIES
-- ============================================================
-- Run each query separately in pgAdmin and export results
-- (right-click results → Export/Save As → CSV)
-- ============================================================


-- ============================================================
-- QUERY 1 — gps_traces structure and timeStamp sample
-- ============================================================
-- Check the raw values of timeStamp for one month of data.

SELECT ride_id, lat, lon, "timeStamp", year, month
FROM gps_traces
WHERE year = '2021' AND month = '08'
ORDER BY ride_id, "timeStamp"
LIMIT 500;


-- ============================================================
-- QUERY 2 — timeStamp range within a single ride
-- ============================================================
-- Shows min, max and difference of timeStamp for ONE ride_id.
-- This tells us if timeStamp is in milliseconds, seconds, or something else.
-- (replace the ride_id below with one you saw in Query 1 results)

SELECT
    ride_id,
    COUNT(*)                                    AS nb_points,
    MIN("timeStamp")                            AS min_timestamp,
    MAX("timeStamp")                            AS max_timestamp,
    MAX("timeStamp") - MIN("timeStamp")         AS timestamp_range
FROM gps_traces
WHERE year = '2021' AND month = '08'
GROUP BY ride_id
ORDER BY nb_points DESC
LIMIT 10;


-- ============================================================
-- QUERY 3 — incidents structure sample
-- ============================================================

SELECT ride_id, lat, lon, incident, scary, year, month
FROM incidents
WHERE geom IS NOT NULL
  AND incident NOT IN (-5, -2)
LIMIT 500;


-- ============================================================
-- QUERY 4 — bezirk_risk full content
-- ============================================================

SELECT *
FROM bezirk_risk
ORDER BY incident_rate DESC;


-- ============================================================
-- QUERY 5 — bezirke geometry as GeoJSON (sample)
-- ============================================================
-- pydeck's GeoJsonLayer needs actual GeoJSON text, not raw PostGIS geometry.
-- ST_AsGeoJSON converts the geometry to a GeoJSON string.

SELECT name, ST_AsGeoJSON(geom) AS geojson
FROM bezirke
LIMIT 2;


-- ============================================================
-- QUERY 6 — full bezirke GeoJSON (for the choropleth layer)
-- ============================================================
-- This is the query we'll actually use in the Streamlit app
-- to build the GeoJsonLayer, joined with bezirk_risk data.

SELECT
    b.name,
    ST_AsGeoJSON(b.geom)         AS geojson,
    r.total_incidents,
    r.incidents_external,
    r.incidents_inattention,
    r.incidents_other,
    r.incidents_scary,
    r.incidents_not_scary,
    r.total_km,
    r.incident_rate
FROM bezirke b
LEFT JOIN bezirk_risk r ON b.name = r.bezirk_name
ORDER BY b.name;


-- ============================================================
-- QUERY 7 — comparison of straight-line distance vs routed distance
-- ============================================================

SELECT
    s.ride_id,
    ROUND(s.distance_km::numeric, 3)          AS straight_km,
    ROUND(r.routed_km::numeric, 3)            AS routed_km,
    CASE
        WHEN s.distance_km > 0
        THEN ROUND((r.routed_km / s.distance_km)::numeric, 3)
        ELSE NULL
    END                                        AS ratio_routed_to_straight,
    r.n_segments,
    r.n_failed
FROM ride_stats s
LEFT JOIN ride_stats_routed r
    ON s.ride_id = r.ride_id
ORDER BY ratio_routed_to_straight DESC NULLS LAST
LIMIT 50;


-- ============================================================
-- QUERY 8 — top rides with the largest absolute routed distance increase
-- ============================================================

SELECT
    s.ride_id,
    ROUND(s.distance_km::numeric, 3)          AS straight_km,
    ROUND(r.routed_km::numeric, 3)            AS routed_km,
    ROUND((r.routed_km - s.distance_km)::numeric, 3) AS extra_km,
    r.n_failed
FROM ride_stats s
JOIN ride_stats_routed r
    ON s.ride_id = r.ride_id
ORDER BY extra_km DESC
LIMIT 50;


-- ============================================================
-- QUERY 9 — compare total km per Bezirk between straight-line and routed values
-- ============================================================

SELECT
    b.name,
    ROUND(COALESCE(br.total_km, 0)::numeric, 2)         AS total_km_straight,
    ROUND(COALESCE(brr.total_km, 0)::numeric, 2)        AS total_km_routed,
    CASE
        WHEN COALESCE(br.total_km, 0) > 0
        THEN ROUND((COALESCE(brr.total_km, 0) / br.total_km)::numeric, 3)
        ELSE NULL
    END                                                  AS ratio_routed_to_straight
FROM bezirke b
LEFT JOIN bezirk_risk br
    ON b.name = br.bezirk_name
LEFT JOIN bezirk_risk_routed brr
    ON b.name = brr.bezirk_name
ORDER BY ratio_routed_to_straight DESC NULLS LAST;
