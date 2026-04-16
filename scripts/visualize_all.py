"""
visualize_all.py

Produces two report-quality multi-panel figures covering all key results:

  Figure 1 — Model Overview (figure_1_model_overview.png)
    Six panels telling the full model story from inputs to validation:
      (A) Seasonal scenario fan — price uncertainty input
      (B) SOC trajectories across all 40 scenarios — dispatch diversity
      (C) CVaR efficient frontier — risk-return tradeoff
      (D) Deterministic baseline: 3 test cases dispatch comparison
      (E) Per-scenario net revenue distribution — scenario P&L
      (F) Backtest 2024 cumulative revenue — out-of-sample validation

  Figure 2 — Economic Analysis (figure_2_economics.png)
    Four panels covering the investment case:
      (A) EVPI: wait-and-see vs two-stage + scenario revenue CDF
      (B) Monthly backtest performance + LMP spread driver
      (C) NPV vs capacity with break-even gap
      (D) NPV sensitivity heat map (CapEx x cycle life)
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.colors as mcolors
import matplotlib.ticker as mticker

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(__file__)
RES_DIR    = os.path.join(SCRIPT_DIR, "..", "results")

# ── Load data ─────────────────────────────────────────────────────────────────
scenarios     = pd.read_csv(os.path.join(RES_DIR, "..", "data", "scenarios", "scenarios.csv"))
stoch_summary = pd.read_csv(os.path.join(RES_DIR, "stochastic_summary.csv"))
stoch_results = pd.read_csv(os.path.join(RES_DIR, "stochastic_results.csv"))
cvar          = pd.read_csv(os.path.join(RES_DIR, "cvar_frontier.csv"))
backtest      = pd.read_csv(os.path.join(RES_DIR, "backtest_daily.csv"), parse_dates=["date"])
sizing        = pd.read_csv(os.path.join(RES_DIR, "sizing_sweep.csv"))
sensitivity   = pd.read_csv(os.path.join(RES_DIR, "analysis_sensitivity.csv"))
det_cases     = pd.read_csv(os.path.join(RES_DIR, "deterministic_cases.csv"))
det_verify    = pd.read_csv(os.path.join(RES_DIR, "deterministic_verification.csv"))
bt_summary    = pd.read_csv(os.path.join(RES_DIR, "backtest_summary.csv"))

# Optional: multiproduct sweep (only available after running optimize_multiproduct.py)
_mp_path = os.path.join(RES_DIR, "multiproduct_sweep.csv")
multiproduct = pd.read_csv(_mp_path) if os.path.exists(_mp_path) else None

with open(os.path.join(RES_DIR, "stochastic_params.json")) as f:
    stoch_params = json.load(f)

# ── Shared constants ──────────────────────────────────────────────────────────
SEASON_COLORS = {"winter": "#4e91c9", "spring": "#5cb85c",
                 "summer": "#e87a2a", "fall":   "#9b59b6"}
ALPHA_COLORS  = {0.90: "#4e91c9", 0.95: "#e87a2a", 0.99: "#c0392b"}
HOURS         = np.arange(24)
hour_cols     = [f"h{h:02d}" for h in range(24)]
E_MWH         = 1.0
SOC_INIT      = 0.50
ANNUITY       = sum(1 / 1.07 ** y for y in range(1, 16))
FIXED_CAPEX   = 75_000.0
OM_PER_KW_YR  = 10.0

# ── pre-compute things we reference in multiple panels ────────────────────────
ev_net_ws  = float((stoch_summary["total_net"] * stoch_summary["probability"]).sum())
ev_net_ts  = float(cvar[cvar["constrained"] == False]["ev_net"].iloc[0])
evpi_day   = ev_net_ws - ev_net_ts

backtest["month"] = backtest["date"].dt.month
monthly = backtest.groupby("month")[
    ["opt_net", "naive_rank_net", "spread_lmp"]
].mean().reset_index()

# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 1 — MODEL OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════
print("Building Figure 1 — Model Overview...")

fig1 = plt.figure(figsize=(18, 14))
gs   = gridspec.GridSpec(3, 3, figure=fig1, hspace=0.42, wspace=0.35)

axA = fig1.add_subplot(gs[0, 0])
axB = fig1.add_subplot(gs[0, 1])
axC = fig1.add_subplot(gs[0, 2])
axD = fig1.add_subplot(gs[1, :])   # wide — 3-case dispatch
axE = fig1.add_subplot(gs[2, 0:2])
axF = fig1.add_subplot(gs[2, 2])

# ── (A) Seasonal scenario fan ─────────────────────────────────────────────────
for _, row in scenarios.iterrows():
    season = row["season"]
    vals   = row[hour_cols].values.astype(float)
    alpha  = 0.15 + 0.55 * row["probability"] / scenarios["probability"].max()
    axA.plot(HOURS, vals, color=SEASON_COLORS[season], alpha=float(alpha),
             linewidth=0.9)
for season, color in SEASON_COLORS.items():
    axA.plot([], [], color=color, linewidth=2, label=season.capitalize())
axA.set_xlabel("Hour (EPT)", fontsize=9)
axA.set_ylabel("LMP ($/MWh)", fontsize=9)
axA.set_title("(A) Price Scenario Fan\n40 scenarios, 4 seasons", fontsize=10, fontweight="bold")
axA.legend(fontsize=7, loc="upper left")
axA.set_xticks(range(0, 24, 4))
axA.tick_params(labelsize=8)
axA.grid(True, alpha=0.25)

# ── (B) SOC trajectories ──────────────────────────────────────────────────────
soc_by_s = stoch_results.pivot(index=["scenario_id","season","probability"],
                                columns="hour", values="soc_MWh")
for (sid, season, prob), row in soc_by_s.iterrows():
    soc_line = [SOC_INIT * E_MWH] + list(row.values)
    alpha    = 0.12 + 0.55 * prob / scenarios["probability"].max()
    axB.plot(range(25), soc_line, color=SEASON_COLORS[season],
             alpha=float(alpha), linewidth=0.85)
axB.axhline(0.10, color="red",   linestyle="--", linewidth=0.8, alpha=0.6)
axB.axhline(0.90, color="green", linestyle="--", linewidth=0.8, alpha=0.6)
axB.set_xlabel("Hour (EPT)", fontsize=9)
axB.set_ylabel("State of Charge (MWh)", fontsize=9)
axB.set_title("(B) SOC Trajectories\nAll 40 scenarios (wait-and-see)", fontsize=10, fontweight="bold")
axB.set_xticks(range(0, 25, 4))
axB.tick_params(labelsize=8)
axB.grid(True, alpha=0.25)
axB.set_ylim(-0.02, 1.02)

# ── (C) CVaR efficient frontier ───────────────────────────────────────────────
for alpha_val in [0.90, 0.95, 0.99]:
    sub = cvar[cvar["alpha"] == alpha_val].sort_values("cvar_achieved")
    if sub.empty:
        continue
    axC.plot(sub["cvar_achieved"], sub["ev_net"],
             marker="o", markersize=4, linewidth=1.6,
             color=ALPHA_COLORS[alpha_val], label=f"a={alpha_val:.2f}")
    unc = sub[sub["constrained"] == False]
    if not unc.empty:
        axC.scatter(unc["cvar_achieved"], unc["ev_net"],
                    color=ALPHA_COLORS[alpha_val], s=60, zorder=5, marker="*")
axC.axhline(0, color="black", linewidth=0.7, linestyle=":")
axC.set_xlabel("CVaR ($/day)", fontsize=9)
axC.set_ylabel("E[Net Revenue] ($/day)", fontsize=9)
axC.set_title("(C) Risk-Return Frontier\nCVaR two-stage (stars = unconstrained)", fontsize=10, fontweight="bold")
axC.legend(fontsize=8)
axC.tick_params(labelsize=8)
axC.grid(True, alpha=0.25)

# ── (D) Deterministic baseline: 3-case dispatch comparison (wide panel) ───────
test_cases = [
    (10, "High-Spread S10 (Winter, spread=$119)", "#c0392b"),
    (24, "Med-Spread S24 (Summer, spread=$52)",   "#e87a2a"),
    (1,  "Low-Spread S1  (Winter, spread=$9)",    "#4e91c9"),
]
inner_gs = gridspec.GridSpecFromSubplotSpec(1, 3, subplot_spec=gs[1, :],
                                             wspace=0.28)
axD_axes = [fig1.add_subplot(inner_gs[0, i]) for i in range(3)]
axD.set_visible(False)  # hide the placeholder

for ax, (sid, label, color) in zip(axD_axes, test_cases):
    sub   = det_cases[det_cases["scenario_id"] == sid]
    price = sub["lmp"].values
    pc    = sub["p_charge_MW"].values
    pd_   = sub["p_discharge_MW"].values
    soc_v = sub["soc_MWh"].values
    net   = sub["net_revenue"].iloc[0]

    ax2 = ax.twinx()
    ax.bar(HOURS,  pd_,  color="#e87a2a", alpha=0.75, width=0.7, label="Discharge")
    ax.bar(HOURS, -pc,  color="#4e91c9", alpha=0.75, width=0.7, label="Charge")

    ax2.plot(list(range(25)), [SOC_INIT * E_MWH] + list(soc_v),
             color="purple", linewidth=1.6, linestyle="--")
    ax2.axhline(0.10, color="red",   linestyle=":", linewidth=0.7, alpha=0.6)
    ax2.axhline(0.90, color="green", linestyle=":", linewidth=0.7, alpha=0.6)
    ax2.set_ylim(-0.02, 1.05)
    ax2.set_ylabel("SOC (MWh)", fontsize=7.5, color="purple")
    ax2.tick_params(axis="y", labelcolor="purple", labelsize=7)

    ax.set_title(f"(D) {label}\nNet=${net:.2f}", fontsize=8.5, fontweight="bold")
    ax.set_xlabel("Hour", fontsize=8)
    ax.set_ylabel("Power (MW)", fontsize=8)
    ax.set_xticks(range(0, 24, 4))
    ax.tick_params(labelsize=7.5)
    ax.grid(True, alpha=0.2)
    if ax == axD_axes[0]:
        ax.legend(fontsize=7, loc="upper left")

# ── (E) Per-scenario net revenue distribution ─────────────────────────────────
s_sorted = stoch_summary.sort_values("scenario_id")
colors_e = [SEASON_COLORS[s] for s in s_sorted["season"]]
bars = axE.bar(s_sorted["scenario_id"], s_sorted["total_net"],
               color=colors_e, alpha=0.85, width=0.8)
axE.axhline(ev_net_ws, color="black", linestyle="--", linewidth=1.4,
            label=f"E[Net]=${ev_net_ws:.2f}/day")
axE.axhline(0, color="gray", linewidth=0.7)
for season, color in SEASON_COLORS.items():
    axE.bar([], [], color=color, label=season.capitalize())
axE.set_xlabel("Scenario ID", fontsize=9)
axE.set_ylabel("Daily Net Revenue ($/day)", fontsize=9)
axE.set_title("(E) Per-Scenario Net Revenue\n(Revenue - Degradation Cost, 1 MWh LFP)",
              fontsize=10, fontweight="bold")
axE.legend(fontsize=8, ncol=5, loc="upper right")
axE.tick_params(labelsize=8)
axE.grid(True, axis="y", alpha=0.25)

# ── (F) Backtest 2024 cumulative revenue ──────────────────────────────────────
strat_colors = {"opt_net": "#4e91c9", "naive_rank_net": "#9b59b6",
                "naive_fixed_net": "#e87a2a"}
strat_labels = {"opt_net": f"Oracle (${backtest['opt_net'].sum():,.0f}/yr)",
                "naive_rank_net": f"Price-rank (${backtest['naive_rank_net'].sum():,.0f}/yr)",
                "naive_fixed_net": f"Fixed hrs (${backtest['naive_fixed_net'].sum():,.0f}/yr)"}
for col, color in strat_colors.items():
    cumrev = backtest[col].fillna(0).cumsum()
    axF.plot(backtest["date"], cumrev, color=color,
             linewidth=1.5, label=strat_labels[col])
axF.axhline(0, color="black", linewidth=0.6, linestyle=":")
axF.set_xlabel("2024", fontsize=9)
axF.set_ylabel("Cumulative Net Revenue ($)", fontsize=9)
axF.set_title("(F) Backtest 2024\nCumulative net revenue", fontsize=10, fontweight="bold")
axF.legend(fontsize=7.5)
axF.tick_params(labelsize=7.5)
axF.tick_params(axis="x", rotation=30)
axF.grid(True, alpha=0.25)
axF.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

fig1.suptitle(
    "BESS Bidding Optimization — Full Model Overview\n"
    "PJM RT LMP  |  1 MWh / 0.5 MW LFP  |  NREL ATB 2024 params  |  Training: 2020-2023  |  Backtest: 2024",
    fontsize=13, fontweight="bold", y=0.995
)

fig1_path = os.path.join(RES_DIR, "figure_1_model_overview.png")
fig1.savefig(fig1_path, dpi=160, bbox_inches="tight")
plt.close()
print(f"Saved: figure_1_model_overview.png")

# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 2 — ECONOMIC ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════
print("Building Figure 2 — Economic Analysis...")

fig2, axes2 = plt.subplots(2, 2, figsize=(16, 11))
fig2.subplots_adjust(hspace=0.40, wspace=0.33)
axA2, axB2, axC2, axD2 = axes2[0,0], axes2[0,1], axes2[1,0], axes2[1,1]

# ── (A) EVPI: bar chart + scenario CDF ───────────────────────────────────────
# Left half: EVPI bars
inner = gridspec.GridSpecFromSubplotSpec(1, 2, subplot_spec=axA2.get_subplotspec(),
                                          wspace=0.4)
axA2.set_visible(False)
axA2a = fig2.add_subplot(inner[0])
axA2b = fig2.add_subplot(inner[1])

categories = ["Two-Stage\n(committed)", "Wait-and-See\n(per-scenario)"]
vals_evpi  = [ev_net_ts, ev_net_ws]
bars_evpi  = axA2a.bar(categories, vals_evpi,
                        color=["#4e91c9", "#5cb85c"], alpha=0.85, width=0.5)
axA2a.bar_label(bars_evpi, labels=[f"${v:.2f}/day\n${v*365:,.0f}/yr" for v in vals_evpi],
                fontsize=8.5, padding=4)
axA2a.annotate("", xy=(1, ev_net_ws), xytext=(1, ev_net_ts),
               arrowprops=dict(arrowstyle="<->", color="red", lw=2))
axA2a.text(1.08, (ev_net_ws + ev_net_ts) / 2,
           f"EVPI\n${evpi_day:.2f}/day\n(${evpi_day*365:,.0f}/yr)",
           color="red", fontsize=8, va="center")
axA2a.set_ylabel("E[Net] ($/day)", fontsize=9)
axA2a.set_title("(A) EVPI\nValue of perfect information", fontsize=10, fontweight="bold")
axA2a.set_ylim(0, ev_net_ws * 1.45)
axA2a.grid(True, axis="y", alpha=0.25)
axA2a.tick_params(labelsize=8)

# Scenario revenue CDF
s_nets   = stoch_summary["total_net"].values
s_probs  = stoch_summary["probability"].values
sort_idx = np.argsort(s_nets)
cdf_vals = np.cumsum(s_probs[sort_idx])
axA2b.step(s_nets[sort_idx], cdf_vals, color="#4e91c9", linewidth=2, where="post")
axA2b.axvline(ev_net_ws, color="#5cb85c", linestyle="--", linewidth=1.3,
              label=f"WS ${ev_net_ws:.2f}")
axA2b.axvline(ev_net_ts, color="#e87a2a", linestyle="--", linewidth=1.3,
              label=f"TS ${ev_net_ts:.2f}")
axA2b.axvline(0, color="black", linewidth=0.8, linestyle=":")
axA2b.fill_betweenx([0,1], s_nets.min(), 0, color="red", alpha=0.08, label="Loss")
axA2b.set_xlabel("Scenario Net ($/day)", fontsize=9)
axA2b.set_ylabel("Cumulative Probability", fontsize=9)
axA2b.set_title("Scenario Revenue CDF", fontsize=9, fontweight="bold")
axA2b.legend(fontsize=7.5)
axA2b.grid(True, alpha=0.25)
axA2b.tick_params(labelsize=8)

# ── (B) Monthly backtest: oracle revenue + LMP spread as driver ───────────────
month_labels = ["J","F","M","A","M","J","J","A","S","O","N","D"]
x = np.arange(12)
w = 0.35

ax_b_twin = axB2.twinx()
axB2.bar(x - w/2, monthly["opt_net"],        width=w, color="#4e91c9",
         alpha=0.85, label="Oracle ($/day)")
axB2.bar(x + w/2, monthly["naive_rank_net"], width=w, color="#9b59b6",
         alpha=0.85, label="Price-rank ($/day)")
ax_b_twin.plot(x, monthly["spread_lmp"], color="#e87a2a", marker="o",
               linewidth=1.6, markersize=5, label="LMP spread ($/MWh)")
ax_b_twin.set_ylabel("Daily LMP Spread ($/MWh)", fontsize=9, color="#e87a2a")
ax_b_twin.tick_params(axis="y", labelcolor="#e87a2a", labelsize=8)

axB2.set_xticks(x)
axB2.set_xticklabels(month_labels, fontsize=8)
axB2.set_xlabel("Month (2024)", fontsize=9)
axB2.set_ylabel("Avg Daily Net Revenue ($/day)", fontsize=9)
axB2.set_title("(B) Backtest 2024 by Month\nRevenue vs LMP spread driver",
               fontsize=10, fontweight="bold")
lines1, lbl1 = axB2.get_legend_handles_labels()
lines2, lbl2 = ax_b_twin.get_legend_handles_labels()
axB2.legend(lines1+lines2, lbl1+lbl2, fontsize=8, loc="upper left")
axB2.tick_params(labelsize=8)
axB2.grid(True, axis="y", alpha=0.25)
axB2.axhline(0, color="black", linewidth=0.6)

# ── (C) NPV vs capacity: arbitrage-only vs multiproduct ───────────────────────
E_vals   = sizing["E_MWh"].values
npv_vals = sizing["npv_$"].values

if multiproduct is not None:
    # Show NPV curves at each P_REG from the multiproduct sweep
    mp_pregs  = sorted(multiproduct["P_REG"].unique())
    mp_colors = plt.cm.plasma(np.linspace(0.08, 0.92, len(mp_pregs)))
    for i, p_reg in enumerate(mp_pregs):
        sub = multiproduct[multiproduct["P_REG"] == p_reg].sort_values("E_MWh")
        if sub.empty:
            continue
        lbl = f"P_REG=${p_reg:.0f}" if p_reg > 0 else "Arb only"
        ls  = "--" if p_reg == 0 else "-"
        axC2.plot(sub["E_MWh"], sub["npv_$"] / 1e3,
                  color=mp_colors[i], linewidth=1.6, linestyle=ls,
                  marker="o", markersize=3, label=lbl)
    axC2.axhline(0, color="black", linewidth=1.0, linestyle=":",
                 label="NPV = 0")
    axC2.set_ylabel("NPV ($k)", fontsize=9)
    axC2.set_xlabel("Battery Capacity (MWh)", fontsize=9)
    axC2.set_title("(C) NPV vs Capacity: Arbitrage + PJM RegD\n"
                   "Each curve = different RegD clearing price ($/MW-h)",
                   fontsize=10, fontweight="bold")
    axC2.legend(fontsize=7, loc="lower left", ncol=2)
    axC2.tick_params(labelsize=8)
    axC2.grid(True, alpha=0.25)
else:
    # Fallback: arbitrage-only NPV + revenue gap bar chart
    arb_rev  = sizing["annual_arb_$"].values
    anc_need = (sizing["ancillary_needed_$"].values
                if "ancillary_needed_$" in sizing.columns
                else np.zeros(len(E_vals)))
    ax_c2 = axC2.twinx()
    axC2.bar(E_vals, arb_rev / 1000, width=0.35, color="#5cb85c",
             alpha=0.85, label="Arbitrage revenue ($k/yr)")
    axC2.bar(E_vals, anc_need / 1000, width=0.35, bottom=arb_rev / 1000,
             color="#e87a2a", alpha=0.60, label="Ancillary needed ($k/yr)")
    be_line = [(334000*E + FIXED_CAPEX) / ANNUITY / 1000 + OM_PER_KW_YR * 0.5 * E
               for E in E_vals]
    axC2.plot(E_vals, be_line, "r--s", linewidth=1.6, markersize=4,
              label="Break-even revenue ($k/yr)")
    ax_c2.plot(E_vals, npv_vals / 1000, color="black", marker="^",
               linewidth=1.8, markersize=5, linestyle="-.", label="NPV ($k)")
    ax_c2.axhline(0, color="black", linewidth=0.7, linestyle=":")
    ax_c2.set_ylabel("NPV ($k)", fontsize=9)
    ax_c2.tick_params(labelsize=8)
    axC2.set_xlabel("Battery Capacity (MWh)", fontsize=9)
    axC2.set_ylabel("Annual Revenue ($k)", fontsize=9)
    axC2.set_title("(C) Sizing & Revenue Gap\nNPV (arbitrage only) + break-even analysis",
                   fontsize=10, fontweight="bold")
    lines1, lbl1 = axC2.get_legend_handles_labels()
    lines2, lbl2 = ax_c2.get_legend_handles_labels()
    axC2.legend(lines1+lines2, lbl1+lbl2, fontsize=7.5, loc="upper left")
    axC2.tick_params(labelsize=8)
    axC2.grid(True, axis="y", alpha=0.25)

# ── (D) NPV sensitivity heat map (CapEx x cycle life) ────────────────────────
capex_range   = [150, 200, 250, 300, 334, 400, 500]
ncycles_range = [3000, 4000, 5000, 6000, 7000, 8000, 10000]
oracle_2024   = float(backtest["opt_net"].sum())

npv_grid = np.zeros((len(ncycles_range), len(capex_range)))
for i, nc in enumerate(ncycles_range):
    for j, cp in enumerate(capex_range):
        cap = FIXED_CAPEX + cp * 1000.0
        om  = OM_PER_KW_YR * 0.5 * 1000.0
        npv_grid[i, j] = ((oracle_2024 - om) * ANNUITY - cap) / 1000.0

vmax = max(abs(npv_grid.min()), abs(npv_grid.max()))
norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
im = axD2.imshow(npv_grid, cmap="RdYlGn", norm=norm, aspect="auto")
cbar = plt.colorbar(im, ax=axD2, fraction=0.035, pad=0.04)
cbar.set_label("NPV ($k)", fontsize=8)
cbar.ax.tick_params(labelsize=7.5)

axD2.set_xticks(range(len(capex_range)))
axD2.set_yticks(range(len(ncycles_range)))
axD2.set_xticklabels([f"${c}" for c in capex_range], fontsize=7.5)
axD2.set_yticklabels([f"{n:,}" for n in ncycles_range], fontsize=7.5)
axD2.set_xlabel("CapEx ($/kWh all-in)", fontsize=9)
axD2.set_ylabel("LFP Cycle Life (cycles at 80% DoD)", fontsize=9)
axD2.set_title(f"(D) NPV Sensitivity to CapEx\n(1 MWh, 2024 oracle ${oracle_2024:,.0f}/yr, 7% WACC, 15yr)\n"
               r"[Row axis shows cycle life ref — NPV driven by CapEx column]",
               fontsize=9, fontweight="bold")

for i in range(len(ncycles_range)):
    for j in range(len(capex_range)):
        val = npv_grid[i, j]
        txt_color = "white" if abs(val) > vmax * 0.55 else "black"
        axD2.text(j, i, f"${val:.0f}k", ha="center", va="center",
                  fontsize=7, color=txt_color, fontweight="bold")

# Mark current parameters
if 334 in capex_range and 6000 in ncycles_range:
    ci, cj = ncycles_range.index(6000), capex_range.index(334)
    axD2.add_patch(plt.Rectangle((cj-.5, ci-.5), 1, 1, fill=False,
                                  edgecolor="blue", linewidth=2.5))
    axD2.text(cj, ci - 0.65, "current", ha="center", fontsize=7,
              color="blue", fontweight="bold")

c_panel = ("(C) shows NPV vs capacity with PJM RegD revenue at multiple clearing prices"
           if multiproduct is not None
           else "(C) shows arbitrage-only NPV gap vs break-even")
fig2.suptitle(
    "BESS Bidding Optimization -- Economic Analysis\n"
    "NREL ATB 2024: $334/kWh + $75k fixed  |  6,000 cycles  |  C_DEG=$27.83/MWh  |  7% WACC, 15-yr\n"
    + c_panel,
    fontsize=11, fontweight="bold", y=0.998
)

fig2_path = os.path.join(RES_DIR, "figure_2_economics.png")
fig2.savefig(fig2_path, dpi=160, bbox_inches="tight")
plt.close()
print(f"Saved: figure_2_economics.png")
print("\nDone.")
