-- ============================================================
-- PHASE 5 — INCIDENT RATE CALCULATION PER BEZIRK
-- ============================================================
-- Computes the incident rate per Berlin district (Bezirk):
--     incident_rate = incidents in Bezirk / km travelled in Bezirk
--
-- Incident classification (based on official SimRa documentation):
--   Excluded        : incident IN (-5, -2)  — technical/unknown rows
--   External factor : incident IN (1,2,3,4,5,6) — caused by other road users
--   Inattention     : incident = 7          — obstacle dodging
--   Other           : incident = 8
--   Scary           : scary = 1
--   Non scary       : scary = 0
--
-- Spatial logic:
--   - Incidents are assigned to the Bezirk where they occurred (ST_Within)
--   - km are computed per Bezirk by intersecting GPS traces with Bezirk polygons
--
-- Result table: bezirk_risk
-- ============================================================


-- ============================================================
-- STEP 1 — Create result table
-- ============================================================

DROP TABLE IF EXISTS bezirk_risk;

CREATE TABLE bezirk_risk (
    bezirk_name             TEXT PRIMARY KEY,
    total_incidents         INTEGER,   -- all real incidents (incident >= 1)
    incidents_external      INTEGER,   -- incident IN (1,2,3,4,5,6)
    incidents_inattention   INTEGER,   -- incident = 7
    incidents_other         INTEGER,   -- incident = 8
    incidents_scary         INTEGER,   -- scary = 1
    incidents_not_scary     INTEGER,   -- scary = 0
    total_km                DOUBLE PRECISION,
    incident_rate           DOUBLE PRECISION  -- total incidents / total km
);


-- ============================================================
-- STEP 2 — Compute km travelled per Bezirk
-- ============================================================
-- For each GPS point, find its Bezirk via ST_Within.
-- Sum distances per Bezirk using ride_stats.
-- Exclude aberrant rides (< 0.01 km or > 100 km).
-- A ride crossing multiple Bezirke contributes its full distance
-- to each Bezirk proportionally via point count weighting.
-- ============================================================

WITH

-- CTE 1: count GPS points per ride per Bezirk
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

-- CTE 2: total points per ride (to compute proportion per Bezirk)
total_points_per_ride AS (
    SELECT
        ride_id,
        SUM(point_count)                    AS total_points
    FROM points_per_ride_bezirk
    GROUP BY ride_id
),

-- CTE 3: km per Bezirk = distance * proportion of points in that Bezirk
-- Example: ride of 10 km with 60% of points in Mitte → 6 km assigned to Mitte
km_per_bezirk AS (
    SELECT
        p.bezirk_name,
        SUM(
            rs.distance_km
            * (p.point_count::float / t.total_points::float)
        )                                   AS total_km
    FROM points_per_ride_bezirk p
    JOIN total_points_per_ride t
        ON p.ride_id = t.ride_id
    JOIN ride_stats rs
        ON p.ride_id = rs.ride_id
    WHERE rs.distance_km >= 0.01
      AND rs.distance_km <= 100
    GROUP BY p.bezirk_name
),

-- ============================================================
-- STEP 3 — Count incidents per Bezirk by category
-- ============================================================

-- CTE 4: all real incidents per Bezirk
incidents_total AS (
    SELECT
        b.name                              AS bezirk_name,
        COUNT(*)                            AS total_incidents
    FROM incidents i
    JOIN bezirke b
        ON ST_Within(i.geom, b.geom)
    WHERE i.geom IS NOT NULL
      AND i.incident NOT IN (-5, -2)        -- exclude technical rows
    GROUP BY b.name
),

-- CTE 5: external factor incidents (other road users)
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

-- CTE 6: inattention / environment incidents
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

-- CTE 7: other incidents
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

-- CTE 8: scary incidents
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

-- CTE 9: non scary incidents
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

-- ============================================================
-- Final INSERT
-- ============================================================

INSERT INTO bezirk_risk (
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


-- ============================================================
-- STEP 4 — Verification
-- ============================================================

SELECT
    bezirk_name,
    total_incidents,
    incidents_external,
    incidents_inattention,
    incidents_other,
    incidents_scary,
    incidents_not_scary,
    ROUND(total_km::numeric, 1)             AS total_km,
    incident_rate                           AS incidents_per_km
FROM bezirk_risk
ORDER BY incident_rate DESC;
