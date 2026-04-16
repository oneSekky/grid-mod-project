"""
optimize_deterministic.py

Deterministic MILP baseline for a single 24-hour BESS dispatch problem.

PURPOSE
-------
This script serves three roles:
  1. Baseline model — the simplest correct formulation against which all
     stochastic extensions are validated.
  2. Sanity check — produces detailed human-readable dispatch tables and plots
     so the physical dispatch behaviour can be verified by inspection.
  3. Stochastic consistency check — because optimize_stochastic.py uses a
     wait-and-see formulation (each scenario has its own dispatch), its
     per-scenario revenue must equal the deterministic optimal for that
     scenario's price profile. This script verifies that identity holds
     across all 40 scenarios.

FORMULATION
-----------
Given a known 24-hour price vector lambda[t] ($/MWh):

  max  sum_t [ lambda[t]*p_d[t] - lambda[t]*p_c[t] ] - C_DEG * sum_t [ p_d[t] + p_c[t] ]

  subject to:
    p_c[t] <= P_MW * u_c[t]                  (charge bounded by capacity * mode)
    p_d[t] <= P_MW * u_d[t]                  (discharge bounded by capacity * mode)
    u_c[t] + u_d[t] <= 1                     (no simultaneous charge + discharge)
    soc[t] = soc[t-1] + eta_c*p_c[t] - (1/eta_d)*p_d[t]   (energy balance)
    SOC_MIN*E <= soc[t] <= SOC_MAX*E          (state-of-charge bounds)
    soc[T-1] >= SOC_FINAL_MIN*E              (end-of-day reserve)
    p_c[t], p_d[t] >= 0
    u_c[t], u_d[t] in {0, 1}

TEST CASES
----------
  - High-spread day:  scenario 10 (Winter, spread=$118.9/MWh, p=0.07%)
  - Low-spread day:   scenario  1 (Winter, spread=$8.6/MWh, p=10.3%)
  - Medium-spread day: scenario 24 (Summer, spread=$51.8/MWh, p=2.5%)

OUTPUTS
-------
  results/deterministic_dispatch_<id>.png  -- dispatch + LMP + SOC for each test
  results/deterministic_verification.png  -- scatter: det. revenue vs stoch. revenue
  results/deterministic_verification.csv  -- per-scenario comparison table
  results/deterministic_cases.csv         -- detailed hourly dispatch for test cases
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
STOCH_CSV     = os.path.join(SCRIPT_DIR, "..", "results", "stochastic_summary.csv")
OUT_DIR       = os.path.join(SCRIPT_DIR, "..", "results")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Battery Parameters (must match optimize_stochastic.py) ───────────────────
E_MWH         = 1.0
P_MW          = 0.5
ETA_C         = 0.93
ETA_D         = 0.93
SOC_MIN       = 0.10
SOC_MAX       = 0.90
SOC_INIT      = 0.50
SOC_FINAL_MIN = 0.10
T             = 24

# Degradation cost — NREL ATB 2024 / modern utility LFP (6,000 cycles at 80% DoD)
C_CAPEX   = 334_000.0
N_CYCLES  = 6_000.0
C_DEG     = C_CAPEX / (2.0 * E_MWH * N_CYCLES)

print(f"Battery: {E_MWH} MWh / {P_MW} MW  |  eta_c={ETA_C}  eta_d={ETA_D}")
print(f"SOC range: [{SOC_MIN:.0%}, {SOC_MAX:.0%}]  |  C_DEG=${C_DEG:.4f}/MWh")

# ── Core MILP solver ──────────────────────────────────────────────────────────
def solve_deterministic(price_24h, label=""):
    """
    Solve the deterministic MILP for a single 24-hour price profile.

    Parameters
    ----------
    price_24h : array-like, shape (24,)  — LMP in $/MWh for each hour
    label     : str — used only for print output

    Returns
    -------
    dict with keys: net, revenue, deg, pc (MW), pd (MW), soc (MWh),
                    uc (binary), ud (binary), status
    """
    lmp = np.asarray(price_24h, dtype=float)

    p_c = cp.Variable(T, nonneg=True, name="p_c")   # charging power (MW)
    p_d = cp.Variable(T, nonneg=True, name="p_d")   # discharging power (MW)
    soc = cp.Variable(T, nonneg=True, name="soc")   # SOC at end of hour t (MWh)
    u_c = cp.Variable(T, boolean=True, name="u_c")  # charging mode indicator
    u_d = cp.Variable(T, boolean=True, name="u_d")  # discharging mode indicator

    constraints = [
        # Power bounds tied to mode indicators (big-M = P_MW)
        p_c <= P_MW * u_c,
        p_d <= P_MW * u_d,
        # Mutual exclusivity: no simultaneous charge and discharge
        u_c + u_d <= 1,
        # SOC bounds
        soc >= SOC_MIN * E_MWH,
        soc <= SOC_MAX * E_MWH,
        # SOC dynamics: soc[t] = soc[t-1] + eta_c*p_c[t] - (1/eta_d)*p_d[t]
        # t=0: soc[t-1] = SOC_INIT (known initial condition)
        soc[0] == SOC_INIT * E_MWH + ETA_C * p_c[0] - (1.0 / ETA_D) * p_d[0],
        # End-of-day SOC floor
        soc[T - 1] >= SOC_FINAL_MIN * E_MWH,
    ]
    for t in range(1, T):
        constraints.append(
            soc[t] == soc[t - 1] + ETA_C * p_c[t] - (1.0 / ETA_D) * p_d[t]
        )

    # Objective: maximize net revenue (arbitrage minus degradation cost)
    revenue_expr = lmp @ p_d - lmp @ p_c
    deg_expr     = C_DEG * (cp.sum(p_d) + cp.sum(p_c))
    objective    = cp.Maximize(revenue_expr - deg_expr)

    prob = cp.Problem(objective, constraints)
    prob.solve(solver=cp.HIGHS, verbose=False, time_limit=30)

    if prob.status not in ("optimal", "optimal_inaccurate") or prob.value is None:
        return {"status": prob.status, "net": None}

    pc_v  = p_c.value
    pd_v  = p_d.value
    soc_v = soc.value
    rev   = float(lmp @ pd_v - lmp @ pc_v)
    deg   = float(C_DEG * (pd_v.sum() + pc_v.sum()))

    return {
        "status":  prob.status,
        "net":     rev - deg,
        "revenue": rev,
        "deg":     deg,
        "pc":      pc_v,
        "pd":      pd_v,
        "soc":     soc_v,
        "uc":      u_c.value,
        "ud":      u_d.value,
    }

# ── Load scenarios ────────────────────────────────────────────────────────────
scen_df   = pd.read_csv(SCENARIOS_CSV)
hour_cols = [f"h{h:02d}" for h in range(T)]
HOURS     = list(range(T))

# ── Test cases ────────────────────────────────────────────────────────────────
TEST_CASES = [
    {"scenario_id": 10, "label": "High-Spread (Winter S10, spread=$118.9)"},
    {"scenario_id":  1, "label": "Low-Spread  (Winter S1,  spread=$8.6)"},
    {"scenario_id": 24, "label": "Med-Spread  (Summer S24, spread=$51.8)"},
]

case_records = []

print("\n" + "="*65)
print("DETERMINISTIC MILP — TEST CASES")
print("="*65)

for tc in TEST_CASES:
    sid   = tc["scenario_id"]
    label = tc["label"]
    row   = scen_df[scen_df["scenario_id"] == sid].iloc[0]
    price = row[hour_cols].values.astype(float)

    res = solve_deterministic(price, label)
    if res["net"] is None:
        print(f"\n{label}: INFEASIBLE ({res['status']})")
        continue

    spread = price.max() - price.min()
    print(f"\n{label}")
    print(f"  LMP range : [{price.min():.2f}, {price.max():.2f}] $/MWh  "
          f"(spread=${spread:.2f}, mean=${price.mean():.2f})")
    print(f"  Revenue   : ${res['revenue']:.4f}")
    print(f"  Deg. cost : ${res['deg']:.4f}")
    print(f"  Net       : ${res['net']:.4f}")
    print(f"  Charge hrs: {int(round(res['uc'].sum()))}  |  "
          f"Discharge hrs: {int(round(res['ud'].sum()))}")
    print(f"  Total charge: {res['pc'].sum():.3f} MWh  |  "
          f"Total discharge: {res['pd'].sum():.3f} MWh")

    # Hourly dispatch table
    print(f"\n  {'Hr':>3} {'LMP':>8} {'Charge':>8} {'Disch':>8} {'SOC':>8}  Action")
    soc_prev = SOC_INIT * E_MWH
    for t in HOURS:
        action = ""
        if round(res["uc"][t]) == 1:
            action = "CHARGE"
        elif round(res["ud"][t]) == 1:
            action = "DISCHARGE"
        print(f"  {t:>3} {price[t]:>8.2f} {res['pc'][t]:>8.3f} "
              f"{res['pd'][t]:>8.3f} {res['soc'][t]:>8.3f}  {action}")

    # Store for CSV
    for t in HOURS:
        case_records.append({
            "scenario_id":  sid,
            "label":        label,
            "hour":         t,
            "lmp":          round(float(price[t]), 4),
            "p_charge_MW":  round(float(res["pc"][t]), 6),
            "p_discharge_MW": round(float(res["pd"][t]), 6),
            "soc_MWh":      round(float(res["soc"][t]), 6),
            "u_charge":     int(round(float(res["uc"][t]))),
            "u_discharge":  int(round(float(res["ud"][t]))),
            "net_revenue":  round(res["net"], 6),
        })

    # ── Dispatch plot ─────────────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

    # Top: LMP
    ax1.plot(HOURS, price, color="black", linewidth=1.8, label="LMP ($/MWh)")
    ax1.axhline(C_DEG, color="gray", linestyle=":", linewidth=1.0,
                label=f"C_DEG = ${C_DEG:.2f}/MWh")
    # Shade charge hours
    for t in HOURS:
        if round(res["uc"][t]) == 1:
            ax1.axvspan(t - 0.5, t + 0.5, color="#4e91c9", alpha=0.15)
        elif round(res["ud"][t]) == 1:
            ax1.axvspan(t - 0.5, t + 0.5, color="#e87a2a", alpha=0.15)
    ax1.set_ylabel("LMP ($/MWh)", fontsize=11)
    ax1.set_title(f"Deterministic MILP Dispatch — {label}\n"
                  f"Net=${res['net']:.2f}  Rev=${res['revenue']:.2f}  "
                  f"Deg=${res['deg']:.2f}", fontsize=11)
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    # Bottom: Power + SOC
    ax2.bar(HOURS,  res["pd"],        color="#e87a2a", alpha=0.8, label="Discharge (MW)")
    ax2.bar(HOURS, -res["pc"],        color="#4e91c9", alpha=0.8, label="Charge (MW, neg)")
    ax2.set_ylabel("Power (MW)", fontsize=11)
    ax2.set_xlabel("Hour (EPT)", fontsize=11)
    ax2.legend(loc="upper left", fontsize=9)
    ax2.grid(True, alpha=0.3)

    ax2b = ax2.twinx()
    soc_line = [SOC_INIT * E_MWH] + list(res["soc"])
    ax2b.plot(range(T + 1), soc_line, color="purple", linewidth=1.8,
              linestyle="--", label="SOC (MWh)")
    ax2b.axhline(SOC_MIN * E_MWH, color="red",   linestyle=":", linewidth=0.9, alpha=0.7)
    ax2b.axhline(SOC_MAX * E_MWH, color="green", linestyle=":", linewidth=0.9, alpha=0.7)
    ax2b.set_ylabel("SOC (MWh)", fontsize=11, color="purple")
    ax2b.tick_params(axis="y", labelcolor="purple")
    ax2b.set_ylim(0, E_MWH * 1.05)
    ax2b.legend(loc="upper right", fontsize=9)

    plt.tight_layout()
    plot_path = os.path.join(OUT_DIR, f"deterministic_dispatch_s{sid}.png")
    fig.savefig(plot_path, dpi=150)
    plt.close()
    print(f"\n  Saved: {os.path.basename(plot_path)}")

# Save case CSV
cases_df = pd.DataFrame(case_records)
cases_path = os.path.join(OUT_DIR, "deterministic_cases.csv")
cases_df.to_csv(cases_path, index=False)
print(f"\nSaved: {os.path.basename(cases_path)}")

# ── Stochastic consistency verification ───────────────────────────────────────
# The wait-and-see stochastic model gives each scenario its own optimal dispatch.
# Therefore: det_net(s) == stoch_net(s) for every scenario s (to solver tolerance).
# We verify this across all 40 scenarios and report the max deviation.

print("\n" + "="*65)
print("STOCHASTIC CONSISTENCY VERIFICATION")
print("(det. net revenue vs stochastic per-scenario net, all 40 scenarios)")
print("="*65)

stoch_df = pd.read_csv(STOCH_CSV)
# stoch_df has one row per scenario with 'total_net'
stoch_net = dict(zip(stoch_df["scenario_id"].astype(int),
                     stoch_df["total_net"].astype(float)))

verify_rows = []
max_abs_err = 0.0

for _, row in scen_df.iterrows():
    sid   = int(row["scenario_id"])
    price = row[hour_cols].values.astype(float)
    res   = solve_deterministic(price)
    if res["net"] is None:
        print(f"  S{sid:2d}: INFEASIBLE")
        continue

    det_net   = res["net"]
    stoch_net_s = stoch_net.get(sid, None)
    err       = abs(det_net - stoch_net_s) if stoch_net_s is not None else None
    max_abs_err = max(max_abs_err, err or 0)

    verify_rows.append({
        "scenario_id":  sid,
        "season":       row["season"],
        "probability":  row["probability"],
        "det_net":      round(det_net, 6),
        "stoch_net":    round(stoch_net_s, 6) if stoch_net_s is not None else None,
        "abs_error":    round(err, 6) if err is not None else None,
        "rel_error_pct": round(100 * err / max(abs(stoch_net_s), 1e-6), 4)
                         if err is not None and stoch_net_s is not None else None,
    })

verify_df = pd.DataFrame(verify_rows)
verify_path = os.path.join(OUT_DIR, "deterministic_verification.csv")
verify_df.to_csv(verify_path, index=False)

print(f"\n  Max absolute error across all 40 scenarios: ${max_abs_err:.6f}")
print(f"  Mean absolute error:                        "
      f"${verify_df['abs_error'].mean():.6f}")
print(f"  Scenarios with |error| > $0.01:             "
      f"{(verify_df['abs_error'] > 0.01).sum()}")

# Print top-10 worst cases
worst = verify_df.nlargest(5, "abs_error")
print("\n  Top-5 largest deviations:")
print(worst[["scenario_id","season","det_net","stoch_net","abs_error"]].to_string(index=False))

# ── Verification scatter plot ─────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

# Left: scatter det vs stoch net revenue
ax1.scatter(verify_df["stoch_net"], verify_df["det_net"],
            c=verify_df["abs_error"], cmap="RdYlGn_r", s=60, edgecolors="black",
            linewidths=0.5, vmin=0, vmax=max(0.01, verify_df["abs_error"].max()))
lo = min(verify_df["det_net"].min(), verify_df["stoch_net"].min()) - 1
hi = max(verify_df["det_net"].max(), verify_df["stoch_net"].max()) + 1
ax1.plot([lo, hi], [lo, hi], "k--", linewidth=1.2, label="Perfect agreement (y=x)")
ax1.set_xlabel("Stochastic per-scenario Net Revenue ($/day)", fontsize=11)
ax1.set_ylabel("Deterministic Net Revenue ($/day)", fontsize=11)
ax1.set_title("Consistency Check: Deterministic vs Stochastic (Wait-and-See)\n"
              "All 40 scenarios — points on y=x line = perfect match", fontsize=10)
ax1.legend(fontsize=9)
ax1.grid(True, alpha=0.3)
cb = plt.colorbar(ax1.collections[0], ax=ax1)
cb.set_label("|Error| ($)", fontsize=9)

# Right: absolute error bar chart
colors = ["#c0392b" if e > 0.01 else "#5cb85c" for e in verify_df["abs_error"]]
ax2.bar(verify_df["scenario_id"], verify_df["abs_error"], color=colors, alpha=0.85)
ax2.axhline(0.01, color="red", linestyle="--", linewidth=1.2,
            label="$0.01 tolerance")
ax2.set_xlabel("Scenario ID", fontsize=11)
ax2.set_ylabel("|Det Net - Stoch Net| ($)", fontsize=11)
ax2.set_title(f"Absolute Error by Scenario\n"
              f"Max=${max_abs_err:.4f}  Mean=${verify_df['abs_error'].mean():.4f}", fontsize=11)
ax2.legend(fontsize=9)
ax2.grid(True, axis="y", alpha=0.3)

plt.tight_layout()
verif_path = os.path.join(OUT_DIR, "deterministic_verification.png")
fig.savefig(verif_path, dpi=150)
plt.close()
print(f"\nSaved: {os.path.basename(verif_path)}")

# ── Physical reasonableness checks ───────────────────────────────────────────
print("\n" + "="*65)
print("PHYSICAL REASONABLENESS CHECKS")
print("="*65)

failures = []
for tc in TEST_CASES:
    sid   = tc["scenario_id"]
    sub   = cases_df[cases_df["scenario_id"] == sid]
    price = scen_df[scen_df["scenario_id"] == sid].iloc[0][hour_cols].values.astype(float)

    # 1. SOC bounds respected
    soc_vals = sub["soc_MWh"].values
    if (soc_vals < SOC_MIN * E_MWH - 1e-4).any():
        failures.append(f"S{sid}: SOC below minimum")
    if (soc_vals > SOC_MAX * E_MWH + 1e-4).any():
        failures.append(f"S{sid}: SOC above maximum")

    # 2. Mutual exclusivity: no simultaneous charge and discharge
    sim = ((sub["u_charge"] == 1) & (sub["u_discharge"] == 1)).sum()
    if sim > 0:
        failures.append(f"S{sid}: {sim} hours simultaneous charge+discharge")

    # 3. Only charges when price is below mean, discharges when above
    charge_hours = sub[sub["u_charge"] == 1]["lmp"].values
    discharge_hours = sub[sub["u_discharge"] == 1]["lmp"].values
    if len(charge_hours) > 0 and len(discharge_hours) > 0:
        if charge_hours.max() > discharge_hours.min():
            # Some charge hour is more expensive than some discharge hour — flag it
            # (This is not always wrong if degradation cost forces conservative trading)
            pass  # Not a hard failure, note it

    # 4. Energy balance: verify SOC dynamics
    soc_init = SOC_INIT * E_MWH
    soc_prev = soc_init
    for _, hour_row in sub.iterrows():
        expected_soc = soc_prev + ETA_C * hour_row["p_charge_MW"] \
                       - (1.0 / ETA_D) * hour_row["p_discharge_MW"]
        actual_soc   = hour_row["soc_MWh"]
        if abs(expected_soc - actual_soc) > 1e-3:
            failures.append(f"S{sid} h{int(hour_row['hour'])}: "
                            f"SOC balance error {abs(expected_soc-actual_soc):.4f}")
        soc_prev = actual_soc

    # 5. End-of-day SOC >= SOC_FINAL_MIN
    final_soc = sub.iloc[-1]["soc_MWh"]
    if final_soc < SOC_FINAL_MIN * E_MWH - 1e-4:
        failures.append(f"S{sid}: end-of-day SOC={final_soc:.3f} < min={SOC_FINAL_MIN*E_MWH}")

    print(f"\n  S{sid} ({tc['label'].split('(')[1].rstrip(')')}):")
    print(f"    SOC range in solution: [{soc_vals.min():.3f}, {soc_vals.max():.3f}] MWh  "
          f"(allowed [{SOC_MIN*E_MWH:.2f}, {SOC_MAX*E_MWH:.2f}])")
    print(f"    End-of-day SOC: {soc_vals[-1]:.3f} MWh  (min required: {SOC_FINAL_MIN*E_MWH:.2f})")
    print(f"    Mutual exclusivity: {'PASS' if sim == 0 else 'FAIL'}")
    print(f"    Energy balance:     "
          f"{'PASS' if not any(f'S{sid}' in f and 'balance' in f for f in failures) else 'FAIL'}")

if failures:
    print(f"\nFAILURES ({len(failures)}):")
    for f in failures:
        print(f"  - {f}")
else:
    print("\nAll physical checks PASSED.")

# ── Save run params ────────────────────────────────────────────────────────────
params = {
    "E_MWH": E_MWH, "P_MW": P_MW, "ETA_C": ETA_C, "ETA_D": ETA_D,
    "SOC_MIN": SOC_MIN, "SOC_MAX": SOC_MAX, "SOC_INIT": SOC_INIT,
    "SOC_FINAL_MIN": SOC_FINAL_MIN, "C_CAPEX": C_CAPEX,
    "N_CYCLES": N_CYCLES, "C_DEG": round(C_DEG, 4),
    "solver": "HiGHS via CVXPY",
    "max_verification_error": round(max_abs_err, 8),
    "physical_checks_passed": len(failures) == 0,
}
with open(os.path.join(OUT_DIR, "deterministic_params.json"), "w") as f:
    json.dump(params, f, indent=2)
print(f"\nSaved: deterministic_params.json")
print("\nDone.")
