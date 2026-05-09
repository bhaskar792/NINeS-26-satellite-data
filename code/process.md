# Pipeline Overview

Code for the satellite identification and performance measurement pipeline described in *"What Obstructed Skies Teach Us About Satellite Internet"* (NINeS 2026).

## Files

### `config.py`
Central configuration. Set `STARLINK_DATA_PATH` as an environment variable to point at your data directory, or edit `DATA_PATH` directly. Also holds the dish coordinates and obstruction-map constants.

---

### `tle_processing.py`
**Run once per day before matching.**

Downloads Starlink TLE files from Celestrak (stored under `daily_tles/`) and uses Skyfield to compute, for every second a satellite is above 25° elevation at the dish site, its azimuth and elevation. Outputs:
- `processed_tle/dual_YYYY-MM-DD.json` — time-keyed satellite positions
- `processed_tle_pd/azimuth_data_YYYY-MM-DD.csv` — flat table used by matching

Skips dates already processed. Run with `python tle_processing.py`.

---

### `matching_utils.py`
**Library — not run directly.**

Low-level helpers used by `satellite_matching.py`:
- **Image processing** — `find_longest_contiguous_non_black`, `calculate_radius`, `calculate_clockwise`: extract the satellite trajectory from an obstruction-map frame as a list of (elevation, azimuth) polar pairs.
- **DTW variants** — `calculate_dtw_error`, `max75_normalize`, `max90_normalize`, `cos_normalize`, `sin_normalize`: five ways to convert polar coordinates to Cartesian before computing FastDTW distance. `cos_normalize` performed best in the paper.
- **Matching** — `match_top_k_sat`, `get_single_sat_from_top_k`: find the top-k TLE candidates per dish and pick the joint-best assignment.
- **I/O** — `read_sat_json`, `convert_pickled_dict`: read the JSON files produced by `tle_processing.py`.

---

### `satellite_matching.py`
**Library — not run directly.**

Core pipeline functions called by `run_pipeline.py`:

1. `get_rst_obsmap_dict(start, end)` — loads obstruction-map PNGs, converts RGBA → grayscale, returns `{dish: {datetime: filepath}}`.
2. `get_pi_coord_dict(rst_obsmap_dict)` — for each 15-second frame, XORs consecutive images to isolate the moving satellite dot, then converts pixels to (elevation, azimuth) pairs.
3. `read_processed_tle_df(start, end)` — loads the CSVs from `tle_processing.py` into a DataFrame.
4. `get_sat_pc_dict_multi(az_pd, pi_coord_dict)` — builds a `{datetime: {sat_name: [(aoe, az)]}}` lookup using shared memory and multiprocessing.
5. `match_satellite_multi(all_sat_pc, pi_coord_dict, k)` — runs DTW matching in parallel, returns `(pi_sat_match, pi_sat_error)`.

Also contains `match_trajectories` for evaluating DTW normalization variants.

---

### `irtt_processing.py`
**Run before loading RTT/loss data.**

Processes raw iRTT JSON output files into flat CSVs:
1. `create_directory` — decompresses `.gz` archives into `Month/DD/` subdirectories.
2. `process_irtt_chunk` — parses iRTT JSON for a chunk of dates and one dish, writing `irtt_data_walltime.csv` (RTT) and `loss_data_walltime.csv` (packet loss) per day.
3. `process_irtt(start, end)` — parallelises the above across all dates and both dishes.

Run with `python irtt_processing.py` (dates set in `__main__` block).

---

### `run_pipeline.py`
**Main entry point for satellite matching.**

Loops day-by-day over a date range and runs the full matching pipeline:
`get_rst_obsmap_dict` → `get_pi_coord_dict` → `read_processed_tle_df` → `get_sat_pc_dict_multi` → `match_satellite_multi` → save results.

Outputs per day under `sat_match/`:
- `YYYY_MM_DD_sat_match.csv` — matched satellite per dish per 15-second window
- `YYYY_MM_DD_all_sat_pc.pkl` — full satellite position lookup (used for analysis)

Edit the `abs_start_date` / `abs_end_date` in the `__main__` block and run with `python run_pipeline.py`.

---

### `data_loading.py`
**Library for notebooks and analysis scripts.**

Loads all processed outputs into pandas DataFrames:
- `read_sat_match_data(start, end)` — satellite match CSVs → DataFrame with `pi1_sat`, `pi2_sat`, first azimuth/elevation per window.
- `read_all_sat_pc(start, end)` — satellite position pickles.
- `read_rtt_data(start, end)` — iRTT CSVs → joined `rtt_pi1`, `rtt_pi2` DataFrame.
- `get_loss_data(start, end)` — loss CSVs → `pi1_loss`, `pi2_loss` counts per second.
- `get_traceroute_fh_latency(start, end)` — traceroute JSON → first-hop RTT DataFrame.
- `parse_irtt_loss_data(start, end)` — runs `process_irtt` to generate CSVs if not already done.
- Visualization helpers: `get_image`, `get_image_small`, `show_obs_image`, `remove_longest_block` — used in notebooks to inspect obstruction-map frames.

---

## Typical Order of Operations

```
1. Collect TLE files into  data/starlink/daily_tles/
2. python tle_processing.py          # propagate satellite positions
3. python irtt_processing.py         # convert iRTT JSON → CSV
4. python run_pipeline.py            # match satellites per 15-second window
5. Open notebooks                    # load results via data_loading.py
```

---

## Data File Map

All paths are relative to `DATA_PATH` (set via `STARLINK_DATA_PATH` or `config.py`).

### Raw inputs — collected externally, never written by this code

```
daily_tles/
    TLE_YYYY-MM-DD*.txt              Starlink TLE snapshots from Celestrak (~6-hourly)

obs_data/perf_starlink/{pi}/
    obs_maps_rst/*.png               Obstruction-map frames from Starlink gRPC API (every 15 s)
    irtt_hourly/*.json.gz            Compressed hourly iRTT output files (20 ms packet interval)
    traceroute/%Y/%m/%d/%H/
        traceroute_%m-%d-%Y_%H:%M:%S.json   Traceroute snapshots (every 15 s)
```

`{pi}` is `pi1` (control dish) or `pi2` (test/obstructed dish).

---

### `tle_processing.py`

| Reads | Writes |
|---|---|
| `daily_tles/TLE_*.txt` | `processed_tle/dual_YYYY-MM-DD.json` |
| | `processed_tle_pd/azimuth_data_YYYY-MM-DD.csv` |

`processed_tle/dual_YYYY-MM-DD.json`
: Time-keyed dict `{ "YYYY-MM-DD HH:MM:SS": "[(sat_name, elevation, azimuth, distance_km), ...]" }` covering all satellites above 25° at the dish site for that day ±1 hour.

`processed_tle_pd/azimuth_data_YYYY-MM-DD.csv`
: Flat table with columns `c_time, sat, aoe, az, az_rad`. One row per (second, satellite) pair. This is the file read by `run_pipeline.py`.

---

### `irtt_processing.py`

| Reads | Writes |
|---|---|
| `obs_data/perf_starlink/{pi}/irtt_hourly/*.json.gz` | `obs_data/perf_starlink/{pi}/irtt_hourly/{Month}/{DD}/irtt_data_walltime.csv` |
| (decompresses to `{Month}/{DD}/*.json` first) | `obs_data/perf_starlink/{pi}/irtt_hourly/{Month}/{DD}/loss_data_walltime.csv` |

`irtt_data_walltime.csv`
: Columns `full_timestamp, rtt, pi`. One row per received packet (RTT in ms, wall-clock timestamp in US/Eastern).

`loss_data_walltime.csv`
: Columns `full_timestamp, loss, pi`. One row per lost packet.

---

### `run_pipeline.py` (via `satellite_matching.py`)

| Reads | Writes |
|---|---|
| `obs_data/perf_starlink/{pi}/obs_maps_rst/*.png` | `obs_data/perf_starlink/{pi}/obs_maps_rst/converted/*.png` (cache) |
| `processed_tle_pd/azimuth_data_YYYY-MM-DD.csv` | `sat_match/YYYY_MM_DD_sat_match.csv` |
| | `sat_match/YYYY_MM_DD_all_sat_pc.pkl` |

`sat_match/YYYY_MM_DD_sat_match.csv`
: One row per matched 15-second window. Columns: `date, pi1_sat, pi2_sat, pi1_min_ele, pi1_max_ele, pi1_min_az, pi1_max_az, pi2_min_ele, pi2_max_ele, pi2_min_az, pi2_max_az, pi1_az_ele, pi2_az_ele`.

`sat_match/YYYY_MM_DD_all_sat_pc.pkl`
: Pickle of `{ datetime: { sat_name: [(aoe, az), ...] } }` — all candidate satellite positions for every matched window. Used by `read_all_sat_pc` in notebooks.

---

### `data_loading.py` — what each function reads

| Function | Reads |
|---|---|
| `read_sat_match_data` | `sat_match/YYYY_MM_DD_sat_match.csv` |
| `read_all_sat_pc` | `sat_match/YYYY_MM_DD_all_sat_pc.pkl` |
| `read_rtt_data` | `obs_data/.../irtt_hourly/{Month}/{DD}/irtt_data_walltime.csv` |
| `get_loss_data` | `obs_data/.../irtt_hourly/{Month}/{DD}/loss_data_walltime.csv` |
| `get_traceroute_fh_latency` | `obs_data/.../traceroute/%Y/%m/%d/%H/traceroute_*.json` |
| `get_image` / `show_obs_image` | `obs_data/.../obs_maps_rst/converted/*.png` |

---

---

## Dataset contents

**`sat_match/*_sat_match.csv`**
One file per day. Each row is one 15-second observation window.

| Column | Description |
|---|---|
| `date` | Window start timestamp (US/Eastern) |
| `pi1_sat` / `pi2_sat` | Matched Starlink satellite name for each dish |
| `pi1_min_ele` / `pi1_max_ele` | Elevation range (degrees) of the satellite trajectory in this window |
| `pi1_min_az` / `pi1_max_az` | Azimuth range (degrees) |
| `pi1_az_ele` / `pi2_az_ele` | Full list of (elevation, azimuth) pairs along the trajectory |

**`processed_tle_pd/azimuth_data_*.csv`**
One file per day. Each row is one satellite at one second.

| Column | Description |
|---|---|
| `c_time` | UTC timestamp |
| `sat` | Satellite name |
| `aoe` | Elevation (degrees above horizon) |
| `az` | Azimuth (degrees, clockwise from north) |
| `az_rad` | Azimuth in radians |

**`irtt_data_walltime.csv`** (one per dish per day)

| Column | Description |
|---|---|
| `full_timestamp` | Wall-clock send time (US/Eastern, ms precision) |
| `rtt` | Round-trip time in milliseconds |
| `pi` | Dish ID (`pi1` = control, `pi2` = test/obstructed) |

**`loss_data_walltime.csv`** (one per dish per day)

| Column | Description |
|---|---|
| `full_timestamp` | Wall-clock send time (US/Eastern, ms precision) |
| `loss` | Loss reason string from iRTT |
| `pi` | Dish ID |

**`obs_maps_rst/*.png`**
123×123 pixel grayscale images. Each pixel represents a direction in the sky using a polar projection — center is zenith, edge is the horizon. Bright pixels indicate the current satellite's position. Filename encodes the timestamp.

---

### Full dependency graph

```
daily_tles/*.txt
    └── tle_processing.py
            ├── processed_tle/dual_*.json
            └── processed_tle_pd/azimuth_data_*.csv
                                        │
obs_maps_rst/*.png ─────────────────────┤
    └── run_pipeline.py ────────────────┘
            ├── sat_match/*_sat_match.csv ──────┐
            └── sat_match/*_all_sat_pc.pkl ─────┤
                                                │
irtt_hourly/*.json.gz                           │
    └── irtt_processing.py                      │
            ├── irtt_data_walltime.csv ──────────┤
            └── loss_data_walltime.csv ──────────┤
                                                │
traceroute/*.json ──────────────────────────────┤
                                                ▼
                                        data_loading.py
                                        (notebooks)
```