"""
optimize_cvar.py

Two-stage CVaR-constrained stochastic MILP for BESS bidding.

KEY DIFFERENCE FROM optimize_stochastic.py:
  Non-anticipativity constraints enforce that the dispatch schedule
  (p_c[t], p_d[t], u_c[t], u_d[t], soc[t]) is the SAME across all scenarios.
  This is the correct two-stage structure:
    Stage 1 (day-ahead): commit to a single 24-hour dispatch schedule
    Stage 2 (real-time): revenue is realized at the actual scenario price

  Revenue then varies by scenario even though dispatch is fixed:
    R[s] = sum_t lmp[s,t] * (p_d[t] - p_c[t])

  This creates a genuine risk-return tradeoff: improving CVaR (tail revenue)
  requires choosing a more conservative dispatch, which reduces E[Revenue].

CVaR linearization (Rockafellar-Uryasev):
  eta         : VaR threshold (scalar)
  z[s]        : shortfall below eta in scenario s  (>= 0)
  z[s]       >= eta - NetRev[s]   for all s
  CVaR_alpha  = eta - 1/(1-alpha) * sum_s prob[s]*z[s]

Sweep: for each alpha in {0.90, 0.95, 0.99}, sweep CVaR_budget from
  unconstrained (non-binding) upward to trace the efficient frontier.

Outputs:
  results/cvar_frontier.csv    -- frontier table
  results/cvar_frontier.png    -- E[Net] vs CVaR plot
  results/cvar_params.json     -- run log
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

# ── Battery Parameters ────────────────────────────────────────────────────────
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

# ── CVaR sweep config ─────────────────────────────────────────────────────────
ALPHAS       = [0.90, 0.95, 0.99]
N_BUDGET_PTS = 15

# ── Load Scenarios ────────────────────────────────────────────────────────────
print("Loading scenarios...")
scen_df   = pd.read_csv(SCENARIOS_CSV)
S         = len(scen_df)
T         = 24
hour_cols = [f"h{h:02d}" for h in range(T)]
probs     = scen_df["probability"].values   # (S,)
lmp       = scen_df[hour_cols].values       # (S, T)
E_lmp     = probs @ lmp                     # (T,) probability-weighted average LMP

print(f"  {S} scenarios  |  E[LMP] range: [{E_lmp.min():.2f}, {E_lmp.max():.2f}] $/MWh")

def build_and_solve(alpha, cvar_budget=None, verbose=False):
    """
    Two-stage MILP with non-anticipativity.

    First-stage (scenario-independent) dispatch variables:
      p_c[t], p_d[t], soc[t], u_c[t], u_d[t]

    Per-scenario net revenue (after degradation):
      NetRev[s] = sum_t lmp[s,t]*(p_d[t] - p_c[t]) - C_DEG*sum_t(p_d[t]+p_c[t])

    Objective: max E[NetRev] = sum_s prob[s] * NetRev[s]

    CVaR constraint (optional):
      CVaR_alpha(NetRev) >= cvar_budget
    """
    # ── First-stage variables (single dispatch schedule) ──────────────────────
    p_c = cp.Variable(T, nonneg=True, name="p_c")
    p_d = cp.Variable(T, nonneg=True, name="p_d")
    soc = cp.Variable(T, nonneg=True, name="soc")
    u_c = cp.Variable(T, boolean=True, name="u_c")
    u_d = cp.Variable(T, boolean=True, name="u_d")

    # ── CVaR auxiliary variables ──────────────────────────────────────────────
    eta = cp.Variable(name="eta")
    z   = cp.Variable(S, nonneg=True, name="z")

    constraints = []

    # Power bounds
    constraints.append(p_c <= P_MW * u_c)
    constraints.append(p_d <= P_MW * u_d)

    # Mutual exclusivity
    constraints.append(u_c + u_d <= 1)

    # SOC bounds
    constraints.append(soc >= SOC_MIN * E_MWH)
    constraints.append(soc <= SOC_MAX * E_MWH)

    # SOC dynamics (deterministic — dispatch is fixed across scenarios)
    constraints.append(
        soc[0] == SOC_INIT * E_MWH + ETA_C * p_c[0] - (1.0 / ETA_D) * p_d[0]
    )
    for t in range(1, T):
        constraints.append(
            soc[t] == soc[t-1] + ETA_C * p_c[t] - (1.0 / ETA_D) * p_d[t]
        )

    # End-of-day SOC floor
    constraints.append(soc[T-1] >= SOC_FINAL_MIN * E_MWH)

    # ── Per-scenario net revenue ───────────────────────────────────────────────
    # NetRev[s] = lmp[s,:] @ (p_d - p_c) - C_DEG * sum(p_d + p_c)
    # Expressed as a (S,) CVXPY expression:
    deg_cost  = C_DEG * (cp.sum(p_d) + cp.sum(p_c))   # scalar, same for all s
    arb_rev   = lmp @ (p_d - p_c)                      # (S,) scenario revenues
    net_rev   = arb_rev - deg_cost                      # (S,) net per scenario

    # ── Rockafellar-Uryasev CVaR constraints ──────────────────────────────────
    # z[s] >= eta - NetRev[s]  for all s  (z >= 0 enforced by nonneg)
    constraints.append(z >= eta - net_rev)

    cvar_expr = eta - (1.0 / (1.0 - alpha)) * (probs @ z)

    if cvar_budget is not None:
        constraints.append(cvar_expr >= cvar_budget)

    # ── Objective: maximize expected net revenue ───────────────────────────────
    # E[NetRev] = sum_s prob[s] * NetRev[s]
    # Since deg_cost is fixed across scenarios:
    #   E[NetRev] = E_lmp @ (p_d - p_c) - C_DEG * sum(p_d + p_c)
    ev_net = probs @ net_rev
    objective = cp.Maximize(ev_net)

    prob_model = cp.Problem(objective, constraints)
    prob_model.solve(solver=cp.HIGHS, verbose=verbose, time_limit=60)

    if prob_model.status not in ("optimal", "optimal_inaccurate") or prob_model.value is None:
        return None

    pc_val  = p_c.value
    pd_val  = p_d.value
    net_rev_vals = net_rev.value                          # (S,) realized net per scenario
    cvar_val     = float(eta.value) - (1.0 / (1.0 - alpha)) * float(probs @ z.value)

    ev_net_val     = float(probs @ net_rev_vals)
    ev_revenue_val = float(probs @ (lmp @ (pd_val - pc_val)))
    ev_deg_val     = float(C_DEG * (pd_val.sum() + pc_val.sum()))

    return {
        "ev_net":     ev_net_val,
        "ev_revenue": ev_revenue_val,
        "ev_deg":     ev_deg_val,
        "cvar":       cvar_val,
        "net_rev_by_scenario": net_rev_vals,
        "pc":         pc_val,
        "pd":         pd_val,
        "soc":        soc.value,
    }

# ── Baseline: unconstrained two-stage EV solve ────────────────────────────────
print("\nSolving unconstrained two-stage EV model...")
base = build_and_solve(alpha=0.95, cvar_budget=None)
print(f"  E[Net]       = ${base['ev_net']:.4f}/day")
print(f"  CVaR_0.95    = ${base['cvar']:.4f}/day")
print(f"  Scenario net revenues (min/mean/max): "
      f"${base['net_rev_by_scenario'].min():.2f} / "
      f"${base['net_rev_by_scenario'].mean():.2f} / "
      f"${base['net_rev_by_scenario'].max():.2f}")

# The unconstrained CVaR is the baseline (non-binding lower bound).
# Sweep CVaR_budget UPWARD from this value — tightening the constraint forces
# a more conservative dispatch that sacrifices E[Net] to improve the tail.
CVAR_UNCONSTRAINED = base["cvar"]
EV_UNCONSTRAINED   = base["ev_net"]

# Upper limit: we stop when the problem becomes infeasible or E[Net] goes negative.
# Start with a generous upper estimate; the solver will tell us when it's infeasible.
CVAR_BUDGET_MAX = max(EV_UNCONSTRAINED * 0.95, CVAR_UNCONSTRAINED + 5.0)

# ── Parametric sweep ─────────────────────────────────────────────────────────
frontier_rows = []

for alpha in ALPHAS:
    print(f"\nAlpha = {alpha:.2f}")

    # Re-run unconstrained for this alpha to get its specific CVaR baseline
    unc = build_and_solve(alpha=alpha, cvar_budget=None)
    if unc is None:
        print("  Unconstrained solve failed, skipping.")
        continue
    cvar_unc = unc["cvar"]
    ev_unc   = unc["ev_net"]
    print(f"  Unconstrained: E[Net]=${ev_unc:.4f}  CVaR=${cvar_unc:.4f}")

    # Record unconstrained point (rightmost on frontier = best CVaR achievable
    # without sacrificing EV — this is the Pareto-dominant corner)
    frontier_rows.append({
        "alpha": alpha, "cvar_budget": round(float(cvar_unc), 6),
        "ev_revenue": round(unc["ev_revenue"], 6),
        "ev_deg_cost": round(unc["ev_deg"], 6),
        "ev_net": round(ev_unc, 6),
        "cvar_achieved": round(cvar_unc, 6),
        "constrained": False,
    })

    # Sweep budgets upward from the unconstrained CVaR
    budgets = np.linspace(cvar_unc, CVAR_BUDGET_MAX, N_BUDGET_PTS + 1)[1:]  # skip cvar_unc itself

    for budget in budgets:
        res = build_and_solve(alpha=alpha, cvar_budget=float(budget))
        if res is None:
            print(f"  budget=${budget:.4f} -> infeasible, stopping sweep")
            break
        if res["ev_net"] < -0.5:
            print(f"  budget=${budget:.4f} -> E[Net]=${res['ev_net']:.4f} (economically infeasible)")
            break
        print(f"  budget=${budget:.4f}  E[Net]=${res['ev_net']:.4f}  CVaR=${res['cvar']:.4f}")
        frontier_rows.append({
            "alpha": alpha, "cvar_budget": round(float(budget), 6),
            "ev_revenue": round(res["ev_revenue"], 6),
            "ev_deg_cost": round(res["ev_deg"], 6),
            "ev_net": round(res["ev_net"], 6),
            "cvar_achieved": round(res["cvar"], 6),
            "constrained": True,
        })

frontier_df = pd.DataFrame(frontier_rows)
frontier_path = os.path.join(OUT_DIR, "cvar_frontier.csv")
frontier_df.to_csv(frontier_path, index=False)
print(f"\nSaved: {frontier_path}")
print(frontier_df[["alpha","ev_net","cvar_achieved","constrained"]].to_string(index=False))

# ── Plot: Risk-Return Efficient Frontier ──────────────────────────────────────
alpha_colors = {0.90: "#4e91c9", 0.95: "#e87a2a", 0.99: "#c0392b"}

fig, ax = plt.subplots(figsize=(9, 6))

for alpha in ALPHAS:
    sub = frontier_df[frontier_df["alpha"] == alpha].sort_values("cvar_achieved")
    if sub.empty:
        continue
    ax.plot(sub["cvar_achieved"], sub["ev_net"],
            marker="o", markersize=5, linewidth=1.8,
            color=alpha_colors[alpha], label=f"alpha={alpha:.2f}")
    # Star on the unconstrained point
    unc_pt = sub[~sub["constrained"]]
    if not unc_pt.empty:
        ax.scatter(unc_pt["cvar_achieved"], unc_pt["ev_net"],
                   color=alpha_colors[alpha], s=90, zorder=6, marker="*")

ax.set_xlabel("CVaR ($/day)  [tail revenue; higher = better worst-case]", fontsize=11)
ax.set_ylabel("E[Net Revenue] ($/day)", fontsize=11)
ax.set_title(
    "BESS Risk-Return Efficient Frontier (Two-Stage, Non-Anticipativity)\n"
    "Stars = unconstrained EV solution; moving left = more risk-averse",
    fontsize=11
)
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)
ax.axhline(0, color="black", linewidth=0.7, linestyle="--")

plt.tight_layout()
fig.savefig(os.path.join(OUT_DIR, "cvar_frontier.png"), dpi=150)
plt.close()
print(f"Saved: {os.path.join(OUT_DIR, 'cvar_frontier.png')}")

# ── Plot: Dispatch schedule comparison (unconstrained vs most risk-averse) ────
# Use alpha=0.95 for this illustration
sub95 = frontier_df[frontier_df["alpha"] == 0.95].sort_values("cvar_achieved")
if len(sub95) >= 2:
    # Re-solve unconstrained and most constrained to get dispatch arrays
    unc_res  = build_and_solve(alpha=0.95, cvar_budget=None)
    cons_res = build_and_solve(alpha=0.95, cvar_budget=float(sub95.iloc[0]["cvar_budget"]))

    if unc_res and cons_res:
        hours = np.arange(T)
        fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

        for ax, res, label, color in [
            (axes[0], unc_res,  f"Unconstrained EV  (E[Net]=${unc_res['ev_net']:.2f}/day)", "#4e91c9"),
            (axes[1], cons_res, f"CVaR-Constrained  (E[Net]=${cons_res['ev_net']:.2f}/day)", "#c0392b"),
        ]:
            ax.bar(hours,  res["pd"],        color="#e87a2a", alpha=0.8, label="Discharge (MW)")
            ax.bar(hours, -res["pc"],        color=color,    alpha=0.8, label="Charge (MW, neg)")
            ax2 = ax.twinx()
            soc_line = [SOC_INIT * E_MWH] + list(res["soc"])
            ax2.plot(range(T + 1), soc_line, color="purple", linewidth=1.5,
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
        fig.savefig(os.path.join(OUT_DIR, "cvar_dispatch_comparison.png"), dpi=150)
        plt.close()
        print(f"Saved: {os.path.join(OUT_DIR, 'cvar_dispatch_comparison.png')}")

# ── Save params ────────────────────────────────────────────────────────────────
params = {
    "formulation": "two-stage non-anticipativity",
    "E_MWH": E_MWH, "P_MW": P_MW, "ETA_C": ETA_C, "ETA_D": ETA_D,
    "SOC_MIN": SOC_MIN, "SOC_MAX": SOC_MAX, "C_DEG_per_MWh": round(C_DEG, 4),
    "alphas": ALPHAS, "n_budget_pts": N_BUDGET_PTS,
    "unconstrained_ev_net": round(EV_UNCONSTRAINED, 6),
    "unconstrained_cvar_095": round(CVAR_UNCONSTRAINED, 6),
    "solver": "HiGHS via CVXPY",
}
with open(os.path.join(OUT_DIR, "cvar_params.json"), "w") as f:
    json.dump(params, f, indent=2)
print(f"Saved: {os.path.join(OUT_DIR, 'cvar_params.json')}")
print("\nDone.")
