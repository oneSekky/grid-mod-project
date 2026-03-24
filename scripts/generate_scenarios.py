"""
generate_scenarios.py

Reads PJM system-wide hourly average RT LMP, cleans the data, and generates
50 representative daily price scenarios using season-stratified k-means:
  Winter (Dec/Jan/Feb): 13 scenarios
  Spring (Mar/Apr/May): 12 scenarios
  Summer (Jun/Jul/Aug): 13 scenarios
  Fall   (Sep/Oct/Nov): 12 scenarios

Probabilities are computed as (days in cluster) / (total training days).

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

# ── Paths ─────────────────────────────────────────────────────────────────────
RAW_PATH = "D:/pjm-project/data/raw/pjm/pjm_system_lmp_hourly_avg.csv"
OUT_DIR  = os.path.join(os.path.dirname(__file__), "..", "data", "scenarios")
os.makedirs(OUT_DIR, exist_ok=True)

TRAIN_END   = "2023-12-31"
RANDOM_SEED = 42

SEASON_CONFIG = {
    "winter": {"months": [12, 1, 2],  "n": 13, "color": "#4e91c9"},
    "spring": {"months": [3,  4, 5],  "n": 12, "color": "#5cb85c"},
    "summer": {"months": [6,  7, 8],  "n": 13, "color": "#e87a2a"},
    "fall":   {"months": [9, 10, 11], "n": 12, "color": "#9b59b6"},
}

# ── 1. Load ───────────────────────────────────────────────────────────────────
print("Loading data...")
df = pd.read_csv(RAW_PATH, parse_dates=["datetime"])
df = df.rename(columns={"system_lmp_avg": "lmp"})
df = df.sort_values("datetime").reset_index(drop=True)
print(f"  Loaded {len(df):,} rows  |  {df['datetime'].min()} to {df['datetime'].max()}")

# ── 2. Training window ────────────────────────────────────────────────────────
train = df[df["datetime"] <= TRAIN_END].copy()
print(f"  Training rows (<= {TRAIN_END}): {len(train):,}")

# ── 3. Clean ──────────────────────────────────────────────────────────────────
n_before = len(train)
train = train.drop_duplicates(subset="datetime", keep="first")
print(f"  Dropped {n_before - len(train)} duplicate timestamps")

full_idx = pd.date_range(train["datetime"].min(), train["datetime"].max(), freq="h")
train = train.set_index("datetime").reindex(full_idx)
train.index.name = "datetime"
n_missing = train["lmp"].isna().sum()
train["lmp"] = train["lmp"].interpolate(method="linear")
train = train.reset_index()
print(f"  Filled {n_missing} missing hours via linear interpolation")

p01 = train["lmp"].quantile(0.01)
p99 = train["lmp"].quantile(0.99)
n_clipped = ((train["lmp"] < p01) | (train["lmp"] > p99)).sum()
train["lmp"] = train["lmp"].clip(lower=p01, upper=p99)
print(f"  Clipped {n_clipped} outlier values  (bounds: [{p01:.2f}, {p99:.2f}] $/MWh)")

# ── 4. Build daily 24-hour feature matrix ────────────────────────────────────
train["date"]  = train["datetime"].dt.date
train["hour"]  = train["datetime"].dt.hour
train["month"] = train["datetime"].dt.month

daily = (
    train.pivot(index="date", columns="hour", values="lmp")
    .dropna()
)
daily.columns = [f"h{c:02d}" for c in daily.columns]
daily["month"] = pd.to_datetime(daily.index.astype(str)).month
print(f"  Complete daily profiles: {len(daily)}")

total_days = len(daily)

# ── 5. Season-stratified k-means ─────────────────────────────────────────────
all_scenarios = []
scenario_id   = 1

for season, cfg in SEASON_CONFIG.items():
    mask     = daily["month"].isin(cfg["months"])
    season_days = daily[mask].drop(columns="month")
    n_days   = len(season_days)
    n_clust  = cfg["n"]
    print(f"\n  {season.capitalize()} ({n_days} days) -> {n_clust} scenarios")

    scaler  = StandardScaler()
    X       = scaler.fit_transform(season_days.values)
    km      = KMeans(n_clusters=n_clust, random_state=RANDOM_SEED, n_init=20, max_iter=500)
    km.fit(X)

    centroids = scaler.inverse_transform(km.cluster_centers_)
    labels, counts = np.unique(km.labels_, return_counts=True)
    # probability = days in cluster / total training days (so all 50 sum to 1)
    probs = counts / total_days

    # sort by descending probability within season
    order     = np.argsort(-probs)
    centroids = centroids[order]
    probs     = probs[order]

    for i in range(n_clust):
        row = {"scenario_id": scenario_id, "season": season, "probability": probs[i]}
        for h in range(24):
            row[f"h{h:02d}"] = centroids[i, h]
        all_scenarios.append(row)
        scenario_id += 1

# ── 6. Save scenarios.csv ────────────────────────────────────────────────────
hour_cols = [f"h{h:02d}" for h in range(24)]
scen_df   = pd.DataFrame(all_scenarios)
col_order = ["scenario_id", "season", "probability"] + hour_cols
scen_df   = scen_df[col_order]

prob_sum = scen_df["probability"].sum()
print(f"\n  Probability sum across all 50 scenarios: {prob_sum:.4f}")

scen_path = os.path.join(OUT_DIR, "scenarios.csv")
scen_df.to_csv(scen_path, index=False, float_format="%.4f")
print(f"Saved: {scen_path}")

# ── 7. scenario_metadata.csv ─────────────────────────────────────────────────
centroid_vals = scen_df[hour_cols].values
meta = scen_df[["scenario_id", "season", "probability"]].copy()
meta["mean_lmp"]  = centroid_vals.mean(axis=1)
meta["min_lmp"]   = centroid_vals.min(axis=1)
meta["max_lmp"]   = centroid_vals.max(axis=1)
meta["peak_hour"] = centroid_vals.argmax(axis=1)
meta_path = os.path.join(OUT_DIR, "scenario_metadata.csv")
meta.to_csv(meta_path, index=False, float_format="%.4f")
print(f"Saved: {meta_path}")

# ── 8. cleaning_log.csv ───────────────────────────────────────────────────────
log = pd.DataFrame([{
    "raw_rows":         len(df),
    "train_rows":       len(train),
    "missing_filled":   int(n_missing),
    "outliers_clipped": int(n_clipped),
    "p01_clip":         round(p01, 4),
    "p99_clip":         round(p99, 4),
    "complete_days":    total_days,
    "n_scenarios":      50,
    "train_end":        TRAIN_END,
    "method":           "season-stratified k-means",
}])
log.to_csv(os.path.join(OUT_DIR, "cleaning_log.csv"), index=False)

# ── 9. Grid plot: 4 seasons x (12-13) scenarios ───────────────────────────────
hours  = np.arange(24)
season_list = list(SEASON_CONFIG.keys())

fig, axes = plt.subplots(4, 13, figsize=(26, 12), sharey=False)

for s_idx, season in enumerate(season_list):
    cfg      = SEASON_CONFIG[season]
    s_rows   = scen_df[scen_df["season"] == season].reset_index(drop=True)
    n_clust  = cfg["n"]
    for i in range(13):
        ax = axes[s_idx, i]
        if i < n_clust:
            row = s_rows.iloc[i]
            vals = row[hour_cols].values.astype(float)
            ax.plot(hours, vals, color=cfg["color"], linewidth=1.2)
            ax.fill_between(hours, vals, alpha=0.2, color=cfg["color"])
            ax.set_title(f"S{int(row['scenario_id'])}\np={row['probability']:.3f}",
                         fontsize=6.5, pad=2)
            ax.set_xticks([0, 6, 12, 18, 23])
            ax.tick_params(labelsize=5.5)
            ax.grid(True, alpha=0.3, linewidth=0.5)
        else:
            ax.set_visible(False)
    # Season label on left
    axes[s_idx, 0].set_ylabel(season.capitalize(), fontsize=9, fontweight="bold",
                               labelpad=4)

fig.suptitle(
    "PJM System RT LMP — 50 Season-Stratified K-Means Scenarios (2020-2023 training)\n"
    "Rows: Winter / Spring / Summer / Fall   |   Y: System Avg LMP ($/MWh)   X: Hour (EPT)",
    fontsize=10
)
plt.tight_layout()
grid_path = os.path.join(OUT_DIR, "scenario_grid.png")
fig.savefig(grid_path, dpi=150)
print(f"Saved: {grid_path}")

# ── 10. Fan plot: one panel per season ───────────────────────────────────────
fig2, axes2 = plt.subplots(2, 2, figsize=(14, 8), sharey=False)
axes2 = axes2.flatten()

for s_idx, season in enumerate(season_list):
    cfg    = SEASON_CONFIG[season]
    s_rows = scen_df[scen_df["season"] == season]
    ax     = axes2[s_idx]
    probs_s = s_rows["probability"].values
    for _, row in s_rows.iterrows():
        alpha = 0.25 + 0.6 * row["probability"] / probs_s.max()
        ax.plot(hours, row[hour_cols].values.astype(float),
                color=cfg["color"], alpha=float(alpha), linewidth=1.1)
    ax.set_title(f"{season.capitalize()} ({cfg['n']} scenarios)", fontsize=10)
    ax.set_xlabel("Hour (EPT)")
    ax.set_ylabel("LMP ($/MWh)")
    ax.set_xticks(range(0, 24, 2))
    ax.grid(True, alpha=0.3)

fig2.suptitle("PJM System RT LMP — Seasonal Scenario Fans (2020-2023 training)", fontsize=11)
plt.tight_layout()
fan_path = os.path.join(OUT_DIR, "scenario_fan.png")
fig2.savefig(fan_path, dpi=150)
print(f"Saved: {fan_path}")

print("\nDone.")
