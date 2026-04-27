"""
optimize_stochastic.py

Stochastic MILP for BESS day-ahead bidding over 40 price scenarios.

Objective: Maximize probability-weighted expected revenue minus degradation cost.

Decision variables (scenario-indexed):
  p_c[s, t]  -- charging power in scenario s at hour t  (MW)
  p_d[s, t]  -- discharging power in scenario s at hour t  (MW)
  soc[s, t]  -- state of charge at END of hour t  (MWh)
  u_c[s, t]  -- binary: 1 if charging in scenario s at hour t
  u_d[s, t]  -- binary: 1 if discharging in scenario s at hour t

Degradation model (Xu et al.):
  Each MWh of throughput incurs cost C_DEG ($/MWh).
  Derived from LFP cycle-life curve: N_cycles(DoD) = A * exp(B * DoD).
  C_DEG = C_CAPEX / (2 * E * N_cycles(DOD_TYPICAL))

Solver: CVXPY + HiGHS (Gurobi restricted license is size-limited).

Outputs:
  results/stochastic_results.csv        -- per-scenario hourly dispatch table
  results/stochastic_summary.csv        -- per-scenario aggregated P&L
  results/stochastic_params.json        -- run parameters log
  results/stochastic_soc.png            -- SOC trajectories (scenario bands)
  results/stochastic_dispatch.png       -- dispatch + price overlay (best scenario)
  results/stochastic_revenue_dist.png   -- per-scenario net revenue bar chart
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
SCRIPT_DIR    = os.path.dirname(__file__)
SCENARIOS_CSV = os.path.join(SCRIPT_DIR, "..", "data", "scenarios", "scenarios.csv")
OUT_DIR       = os.path.join(SCRIPT_DIR, "..", "results")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Battery Parameters (LFP 1 MWh reference system) ──────────────────────────
E_MWH         = 1.0    # Energy capacity (MWh)
P_MW          = 0.5    # Power capacity (MW) — 0.5C rate
ETA_C         = 0.93   # Charging efficiency (one-way)
ETA_D         = 0.93   # Discharging efficiency (one-way)
SOC_MIN       = 0.10   # Minimum SOC fraction
SOC_MAX       = 0.90   # Maximum SOC fraction
SOC_INIT      = 0.50   # Initial SOC fraction (beginning of day)
SOC_FINAL_MIN = 0.10   # Minimum SOC at end of day (return-to-reserve)

# ── Degradation cost (Xu et al. model, calibrated to current LFP data) ────────
# Sources:
#   CapEx: NREL ATB 2024 — $334/kWh all-in installed cost for US utility BESS
#          (https://atb.nrel.gov/electricity/2024/utility-scale_battery_storage)
#   Cycle life: 6,000 cycles at 80% DoD to 70-80% SOH — modern utility-grade LFP
#          (DOE 2024 whitepaper; NextG Power; Himax Battery 2024 test data)
#          Previous value of ~3,400 cycles was Xu et al. (2016) lab cells;
#          current commercial cells are ~2x better.
# C_DEG = C_CAPEX / (2 * E * N_cycles):
#   numerator  = total capital to recover
#   denominator = lifetime energy throughput (each cycle = 2*E MWh of stress)
C_CAPEX     = 334_000.0      # $ all-in installed CapEx for 1 MWh LFP (NREL ATB 2024)
DOD_TYPICAL = SOC_MAX - SOC_MIN             # 0.80
N_CYCLES    = 6_000.0        # cycles to 70-80% SOH at 80% DoD (modern utility LFP)
C_DEG       = C_CAPEX / (2.0 * E_MWH * N_CYCLES)

print("Degradation parameters:")
print(f"  N_cycles at DoD={DOD_TYPICAL:.2f}: {N_CYCLES:.0f}")
print(f"  C_DEG = ${C_DEG:.4f}/MWh throughput")

# ── Load Scenarios ────────────────────────────────────────────────────────────
print("\nLoading scenarios...")
scen_df   = pd.read_csv(SCENARIOS_CSV)
S_ids     = scen_df["scenario_id"].tolist()
S         = len(S_ids)
T         = 24
HOURS     = list(range(T))
hour_cols = [f"h{h:02d}" for h in HOURS]

probs = scen_df["probability"].values           # (S,)
lmp   = scen_df[hour_cols].values              # (S, T)  $/MWh

print(f"  Loaded {S} scenarios  |  probability sum = {probs.sum():.4f}")
print(f"  LMP range: [{lmp.min():.2f}, {lmp.max():.2f}] $/MWh")

# ── Decision Variables (numpy-array-shaped CVXPY variables) ──────────────────
# Using shape (S, T) arrays for readability and vectorised constraint building.
print("\nBuilding stochastic MILP...")

p_c = cp.Variable((S, T), nonneg=True, name="p_c")   # charging power (MW)
p_d = cp.Variable((S, T), nonneg=True, name="p_d")   # discharging power (MW)
soc = cp.Variable((S, T), nonneg=True, name="soc")   # SOC at end of hour t (MWh)
u_c = cp.Variable((S, T), boolean=True, name="u_c")  # charging mode binary
u_d = cp.Variable((S, T), boolean=True, name="u_d")  # discharging mode binary

constraints = []

# ── Power bounds tied to binary mode indicators ───────────────────────────────
# p_c[s,t] <= P_MW * u_c[s,t]
constraints.append(p_c <= P_MW * u_c)
# p_d[s,t] <= P_MW * u_d[s,t]
constraints.append(p_d <= P_MW * u_d)

# ── Mutual exclusivity: cannot charge and discharge simultaneously ─────────────
constraints.append(u_c + u_d <= 1)

# ── SOC bounds ────────────────────────────────────────────────────────────────
constraints.append(soc >= SOC_MIN * E_MWH)
constraints.append(soc <= SOC_MAX * E_MWH)

# ── SOC dynamics (energy balance): soc(t) = soc(t-1) + eta_c*p_c(t) - p_d(t)/eta_d
# t=0: soc_prev = SOC_INIT * E_MWH  (scalar, known initial condition)
constraints.append(
    soc[:, 0] == SOC_INIT * E_MWH + ETA_C * p_c[:, 0] - (1.0 / ETA_D) * p_d[:, 0]
)
for t in range(1, T):
    constraints.append(
        soc[:, t] == soc[:, t - 1] + ETA_C * p_c[:, t] - (1.0 / ETA_D) * p_d[:, t]
    )

# ── End-of-day SOC lower bound (return-to-reserve) ───────────────────────────
constraints.append(soc[:, T - 1] >= SOC_FINAL_MIN * E_MWH)

# ── Objective: Maximize E[Revenue] - E[Degradation cost] ─────────────────────
#
# Revenue in scenario s:
#   R(s) = sum_t [ lmp[s,t]*p_d[s,t] - lmp[s,t]*p_c[s,t] ]
#
# Degradation in scenario s (Xu et al.):
#   D(s) = C_DEG * sum_t [ p_d[s,t] + p_c[s,t] ]   (all throughput is stress)
#
# Expected net objective:
#   max sum_s prob[s] * ( R(s) - D(s) )
#
# Rearranged in matrix form for efficiency:
net_price = lmp - C_DEG   # effective sell price after degradation  (S, T)
# Revenue = sum over s,t of prob[s] * net_price[s,t] * p_d[s,t]
# Cost    = sum over s,t of prob[s] * (net_price[s,t] + 2*C_DEG) * ... (simplified below)
# Full form: prob @ (net_price * p_d) - prob @ ((lmp + C_DEG) * p_c)
#   where @ means row-wise dot product summed over t, then weighted by probs

objective = cp.Maximize(
    probs @ cp.sum(cp.multiply(net_price, p_d) - cp.multiply(lmp + C_DEG, p_c), axis=1)
)

# ── Solve ─────────────────────────────────────────────────────────────────────
prob_model = cp.Problem(objective, constraints)
print("Solving with HiGHS...")
prob_model.solve(solver=cp.HIGHS, verbose=True, time_limit=300)

status = prob_model.status
print(f"\nSolver status  : {status}")
if prob_model.value is None:
    print("No solution found.")
    raise SystemExit(1)
print(f"Objective value: ${prob_model.value:.4f}  (expected net revenue per day)")

# ── Extract Results ───────────────────────────────────────────────────────────
pc_val  = p_c.value    # (S, T)
pd_val  = p_d.value    # (S, T)
soc_val = soc.value    # (S, T)
uc_val  = u_c.value    # (S, T)
ud_val  = u_d.value    # (S, T)

records = []
for s in range(S):
    sid    = S_ids[s]
    season = scen_df.loc[s, "season"]
    prob_s = probs[s]
    for t in HOURS:
        price   = lmp[s, t]
        pc      = float(pc_val[s, t])
        pdis    = float(pd_val[s, t])
        sc      = float(soc_val[s, t])
        revenue = price * pdis - price * pc
        deg     = C_DEG * (pdis + pc)
        records.append({
            "scenario_id":      sid,
            "season":           season,
            "probability":      prob_s,
            "hour":             t,
            "lmp":              round(price, 4),
            "p_charge_MW":      round(pc, 6),
            "p_discharge_MW":   round(pdis, 6),
            "soc_MWh":          round(sc, 6),
            "u_charge":         int(round(float(uc_val[s, t]))),
            "u_discharge":      int(round(float(ud_val[s, t]))),
            "revenue_$":        round(revenue, 6),
            "deg_cost_$":       round(deg, 6),
            "net_$":            round(revenue - deg, 6),
        })

results_df = pd.DataFrame(records)

summary = (
    results_df.groupby(["scenario_id", "season", "probability"])
    .agg(
        total_revenue   =("revenue_$",        "sum"),
        total_deg_cost  =("deg_cost_$",       "sum"),
        total_net       =("net_$",            "sum"),
        total_charge_MWh=("p_charge_MW",      "sum"),
        total_discharge_MWh=("p_discharge_MW","sum"),
        n_charge_hours  =("u_charge",         "sum"),
        n_discharge_hours=("u_discharge",     "sum"),
    )
    .reset_index()
)
summary["weighted_net"] = summary["total_net"] * summary["probability"]

ev_revenue = float((summary["total_revenue"] * summary["probability"]).sum())
ev_deg     = float((summary["total_deg_cost"] * summary["probability"]).sum())
ev_net     = float(summary["weighted_net"].sum())

print(f"\n--- Expected Value Summary ---")
print(f"  E[Revenue]          : ${ev_revenue:.4f}/day")
print(f"  E[Degradation cost] : ${ev_deg:.4f}/day")
print(f"  E[Net]              : ${ev_net:.4f}/day")
print(f"  Annualized E[Net]   : ${ev_net * 365:.0f}/year")

# ── Save outputs ──────────────────────────────────────────────────────────────
results_path = os.path.join(OUT_DIR, "stochastic_results.csv")
summary_path = os.path.join(OUT_DIR, "stochastic_summary.csv")
results_df.to_csv(results_path, index=False, float_format="%.6f")
summary.to_csv(summary_path, index=False, float_format="%.6f")
print(f"\nSaved: {results_path}")
print(f"Saved: {summary_path}")

params = {
    "E_MWH": E_MWH, "P_MW": P_MW, "ETA_C": ETA_C, "ETA_D": ETA_D,
    "SOC_MIN": SOC_MIN, "SOC_MAX": SOC_MAX, "SOC_INIT": SOC_INIT,
    "SOC_FINAL_MIN": SOC_FINAL_MIN, "C_CAPEX": C_CAPEX,
    "DOD_TYPICAL": DOD_TYPICAL, "N_CYCLES": round(N_CYCLES, 1),
    "C_DEG_per_MWh": round(C_DEG, 4),
    "n_scenarios": S, "n_hours": T, "solver": "HiGHS via CVXPY",
    "solver_status": status, "obj_value": round(prob_model.value, 6),
    "ev_revenue": round(ev_revenue, 6), "ev_deg_cost": round(ev_deg, 6),
    "ev_net": round(ev_net, 6),
}
with open(os.path.join(OUT_DIR, "stochastic_params.json"), "w") as f:
    json.dump(params, f, indent=2)
print(f"Saved: {os.path.join(OUT_DIR, 'stochastic_params.json')}")

# ── Plot 1: SOC Trajectories (scenario bands) ─────────────────────────────────
print("\nGenerating plots...")
season_colors = {"winter": "#4e91c9", "spring": "#5cb85c",
                 "summer": "#e87a2a", "fall":   "#9b59b6"}

fig, ax = plt.subplots(figsize=(12, 5))
for s in range(S):
    season   = scen_df.loc[s, "season"]
    alpha_val = 0.15 + 0.5 * probs[s] / probs.max()
    ax.plot(HOURS, soc_val[s],
            color=season_colors[season], alpha=float(alpha_val), linewidth=0.9)

for season, color in season_colors.items():
    ax.plot([], [], color=color, label=season.capitalize(), linewidth=2)
ax.axhline(SOC_MIN * E_MWH, color="red",   linestyle="--", linewidth=0.8,
           alpha=0.6, label=f"SOC min ({SOC_MIN:.0%})")
ax.axhline(SOC_MAX * E_MWH, color="green", linestyle="--", linewidth=0.8,
           alpha=0.6, label=f"SOC max ({SOC_MAX:.0%})")
ax.set_xlabel("Hour (EPT)", fontsize=11)
ax.set_ylabel("State of Charge (MWh)", fontsize=11)
ax.set_title("BESS SOC Trajectories — Stochastic EV Optimization (40 Scenarios)", fontsize=12)
ax.set_xticks(range(0, T, 2))
ax.set_xlim(-0.5, 23.5)
ax.legend(loc="upper right", fontsize=9)
ax.grid(True, alpha=0.3)
plt.tight_layout()
soc_path = os.path.join(OUT_DIR, "stochastic_soc.png")
fig.savefig(soc_path, dpi=150)
plt.close()
print(f"Saved: {soc_path}")

# ── Plot 2: Dispatch + LMP overlay for the highest-net scenario ───────────────
best_row = summary.sort_values("total_net", ascending=False).iloc[0]
best_s   = S_ids.index(int(best_row["scenario_id"]))

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

ax1.plot(HOURS, lmp[best_s], color="black", linewidth=1.5, label="LMP ($/MWh)")
ax1.set_ylabel("LMP ($/MWh)", fontsize=11)
ax1.set_title(
    f"Best-Revenue Scenario: S{int(best_row['scenario_id'])} "
    f"({best_row['season'].capitalize()}, p={best_row['probability']:.3f}) — "
    f"Net ${best_row['total_net']:.2f}",
    fontsize=11
)
ax1.grid(True, alpha=0.3)
ax1.legend(fontsize=9)

ax2.bar(HOURS, pd_val[best_s], color="#e87a2a", alpha=0.8, label="Discharge (MW)")
ax2.bar(HOURS, -pc_val[best_s], color="#4e91c9", alpha=0.8, label="Charge (MW, neg)")
ax2.set_ylabel("Power (MW)", fontsize=11)
ax2.set_xlabel("Hour (EPT)", fontsize=11)
ax2.set_xlim(-0.5, 23.5)
ax2.set_xticks(range(0, T, 2))
ax2.legend(loc="upper left", fontsize=9)
ax2.grid(True, alpha=0.3)

ax2b = ax2.twinx()
ax2b.plot(HOURS, soc_val[best_s], color="purple", linewidth=1.5,
          linestyle="--", label="SOC (MWh)")
ax2b.set_ylabel("SOC (MWh)", fontsize=11, color="purple")
ax2b.tick_params(axis="y", labelcolor="purple")
ax2b.legend(loc="upper right", fontsize=9)

plt.tight_layout()
dispatch_path = os.path.join(OUT_DIR, "stochastic_dispatch.png")
fig.savefig(dispatch_path, dpi=150)
plt.close()
print(f"Saved: {dispatch_path}")

# ── Plot 3: Per-scenario net revenue bar chart ────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 4))
colors = [season_colors[scen_df.loc[i, "season"]] for i in range(S)]
ax.bar(S_ids, summary.set_index("scenario_id").loc[S_ids, "total_net"].values,
       color=colors, alpha=0.85)
for season, color in season_colors.items():
    ax.bar([], [], color=color, label=season.capitalize())
ax.axhline(0, color="black", linewidth=0.8)
ax.axhline(ev_net, color="red", linestyle="--", linewidth=1.2,
           label=f"E[Net] = ${ev_net:.3f}/day")
ax.set_xlabel("Scenario ID", fontsize=11)
ax.set_ylabel("Daily Net Revenue ($)", fontsize=11)
ax.set_title("Per-Scenario Daily Net Revenue (Revenue − Degradation Cost)", fontsize=12)
ax.legend(fontsize=9)
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
rev_path = os.path.join(OUT_DIR, "stochastic_revenue_dist.png")
fig.savefig(rev_path, dpi=150)
plt.close()
print(f"Saved: {rev_path}")

print("\nDone.")
