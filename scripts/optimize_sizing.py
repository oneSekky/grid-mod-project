"""
optimize_sizing.py

Battery sizing optimization: sweeps E_MWH from 0.5 to 10 MWh, solving the
stochastic EV MILP at each size, then computes NPV to find the optimal capacity.

At each size:
  - Power capacity P = E / 2  (fixed 0.5C rate)
  - Solve 40-scenario stochastic MILP (same formulation as optimize_stochastic.py)
  - Compute annualized net revenue
  - Compute NPV over ASSET_LIFE years using DISCOUNT_RATE

NPV formula:
  NPV(E) = sum_{y=1}^{L} [ net_annual / (1+r)^y ] - C_CAPEX(E)

CapEx model:
  C_CAPEX(E) = CAPEX_PER_KWH * E * 1000   (linear in capacity, $/kWh * kWh)

Degradation cost:
  C_DEG(E) = C_CAPEX(E) / (2 * E * N_CYCLES)  -- constant $/MWh regardless of E
  (because CapEx and lifetime throughput both scale with E, they cancel)

Outputs:
  results/sizing_sweep.csv      -- NPV table across capacity sizes
  results/sizing_npv.png        -- NPV vs capacity curve
  results/sizing_revenue.png    -- annualized net revenue vs capacity
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

# ── Fixed battery parameters ──────────────────────────────────────────────────
ETA_C         = 0.93
ETA_D         = 0.93
SOC_MIN       = 0.10
SOC_MAX       = 0.90
SOC_INIT      = 0.50
SOC_FINAL_MIN = 0.10
C_RATE        = 0.5          # P = C_RATE * E  (MW per MWh)

# ── CapEx and degradation model (Xu et al.) ───────────────────────────────────
# Sources: NREL ATB 2024 ($334/kWh), modern utility LFP cycle life 6,000 cycles at 80% DoD
CAPEX_PER_KWH = 334.0        # $/kWh all-in installed (NREL ATB 2024, US utility-scale)
DOD_TYPICAL   = SOC_MAX - SOC_MIN
N_CYCLES      = 6_000.0      # cycles to 70-80% SOH at 80% DoD (modern LFP, DOE 2024)
# C_DEG is constant in $/MWh regardless of E (CapEx and throughput both scale with E)
C_DEG_BASE    = (CAPEX_PER_KWH * 1000.0) / (2.0 * N_CYCLES)  # $/MWh, per kWh of capacity

# ── Economic parameters ───────────────────────────────────────────────────────
ASSET_LIFE    = 15           # years
DISCOUNT_RATE = 0.07         # 7% WACC

# ── Non-linear CapEx model ────────────────────────────────────────────────────
# Real BESS projects have fixed costs (interconnection study, permitting, site
# prep, EPC mobilization) that don't scale with battery capacity. For a small-
# to-medium project these are roughly $75,000–$100,000 regardless of size.
# Source: NREL ATB 2024 project-level cost breakdown; Wood Mackenzie 2024.
FIXED_CAPEX   = 75_000.0    # $ — BOS, interconnection, permitting, site prep

# Fixed O&M from NREL ATB 2024: ~$10/kW-yr on rated power (= C_RATE * E_MWH)
FIXED_OM_PER_KW_YR = 10.0   # $/kW-yr

# ── Capacity sweep ────────────────────────────────────────────────────────────
E_VALUES = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]  # MWh

# ── Load scenarios ────────────────────────────────────────────────────────────
print("Loading scenarios...")
scen_df   = pd.read_csv(SCENARIOS_CSV)
S_ids     = scen_df["scenario_id"].tolist()
S         = len(S_ids)
T         = 24
HOURS     = list(range(T))
hour_cols = [f"h{h:02d}" for h in HOURS]
probs     = scen_df["probability"].values
lmp       = scen_df[hour_cols].values
print(f"  {S} scenarios loaded.")

def solve_for_size(E_mwh):
    """Solve stochastic EV MILP for a given energy capacity E_mwh (MWh)."""
    P_mw  = C_RATE * E_mwh
    C_DEG = C_DEG_BASE   # $/MWh, constant (see note above)

    p_c = cp.Variable((S, T), nonneg=True)
    p_d = cp.Variable((S, T), nonneg=True)
    soc = cp.Variable((S, T), nonneg=True)
    u_c = cp.Variable((S, T), boolean=True)
    u_d = cp.Variable((S, T), boolean=True)

    constraints = []

    constraints.append(p_c <= P_mw * u_c)
    constraints.append(p_d <= P_mw * u_d)
    constraints.append(u_c + u_d <= 1)
    constraints.append(soc >= SOC_MIN * E_mwh)
    constraints.append(soc <= SOC_MAX * E_mwh)

    constraints.append(
        soc[:, 0] == SOC_INIT * E_mwh + ETA_C * p_c[:, 0] - (1.0 / ETA_D) * p_d[:, 0]
    )
    for t in range(1, T):
        constraints.append(
            soc[:, t] == soc[:, t-1] + ETA_C * p_c[:, t] - (1.0 / ETA_D) * p_d[:, t]
        )
    constraints.append(soc[:, T-1] >= SOC_FINAL_MIN * E_mwh)

    net_price   = lmp - C_DEG
    charge_cost = lmp + C_DEG
    objective = cp.Maximize(
        probs @ cp.sum(cp.multiply(net_price, p_d) - cp.multiply(charge_cost, p_c), axis=1)
    )

    prob_model = cp.Problem(objective, constraints)
    prob_model.solve(solver=cp.HIGHS, verbose=False, time_limit=120)

    if prob_model.status not in ("optimal", "optimal_inaccurate") or prob_model.value is None:
        return None

    pc_arr = p_c.value
    pd_arr = p_d.value

    ev_net     = float(prob_model.value)
    ev_revenue = float(probs @ np.sum(lmp * pd_arr - lmp * pc_arr, axis=1))
    ev_deg     = float(probs @ np.sum(C_DEG * (pd_arr + pc_arr), axis=1))

    return {"ev_net": ev_net, "ev_revenue": ev_revenue, "ev_deg": ev_deg}

def total_capex(E_mwh):
    """Non-linear CapEx: fixed project costs + variable battery/BOS cost."""
    return FIXED_CAPEX + CAPEX_PER_KWH * E_mwh * 1000.0

def annual_om(E_mwh):
    """Fixed O&M scales with rated power (NREL ATB 2024: $10/kW-yr)."""
    return FIXED_OM_PER_KW_YR * C_RATE * E_mwh * 1000.0   # kW → MW → kW

def npv(annual_net_revenue, E_mwh, life=ASSET_LIFE, rate=DISCOUNT_RATE):
    """
    NPV = PV(annual net revenue - O&M) - CapEx(E)
    Both revenue and O&M are assumed constant over asset life.
    """
    capex = total_capex(E_mwh)
    om    = annual_om(E_mwh)
    net_annual = annual_net_revenue - om
    pv = sum(net_annual / (1 + rate) ** y for y in range(1, life + 1))
    return pv - capex

# ── Sweep ─────────────────────────────────────────────────────────────────────
rows = []
print("\nSweeping capacity...")
for E in E_VALUES:
    capex = CAPEX_PER_KWH * E * 1000.0   # $
    print(f"  E={E:.1f} MWh  P={C_RATE*E:.2f} MW  CapEx=${capex:,.0f} ...", end=" ", flush=True)

    res = solve_for_size(E)
    if res is None:
        print("INFEASIBLE")
        continue

    capex      = total_capex(E)
    om         = annual_om(E)
    annual_net = res["ev_net"] * 365.0
    npv_val    = npv(annual_net, E)
    payback    = capex / max(annual_net - om, 1e-6)

    # Break-even: what total annual revenue (arbitrage + ancillary) makes NPV=0?
    r, L = DISCOUNT_RATE, ASSET_LIFE
    annuity = sum(1 / (1 + r) ** y for y in range(1, L + 1))
    breakeven_annual = capex / annuity + om
    ancillary_needed = max(0.0, breakeven_annual - annual_net)

    print(f"E[Net]=${res['ev_net']:.3f}/day  annual=${annual_net:,.0f}  "
          f"O&M=${om:,.0f}  CapEx=${capex:,.0f}  NPV=${npv_val:,.0f}  "
          f"ancillary_needed=${ancillary_needed:,.0f}/yr")
    rows.append({
        "E_MWh":              E,
        "P_MW":               round(C_RATE * E, 3),
        "capex_$":            round(capex, 0),
        "annual_om_$":        round(om, 0),
        "ev_net_day":         round(res["ev_net"], 4),
        "ev_revenue_day":     round(res["ev_revenue"], 4),
        "ev_deg_day":         round(res["ev_deg"], 4),
        "annual_arb_$":       round(annual_net, 2),
        "npv_$":              round(npv_val, 2),
        "payback_yrs":        round(payback, 1) if payback < 999 else None,
        "ancillary_needed_$": round(ancillary_needed, 0),
    })

sweep_df = pd.DataFrame(rows)
sweep_path = os.path.join(OUT_DIR, "sizing_sweep.csv")
sweep_df.to_csv(sweep_path, index=False)
print(f"\nSaved: {sweep_path}")

# ── Find optimal size ──────────────────────────────────────────────────────────
best = sweep_df.loc[sweep_df["npv_$"].idxmax()]
print(f"\nOptimal capacity (max NPV): {best['E_MWh']} MWh  |  NPV = ${best['npv_$']:,.0f}")
print(f"  Annual arbitrage revenue: ${best['annual_arb_$']:,.0f}/yr")
print(f"  Annual O&M:              ${best['annual_om_$']:,.0f}/yr")
print(f"  Ancillary needed for NPV=0: ${best['ancillary_needed_$']:,.0f}/yr")

# ── Plot 1: NPV vs capacity with fixed-cost kink ──────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(sweep_df["E_MWh"], sweep_df["npv_$"] / 1000, marker="o",
        color="#4e91c9", linewidth=2, markersize=6, label="NPV (arbitrage only)")
ax.axhline(0, color="black", linewidth=0.8, linestyle="--", label="Break-even")
# Shade the ancillary gap on the best-looking size
ax.set_xlabel("Battery Capacity (MWh)", fontsize=11)
ax.set_ylabel("NPV ($k)", fontsize=11)
ax.set_title(
    f"NPV vs Battery Capacity  (CapEx=${CAPEX_PER_KWH}/kWh + ${FIXED_CAPEX/1000:.0f}k fixed, "
    f"O&M=${FIXED_OM_PER_KW_YR}/kW-yr, {ASSET_LIFE}-yr, {DISCOUNT_RATE*100:.0f}% WACC)",
    fontsize=10
)
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)
plt.tight_layout()
npv_path = os.path.join(OUT_DIR, "sizing_npv.png")
fig.savefig(npv_path, dpi=150)
plt.close()
print(f"Saved: {npv_path}")

# ── Plot 2: Revenue stack vs break-even at each capacity ──────────────────────
fig, ax = plt.subplots(figsize=(11, 5))
x = sweep_df["E_MWh"].values
w = 0.35
ax.bar(x, sweep_df["annual_arb_$"] / 1000, width=w,
       color="#5cb85c", alpha=0.85, label="Arbitrage revenue (optimized)")
# Stack ancillary needed on top
ax.bar(x, sweep_df["ancillary_needed_$"] / 1000, width=w,
       bottom=sweep_df["annual_arb_$"] / 1000,
       color="#e87a2a", alpha=0.6, label="Ancillary revenue needed to break even")
# Break-even line
r, L = DISCOUNT_RATE, ASSET_LIFE
annuity = sum(1 / (1 + r) ** y for y in range(1, L + 1))
be_vals = [(total_capex(E) / annuity + annual_om(E)) / 1000 for E in x]
ax.plot(x, be_vals, color="red", linewidth=1.8, linestyle="--",
        marker="s", markersize=4, label="Break-even annual revenue (CapEx + O&M)")

ax.set_xlabel("Battery Capacity (MWh)", fontsize=11)
ax.set_ylabel("Annual Revenue ($k)", fontsize=11)
ax.set_title("Revenue Gap: Arbitrage vs Break-Even\n"
             "(Gap must be filled by ancillary services, capacity markets, etc.)", fontsize=11)
ax.legend(fontsize=9)
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
rev_path = os.path.join(OUT_DIR, "sizing_revenue.png")
fig.savefig(rev_path, dpi=150)
plt.close()
print(f"Saved: {rev_path}")

# ── Save params ────────────────────────────────────────────────────────────────
params = {
    "ETA_C": ETA_C, "ETA_D": ETA_D, "SOC_MIN": SOC_MIN, "SOC_MAX": SOC_MAX,
    "C_RATE": C_RATE, "CAPEX_PER_KWH": CAPEX_PER_KWH, "N_CYCLES": round(N_CYCLES, 1),
    "C_DEG_per_MWh": round(C_DEG_BASE, 4), "ASSET_LIFE": ASSET_LIFE,
    "DISCOUNT_RATE": DISCOUNT_RATE, "E_VALUES": E_VALUES,
    "optimal_E_MWh": float(best["E_MWh"]),
    "optimal_NPV_$": float(best["npv_$"]),
    "solver": "HiGHS via CVXPY",
}
with open(os.path.join(OUT_DIR, "sizing_params.json"), "w") as f:
    json.dump(params, f, indent=2)
print(f"Saved: {os.path.join(OUT_DIR, 'sizing_params.json')}")

print("\nDone.")
