"""
Full-scale routed-distance computation for all rides (SimRa Risk Berlin).

Why this is a standalone script and not a notebook cell:
On Windows, multiprocessing uses "spawn" -- each worker process must be
able to *import* the worker function from a real module. Functions
defined inline in Jupyter cells can't be pickled/imported that way, so
true multi-core parallelism has to live in a .py file run from a
terminal (`python run_routing_full.py`), not inside the notebook.

This script is also robust to partial progress and re-runs:
- It writes results incrementally in batches.
- It skips rides already present in the results table.
- It uses a single shared PostgreSQL session for temp tables.
- It handles rides with missing Bezirk/node matches by recording a zero-distance result.

Usage:
    python run_routing_full.py [--workers N] [--batch-size N] [--chunk-size N] [--interval N]
"""

import argparse
import gc
import logging
import os
import pickle
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import igraph as ig
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

BEZIRKE_DIR = Path(os.getenv(
    "BEZIRKE_DIR",
    r"C:\Users\PC\Documents\Projekt_Geodaten_haltung_Vernetzung\data\routing\bezirke"
))
TARGET_INTERVAL_SEC = int(os.getenv("TARGET_INTERVAL_SEC", 30))
MAX_CACHED_GRAPHS = int(os.getenv("MAX_CACHED_GRAPHS", 2))
DEFAULT_N_WORKERS = max(1, (os.cpu_count() or 2) - 1)
DEFAULT_RIDES_PER_BATCH = int(os.getenv("RIDES_PER_BATCH", 200))
DEFAULT_RIDES_PER_CHUNK = int(os.getenv("RIDES_PER_CHUNK", 1000))

DB_CONFIG = dict(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "simra_inspired"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", ""),
)

# --------------------------------------------------------------------------
# PER-PROCESS CACHES
# --------------------------------------------------------------------------
_graph_cache: Dict[str, nx.MultiDiGraph] = {}
_component_cache: Dict[int, Dict] = {}
_igraph_cache: Dict[int, Tuple[ig.Graph, Dict]] = {}


def _drop_graph(name: str) -> None:
    """Remove a graph from cache and free its memory."""
    G = _graph_cache.pop(name, None)
    if G is not None:
        _component_cache.pop(id(G), None)
        _igraph_cache.pop(id(G), None)
        del G
        gc.collect()


def _evict_if_needed() -> None:
    """Keep the cache inside the configured graph limit."""
    while len(_graph_cache) > MAX_CACHED_GRAPHS:
        oldest_name = next(iter(_graph_cache))
        _drop_graph(oldest_name)


def load_bezirk_graph(name: str) -> nx.MultiDiGraph:
    """Load a Bezirk graph from pickle with in-process caching."""
    if name in _graph_cache:
        G = _graph_cache.pop(name)
        _graph_cache[name] = G
        return G

    path = BEZIRKE_DIR / f"{name}.pkl"
    if not path.exists():
        raise FileNotFoundError(f"Bezirk graph not found: {path}")

    try:
        with open(path, "rb") as f:
            G = pickle.load(f)
    except MemoryError:
        _graph_cache.clear()
        _component_cache.clear()
        _igraph_cache.clear()
        gc.collect()
        with open(path, "rb") as f:
            G = pickle.load(f)

    _graph_cache[name] = G
    _evict_if_needed()
    return G


def get_component_map(G: nx.MultiDiGraph) -> Dict:
    """Map nodes to their weakly connected component ID."""
    key = id(G)
    if key not in _component_cache:
        comp_map = {}
        for island_id, component in enumerate(nx.weakly_connected_components(G)):
            for node in component:
                comp_map[node] = island_id
        _component_cache[key] = comp_map
    return _component_cache[key]


def get_igraph_for(G: nx.MultiDiGraph) -> Tuple[ig.Graph, Dict]:
    """Convert a NetworkX graph to igraph for faster path calculations."""
    key = id(G)
    if key not in _igraph_cache:
        node_list = list(G.nodes())
        node_to_idx = {n: i for i, n in enumerate(node_list)}
        edges, weights = [], []
        for u, v, data in G.edges(data=True):
            edges.append((node_to_idx[u], node_to_idx[v]))
            weights.append(float(data.get("length", 1.0)))

        Gi = ig.Graph(n=len(node_list), edges=edges, directed=True)
        Gi.es["length"] = weights
        _igraph_cache[key] = (Gi, node_to_idx)
    return _igraph_cache[key]


def routed_distance_for_ride(nodes: List[Optional[int]], bezirk_name: str) -> Tuple[float, int, int]:
    """Route a ride by nearest graph nodes and report total routed distance."""
    if len(nodes) < 2:
        return 0.0, 0, 0

    valid_nodes = [n for n in nodes if n is not None]
    if len(valid_nodes) < 2:
        return 0.0, 0, 0

    G = load_bezirk_graph(bezirk_name)
    comp_map = get_component_map(G)
    Gi, node_to_idx = get_igraph_for(G)

    pair_u, pair_v = [], []
    n_failed = 0
    for u, v in zip(valid_nodes, valid_nodes[1:]):
        if u == v:
            continue
        if comp_map.get(u) != comp_map.get(v):
            n_failed += 1
            continue
        pair_u.append(u)
        pair_v.append(v)

    if not pair_u:
        return 0.0, 0, n_failed

    src_idx_all = [node_to_idx[u] for u in pair_u]
    tgt_idx_all = [node_to_idx[v] for v in pair_v]

    unique_src = sorted(set(src_idx_all))
    unique_tgt = sorted(set(tgt_idx_all))
    src_pos = {v: i for i, v in enumerate(unique_src)}
    tgt_pos = {v: i for i, v in enumerate(unique_tgt)}

    dist_matrix = np.array(
        Gi.shortest_paths_dijkstra(source=unique_src, target=unique_tgt, weights="length")
    )

    total = 0.0
    n_segments = 0
    for s_idx, t_idx in zip(src_idx_all, tgt_idx_all):
        d = dist_matrix[src_pos[s_idx], tgt_pos[t_idx]]
        if np.isinf(d):
            n_failed += 1
        else:
            total += d
            n_segments += 1

    return total / 1000.0, n_segments, n_failed


def process_ride_batch(batch: List[Tuple[str, str, List[Optional[int]]]]) -> List[Tuple[str, float, int, int]]:
    """Worker function that routes a batch of rides."""
    out = []
    for ride_id, bezirk_name, nodes in batch:
        dist_km, n_seg, n_fail = routed_distance_for_ride(nodes, bezirk_name)
        out.append((str(ride_id), float(dist_km), int(n_seg), int(n_fail)))
    return out


def ensure_result_table(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ride_stats_routed (
                ride_id TEXT PRIMARY KEY,
                routed_km DOUBLE PRECISION,
                n_segments INTEGER,
                n_failed INTEGER
            );
            """
        )
    conn.commit()


def fetch_pending_rides(conn: psycopg2.extensions.connection) -> List[str]:
    sql = """
        SELECT DISTINCT g.ride_id
        FROM gps_traces g
        LEFT JOIN ride_stats_routed r ON g.ride_id = r.ride_id
        WHERE r.ride_id IS NULL
        ORDER BY g.ride_id
    """
    df = pd.read_sql(sql, conn)
    return df["ride_id"].astype(str).tolist()


def downsample_points(points_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ride_id, group in points_df.groupby("ride_id"):
        group = group.sort_values("timeStamp")
        if group.empty:
            continue

        kept = [group.iloc[0]]
        last_ts = group.iloc[0]["timeStamp"]
        for _, row in group.iloc[1:].iterrows():
            dt = (row["timeStamp"] - last_ts) / 1000.0
            if dt >= TARGET_INTERVAL_SEC:
                kept.append(row)
                last_ts = row["timeStamp"]

        if kept[-1]["timeStamp"] != group.iloc[-1]["timeStamp"]:
            kept.append(group.iloc[-1])

        rows.extend(kept)

    return pd.DataFrame(rows).reset_index(drop=True)


def assign_bezirke(conn: psycopg2.extensions.connection, downsampled: pd.DataFrame) -> pd.DataFrame:
    """Attach the Bezirk name to each GPS point using a temp table."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS temp_full_points;")
        cur.execute(
            """
            CREATE TEMP TABLE temp_full_points (
                row_id INTEGER,
                ride_id TEXT,
                lat DOUBLE PRECISION,
                lon DOUBLE PRECISION
            );
            """
        )
        args = [
            (int(i), str(row.ride_id), float(row.lat), float(row.lon))
            for i, row in downsampled.iterrows()
        ]
        execute_values(
            cur,
            "INSERT INTO temp_full_points (row_id, ride_id, lat, lon) VALUES %s",
            args,
        )
    conn.commit()

    bezirk_match = pd.read_sql(
        """
        SELECT p.row_id, b.name AS bezirk_name
        FROM temp_full_points p
        JOIN bezirke b ON ST_Intersects(
            ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326),
            b.geom
        )
        """,
        conn,
    )

    downsampled = downsampled.reset_index().rename(columns={"index": "row_id"})
    downsampled = downsampled.merge(bezirk_match, on="row_id", how="left")
    return downsampled


def build_ride_jobs(downsampled: pd.DataFrame) -> Tuple[List[Tuple[str, str, List[Optional[int]]]], List[str], List[Tuple[str, str]]]:
    ride_jobs: List[Tuple[str, str, List[Optional[int]]]] = []
    invalid_rides: List[str] = []
    invalid_reasons: List[Tuple[str, str]] = []

    for ride_id, group in downsampled.groupby("ride_id"):
        valid = group.dropna(subset=["bezirk_name"])
        if valid.empty:
            reason = "no_bezirk"
            invalid_rides.append(str(ride_id))
            invalid_reasons.append((str(ride_id), reason))
            continue

        if len(valid) < 2:
            reason = "too_few_points"
            invalid_rides.append(str(ride_id))
            invalid_reasons.append((str(ride_id), reason))
            continue

        dominant_bezirk = valid["bezirk_name"].mode().iloc[0]
        nodes = valid.loc[valid["bezirk_name"] == dominant_bezirk, "node"].tolist()
        nodes = [None if pd.isna(n) else int(n) for n in nodes]
        if len(nodes) < 2:
            reason = "too_few_nodes_after_snap"
            invalid_rides.append(str(ride_id))
            invalid_reasons.append((str(ride_id), reason))
            continue

        if all(n is None for n in nodes):
            reason = "snap_failed"
            invalid_rides.append(str(ride_id))
            invalid_reasons.append((str(ride_id), reason))
            continue

        ride_jobs.append((str(ride_id), dominant_bezirk, nodes))

    return ride_jobs, invalid_rides, invalid_reasons


def insert_results(conn: psycopg2.extensions.connection, rows: List[Tuple[str, float, int, int]]) -> None:
    if not rows:
        return
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO ride_stats_routed (ride_id, routed_km, n_segments, n_failed)
            VALUES %s
            ON CONFLICT (ride_id) DO UPDATE SET
                routed_km = EXCLUDED.routed_km,
                n_segments = EXCLUDED.n_segments,
                n_failed = EXCLUDED.n_failed
            """,
            rows,
        )
    conn.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route full SimRa rides and save results to PostgreSQL")
    parser.add_argument("--workers", type=int, default=DEFAULT_N_WORKERS, help="Number of parallel worker processes")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_RIDES_PER_BATCH, help="Number of rides to route per worker batch")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_RIDES_PER_CHUNK, help="Number of rides to fetch in each SQL chunk")
    parser.add_argument("--interval", type=int, default=TARGET_INTERVAL_SEC, help="GPS downsample interval in seconds")
    parser.add_argument("--bezirk-dir", type=Path, default=BEZIRKE_DIR, help="Directory containing Bezirk graph pickle files")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s",
        level=level,
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    args = parse_args()
    configure_logging(args.verbose)

    global TARGET_INTERVAL_SEC, BEZIRKE_DIR
    TARGET_INTERVAL_SEC = args.interval
    BEZIRKE_DIR = args.bezirk_dir

    logging.info("SIMRA ROUTING - FULL SCALE")
    logging.info("Workers: %d", args.workers)
    logging.info("Rides per batch: %d", args.batch_size)
    logging.info("Rides per chunk: %d", args.chunk_size)
    logging.info("Target interval: %ds", TARGET_INTERVAL_SEC)
    logging.info("Bezirk dir: %s", BEZIRKE_DIR)

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        ensure_result_table(conn)
        todo_rides = fetch_pending_rides(conn)
        logging.info("Rides remaining to process: %d", len(todo_rides))

        if not todo_rides:
            logging.info("All rides have already been routed. Nothing to do.")
            return

        ride_chunks = [todo_rides[i : i + args.chunk_size] for i in range(0, len(todo_rides), args.chunk_size)]
        logging.info("Processing %d rides in %d chunks", len(todo_rides), len(ride_chunks))

        t0 = time.time()
        total_done = 0

        for chunk_num, ride_chunk in enumerate(ride_chunks, start=1):
            chunk_t0 = time.time()
            logging.info("Starting chunk %d/%d (%d rides)", chunk_num, len(ride_chunks), len(ride_chunk))

            points_df = pd.read_sql(
                """
                SELECT ride_id, lat, lon, \"timeStamp\"
                FROM gps_traces
                WHERE ride_id IN %(ride_ids)s
                ORDER BY ride_id, \"timeStamp\"
                """,
                conn,
                params={"ride_ids": tuple(ride_chunk)},
            )
            original_count = len(points_df)

            downsampled = downsample_points(points_df)
            del points_df
            logging.info("  Points after downsampling: %s (was %s)", f"{len(downsampled):,}", f"{original_count:,}")

            if downsampled.empty:
                logging.warning("  No points in chunk %d after downsampling", chunk_num)
                continue

            downsampled = assign_bezirke(conn, downsampled)
            downsampled["node"] = None
            for bezirk_name, group in downsampled.dropna(subset=["bezirk_name"]).groupby("bezirk_name"):
                G = load_bezirk_graph(bezirk_name)
                try:
                    nodes = ox.distance.nearest_nodes(G, X=group["lon"].values, Y=group["lat"].values)
                except Exception as exc:
                    logging.exception("Nearest-node snapping failed for Bezirk %s", bezirk_name)
                    nodes = [None] * len(group)
                downsampled.loc[group.index, "node"] = nodes
                _drop_graph(bezirk_name)

            ride_jobs, invalid_rides, invalid_reasons = build_ride_jobs(downsampled)
            del downsampled

            results: List[Tuple[str, float, int, int]] = []
            results.extend([(rid, 0.0, 0, 0) for rid in invalid_rides])

            if invalid_reasons:
                reason_counts = Counter(reason for _, reason in invalid_reasons)
                logging.info("  Invalid rides summary: %s", dict(sorted(reason_counts.items())))
                logging.info("  Invalid rides: %d / %d", len(invalid_rides), len(invalid_rides) + len(ride_jobs))

            ride_jobs.sort(key=lambda x: x[1])
            batches = [ride_jobs[i : i + args.batch_size] for i in range(0, len(ride_jobs), args.batch_size)]
            logging.info("  %d rides grouped into %d batches", len(ride_jobs), len(batches))

            with ProcessPoolExecutor(max_workers=args.workers) as executor:
                futures = {executor.submit(process_ride_batch, batch): batch for batch in batches}
                for fut in as_completed(futures):
                    batch_results = fut.result()
                    results.extend(batch_results)
                    total_done += len(batch_results)

                    elapsed = time.time() - t0
                    rate = total_done / elapsed if elapsed > 0 else 0.0
                    remaining = len(todo_rides) - total_done
                    eta_h = remaining / rate / 3600.0 if rate > 0 else float("inf")
                    logging.info(
                        "  Progress: %d/%d rides routed (%.2fh elapsed, ETA %.1fh, %.2f rides/s)",
                        total_done,
                        len(todo_rides),
                        elapsed / 3600.0,
                        eta_h,
                        rate,
                    )

            insert_results(conn, results)
            logging.info("  Chunk %d completed in %.1f minutes", chunk_num, (time.time() - chunk_t0) / 60.0)

        total_time = (time.time() - t0) / 3600.0
        logging.info("Routing completed successfully")
        logging.info("Total rides processed: %d", total_done)
        logging.info("Total time: %.2f hours", total_time)
        if total_time > 0:
            logging.info("Average speed: %.2f rides/second", total_done / (total_time * 3600.0))

    finally:
        conn.close()


if __name__ == "__main__":
    main()
