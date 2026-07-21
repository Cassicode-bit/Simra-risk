-- ============================================================
-- PHASE 5B — INCIDENT RATE CALCULATION FOR ROUTED DISTANCE
-- ============================================================
-- Computes Bezirk-level km totals and incident rates using the
-- routed distance values stored in ride_stats_routed.
-- This leaves the original `bezirk_risk` logic intact and adds
-- a second result table for comparison with straight-line km.
-- ============================================================

DROP TABLE IF EXISTS bezirk_risk_routed;

CREATE TABLE bezirk_risk_routed (
    bezirk_name             TEXT PRIMARY KEY,
    total_incidents         INTEGER,
    incidents_external      INTEGER,
    incidents_inattention   INTEGER,
    incidents_other         INTEGER,
    incidents_scary         INTEGER,
    incidents_not_scary     INTEGER,
    total_km                DOUBLE PRECISION,
    incident_rate           DOUBLE PRECISION
);

WITH
points_per_ride_bezirk AS (
    SELECT
        g.ride_id,
        b.name                              AS bezirk_name,
        COUNT(*)                            AS point_count
    FROM gps_traces g
    JOIN bezirke b
        ON ST_Within(g.geom, b.geom)
    WHERE g.geom IS NOT NULL
    GROUP BY g.ride_id, b.name
),

total_points_per_ride AS (
    SELECT
        ride_id,
        SUM(point_count)                    AS total_points
    FROM points_per_ride_bezirk
    GROUP BY ride_id
),

km_per_bezirk AS (
    SELECT
        p.bezirk_name,
        SUM(
            r.routed_km
            * (p.point_count::float / t.total_points::float)
        )                                   AS total_km
    FROM points_per_ride_bezirk p
    JOIN total_points_per_ride t
        ON p.ride_id = t.ride_id
    JOIN ride_stats_routed r
        ON p.ride_id = r.ride_id
    WHERE r.routed_km >= 0.01
      AND r.routed_km <= 100
    GROUP BY p.bezirk_name
),

incidents_total AS (
    SELECT
        b.name                              AS bezirk_name,
        COUNT(*)                            AS total_incidents
    FROM incidents i
    JOIN bezirke b
        ON ST_Within(i.geom, b.geom)
    WHERE i.geom IS NOT NULL
      AND i.incident NOT IN (-5, -2)
    GROUP BY b.name
),

incidents_external AS (
    SELECT
        b.name                              AS bezirk_name,
        COUNT(*)                            AS nb
    FROM incidents i
    JOIN bezirke b
        ON ST_Within(i.geom, b.geom)
    WHERE i.geom IS NOT NULL
      AND i.incident IN (1, 2, 3, 4, 5, 6)
    GROUP BY b.name
),

incidents_inattention AS (
    SELECT
        b.name                              AS bezirk_name,
        COUNT(*)                            AS nb
    FROM incidents i
    JOIN bezirke b
        ON ST_Within(i.geom, b.geom)
    WHERE i.geom IS NOT NULL
      AND i.incident = 7
    GROUP BY b.name
),

incidents_other AS (
    SELECT
        b.name                              AS bezirk_name,
        COUNT(*)                            AS nb
    FROM incidents i
    JOIN bezirke b
        ON ST_Within(i.geom, b.geom)
    WHERE i.geom IS NOT NULL
      AND i.incident = 8
    GROUP BY b.name
),

incidents_scary AS (
    SELECT
        b.name                              AS bezirk_name,
        COUNT(*)                            AS nb
    FROM incidents i
    JOIN bezirke b
        ON ST_Within(i.geom, b.geom)
    WHERE i.geom IS NOT NULL
      AND i.incident NOT IN (-5, -2)
      AND i.scary = 1
    GROUP BY b.name
),

incidents_not_scary AS (
    SELECT
        b.name                              AS bezirk_name,
        COUNT(*)                            AS nb
    FROM incidents i
    JOIN bezirke b
        ON ST_Within(i.geom, b.geom)
    WHERE i.geom IS NOT NULL
      AND i.incident NOT IN (-5, -2)
      AND i.scary = 0
    GROUP BY b.name
)

INSERT INTO bezirk_risk_routed (
    bezirk_name,
    total_incidents,
    incidents_external,
    incidents_inattention,
    incidents_other,
    incidents_scary,
    incidents_not_scary,
    total_km,
    incident_rate
)
SELECT
    k.bezirk_name,
    COALESCE(it.total_incidents,    0)      AS total_incidents,
    COALESCE(ie.nb,                 0)      AS incidents_external,
    COALESCE(ii.nb,                 0)      AS incidents_inattention,
    COALESCE(io.nb,                 0)      AS incidents_other,
    COALESCE(isc.nb,                0)      AS incidents_scary,
    COALESCE(ins.nb,                0)      AS incidents_not_scary,
    ROUND(k.total_km::numeric,      2)      AS total_km,
    CASE
        WHEN k.total_km > 0
        THEN ROUND(
            (COALESCE(it.total_incidents, 0)
             / k.total_km)::numeric, 4)
        ELSE 0
    END                                     AS incident_rate
FROM km_per_bezirk k
LEFT JOIN incidents_total       it  ON k.bezirk_name = it.bezirk_name
LEFT JOIN incidents_external    ie  ON k.bezirk_name = ie.bezirk_name
LEFT JOIN incidents_inattention ii  ON k.bezirk_name = ii.bezirk_name
LEFT JOIN incidents_other       io  ON k.bezirk_name = io.bezirk_name
LEFT JOIN incidents_scary       isc ON k.bezirk_name = isc.bezirk_name
LEFT JOIN incidents_not_scary   ins ON k.bezirk_name = ins.bezirk_name
ORDER BY incident_rate DESC;
