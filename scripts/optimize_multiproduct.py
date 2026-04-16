"""
optimize_multiproduct.py

Two-stage stochastic MILP co-optimizing energy arbitrage + PJM RegD regulation.

Formulation
-----------
First-stage decision (committed before price scenario realizes):
  r[t]     -- regulation capacity bid (MW) for each hour

Second-stage decisions (adapt to the realized price scenario s):
  p_c[s,t] -- charging power   (MW)
  p_d[s,t] -- discharging power (MW)
  soc[s,t] -- state of charge   (MWh) at end of hour t
  u_c[s,t] -- charging binary
  u_d[s,t] -- discharging binary

Key constraints
---------------
  Power headroom:  p_c[s,t] + r[t] <= P_MW    (charge path cannot exceed capacity)
                   p_d[s,t] + r[t] <= P_MW    (discharge path cannot exceed capacity)
  SOC headroom:    soc[s,t] >= SOC_MIN*E + r[t]/ETA_D    (can fully respond to reg-up)
                   soc[s,t] <= SOC_MAX*E - r[t]*ETA_C    (can fully respond to reg-down)

PJM RegD revenue model
-----------------------
  Net revenue per MW-h of capacity:
      regd_net  = P_REG - C_DEG_REG * MILEAGE_RATIO

  C_DEG_REG = C_DEG_BASE / DOD_RATIO
    -- Regulation cycles at ~10% DoD vs 80% for arbitrage.
    -- Cycle-life scales roughly as (DOD_ref/DoD)^2; empirical LFP data supports
       ~8x conservative improvement at 10% DoD (DOD_RATIO = 8).
    -- C_DEG_BASE = $27.83/MWh  ->  C_DEG_REG = $3.48/MWh

  MILEAGE_RATIO = 3.0  (PJM RegD typically produces 2-4x mileage vs capacity)

  Total daily regulation revenue = regd_net * sum_t(r[t])

Objective
---------
  max  regd_net * sum(r) + E_probs[sum_t(lmp[s,t]*(p_d - p_c)) - C_DEG*(p_d+p_c)]

Outputs
-------
  results/multiproduct_sweep.csv    -- NPV table across (E, P_REG) combinations
  results/multiproduct_npv.png      -- NPV vs capacity for different P_REG values
  results/multiproduct_revenue.png  -- Revenue breakdown and NPV vs P_REG at 1 MWh
  results/multiproduct_params.json  -- Model parameters
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cvxpy as cp

# -- Paths --------------------------------------------------------------------
SCRIPT_DIR    = os.path.dirname(__file__)
SCENARIOS_CSV = os.path.join(SCRIPT_DIR, "..", "data", "scenarios", "scenarios.csv")
OUT_DIR       = os.path.join(SCRIPT_DIR, "..", "results")
os.makedirs(OUT_DIR, exist_ok=True)

# -- Battery parameters (identical to optimize_stochastic.py) -----------------
ETA_C         = 0.93
ETA_D         = 0.93
SOC_MIN       = 0.10
SOC_MAX       = 0.90
SOC_INIT      = 0.50
SOC_FINAL_MIN = 0.10
C_RATE        = 0.5          # P = C_RATE * E  (0.5C rate)

# -- CapEx & degradation (NREL ATB 2024, Xu et al.) ---------------------------
CAPEX_PER_KWH = 334.0        # $/kWh all-in (NREL ATB 2024, US utility-scale)
N_CYCLES      = 6_000.0      # cycles at 80% DoD (modern LFP, DOE 2024)
C_DEG_BASE    = (CAPEX_PER_KWH * 1000.0) / (2.0 * N_CYCLES)   # $27.83/MWh

# -- Regulation degradation model (small-DoD discount) ------------------------
# At ~10% DoD the LFP cycle count scales as (80/10)^k with k~1.5-2.
# Conservative empirical estimate: ~8x fewer equivalent cycles per MWh throughput.
# Source: Wang et al. 2016 (DoD-dependent degradation for LFP).
DOD_RATIO     = 8.0
C_DEG_REG     = C_DEG_BASE / DOD_RATIO   # $3.48/MWh at small DoD

# -- PJM RegD parameters ------------------------------------------------------
MILEAGE_RATIO = 3.0          # RegD mileage / capacity (typical PJM value: 2-4)

# -- Economic parameters ------------------------------------------------------
FIXED_CAPEX         = 75_000.0   # $ -- BOS, interconnection, permitting (NREL ATB 2024)
FIXED_OM_PER_KW_YR  = 10.0       # $/kW-yr (NREL ATB 2024)
ASSET_LIFE          = 15         # years
DISCOUNT_RATE       = 0.07       # 7% WACC

ANNUITY = sum(1.0 / (1.0 + DISCOUNT_RATE) ** y for y in range(1, ASSET_LIFE + 1))

# -- Sweep parameters ---------------------------------------------------------
E_VALUES     = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]   # MWh
P_REG_VALUES = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0]          # $/MW-h

# -- Load scenarios -----------------------------------------------------------
print("Loading scenarios...")
scen_df   = pd.read_csv(SCENARIOS_CSV)
S         = len(scen_df)
T         = 24
hour_cols = [f"h{h:02d}" for h in range(T)]
probs     = scen_df["probability"].values            # shape (S,)
lmp       = scen_df[hour_cols].values.astype(float)  # shape (S, T)
print(f"  {S} scenarios, T={T} hours.")
print(f"  C_DEG_BASE = ${C_DEG_BASE:.2f}/MWh  |  C_DEG_REG = ${C_DEG_REG:.2f}/MWh")


# =============================================================================
def solve_multiproduct(E_mwh, P_REG, mileage=MILEAGE_RATIO, time_limit=90):
    """
    Two-stage MILP: first-stage r[t] regulation capacity, second-stage per-scenario arbitrage.

    Returns dict with daily revenue components, or None if infeasible.
    """
    P_MW     = C_RATE * E_mwh
    regd_net = P_REG - C_DEG_REG * mileage   # $/MW-h net regulation revenue (can be negative)

    # -- First-stage variable: regulation capacity (committed, scenario-independent)
    r = cp.Variable(T, nonneg=True)           # shape (T,)

    # -- Second-stage variables: energy arbitrage per scenario
    p_c = cp.Variable((S, T), nonneg=True)
    p_d = cp.Variable((S, T), nonneg=True)
    soc = cp.Variable((S, T), nonneg=True)
    u_c = cp.Variable((S, T), boolean=True)
    u_d = cp.Variable((S, T), boolean=True)

    # Broadcast r[t] across all S scenarios: shape (S, T)
    ones_S = np.ones((S, 1))
    r_bc   = ones_S @ cp.reshape(r, (1, T))   # (S, T), row s = r[:]

    constraints = []

    # Regulation capacity upper bound
    constraints.append(r <= P_MW)

    # Energy arbitrage mutual exclusivity (big-M dispatch)
    constraints.append(p_c <= P_MW * u_c)
    constraints.append(p_d <= P_MW * u_d)
    constraints.append(u_c + u_d <= 1)

    # Power headroom: arbitrage + regulation <= rated power
    constraints.append(p_c + r_bc <= P_MW)
    constraints.append(p_d + r_bc <= P_MW)

    # SOC hard bounds
    constraints.append(soc >= SOC_MIN * E_mwh)
    constraints.append(soc <= SOC_MAX * E_mwh)

    # SOC headroom: must be able to fully respond to 1-hour regulation signal
    #   Reg-up  (discharge r MW for 1h): need soc >= SOC_MIN*E + r/ETA_D
    #   Reg-down (charge   r MW for 1h): need soc <= SOC_MAX*E - r*ETA_C
    constraints.append(soc >= SOC_MIN * E_mwh + r_bc / ETA_D)
    constraints.append(soc <= SOC_MAX * E_mwh - r_bc * ETA_C)

    # SOC dynamics
    constraints.append(
        soc[:, 0] == SOC_INIT * E_mwh + ETA_C * p_c[:, 0] - (1.0 / ETA_D) * p_d[:, 0]
    )
    for t in range(1, T):
        constraints.append(
            soc[:, t] == soc[:, t - 1] + ETA_C * p_c[:, t] - (1.0 / ETA_D) * p_d[:, t]
        )
    constraints.append(soc[:, T - 1] >= SOC_FINAL_MIN * E_mwh)

    # -- Objective: regulation EV + arbitrage expected net
    reg_obj = regd_net * cp.sum(r)
    net_price   = lmp - C_DEG_BASE
    charge_cost = lmp + C_DEG_BASE
    arb_obj = probs @ cp.sum(
        cp.multiply(net_price, p_d) - cp.multiply(charge_cost, p_c), axis=1
    )
    objective = cp.Maximize(reg_obj + arb_obj)

    prob_model = cp.Problem(objective, constraints)
    prob_model.solve(solver=cp.HIGHS, verbose=False, time_limit=time_limit)

    if prob_model.status not in ("optimal", "optimal_inaccurate") or prob_model.value is None:
        return None

    r_arr  = r.value if r.value is not None else np.zeros(T)
    pc_arr = p_c.value
    pd_arr = p_d.value

    total_obj   = float(prob_model.value)
    reg_day     = float(regd_net * np.sum(r_arr))
    arb_gross   = float(probs @ np.sum(lmp * pd_arr - lmp * pc_arr, axis=1))
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
        "r_vals":        r_arr.tolist(),
    }


def total_capex(E_mwh):
    return FIXED_CAPEX + CAPEX_PER_KWH * E_mwh * 1000.0

def annual_om(E_mwh):
    return FIXED_OM_PER_KW_YR * C_RATE * E_mwh * 1000.0   # kW/MW * E * 1000

def compute_npv(annual_net, E_mwh):
    capex = total_capex(E_mwh)
    om    = annual_om(E_mwh)
    return (annual_net - om) * ANNUITY - capex


# =============================================================================
# Capacity x P_REG sweep
# =============================================================================
rows = []
cached = {}   # (E, P_REG) -> result dict for later use
n_total = len(E_VALUES) * len(P_REG_VALUES)
print(f"\nSweeping {len(E_VALUES)} sizes x {len(P_REG_VALUES)} P_REG values "
      f"= {n_total} MILPs...")

idx = 0
for E in E_VALUES:
    for P_REG in P_REG_VALUES:
        idx += 1
        P_MW     = C_RATE * E
        regd_net = P_REG - C_DEG_REG * MILEAGE_RATIO
        print(f"  [{idx:02d}/{n_total}] E={E:.1f} MWh  P_REG=${P_REG:.0f}/MW-h  "
              f"regd_net=${regd_net:.2f}/MW-h ...", end=" ", flush=True)

        res = solve_multiproduct(E, P_REG)
        if res is None:
            print("INFEASIBLE/TIMEOUT")
            continue

        cached[(E, P_REG)] = res

        annual_total = res["total_net_day"] * 365.0
        annual_reg   = res["reg_net_day"]   * 365.0
        annual_arb   = res["arb_net_day"]   * 365.0
        npv_val      = compute_npv(annual_total, E)
        capex_val    = total_capex(E)
        om_val       = annual_om(E)
        breakeven    = capex_val / ANNUITY + om_val   # annual revenue needed for NPV=0

        print(f"reg=${annual_reg:,.0f}/yr  arb=${annual_arb:,.0f}/yr  "
              f"NPV=${npv_val:,.0f}  r_mean={res['r_mean_mw']:.3f} MW")

        rows.append({
            "E_MWh":             E,
            "P_MW":              round(P_MW, 3),
            "P_REG":             P_REG,
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

sweep_df = pd.DataFrame(rows)
sweep_path = os.path.join(OUT_DIR, "multiproduct_sweep.csv")
sweep_df.to_csv(sweep_path, index=False)
print(f"\nSaved: {sweep_path}")

# -- Summary: optimal capacity at each P_REG level
print("\nOptimal capacity at each P_REG:")
for P_REG in P_REG_VALUES:
    sub = sweep_df[sweep_df["P_REG"] == P_REG]
    if sub.empty:
        continue
    best = sub.loc[sub["npv_$"].idxmax()]
    status = "PROFITABLE" if best["npv_$"] > 0 else "negative NPV"
    print(f"  P_REG=${P_REG:>4.0f}: best E={best['E_MWh']:.1f} MWh  "
          f"NPV=${best['npv_$']:>10,.0f}  [{status}]")


# =============================================================================
# Plot 1: NPV vs Capacity — one curve per P_REG level
# =============================================================================
fig, ax = plt.subplots(figsize=(11, 6))
colors = plt.cm.plasma(np.linspace(0.08, 0.92, len(P_REG_VALUES)))

for i, P_REG in enumerate(P_REG_VALUES):
    sub = sweep_df[sweep_df["P_REG"] == P_REG].sort_values("E_MWh")
    if sub.empty:
        continue
    label = (f"P_REG = ${P_REG:.0f}/MW-h"
             if P_REG > 0 else "Arbitrage only  (P_REG = $0)")
    ls    = "--" if P_REG == 0 else "-"
    lw    = 1.5  if P_REG == 0 else 2.0
    ax.plot(sub["E_MWh"], sub["npv_$"] / 1e6, marker="o", markersize=4,
            color=colors[i], linewidth=lw, linestyle=ls, label=label)

ax.axhline(0, color="black", linewidth=1.0, linestyle=":", label="NPV = 0 (break-even)")
ax.fill_between(sweep_df["E_MWh"].unique(), 0, 5.0, alpha=0.06,
                color="green", label="Profitable region")

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
npv_path = os.path.join(OUT_DIR, "multiproduct_npv.png")
fig.savefig(npv_path, dpi=150)
plt.close()
print(f"Saved: {npv_path}")


# =============================================================================
# Plot 2: Revenue breakdown at 1 MWh + NPV vs P_REG
# =============================================================================
sub1 = sweep_df[sweep_df["E_MWh"] == 1.0].sort_values("P_REG")
if not sub1.empty:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # (left) Revenue stack vs break-even
    ax = axes[0]
    be_1mwh = sub1["breakeven_$"].iloc[0] / 1e3   # same for all P_REG (capex fixed)
    ax.bar(sub1["P_REG"], sub1["annual_arb_$"] / 1e3,
           color="#5cb85c", alpha=0.85, label="Arbitrage net revenue ($k/yr)")
    ax.bar(sub1["P_REG"], sub1["annual_reg_$"] / 1e3,
           bottom=sub1["annual_arb_$"] / 1e3,
           color="#4e91c9", alpha=0.85, label="RegD net revenue ($k/yr)")
    ax.axhline(be_1mwh, color="red", linewidth=2.0, linestyle="--",
               label=f"Break-even = ${be_1mwh:.0f}k/yr")
    ax.set_xlabel("RegD Clearing Price ($/MW-h)", fontsize=11)
    ax.set_ylabel("Annual Net Revenue ($k/yr)", fontsize=11)
    ax.set_title("(A) Revenue Stack vs Break-Even\n1 MWh / 0.5 MW LFP battery", fontsize=11,
                 fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    ax.tick_params(labelsize=9)

    # (right) NPV vs P_REG
    ax = axes[1]
    npv_k = sub1["npv_$"] / 1e3
    profitable = npv_k > 0

    ax.plot(sub1["P_REG"], npv_k, marker="o", color="#e87a2a",
            linewidth=2.2, markersize=6)
    ax.axhline(0, color="black", linewidth=1.0, linestyle="--", label="NPV = 0")

    if profitable.any():
        ax.fill_between(sub1["P_REG"], npv_k, 0,
                        where=profitable, alpha=0.18, color="green",
                        label="Profitable (NPV > 0)")
    ax.fill_between(sub1["P_REG"], npv_k, 0,
                    where=~profitable, alpha=0.12, color="red",
                    label="Unprofitable (NPV < 0)")

    # Annotate break-even P_REG
    if profitable.any() and (~profitable).any():
        # Interpolate approximate break-even price
        x_arr = sub1["P_REG"].values.astype(float)
        y_arr = npv_k.values.astype(float)
        # Find where sign changes
        for k in range(len(y_arr) - 1):
            if y_arr[k] <= 0 < y_arr[k + 1]:
                # Linear interpolation
                be_price = x_arr[k] + (0 - y_arr[k]) / (y_arr[k + 1] - y_arr[k]) * (x_arr[k + 1] - x_arr[k])
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
    rev_path = os.path.join(OUT_DIR, "multiproduct_revenue.png")
    fig.savefig(rev_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {rev_path}")


# =============================================================================
# Save parameters JSON
# =============================================================================
params = {
    "C_DEG_BASE_per_MWh":  round(C_DEG_BASE, 4),
    "C_DEG_REG_per_MWh":   round(C_DEG_REG, 4),
    "DOD_RATIO":           DOD_RATIO,
    "MILEAGE_RATIO":       MILEAGE_RATIO,
    "CAPEX_PER_KWH":       CAPEX_PER_KWH,
    "FIXED_CAPEX":         FIXED_CAPEX,
    "FIXED_OM_PER_KW_YR":  FIXED_OM_PER_KW_YR,
    "ASSET_LIFE":          ASSET_LIFE,
    "DISCOUNT_RATE":       DISCOUNT_RATE,
    "ANNUITY_FACTOR":      round(ANNUITY, 4),
    "solver":              "HiGHS via CVXPY",
    "E_VALUES":            E_VALUES,
    "P_REG_VALUES":        P_REG_VALUES,
}

# Attach example result if solved
key_e1p20 = (1.0, 20.0)
if key_e1p20 in cached:
    res_e1 = cached[key_e1p20]
    params["example_E1_P20"] = {
        "total_net_day":  round(res_e1["total_net_day"], 4),
        "reg_net_day":    round(res_e1["reg_net_day"], 4),
        "arb_net_day":    round(res_e1["arb_net_day"], 4),
        "r_mean_mw":      round(res_e1["r_mean_mw"], 4),
        "r_vals":         [round(v, 4) for v in res_e1["r_vals"]],
    }

params_path = os.path.join(OUT_DIR, "multiproduct_params.json")
with open(params_path, "w") as f:
    json.dump(params, f, indent=2)
print(f"Saved: {params_path}")

print("\nDone.")
