# Dataset: Starlink Obstruction Measurement Study

Data collected for *"What Obstructed Skies Teach Us About Satellite Internet"* (NINeS 2026).  
Paper: https://drops.dagstuhl.de/storage/01oasics/oasics-vol139-nines2026/OASIcs.NINeS.2026.7/OASIcs.NINeS.2026.7.pdf

---

## Measurement Setup

Two identical Starlink Residential dishes were co-located on a rooftop in Ithaca, NY (42.445°N, 76.480°W), approximately 6 feet apart.

- **pi1** — control dish, always unobstructed
- **pi2** — test dish, obstructed under experimental conditions

Each dish was connected via wired Ethernet to a dedicated Intel N95 mini-PC running Ubuntu 22.04. Measurements ran from **July 2024 through February 2025** at 20 ms packet granularity.

**Obstruction conditions tested:**

| Period | Condition |
|---|---|
| Jul–Oct 2024 | Baseline (no obstruction) |
| Jan 8–18, 2025 | SE obstruction — 30×25 in galvanized steel sheet placed in the SE direction |
| Jan 17–27, 2025 | SE obstruction (second run) |
| Jan 29 – Feb 7, 2025 | Unobstructed baseline |
| Feb 14–18, 2025 | Additional runs |

---

## Tools Used for Collection

| What | Tool |
|---|---|
| RTT and packet loss | [iRTT](https://github.com/heistp/irtt) — sends UDP packets every 20 ms to a remote server and records round-trip time and loss with wall-clock timestamps |
| Obstruction maps | [starlink-grpc-tools](https://github.com/sparky8512/starlink-grpc-tools) — polls the Starlink dish gRPC API every 15 seconds and saves the obstruction map as a PNG |
| Satellite ephemeris | [Celestrak](https://celestrak.org/SOCRATES/) — TLE snapshots downloaded every 6 hours |
| Satellite position propagation | [Skyfield](https://rhodesmill.org/skyfield/) with SGP4 — used offline to compute azimuth/elevation of every visible Starlink satellite at 1-second resolution |
| Satellite identification | Custom DTW-based matching algorithm (see `../code/satellite_matching.py`) |

---

## Folder Structure

```
data/
├── sat_match/               # Which satellite each dish was connected to (primary output)
├── satellite_positions/     # TLE-derived satellite positions at the dish site
├── measurements/
│   ├── pi1/                 # RTT and loss measurements for the control dish
│   └── pi2/                 # RTT and loss measurements for the test dish
└── obstruction_maps/
    ├── pi1/                 # Obstruction map images for the control dish
    └── pi2/                 # Obstruction map images for the test dish
```

---

## File Descriptions

### `sat_match/`

One CSV file per day, named `YYYY_MM_DD_sat_match.csv`.

Each row is one 15-second observation window in which both dishes had a detectable satellite trajectory in their obstruction maps and a matching TLE candidate was found.

**How it is generated:** `../code/run_pipeline.py` loads the obstruction map images for both dishes, extracts the satellite trajectory from each frame using XOR of consecutive images, converts the pixel trajectory to (elevation, azimuth) polar coordinates, then uses FastDTW to match against all TLE-derived satellite trajectories visible at that time. See `../code/process.md` for the full pipeline.

**Schema:**

| Column | Type | Description |
|---|---|---|
| `date` | datetime (US/Eastern) | Start of the 15-second window |
| `pi1_sat` | string | Name of the matched Starlink satellite for the control dish |
| `pi2_sat` | string | Name of the matched Starlink satellite for the test dish |
| `pi1_min_ele` | float (degrees) | Minimum elevation of the satellite trajectory in this window, control dish |
| `pi1_max_ele` | float (degrees) | Maximum elevation |
| `pi1_min_az` | float (degrees) | Minimum azimuth (clockwise from north) |
| `pi1_max_az` | float (degrees) | Maximum azimuth |
| `pi2_min_ele` | float (degrees) | Same for test dish |
| `pi2_max_ele` | float (degrees) | |
| `pi2_min_az` | float (degrees) | |
| `pi2_max_az` | float (degrees) | |
| `pi1_az_ele` | list of (float, float) | Full trajectory as [(azimuth, elevation), ...] for control dish |
| `pi2_az_ele` | list of (float, float) | Full trajectory for test dish |

**Load with:** `read_sat_match_data(start_date, end_date)` in `../code/data_loading.py`

---

### `satellite_positions/`

One CSV file per day, named `azimuth_data_YYYY-MM-DD.csv`.

Contains the azimuth and elevation of every Starlink satellite that was above 25° elevation at the dish location for every second of the day. This is the TLE reference used during satellite matching.

**How it is generated:** `../code/tle_processing.py` reads a Celestrak TLE snapshot for the day, uses Skyfield with SGP4 to propagate each satellite's orbit, finds all rise/set events above 25°, then computes per-second azimuth and elevation for each pass. The raw output is first saved as `processed_tle/dual_YYYY-MM-DD.json` and then flattened to this CSV.

**Schema:**

| Column | Type | Description |
|---|---|---|
| `c_time` | datetime (UTC) | Timestamp at 1-second resolution |
| `sat` | string | Starlink satellite name (e.g. `STARLINK-1234`) |
| `aoe` | float (degrees) | Elevation above horizon |
| `az` | float (degrees) | Azimuth, clockwise from north |
| `az_rad` | float (radians) | Azimuth in radians (`az × π/180`) |

**Load with:** `read_processed_tle_df(start_date, end_date)` in `../code/satellite_matching.py`

---

### `measurements/pi1/` and `measurements/pi2/`

Organized by `{Month}/{DD}/`, matching the collection schedule.

#### `irtt_data_walltime.csv`

One file per dish per day. Contains every successfully received iRTT packet.

**How it is generated:** Raw iRTT output is saved hourly as compressed JSON (`.json.gz`). `../code/irtt_processing.py` decompresses these, parses each packet's round-trip time and wall-clock send timestamp, and writes this flat CSV.

**Schema:**

| Column | Type | Description |
|---|---|---|
| `full_timestamp` | string `YYYY-MM-DD HH:MM:SS:fff` | Wall-clock time the packet was sent, in US/Eastern, millisecond precision |
| `rtt` | float (ms) | Round-trip time in milliseconds |
| `pi` | string | Dish ID (`pi1` or `pi2`) |

**Load with:** `read_rtt_data(start_date, end_date)` in `../code/data_loading.py` — returns a joined DataFrame with columns `date`, `rtt_pi1`, `rtt_pi2`.

#### `loss_data_walltime.csv`

One file per dish per day. Contains every lost packet.

**How it is generated:** Same pipeline as the RTT CSV above. iRTT marks packets as lost when no response is received within the timeout window.

**Schema:**

| Column | Type | Description |
|---|---|---|
| `full_timestamp` | string `YYYY-MM-DD HH:MM:SS:fff` | Wall-clock send time, US/Eastern |
| `loss` | string | Loss reason from iRTT (e.g. `true`) |
| `pi` | string | Dish ID |

**Load with:** `get_loss_data(start_date, end_date)` in `../code/data_loading.py` — returns a DataFrame with columns `date`, `pi1_loss`, `pi2_loss` (packet counts per second).

---

### `obstruction_maps/pi1/` and `obstruction_maps/pi2/`

Raw PNG obstruction map frames from the Starlink gRPC API, one image every 15 seconds per dish.

**How it is generated:** `starlink-grpc-tools` polls the dish API continuously and writes one PNG per poll. No processing has been applied — these are the raw API outputs.

**Image format:**

- Size: 123×123 pixels, RGBA
- Projection: polar — the center pixel is zenith (90° elevation), the edge is the horizon (0°). Each pixel's distance from center encodes elevation; its angle encodes azimuth (clockwise from north = up).
- Bright pixels indicate where the dish's current satellite appears in the sky. The trail accumulates over the 15-second slot.
- Transparent pixels (alpha = 0) represent directions below the horizon or outside the dish's field of view.

**Filename format:** `obs_map_MM-DD-YYYY_HH:MM:SS.png` — timestamp is in US/Eastern.

**How the pipeline uses these:** `get_rst_obsmap_dict` converts transparent pixels to black, then `get_pi_coord_dict` XORs consecutive frames to isolate the moving satellite dot and converts its pixel position to (elevation, azimuth) using:
- elevation = 90 − (pixel_radius × 1.333)
- azimuth = clockwise angle from the top of the image

**Load with:** `get_rst_obsmap_dict(start_date, end_date)` in `../code/satellite_matching.py`

---

## Coordinate System

All azimuth values are **clockwise from north** (0° = north, 90° = east, 180° = south, 270° = west).  
All elevation values are **degrees above the horizon** (0° = horizon, 90° = zenith).

The dish's primary connection region is azimuth 50°–150° (northeast through southeast) based on the measurements in the paper.

---

## Notes

- `pi1` and `pi2` were co-located ~6 feet apart. In ~85% of 15-second windows they connected to the same satellite; in the remaining ~15% they connected to different satellites.
- Timestamps in the obstruction maps and sat_match files use **US/Eastern** local time. Timestamps in satellite_positions use **UTC**.
- The iRTT measurement target was a server outside the Starlink network. RTTs therefore include both the Starlink first-hop and the wider internet path. For first-hop-only latency, traceroute data was also collected but is not included in this release.
- TLE data was sourced from Celestrak's `starlink.txt` group file. A fresh snapshot was downloaded approximately every 6 hours to minimize TLE age error during propagation.
