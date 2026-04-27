"""
fix_plots.py

Regenerates plots that had visual bugs, without re-running expensive optimizations.

Bug 1 — 25-hour x-axis: SOC plotted at range(T+1) extended x-axis to hour 24/25.
  Fix: plot SOC at hours 0-23, set xlim(-0.5, 23.5).
  Regenerates: stochastic_soc.png, stochastic_dispatch.png,
               deterministic_dispatch_s{1,10,24}.png, cvar_dispatch_comparison.png

Bug 2 — Missing $35/MWh bar in multiproduct_revenue.png:
  P_REG_VALUES in optimize_multiproduct.py skipped $35.
  Fix: solve the 10 missing MILPs (E=0.5–10 MWh at P_REG=35), append to
  multiproduct_sweep.csv, and re-generate multiproduct plots.
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cvxpy as cp

SCRIPT_DIR = os.path.dirname(__file__)
RES_DIR    = os.path.join(SCRIPT_DIR, "..", "results")
DATA_DIR   = os.path.join(SCRIPT_DIR, "..", "data", "scenarios")

# ── Shared battery parameters ─────────────────────────────────────────────────
E_MWH         = 1.0
P_MW          = 0.5
ETA_C         = 0.93
ETA_D         = 0.93
SOC_MIN       = 0.10
SOC_MAX       = 0.90
SOC_INIT      = 0.50
SOC_FINAL_MIN = 0.10
T             = 24
HOURS         = list(range(T))
C_CAPEX       = 334_000.0
N_CYCLES      = 6_000.0
C_DEG         = C_CAPEX / (2.0 * E_MWH * N_CYCLES)

season_colors = {"winter": "#4e91c9", "spring": "#5cb85c",
                 "summer": "#e87a2a", "fall":   "#9b59b6"}

scen_df   = pd.read_csv(os.path.join(DATA_DIR, "scenarios.csv"))
S_ids     = scen_df["scenario_id"].tolist()
S         = len(S_ids)
probs     = scen_df["probability"].values
hour_cols = [f"h{h:02d}" for h in HOURS]
lmp_mat   = scen_df[hour_cols].values  # (S, T)

print("=" * 60)
print("FIX PLOTS — loading existing result CSVs")
print("=" * 60)

stoch_results  = pd.read_csv(os.path.join(RES_DIR, "stochastic_results.csv"))
stoch_summary  = pd.read_csv(os.path.join(RES_DIR, "stochastic_summary.csv"))
det_cases      = pd.read_csv(os.path.join(RES_DIR, "deterministic_cases.csv"))


# =============================================================================
# BUG 1a — stochastic_soc.png (25-hour axis)
# =============================================================================
print("\n[1/7] Regenerating stochastic_soc.png ...")

fig, ax = plt.subplots(figsize=(12, 5))

for s in range(S):
    sid    = S_ids[s]
    season = scen_df.loc[s, "season"]
    sub    = stoch_results[stoch_results["scenario_id"] == sid].sort_values("hour")
    soc_v  = sub["soc_MWh"].values  # 24 end-of-hour SOC values
    alpha_val = 0.15 + 0.5 * probs[s] / probs.max()
    ax.plot(HOURS, soc_v,
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
fig.savefig(os.path.join(RES_DIR, "stochastic_soc.png"), dpi=150)
plt.close()
print("  Saved: stochastic_soc.png")


# =============================================================================
# BUG 1b — stochastic_dispatch.png (25-hour axis)
# =============================================================================
print("\n[2/7] Regenerating stochastic_dispatch.png ...")

best_row = stoch_summary.sort_values("total_net", ascending=False).iloc[0]
best_sid = int(best_row["scenario_id"])
best_s   = S_ids.index(best_sid)
sub_best = stoch_results[stoch_results["scenario_id"] == best_sid].sort_values("hour")

pd_v  = sub_best["p_discharge_MW"].values
pc_v  = sub_best["p_charge_MW"].values
soc_v = sub_best["soc_MWh"].values
lmp_v = lmp_mat[best_s]

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

ax1.plot(HOURS, lmp_v, color="black", linewidth=1.5, label="LMP ($/MWh)")
ax1.set_ylabel("LMP ($/MWh)", fontsize=11)
ax1.set_title(
    f"Best-Revenue Scenario: S{best_sid} "
    f"({best_row['season'].capitalize()}, p={best_row['probability']:.3f}) — "
    f"Net ${best_row['total_net']:.2f}",
    fontsize=11
)
ax1.grid(True, alpha=0.3)
ax1.legend(fontsize=9)

ax2.bar(HOURS, pd_v,  color="#e87a2a", alpha=0.8, label="Discharge (MW)")
ax2.bar(HOURS, -pc_v, color="#4e91c9", alpha=0.8, label="Charge (MW, neg)")
ax2.set_ylabel("Power (MW)", fontsize=11)
ax2.set_xlabel("Hour (EPT)", fontsize=11)
ax2.set_xlim(-0.5, 23.5)
ax2.set_xticks(range(0, T, 2))
ax2.legend(loc="upper left", fontsize=9)
ax2.grid(True, alpha=0.3)

ax2b = ax2.twinx()
ax2b.plot(HOURS, soc_v, color="purple", linewidth=1.5,
          linestyle="--", label="SOC (MWh)")
ax2b.set_ylabel("SOC (MWh)", fontsize=11, color="purple")
ax2b.tick_params(axis="y", labelcolor="purple")
ax2b.legend(loc="upper right", fontsize=9)

plt.tight_layout()
fig.savefig(os.path.join(RES_DIR, "stochastic_dispatch.png"), dpi=150)
plt.close()
print("  Saved: stochastic_dispatch.png")


# =============================================================================
# BUG 1c — deterministic_dispatch_s{1,10,24}.png (25-hour axis)
# =============================================================================
print("\n[3-5/7] Regenerating deterministic_dispatch_s{1,10,24}.png ...")

TEST_CASES = [
    (10, "High-Spread", "Winter S10", "$118.9/MWh"),
    (1,  "Low-Spread",  "Winter S1",  "$8.6/MWh"),
    (24, "Med-Spread",  "Summer S24", "$51.8/MWh"),
]

for sid, spread_label, scenario_label, spread_str in TEST_CASES:
    sub = det_cases[det_cases["scenario_id"] == sid].sort_values("hour")
    if sub.empty:
        print(f"  WARNING: no data for scenario {sid} in deterministic_cases.csv")
        continue

    price = lmp_mat[S_ids.index(sid)]
    pd_v  = sub["p_discharge_MW"].values
    pc_v  = sub["p_charge_MW"].values
    soc_v = sub["soc_MWh"].values
    uc_v  = sub["u_charge"].values
    ud_v  = sub["u_discharge"].values
    net   = float(sub["net_revenue"].iloc[0])
    rev   = float((price * pd_v - price * pc_v).sum())
    deg   = float(C_DEG * (pd_v + pc_v).sum())
    spread = price.max() - price.min()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

    ax1.plot(HOURS, price, color="black", linewidth=1.8, label="LMP ($/MWh)")
    ax1.axhline(C_DEG, color="gray", linestyle=":", linewidth=1.0,
                label=f"C_DEG = ${C_DEG:.2f}/MWh")
    clip_ceil = scen_df[hour_cols].values.max()
    for t in HOURS:
        if round(uc_v[t]) == 1:
            ax1.axvspan(t - 0.5, t + 0.5, color="#4e91c9", alpha=0.15)
        elif round(ud_v[t]) == 1:
            ax1.axvspan(t - 0.5, t + 0.5, color="#e87a2a", alpha=0.15)
    # annotate clip ceiling if this scenario hits it
    if price.max() >= clip_ceil - 0.1:
        ax1.axhline(clip_ceil, color="red", linestyle="--", linewidth=0.9, alpha=0.7,
                    label=f"p99 clip ceiling = ${clip_ceil:.2f}/MWh")
        ax1.annotate("Prices clipped at\np99 = $152.91/MWh\n(scenario centroid\nhits ceiling)",
                     xy=(HOURS[price.argmax()] + 2, clip_ceil * 0.99),
                     fontsize=7.5, color="red", va="top")
    ax1.set_ylabel("LMP ($/MWh)", fontsize=11)
    ax1.set_title(
        f"Deterministic MILP Dispatch — {spread_label}  ({scenario_label},  spread=${spread:.1f}/MWh)\n"
        f"Net=${net:.2f}  |  Gross revenue=${rev:.2f}  |  Degradation cost=${deg:.2f}",
        fontsize=11
    )
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(-0.5, 23.5)
    ax1.set_xticks(range(0, T, 2))

    ax2.bar(HOURS,  pd_v, color="#e87a2a", alpha=0.8, label="Discharging (MW) — selling to grid")
    ax2.bar(HOURS, -pc_v, color="#4e91c9", alpha=0.8, label="Charging (MW) — buying from grid")
    ax2.set_ylabel("Power (MW)", fontsize=11)
    ax2.set_xlabel("Hour (EPT)", fontsize=11)
    ax2.set_xlim(-0.5, 23.5)
    ax2.set_xticks(range(0, T, 2))
    ax2.legend(loc="upper left", fontsize=9)
    ax2.grid(True, alpha=0.3)

    ax2b = ax2.twinx()
    ax2b.plot(HOURS, soc_v, color="purple", linewidth=1.8,
              linestyle="--", label="State of charge (MWh)")
    ax2b.axhline(SOC_MIN * E_MWH, color="red",   linestyle=":", linewidth=0.9, alpha=0.7)
    ax2b.axhline(SOC_MAX * E_MWH, color="green", linestyle=":", linewidth=0.9, alpha=0.7)
    ax2b.set_ylabel("State of Charge (MWh)", fontsize=11, color="purple")
    ax2b.tick_params(axis="y", labelcolor="purple")
    ax2b.set_ylim(0, E_MWH * 1.05)
    ax2b.legend(loc="upper right", fontsize=9)

    plt.tight_layout()
    fname = f"deterministic_dispatch_s{sid}.png"
    fig.savefig(os.path.join(RES_DIR, fname), dpi=150)
    plt.close()
    print(f"  Saved: {fname}")


# =============================================================================
# BUG 1d — cvar_dispatch_comparison.png (25-hour axis)
# Re-solve unconstrained + most constrained two-stage MILPs (alpha=0.95)
# =============================================================================
print("\n[6/7] Regenerating cvar_dispatch_comparison.png (re-solving 2 MILPs) ...")

ALPHA = 0.95

def solve_two_stage(alpha, cvar_budget=None):
    p_c = cp.Variable(T, nonneg=True)
    p_d = cp.Variable(T, nonneg=True)
    soc = cp.Variable(T, nonneg=True)
    u_c = cp.Variable(T, boolean=True)
    u_d = cp.Variable(T, boolean=True)
    eta = cp.Variable()
    z   = cp.Variable(S, nonneg=True)

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
        constraints.append(soc[t] == soc[t-1] + ETA_C * p_c[t] - (1.0 / ETA_D) * p_d[t])

    deg_cost = C_DEG * (cp.sum(p_d) + cp.sum(p_c))
    arb_rev  = lmp_mat @ (p_d - p_c)
    net_rev  = arb_rev - deg_cost

    constraints.append(z >= eta - net_rev)
    cvar_expr = eta - (1.0 / (1.0 - alpha)) * (probs @ z)

    if cvar_budget is not None:
        constraints.append(cvar_expr >= cvar_budget)

    ev_net = probs @ net_rev
    prob_model = cp.Problem(cp.Maximize(ev_net), constraints)
    prob_model.solve(solver=cp.HIGHS, verbose=False, time_limit=60)

    if prob_model.status not in ("optimal", "optimal_inaccurate") or prob_model.value is None:
        return None

    cvar_val = float(eta.value) - (1.0 / (1.0 - alpha)) * float(probs @ z.value)
    return {
        "ev_net": float(prob_model.value),
        "cvar":   cvar_val,
        "pc":     p_c.value,
        "pd":     p_d.value,
        "soc":    soc.value,
    }

unc_res  = solve_two_stage(ALPHA)
# Most constrained: push CVaR budget to just below the point where E[Net] goes negative
cons_res = solve_two_stage(ALPHA, cvar_budget=float(unc_res["cvar"]) + 4.0) if unc_res else None

if unc_res and cons_res:
    hours = np.arange(T)
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

    pairs = [
        (axes[0], unc_res,  f"Unconstrained EV  (E[Net]=${unc_res['ev_net']:.2f}/day)", "#4e91c9"),
        (axes[1], cons_res, f"CVaR-Constrained  (E[Net]=${cons_res['ev_net']:.2f}/day)", "#c0392b"),
    ]
    for ax, res, label, color in pairs:
        ax.bar(hours,  res["pd"],  color="#e87a2a", alpha=0.8, label="Discharge (MW)")
        ax.bar(hours, -res["pc"],  color=color,     alpha=0.8, label="Charge (MW, neg)")
        ax.set_xlim(-0.5, 23.5)
        ax.set_xticks(range(0, T, 2))
        ax2 = ax.twinx()
        ax2.plot(hours, res["soc"], color="purple", linewidth=1.5,
                 linestyle="--", label="SOC (MWh)")
        ax2.set_ylabel("SOC (MWh)", color="purple", fontsize=10)
        ax2.tick_params(axis="y", labelcolor="purple")
        ax.set_title(label, fontsize=10)
        ax.set_ylabel("Power (MW)", fontsize=10)
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(True, alpha=0.3)
        ax2.legend(loc="upper right", fontsize=8)

    axes[1].set_xlabel("Hour (EPT)", fontsize=11)
    plt.suptitle("Dispatch Comparison: Unconstrained vs CVaR-Constrained (alpha=0.95)", fontsize=11)
    plt.tight_layout()
    fig.savefig(os.path.join(RES_DIR, "cvar_dispatch_comparison.png"), dpi=150)
    plt.close()
    print("  Saved: cvar_dispatch_comparison.png")
else:
    print("  WARNING: CVaR solve failed, skipping cvar_dispatch_comparison.png")


# =============================================================================
# BUG 2 — missing $35/MWh bar in multiproduct_revenue.png
# Solve 10 MILPs (P_REG=35, E=0.5-10 MWh) and append to multiproduct_sweep.csv
# =============================================================================
print("\n[7/7] Adding missing P_REG=$35 data to multiproduct sweep ...")

# Shared multiproduct parameters
C_RATE             = 0.5
CAPEX_PER_KWH      = 334.0
FIXED_CAPEX        = 75_000.0
FIXED_OM_PER_KW_YR = 10.0
ASSET_LIFE         = 15
DISCOUNT_RATE      = 0.07
MILEAGE_RATIO      = 3.0
DOD_RATIO          = 8.0
C_DEG_BASE         = (CAPEX_PER_KWH * 1000.0) / (2.0 * N_CYCLES)
C_DEG_REG          = C_DEG_BASE / DOD_RATIO
ANNUITY            = sum(1.0 / (1.0 + DISCOUNT_RATE) ** y for y in range(1, ASSET_LIFE + 1))

E_VALUES    = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]
P_REG_NEW   = 35.0

sweep_path = os.path.join(RES_DIR, "multiproduct_sweep.csv")
sweep_df   = pd.read_csv(sweep_path)

# Check if $35 rows already present
if 35.0 in sweep_df["P_REG"].values:
    print("  P_REG=35 already in sweep CSV — skipping solves.")
else:
    def solve_multiproduct_patch(E_mwh, P_REG, time_limit=90):
        P_MW_bat = C_RATE * E_mwh
        regd_net = P_REG - C_DEG_REG * MILEAGE_RATIO
        r   = cp.Variable(T, nonneg=True)
        p_c = cp.Variable((S, T), nonneg=True)
        p_d = cp.Variable((S, T), nonneg=True)
        soc = cp.Variable((S, T), nonneg=True)
        u_c = cp.Variable((S, T), boolean=True)
        u_d = cp.Variable((S, T), boolean=True)

        ones_S = np.ones((S, 1))
        r_bc   = ones_S @ cp.reshape(r, (1, T))

        constraints = [
            r <= P_MW_bat,
            p_c <= P_MW_bat * u_c,
            p_d <= P_MW_bat * u_d,
            u_c + u_d <= 1,
            p_c + r_bc <= P_MW_bat,
            p_d + r_bc <= P_MW_bat,
            soc >= SOC_MIN * E_mwh,
            soc <= SOC_MAX * E_mwh,
            soc >= SOC_MIN * E_mwh + r_bc / ETA_D,
            soc <= SOC_MAX * E_mwh - r_bc * ETA_C,
            soc[:, 0] == SOC_INIT * E_mwh + ETA_C * p_c[:, 0] - (1.0 / ETA_D) * p_d[:, 0],
            soc[:, T-1] >= SOC_FINAL_MIN * E_mwh,
        ]
        for t in range(1, T):
            constraints.append(
                soc[:, t] == soc[:, t-1] + ETA_C * p_c[:, t] - (1.0 / ETA_D) * p_d[:, t]
            )

        net_price   = lmp_mat - C_DEG_BASE
        charge_cost = lmp_mat + C_DEG_BASE
        arb_obj = probs @ cp.sum(
            cp.multiply(net_price, p_d) - cp.multiply(charge_cost, p_c), axis=1
        )
        objective = cp.Maximize(regd_net * cp.sum(r) + arb_obj)
        prob_model = cp.Problem(objective, constraints)
        prob_model.solve(solver=cp.HIGHS, verbose=False, time_limit=time_limit)

        if prob_model.status not in ("optimal", "optimal_inaccurate") or prob_model.value is None:
            return None

        r_arr  = r.value if r.value is not None else np.zeros(T)
        pc_arr = p_c.value
        pd_arr = p_d.value

        total_obj   = float(prob_model.value)
        reg_day     = float(regd_net * np.sum(r_arr))
        arb_gross   = float(probs @ np.sum(lmp_mat * pd_arr - lmp_mat * pc_arr, axis=1))
        arb_deg     = float(probs @ np.sum(C_DEG_BASE * (pd_arr + pc_arr), axis=1))
        arb_net_day = arb_gross - arb_deg
        return {
            "total_net_day": total_obj,
            "reg_net_day":   reg_day,
            "arb_gross_day": arb_gross,
            "arb_deg_day":   arb_deg,
            "arb_net_day":   arb_net_day,
            "r_mean_mw":     float(np.mean(r_arr)),
            "r_max_mw":      float(np.max(r_arr)),
        }

    new_rows = []
    for i, E in enumerate(E_VALUES):
        P_MW_bat = C_RATE * E
        regd_net = P_REG_NEW - C_DEG_REG * MILEAGE_RATIO
        print(f"  [{i+1}/{len(E_VALUES)}] E={E:.1f} MWh  P_REG=$35 ...", end=" ", flush=True)
        res = solve_multiproduct_patch(E, P_REG_NEW)
        if res is None:
            print("INFEASIBLE/TIMEOUT")
            continue
        annual_total = res["total_net_day"] * 365.0
        annual_reg   = res["reg_net_day"]   * 365.0
        annual_arb   = res["arb_net_day"]   * 365.0
        capex_val    = FIXED_CAPEX + CAPEX_PER_KWH * E * 1000.0
        om_val       = FIXED_OM_PER_KW_YR * C_RATE * E * 1000.0
        npv_val      = (annual_total - om_val) * ANNUITY - capex_val
        breakeven    = capex_val / ANNUITY + om_val
        print(f"reg=${annual_reg:,.0f}/yr  arb=${annual_arb:,.0f}/yr  NPV=${npv_val:,.0f}")
        new_rows.append({
            "E_MWh":             E,
            "P_MW":              round(P_MW_bat, 3),
            "P_REG":             P_REG_NEW,
            "regd_net_per_mwh":  round(regd_net, 4),
            "r_mean_mw":         round(res["r_mean_mw"], 4),
            "r_max_mw":          round(res["r_max_mw"], 4),
            "total_net_day":     round(res["total_net_day"], 4),
            "reg_net_day":       round(res["reg_net_day"], 4),
            "arb_net_day":       round(res["arb_net_day"], 4),
            "annual_total_$":    round(annual_total, 2),
            "annual_reg_$":      round(annual_reg, 2),
            "annual_arb_$":      round(annual_arb, 2),
            "annual_om_$":       round(om_val, 0),
            "capex_$":           round(capex_val, 0),
            "npv_$":             round(npv_val, 2),
            "breakeven_$":       round(breakeven, 0),
        })

    if new_rows:
        new_df   = pd.DataFrame(new_rows)
        sweep_df = pd.concat([sweep_df, new_df], ignore_index=True)
        sweep_df = sweep_df.sort_values(["P_REG", "E_MWh"]).reset_index(drop=True)
        sweep_df.to_csv(sweep_path, index=False)
        print(f"  Appended {len(new_rows)} rows to {sweep_path}")

# ── Re-generate multiproduct plots with complete data ─────────────────────────
P_REG_VALUES = sorted(sweep_df["P_REG"].unique())
colors_map   = plt.cm.plasma(np.linspace(0.08, 0.92, len(P_REG_VALUES)))

# Plot 1: NPV vs Capacity
fig, ax = plt.subplots(figsize=(11, 6))
for i, P_REG in enumerate(P_REG_VALUES):
    sub = sweep_df[sweep_df["P_REG"] == P_REG].sort_values("E_MWh")
    if sub.empty:
        continue
    label = (f"P_REG = ${P_REG:.0f}/MW-h"
             if P_REG > 0 else "Arbitrage only  (P_REG = $0)")
    ls = "--" if P_REG == 0 else "-"
    lw = 1.5  if P_REG == 0 else 2.0
    ax.plot(sub["E_MWh"], sub["npv_$"] / 1e6, marker="o", markersize=4,
            color=colors_map[i], linewidth=lw, linestyle=ls, label=label)

ax.axhline(0, color="black", linewidth=1.0, linestyle=":", label="NPV = 0 (break-even)")
e_uniq = sweep_df["E_MWh"].unique()
ax.fill_between(sorted(e_uniq), 0, 5.0, alpha=0.06, color="green", label="Profitable region")
ax.set_xlabel("Battery Capacity (MWh)", fontsize=12)
ax.set_ylabel("NPV ($M)", fontsize=12)
ax.set_title(
    "Project NPV vs Battery Capacity: Energy Arbitrage + PJM RegD Co-Optimization\n"
    f"CapEx=${CAPEX_PER_KWH}/kWh + ${FIXED_CAPEX/1e3:.0f}k fixed  |  "
    f"O&M=${FIXED_OM_PER_KW_YR}/kW-yr  |  "
    f"Mileage={MILEAGE_RATIO}x  |  "
    f"C_DEG_reg=${C_DEG_REG:.2f}/MWh  |  "
    f"{ASSET_LIFE}yr @ {DISCOUNT_RATE*100:.0f}% WACC",
    fontsize=10
)
ax.legend(fontsize=9, loc="lower left", ncol=2)
ax.grid(True, alpha=0.3)
plt.tight_layout()
fig.savefig(os.path.join(RES_DIR, "multiproduct_npv.png"), dpi=150)
plt.close()
print("  Saved: multiproduct_npv.png")

# Plot 2: Revenue stack + NPV vs P_REG at 1 MWh
sub1 = sweep_df[sweep_df["E_MWh"] == 1.0].sort_values("P_REG")
if not sub1.empty:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    be_1mwh = float(sub1["breakeven_$"].iloc[0]) / 1e3
    ax.bar(sub1["P_REG"], sub1["annual_arb_$"] / 1e3,
           color="#5cb85c", alpha=0.85, label="Arbitrage net revenue ($k/yr)")
    ax.bar(sub1["P_REG"], sub1["annual_reg_$"] / 1e3,
           bottom=sub1["annual_arb_$"] / 1e3,
           color="#4e91c9", alpha=0.85, label="RegD net revenue ($k/yr)")
    ax.axhline(be_1mwh, color="red", linewidth=2.0, linestyle="--",
               label=f"Break-even = ${be_1mwh:.0f}k/yr")
    ax.set_xlabel("RegD Clearing Price ($/MW-h)", fontsize=11)
    ax.set_ylabel("Annual Net Revenue ($k/yr)", fontsize=11)
    ax.set_title("(A) Revenue Stack vs Break-Even\n1 MWh / 0.5 MW LFP battery",
                 fontsize=11, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    ax.tick_params(labelsize=9)

    ax = axes[1]
    npv_k      = sub1["npv_$"] / 1e3
    profitable = npv_k > 0
    ax.plot(sub1["P_REG"], npv_k, marker="o", color="#e87a2a", linewidth=2.2, markersize=6)
    ax.axhline(0, color="black", linewidth=1.0, linestyle="--", label="NPV = 0")
    if profitable.any():
        ax.fill_between(sub1["P_REG"], npv_k, 0,
                        where=profitable, alpha=0.18, color="green",
                        label="Profitable (NPV > 0)")
    ax.fill_between(sub1["P_REG"], npv_k, 0,
                    where=~profitable, alpha=0.12, color="red",
                    label="Unprofitable (NPV < 0)")
    if profitable.any() and (~profitable).any():
        x_arr = sub1["P_REG"].values.astype(float)
        y_arr = npv_k.values.astype(float)
        for k in range(len(y_arr) - 1):
            if y_arr[k] <= 0 < y_arr[k + 1]:
                be_price = x_arr[k] + (0 - y_arr[k]) / (y_arr[k+1] - y_arr[k]) * (x_arr[k+1] - x_arr[k])
                ax.axvline(be_price, color="green", linewidth=1.4, linestyle=":",
                           label=f"Break-even ~${be_price:.1f}/MW-h")
                break
    ax.set_xlabel("RegD Clearing Price ($/MW-h)", fontsize=11)
    ax.set_ylabel("NPV ($k)", fontsize=11)
    ax.set_title("(B) NPV vs RegD Clearing Price\n1 MWh / 0.5 MW  |  15yr @ 7% WACC",
                 fontsize=11, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.tick_params(labelsize=9)

    fig.suptitle(
        "Multi-Product BESS: Energy Arbitrage + PJM RegD Co-Optimization\n"
        f"C_DEG_arb=${C_DEG_BASE:.2f}/MWh  |  C_DEG_reg=${C_DEG_REG:.2f}/MWh  "
        f"(DoD discount {DOD_RATIO:.0f}x)  |  Mileage={MILEAGE_RATIO}x",
        fontsize=11, fontweight="bold", y=1.02
    )
    plt.tight_layout()
    fig.savefig(os.path.join(RES_DIR, "multiproduct_revenue.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: multiproduct_revenue.png")

print("\nAll bugs fixed. Run visualize_all.py to regenerate figure_1 and figure_2.")
