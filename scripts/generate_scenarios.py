"""
generate_scenarios.py

Reads PJM system-wide hourly average RT LMP from the external drive,
cleans the data, and generates 50 representative daily price scenarios
using k-means clustering. Saves results to data/scenarios/.

Data source: D:/pjm-project/data/raw/pjm/pjm_system_lmp_hourly_avg.csv
Training window: 2020-01-01 through 2023-12-31 (hold out 2024+ for backtest)
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# ── Paths ────────────────────────────────────────────────────────────────────
RAW_PATH = "D:/pjm-project/data/raw/pjm/pjm_system_lmp_hourly_avg.csv"
OUT_DIR   = os.path.join(os.path.dirname(__file__), "..", "data", "scenarios")
os.makedirs(OUT_DIR, exist_ok=True)

N_SCENARIOS   = 50
TRAIN_END     = "2023-12-31"
RANDOM_SEED   = 42

# ── 1. Load ───────────────────────────────────────────────────────────────────
print("Loading data...")
df = pd.read_csv(RAW_PATH, parse_dates=["datetime"])
df = df.rename(columns={"datetime": "datetime", "system_lmp_avg": "lmp"})
df = df.sort_values("datetime").reset_index(drop=True)

print(f"  Loaded {len(df):,} rows  |  {df['datetime'].min()} to {df['datetime'].max()}")

# ── 2. Restrict to training window ────────────────────────────────────────────
train = df[df["datetime"] <= TRAIN_END].copy()
print(f"  Training rows (<= {TRAIN_END}): {len(train):,}")

# ── 3. Clean ──────────────────────────────────────────────────────────────────
# 3a. Drop duplicate timestamps (can occur at DST fall-back — keep first)
n_before = len(train)
train = train.drop_duplicates(subset="datetime", keep="first")
print(f"  Dropped {n_before - len(train)} duplicate timestamps")

# 3b. Reindex to a complete hourly grid; NaN-fill gaps
full_idx = pd.date_range(train["datetime"].min(), train["datetime"].max(), freq="h")
train = train.set_index("datetime").reindex(full_idx)
train.index.name = "datetime"
n_missing = train["lmp"].isna().sum()
print(f"  Filled {n_missing} missing hours via linear interpolation")
train["lmp"] = train["lmp"].interpolate(method="linear")
train = train.reset_index()

# 3c. Cap extreme outliers at [1st, 99th] percentile to reduce spike distortion
p01 = train["lmp"].quantile(0.01)
p99 = train["lmp"].quantile(0.99)
n_clipped = ((train["lmp"] < p01) | (train["lmp"] > p99)).sum()
train["lmp"] = train["lmp"].clip(lower=p01, upper=p99)
print(f"  Clipped {n_clipped} outlier values  (bounds: [{p01:.2f}, {p99:.2f}] $/MWh)")

# ── 4. Build daily 24-hour feature matrix ─────────────────────────────────────
train["date"] = train["datetime"].dt.date
train["hour"] = train["datetime"].dt.hour

daily = (
    train.pivot(index="date", columns="hour", values="lmp")
    .dropna()                          # drop days with any missing hour
)
daily.columns = [f"h{c:02d}" for c in daily.columns]
print(f"  Daily profiles: {len(daily)} complete days")

# ── 5. K-means clustering → 50 scenarios ─────────────────────────────────────
print(f"\nClustering into {N_SCENARIOS} scenarios...")
scaler  = StandardScaler()
X_scaled = scaler.fit_transform(daily.values)

km = KMeans(n_clusters=N_SCENARIOS, random_state=RANDOM_SEED, n_init=20, max_iter=500)
km.fit(X_scaled)

# Scenario centroids back in $/MWh
centroids = scaler.inverse_transform(km.cluster_centers_)

# Scenario probabilities = fraction of days in each cluster
labels, counts = np.unique(km.labels_, return_counts=True)
probs = counts / counts.sum()

# Sort by probability (descending) for readability
order    = np.argsort(-probs)
centroids = centroids[order]
probs     = probs[order]
scenario_ids = np.arange(1, N_SCENARIOS + 1)

# ── 6. Save ───────────────────────────────────────────────────────────────────
# 6a. scenarios.csv  —  one row per scenario, columns h00..h23 + probability
hour_cols = [f"h{h:02d}" for h in range(24)]
scen_df = pd.DataFrame(centroids, columns=hour_cols)
scen_df.insert(0, "scenario_id", scenario_ids)
scen_df["probability"] = probs

scen_path = os.path.join(OUT_DIR, "scenarios.csv")
scen_df.to_csv(scen_path, index=False, float_format="%.4f")
print(f"\nSaved: {scen_path}")

# 6b. scenario_metadata.csv  —  summary stats per scenario
meta = scen_df[["scenario_id", "probability"]].copy()
meta["mean_lmp"]  = centroids.mean(axis=1)
meta["min_lmp"]   = centroids.min(axis=1)
meta["max_lmp"]   = centroids.max(axis=1)
meta["peak_hour"] = centroids.argmax(axis=1)
meta_path = os.path.join(OUT_DIR, "scenario_metadata.csv")
meta.to_csv(meta_path, index=False, float_format="%.4f")
print(f"Saved: {meta_path}")

# 6c. cleaning_log.csv  —  audit trail
log = pd.DataFrame([{
    "raw_rows":          len(df),
    "train_rows":        len(train),
    "duplicate_drops":   n_before - (n_before - (n_before - len(train))),
    "missing_filled":    int(n_missing),
    "outliers_clipped":  int(n_clipped),
    "p01_clip":          round(p01, 4),
    "p99_clip":          round(p99, 4),
    "complete_days":     len(daily),
    "n_scenarios":       N_SCENARIOS,
    "train_end":         TRAIN_END,
}])
log_path = os.path.join(OUT_DIR, "cleaning_log.csv")
log.to_csv(log_path, index=False)
print(f"Saved: {log_path}")

# ── 7. Plot scenario fan ───────────────────────────────────────────────────────
hours = np.arange(24)
fig, ax = plt.subplots(figsize=(12, 6))
for i in range(N_SCENARIOS):
    alpha = 0.3 + 0.5 * probs[i] / probs.max()
    ax.plot(hours, centroids[i], color="steelblue", alpha=float(alpha), linewidth=1)

# Highlight top-5 most probable
for i in range(5):
    ax.plot(hours, centroids[i], linewidth=2,
            label=f"S{scenario_ids[i]} (p={probs[i]:.3f})")

ax.set_xlabel("Hour of Day (EPT)")
ax.set_ylabel("System Avg LMP ($/MWh)")
ax.set_title(f"PJM System RT LMP — {N_SCENARIOS} K-Means Scenarios (2020–2023 training)")
ax.set_xticks(hours)
ax.legend(fontsize=8, loc="upper left")
ax.grid(True, alpha=0.3)
plt.tight_layout()
fig_path = os.path.join(OUT_DIR, "scenario_fan.png")
fig.savefig(fig_path, dpi=150)
print(f"Saved: {fig_path}")

print("\nDone.")
