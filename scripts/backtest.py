"""
backtest.py

Out-of-sample backtesting on 2024 price data.

For each day in 2024, solves the deterministic MILP with that day's actual
realized prices (perfect foresight within the day), then reports:
  - Realized daily net revenue under the optimized policy
  - Naive benchmark 1: always charge off-peak (hours 0-6), discharge on-peak (hours 16-21)
  - Naive benchmark 2: always charge at cheapest 8 hours, discharge at most expensive 8 hours

The optimized policy here is the "clairvoyant deterministic" upper bound on what
the stochastic policy could earn. This is standard backtesting practice for
storage arbitrage models: use the deterministic oracle as the performance ceiling
and compare naive strategies against it.

Data source:
  D:/pjm-project/data/raw/pjm/pjm_system_lmp_hourly_avg.csv
  (same file used for scenario generation; 2024+ rows are the held-out test set)

Outputs:
  results/backtest_daily.csv          -- per-day revenue for all strategies
  results/backtest_summary.csv        -- aggregate stats (mean, std, total)
  results/backtest_cumulative.png     -- cumulative revenue over 2024
  results/backtest_daily_bar.png      -- daily net revenue comparison bar chart
  results/backtest_monthly.png        -- monthly average net revenue comparison
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cvxpy as cp

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(__file__)
RAW_PATH   = "D:/pjm-project/data/raw/pjm/pjm_system_lmp_hourly_avg.csv"
OUT_DIR    = os.path.join(SCRIPT_DIR, "..", "results")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Battery Parameters (1 MWh reference, same as stochastic model) ───────────
E_MWH         = 1.0
P_MW          = 0.5
ETA_C         = 0.93
ETA_D         = 0.93
SOC_MIN       = 0.10
SOC_MAX       = 0.90
SOC_INIT      = 0.50
SOC_FINAL_MIN = 0.10

# Sources: NREL ATB 2024 ($334/kWh), modern utility LFP cycle life 6,000 cycles at 80% DoD
C_CAPEX     = 334_000.0
DOD_TYPICAL = SOC_MAX - SOC_MIN
N_CYCLES    = 6_000.0
C_DEG       = C_CAPEX / (2.0 * E_MWH * N_CYCLES)

BACKTEST_YEAR = 2024
T = 24

# ── Load and clean 2024 data ─────────────────────────────────────────────────
print("Loading 2024 price data...")
df = pd.read_csv(RAW_PATH, parse_dates=["datetime"])
df = df.rename(columns={"system_lmp_avg": "lmp"})
df = df.sort_values("datetime").reset_index(drop=True)

# Apply same cleaning as training pipeline (clip to training-set p01/p99)
# Load cleaning log to get the exact bounds used during scenario generation
cleaning_log_path = os.path.join(SCRIPT_DIR, "..", "data", "scenarios", "cleaning_log.csv")
if os.path.exists(cleaning_log_path):
    clog = pd.read_csv(cleaning_log_path)
    p01_clip = float(clog["p01_clip"].iloc[0])
    p99_clip = float(clog["p99_clip"].iloc[0])
    print(f"  Applying training-set clip bounds: [{p01_clip:.2f}, {p99_clip:.2f}] $/MWh")
else:
    p01_clip = df["lmp"].quantile(0.01)
    p99_clip = df["lmp"].quantile(0.99)
    print(f"  No cleaning log found; using test-set percentiles: [{p01_clip:.2f}, {p99_clip:.2f}]")

df["lmp"] = df["lmp"].clip(lower=p01_clip, upper=p99_clip)

# Filter to backtest year and build daily profiles
test = df[df["datetime"].dt.year == BACKTEST_YEAR].copy()
test["date"] = test["datetime"].dt.date
test["hour"] = test["datetime"].dt.hour

daily = test.pivot(index="date", columns="hour", values="lmp").dropna()
daily.columns = list(range(24))
n_days = len(daily)
print(f"  Complete days in {BACKTEST_YEAR}: {n_days}")

# ── Deterministic MILP (single-day, perfect foresight) ───────────────────────
def solve_deterministic(price_24h):
    """
    Solve the deterministic MILP for a single 24-hour price profile.
    Returns dict with net revenue, charge/discharge arrays, and SOC.
    """
    p_c = cp.Variable(T, nonneg=True)
    p_d = cp.Variable(T, nonneg=True)
    soc = cp.Variable(T, nonneg=True)
    u_c = cp.Variable(T, boolean=True)
    u_d = cp.Variable(T, boolean=True)

    constraints = [
        p_c <= P_MW * u_c,
        p_d <= P_MW * u_d,
        u_c + u_d <= 1,
        soc >= SOC_MIN * E_MWH,
        soc <= SOC_MAX * E_MWH,
        soc[0] == SOC_INIT * E_MWH + ETA_C * p_c[0] - (1.0 / ETA_D) * p_d[0],
        soc[T-1] >= SOC_FINAL_MIN * E_MWH,
    ]
    for t in range(1, T):
        constraints.append(
            soc[t] == soc[t-1] + ETA_C * p_c[t] - (1.0 / ETA_D) * p_d[t]
        )

    revenue = price_24h @ p_d - price_24h @ p_c
    deg     = C_DEG * (cp.sum(p_d) + cp.sum(p_c))
    objective = cp.Maximize(revenue - deg)

    prob = cp.Problem(objective, constraints)
    prob.solve(solver=cp.HIGHS, verbose=False, time_limit=30)

    if prob.status not in ("optimal", "optimal_inaccurate") or prob.value is None:
        return None

    pc = p_c.value
    pd_ = p_d.value
    revenue_val = float(price_24h @ pd_ - price_24h @ pc)
    deg_val     = float(C_DEG * (pd_.sum() + pc.sum()))

    return {
        "revenue": revenue_val,
        "deg":     deg_val,
        "net":     revenue_val - deg_val,
        "pc":      pc,
        "pd":      pd_,
        "soc":     soc.value,
    }

# ── Naive benchmark: fixed off-peak charge / on-peak discharge ────────────────
# Degradation-aware: only executes a trade if the realized price spread covers
# the round-trip degradation cost (C_DEG per MWh on both legs).
# This is a fairer baseline — a human operator would not trade at a guaranteed loss.
OFFPEAK_HOURS = list(range(0, 7))    # midnight to 6am
ONPEAK_HOURS  = list(range(16, 22))  # 4pm to 9pm

# Minimum net spread required to trade: round-trip degradation on both legs.
# Charging costs C_DEG, discharging costs C_DEG, so minimum spread = 2 * C_DEG
# divided by round-trip efficiency to break even.
MIN_SPREAD = 2 * C_DEG / (ETA_C * ETA_D)

def naive_fixed(price_24h):
    """
    Charge during OFFPEAK_HOURS, discharge during ONPEAK_HOURS.
    Degradation-aware: only trades if expected discharge price minus charge price
    exceeds the round-trip degradation cost threshold (MIN_SPREAD).
    """
    avg_offpeak = np.mean([price_24h[t] for t in OFFPEAK_HOURS])
    avg_onpeak  = np.mean([price_24h[t] for t in ONPEAK_HOURS])
    # Skip day entirely if spread doesn't cover degradation cost
    if avg_onpeak - avg_offpeak < MIN_SPREAD:
        return {"revenue": 0.0, "deg": 0.0, "net": 0.0}

    soc_val = SOC_INIT * E_MWH
    revenue, deg = 0.0, 0.0
    for t in range(T):
        if t in OFFPEAK_HOURS and soc_val < SOC_MAX * E_MWH:
            charge   = min(P_MW, (SOC_MAX * E_MWH - soc_val) / ETA_C)
            soc_val += ETA_C * charge
            revenue -= price_24h[t] * charge
            deg     += C_DEG * charge
        elif t in ONPEAK_HOURS and soc_val > SOC_MIN * E_MWH:
            discharge = min(P_MW, (soc_val - SOC_MIN * E_MWH) * ETA_D)
            soc_val  -= discharge / ETA_D
            revenue  += price_24h[t] * discharge
            deg      += C_DEG * discharge
    return {"revenue": revenue, "deg": deg, "net": revenue - deg}

# ── Naive benchmark 2: charge cheapest hours, discharge most expensive ─────────
# Degradation-aware: only executes the trade if the best achievable spread
# (max price - min charge price) exceeds the minimum required spread.
def naive_price_rank(price_24h):
    """
    Charge at the N cheapest hours, discharge at the N most expensive hours
    (no overlap, N chosen to fill battery once at 0.5C rate = 1 full cycle).
    Degradation-aware: skips the day if best spread < MIN_SPREAD.
    """
    # One full charge/discharge cycle: 0.5 MW * (SOC range / efficiency) hours each
    usable_mwh  = (SOC_MAX - SOC_MIN) * E_MWH          # 0.8 MWh
    n_charge_h  = int(np.ceil(usable_mwh / (ETA_C * P_MW)))   # hours to fill
    n_discharge_h = int(np.ceil(usable_mwh * ETA_D / P_MW))   # hours to empty

    sorted_asc  = np.argsort(price_24h)
    sorted_desc = np.argsort(-price_24h)

    charge_hours    = set(sorted_asc[:n_charge_h].tolist())
    # Discharge from most expensive hours that don't overlap with charge hours
    discharge_hours = set()
    for h in sorted_desc:
        if h not in charge_hours:
            discharge_hours.add(h)
        if len(discharge_hours) == n_discharge_h:
            break

    # Skip if best spread doesn't cover degradation cost
    best_discharge = max(price_24h[h] for h in discharge_hours) if discharge_hours else 0
    best_charge    = min(price_24h[h] for h in charge_hours) if charge_hours else 0
    if best_discharge - best_charge < MIN_SPREAD:
        return {"revenue": 0.0, "deg": 0.0, "net": 0.0}

    soc_val = SOC_INIT * E_MWH
    revenue, deg = 0.0, 0.0
    for t in range(T):
        if t in charge_hours and soc_val < SOC_MAX * E_MWH:
            charge   = min(P_MW, (SOC_MAX * E_MWH - soc_val) / ETA_C)
            soc_val += ETA_C * charge
            revenue -= price_24h[t] * charge
            deg     += C_DEG * charge
        elif t in discharge_hours and soc_val > SOC_MIN * E_MWH:
            discharge = min(P_MW, (soc_val - SOC_MIN * E_MWH) * ETA_D)
            soc_val  -= discharge / ETA_D
            revenue  += price_24h[t] * discharge
            deg      += C_DEG * discharge
    return {"revenue": revenue, "deg": deg, "net": revenue - deg}

# ── Run backtest ──────────────────────────────────────────────────────────────
records = []
print(f"\nRunning backtest over {n_days} days...")
for i, (date, row) in enumerate(daily.iterrows()):
    if i % 50 == 0:
        print(f"  Day {i+1}/{n_days}: {date}")
    price = row.values.astype(float)

    opt  = solve_deterministic(price)
    fix  = naive_fixed(price)
    rank = naive_price_rank(price)

    records.append({
        "date":               str(date),
        "month":              pd.Timestamp(str(date)).month,
        "mean_lmp":           round(price.mean(), 4),
        "spread_lmp":         round(price.max() - price.min(), 4),
        # Optimized (oracle)
        "opt_revenue":        round(opt["revenue"], 4) if opt else None,
        "opt_deg":            round(opt["deg"], 4)     if opt else None,
        "opt_net":            round(opt["net"], 4)     if opt else None,
        # Naive: fixed hours
        "naive_fixed_revenue":round(fix["revenue"], 4),
        "naive_fixed_deg":    round(fix["deg"], 4),
        "naive_fixed_net":    round(fix["net"], 4),
        # Naive: price-rank
        "naive_rank_revenue": round(rank["revenue"], 4),
        "naive_rank_deg":     round(rank["deg"], 4),
        "naive_rank_net":     round(rank["net"], 4),
    })

daily_df = pd.DataFrame(records)
daily_df["date"] = pd.to_datetime(daily_df["date"])
daily_df = daily_df.sort_values("date").reset_index(drop=True)

# ── Summary statistics ────────────────────────────────────────────────────────
strategies = {
    "Optimized (oracle)":  "opt_net",
    "Naive fixed hours":   "naive_fixed_net",
    "Naive price rank":    "naive_rank_net",
}
summary_rows = []
for label, col in strategies.items():
    vals = daily_df[col].dropna()
    summary_rows.append({
        "strategy":        label,
        "mean_daily_net":  round(vals.mean(), 4),
        "std_daily_net":   round(vals.std(), 4),
        "total_net_year":  round(vals.sum(), 2),
        "min_day":         round(vals.min(), 4),
        "max_day":         round(vals.max(), 4),
        "pct_positive":    round((vals > 0).mean() * 100, 1),
    })
summary_df = pd.DataFrame(summary_rows)

print(f"\n--- Backtest Summary ({BACKTEST_YEAR}) ---")
print(summary_df.to_string(index=False))

daily_path   = os.path.join(OUT_DIR, "backtest_daily.csv")
summary_path = os.path.join(OUT_DIR, "backtest_summary.csv")
daily_df.to_csv(daily_path, index=False)
summary_df.to_csv(summary_path, index=False)
print(f"\nSaved: {daily_path}")
print(f"Saved: {summary_path}")

# ── Plot 1: Cumulative revenue over 2024 ──────────────────────────────────────
colors = {"Optimized (oracle)": "#4e91c9", "Naive fixed hours": "#e87a2a", "Naive price rank": "#9b59b6"}
fig, ax = plt.subplots(figsize=(13, 5))
for label, col in strategies.items():
    cumrev = daily_df[col].fillna(0).cumsum()
    ax.plot(daily_df["date"], cumrev, label=label, color=colors[label], linewidth=1.5)
ax.set_xlabel("Date", fontsize=11)
ax.set_ylabel("Cumulative Net Revenue ($)", fontsize=11)
ax.set_title(f"Cumulative Net Revenue — {BACKTEST_YEAR} Out-of-Sample Backtest (1 MWh LFP)", fontsize=12)
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)
ax.axhline(0, color="black", linewidth=0.7, linestyle="--")
plt.tight_layout()
cum_path = os.path.join(OUT_DIR, "backtest_cumulative.png")
fig.savefig(cum_path, dpi=150)
plt.close()
print(f"Saved: {cum_path}")

# ── Plot 2: Monthly average net revenue comparison ────────────────────────────
monthly = daily_df.groupby("month")[
    ["opt_net", "naive_fixed_net", "naive_rank_net"]
].mean().reset_index()

month_labels = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
x = np.arange(12)
w = 0.28

fig, ax = plt.subplots(figsize=(13, 5))
ax.bar(x - w, monthly["opt_net"],         width=w, label="Optimized (oracle)", color="#4e91c9", alpha=0.85)
ax.bar(x,     monthly["naive_fixed_net"], width=w, label="Naive fixed hours",  color="#e87a2a", alpha=0.85)
ax.bar(x + w, monthly["naive_rank_net"],  width=w, label="Naive price rank",   color="#9b59b6", alpha=0.85)
ax.set_xticks(x)
ax.set_xticklabels(month_labels)
ax.set_xlabel("Month", fontsize=11)
ax.set_ylabel("Avg Daily Net Revenue ($/day)", fontsize=11)
ax.set_title(f"Monthly Average Daily Net Revenue — {BACKTEST_YEAR} Backtest", fontsize=12)
ax.legend(fontsize=9)
ax.axhline(0, color="black", linewidth=0.7)
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
monthly_path = os.path.join(OUT_DIR, "backtest_monthly.png")
fig.savefig(monthly_path, dpi=150)
plt.close()
print(f"Saved: {monthly_path}")

# ── Save params ────────────────────────────────────────────────────────────────
params = {
    "E_MWH": E_MWH, "P_MW": P_MW, "ETA_C": ETA_C, "ETA_D": ETA_D,
    "SOC_MIN": SOC_MIN, "SOC_MAX": SOC_MAX, "C_DEG_per_MWh": round(C_DEG, 4),
    "backtest_year": BACKTEST_YEAR, "n_days": n_days,
    "clip_bounds": [p01_clip, p99_clip],
    "solver": "HiGHS via CVXPY",
    "offpeak_hours": OFFPEAK_HOURS, "onpeak_hours": ONPEAK_HOURS,
}
with open(os.path.join(OUT_DIR, "backtest_params.json"), "w") as f:
    json.dump(params, f, indent=2)
print(f"Saved: {os.path.join(OUT_DIR, 'backtest_params.json')}")

print("\nDone.")
