# Starlink Obstruction Analysis — Code

Analysis notebooks and processing pipeline for *"What Obstructed Skies Teach Us about Satellite Internet"* (NINeS 2026).

Two co-located Starlink dishes were measured over several weeks:
- **pi1** — control dish, unobstructed sky
- **pi2** — test dish, SE direction blocked by a steel sheet

---

## Notebooks

### `analysis.ipynb` — Full Analysis

The primary analysis notebook. Covers all measurements and produces every plot and table in the paper.

**Sections:**

| Section | What it shows |
|---|---|
| Daily diff-sat percentage | Day-by-day fraction of 15-second windows where the two dishes connected to different satellites. Covers the full obstructed period. |
| OBS map pixel analysis | For each connection window, classifies pixels on the Starlink obstruction map as on-trajectory, near-trajectory, or isolated. Tables compare all windows vs only diff-sat windows, at several proximity thresholds, strict and relaxed. |
| Hourly RTT and loss | 24-hour RTT traces with P5–P95 shading and hourly loss bars, for both the obstructed (Jan 17–27) and unobstructed (Jan 29 – Feb 7) periods. |
| Second-granularity RTT + loss spike | Zooms into a single responsive-routing handover event at 1-second resolution, showing RTT, packet loss, and handover timestamps for both dishes simultaneously. |
| CDF of RTT difference | Distribution of (control − test) RTT for 15-second same-satellite vs different-satellite windows. Shows the latency penalty paid when the dishes are forced onto different satellites. |
| DTW normalization comparison | CDF of DTW distance for five polar-coordinate normalization schemes (default, max75, max90, cos, sin). Used to select the best matching method. |
| Azimuth vs elevation — unobstructed | Scatter of the test dish's satellite contact points during the unobstructed period, showing where in the sky it connects when unconstrained. |
| CDF of azimuth | Compares the azimuth distribution of the first satellite contact for both dishes across obstructed (Jan 8–18) and unobstructed (Jan 28 – Feb 6) periods, with obstruction boundary lines at 93.4° and 146.6°. |

**Dependencies:** run `process/irtt_processing.py` and `process/run_pipeline.py` before loading data (see [`process.md`](process.md)).

---

### `performance_figures.ipynb` — Key Performance Figures

Focused subset of `analysis.ipynb` containing the four core performance plots. Use this notebook to regenerate those specific figures without running the full analysis.

**Sections:**

| Section | What it shows |
|---|---|
| Hourly RTT and loss | RTT and loss traces for the SE-obstructed period (Jan 17–27) and the unobstructed baseline (Jan 29 – Feb 7). |
| Second-granularity RTT + loss spike | RTT + loss at 1-second resolution for a specific responsive-routing event on Jan 1, 2025. |
| CDF of RTT difference | Distribution of (control − test) RTT for same-satellite vs different-satellite 15-second windows, SE-obstructed period. |

---

### `event_explorer.ipynb` — Interactive Diff-Sat Event Browser

Interactive notebook for browsing individual responsive-routing events — windows where the two dishes are matched to different satellites.

For each event chunk it renders three panels side by side:
- **Sky plot** — azimuth/elevation polar chart showing all visible satellites and the SE obstruction zone (93.4°–146.6°).
- **RTT + loss panel** — second-granularity RTT for both dishes (green = control, red = test) with packet loss on a twin y-axis and first-hop RTT annotated.
- **Obstruction map** — the raw 123×123 px PNG written by the Starlink app, showing the satellite dot in the field of view.

Adjust `start_date` / `end_date` to focus on a different measurement period. Use `skip_first_n` and `total_plots_to_show` to page through large date ranges without rendering every event.

---

### `obs_mes.ipynb` — Obstruction Geometry

Computes the azimuth and elevation range blocked by the steel sheet from its physical dimensions (3.115 ft tall × 2.5 ft wide) and distance from the dish. Derives the 93.4°–146.6° azimuth boundaries cited throughout the analysis and paper.

---

## Processing scripts

All processing code lives in [`process/`](process/). See [`process.md`](process.md) for the full pipeline description, data file map, and typical order of operations.

Quick summary:

```
1. python process/tle_processing.py     # compute satellite positions from TLE files
2. python process/irtt_processing.py    # convert iRTT JSON → per-day CSV
3. python process/run_pipeline.py       # match satellites per 15-second window
4. open notebooks                       # load results and generate plots
```

Set the `STARLINK_DATA_PATH` environment variable to point at your data directory (default: `/data/starlink/home_files/data/starlink`).

---

## Environment

Install dependencies via conda using `requirement.txt`, then add the three pip-only packages:

```bash
conda create --name starlink --file requirement.txt
conda activate starlink
pip install fastdtw skyfield haversine
```
