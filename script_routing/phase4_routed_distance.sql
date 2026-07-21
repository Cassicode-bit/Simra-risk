-- ============================================================
-- PHASE 4B — ROUTED DISTANCE RESULT TABLE
-- ============================================================
-- Defines the table that stores routed distances computed by the
-- Python routing pipeline (`scripts/run_routing_full.py`).
-- This phase does not compute the routed distances itself; it
-- creates the storage schema so that the routing script can insert
-- results without modifying the existing straight-line tables.
-- ============================================================

CREATE TABLE IF NOT EXISTS ride_stats_routed (
    ride_id     TEXT PRIMARY KEY,
    routed_km   DOUBLE PRECISION,
    n_segments  INTEGER,
    n_failed    INTEGER
);
