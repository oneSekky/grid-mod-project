# ELEN 4510 — BESS Bidding Optimization: Project Timeline & Summary

**Course:** ELEN 4510 — Grid Modernization & Clean Tech, Columbia University  
**Team:** Sekander Ali, Gianna Gong  
**Semester:** Spring 2026

---

## Project Overview

This project develops an optimal bidding strategy for a grid-scale Battery Energy Storage System (BESS) participating in PJM's wholesale electricity market. The core question is: given uncertain future prices, how should a battery operator schedule charge and discharge to maximize risk-adjusted revenue while accounting for physical degradation costs?

The project produces a complete end-to-end pipeline: raw price data → scenario generation → stochastic MILP optimization → CVaR risk analysis → economic viability assessment → out-of-sample backtesting → presentation.

---

## Phase Deadlines

| Phase | Deliverable | Due Date | Status |
|-------|-------------|----------|--------|
| Phase 1 | One-slider (concept, literature, approach) | 2/17/2026 | Submitted |
| Phase 2 | Midterm progress report (one page) | 3/25/2026 | Submitted |
| Phase 3 | Final presentation (12 min, visual-first) | 4/26/2026 | Prepared |
| Phase 4 | Final project report | 5/13/2026 | In progress |

---

## Chronological Timeline

### March 24, 2026 — Project Setup & Data Pipeline (all within ~40 minutes)

**16:19 — `f88e735` Initial commit**  
Repository created with a bare `README.md`. No code yet.

**16:20 — `0ac0bea` Add tasks.md**  
A task breakdown document was written covering the full intended scope:
- Data pipeline (LMP cleaning, scenario generation)
- Deterministic MILP baseline
- Stochastic EV extension
- CVaR risk constraint implementation
- Out-of-sample backtesting on 2024 data
- Battery sizing sweep (0.5–10 MWh)
- Visualizations and report

This became the project's working checklist.

**16:31 — `16e8d2a` Add project briefing and midterm report template**  
`BESS_Project_Briefing.md` was written — a 278-line document intended as a full handoff brief for any agent or collaborator. It defines:
- Mathematical formulation (decision variables, objective, constraints in LaTeX-style pseudocode)
- Five literature anchors (Xu et al. degradation model, Rockafellar-Uryasev CVaR, Akbari-Dibavar hybrid stochastic-robust, Wu et al. CVaR framework, Gitizadeh sizing methodology)
- Data sources (PJM Data Miner 2 API, 2022–2024 LMP)
- Tool stack: Python, Gurobi, pandas/numpy, matplotlib, scikit-learn
- Status as of Phase 2: deterministic MILP was working; stochastic extension and CVaR were in progress

A midterm report Word template was also added.

**16:32 — `3f3607b` Merge from GitHub remote**  
Repository synced with the GitHub remote (`oneSekky/grid-mod-project`).

**16:42 — `5521fca` Add data pipeline: PJM LMP cleaning and scenario generation**  
`scripts/generate_scenarios.py` was written and executed for the first time. This script:
- Loads raw PJM system-wide real-time LMP data (2020–2023, ~35,000 daily profiles)
- Cleans outliers by clipping to the 1st–99th percentile range ($10.32–$152.91/MWh)
- Fills 4 missing hours via linear interpolation
- Removes duplicate timestamps
- Builds a matrix of 24-hour price profiles (one row per day)
- Applies k-means clustering to find representative price scenarios

**Outputs created:**
- `data/scenarios/scenarios.csv` — representative 24-hour price profiles
- `data/scenarios/scenario_metadata.csv` — per-scenario stats (mean, min, max LMP, peak hour)
- `data/scenarios/cleaning_log.csv` — audit record of the cleaning procedure
- `data/scenarios/scenario_fan.png` — fanplot of price paths by season

**16:49 — `41670c0` Add grid visualization of all 50 price scenarios**  
The scenario grid visualization was added to `generate_scenarios.py`. At this point the pipeline was producing **50 scenarios** (not yet stratified by season). The grid image (`scenario_grid.png`) showed all scenarios in a multi-panel layout.

**16:57 — `7a30cd5` Regen scenarios with season-stratified k-means (13/12/13/12)**  
A key methodological decision was made: instead of applying k-means globally, cluster within each season separately. This ensures winter, spring, summer, and fall price patterns each get representative coverage rather than being dominated by the most common seasonal pattern.

Initial split: 13 winter / 12 spring / 13 summer / 12 fall = 50 total scenarios.

All scenario files and visualizations were regenerated.

**17:00 — `5c32e34` Reduce to 10 scenarios per season (40 total)**  
The count was reduced from 50 to 40 (10 per season) to balance representativeness against computational tractability — 40 scenarios in a stochastic MILP is a manageable problem size while covering seasonal variation well.

Final scenario distribution:
- Winter (Dec/Jan/Feb): 10 scenarios, probabilities 0.07%–10.27%
- Spring (Mar/Apr/May): 10 scenarios, probabilities 0.41%–8.63%
- Summer (Jun/Jul/Aug): 10 scenarios, probabilities 0.55%–8.36%
- Fall (Sep/Oct/Nov): 10 scenarios, probabilities 0.21%–6.58%
- Probability sum: exactly 1.00

All scenario outputs were regenerated a final time. This is the dataset used for all subsequent optimization.

---

### March 25 – April 14, 2026 — Implementation Sprint (no commits, active development)

During the three weeks between the March 24 scenario commit and the April 15 mega-commit, all optimization scripts were written and run locally. Based on the breadth of the April 15 commit (8 new scripts, 44 result files), this represents the bulk of the implementation work.

The following was built and executed in this period (inferred from commit content):

1. **Deterministic MILP** (`optimize_deterministic.py`) — baseline formulation verified on three test cases (low-spread S1, high-spread S10, medium summer S24)
2. **Stochastic MILP** (`optimize_stochastic.py`) — wait-and-see (per-scenario oracle) and expected value formulations
3. **CVaR-constrained two-stage MILP** (`optimize_cvar.py`) — non-anticipativity enforced; parametric sweep across α ∈ {0.90, 0.95, 0.99} and 25 budget levels
4. **Out-of-sample backtest** (`backtest.py`) — 2024 price data (never seen during development) used to validate three strategies: optimized oracle, naive price-rank, naive fixed-hours
5. **Battery sizing sweep** (`optimize_sizing.py`) — NPV computed across 0.5–10 MWh capacities
6. **Multi-product co-optimization** (`optimize_multiproduct.py`) — energy arbitrage + PJM RegD regulation market co-scheduled in one formulation
7. **Post-processing analysis** (`analyze_results.py`) — EVPI, NPV sensitivity, break-even analysis
8. **Publication-quality visualization** (`visualize_all.py`) — two summary figures (6-panel and 4-panel) plus 20+ individual plots

**Solver note:** The briefing specified Gurobi as the primary solver. The final implementation used CVXPY with HiGHS (an open-source solver), noted as a fallback substitution.

---

### April 15, 2026 — `7631f6f` Full Pipeline Committed (21:00 EDT)

The largest commit in the project: **46 files changed, 5,116 lines inserted**.

Everything built during the implementation sprint was committed at once:

**New scripts (8):**
- `scripts/optimize_deterministic.py`
- `scripts/optimize_stochastic.py`
- `scripts/optimize_cvar.py`
- `scripts/backtest.py`
- `scripts/optimize_sizing.py`
- `scripts/optimize_multiproduct.py`
- `scripts/analyze_results.py`
- `scripts/visualize_all.py`

**New results (36 files):**

*Parameter logs (JSON):*
- `results/stochastic_params.json`, `results/cvar_params.json`, `results/backtest_params.json`, `results/deterministic_params.json`, `results/sizing_params.json`, `results/multiproduct_params.json`

*Tabular results (CSV):*
- `results/stochastic_results.csv` — 960 rows (24h × 40 scenarios) of hourly dispatch
- `results/stochastic_summary.csv` — per-scenario aggregated P&L
- `results/deterministic_cases.csv` — 3 test case dispatch tables
- `results/deterministic_verification.csv` — validation of deterministic vs. stochastic consistency
- `results/cvar_frontier.csv` — 25-point efficient frontier (α × CVaR budget)
- `results/backtest_daily.csv` — 364 daily realized net revenues for 3 strategies
- `results/backtest_summary.csv` — annual aggregate performance
- `results/sizing_sweep.csv` — NPV across 12 capacity points (0.5–10 MWh)
- `results/multiproduct_sweep.csv` — 80-point 2D sweep (capacity × RegD clearing price)
- `results/analysis_summary.csv` — 14-row report-ready summary table
- `results/analysis_sensitivity.csv` — NPV sensitivity grid (CapEx $/kWh × cycle life)

*Visualizations (PNG, 21 files):*
- Dispatch plots for S1, S10, S24 (deterministic test cases)
- Stochastic dispatch, SOC trajectories, revenue distribution
- CVaR dispatch comparison and efficient frontier
- Backtest cumulative revenue and monthly breakdown
- Sizing NPV and revenue curves
- Multi-product NPV and revenue stack plots
- Deterministic verification scatter
- EVPI bar, sensitivity heatmap, break-even chart
- `results/figure_1_model_overview.png` — 6-panel summary figure (539 KB)
- `results/figure_2_economics.png` — 4-panel economics figure (382 KB)

**New documentation:**
- `report.md` — full 12-minute presentation script with per-slide notes and cue marks

---

### April 20, 2026 — Presentation Polish (four commits, 17:47–18:40 EDT)

**17:47 — `08c7dc1` Restructure presentation to 11-slide visual-first format**  
The presentation script in `report.md` was reworked from an earlier structure into a clean 11-slide, 12-minute talk. The design principle adopted: slides are visual anchors only; one idea per slide; script carries all content.

Final slide structure:
1. Title & Team (1 min)
2. The Core Problem — price uncertainty and battery wear (1.5 min)
3. Objective & Class Connection — two-stage MILP, CVaR, NPV/EVPI (1 min)
4. State of the Art — five literature anchors (1.5 min)
5. Pipeline Overview — data to backtest (1 min)
6. MILP in Action — high-spread dispatch example S10 (1.5 min)
7. Managing Risk — CVaR efficient frontier (1 min)
8. Tools & Data — CVXPY + HiGHS, scikit-learn, PJM public data (1.5 min)
9. EVPI & Profitability Gap — $843/yr perfect info value, break-even gap (1 min)
10. Adding RegD Changes the Picture — regulation co-optimization, NPV > 0 at $25+/MWh (1 min)
11. Roadmap — 11-week sprint timeline with role assignments (1 min)

**17:55 — `31c2365` Revise team member roles and project explanation**  
`report.md` updated to correct attribution of individual contributions and refine how the project is explained to a technical audience unfamiliar with PJM market structure.

**18:33 — `3ae8367` Fix factual errors found during audit against raw data and result CSVs**  
An audit was run comparing the presentation script against the raw result CSVs. Several numbers in `report.md` were corrected. `scripts/generate_scenarios.py` was also updated — the commit message indicates a factual fix to the scenario description (likely the training data year range or scenario count wording).

**18:40 — `575a08c` Regenerate slide 6 dispatch plot with cleaner conventions**  
`results/deterministic_dispatch_s10.png` was regenerated. This is the high-spread winter scenario used as Slide 6's visual anchor (the "MILP in Action" slide). The regeneration applied cleaner plotting conventions — axis labels, color scheme, or legend formatting — before the presentation.

---

## What Was Built: Full Inventory

### Scripts

| File | Purpose |
|------|---------|
| `scripts/generate_scenarios.py` | PJM LMP → 40 season-stratified scenarios |
| `scripts/optimize_deterministic.py` | Deterministic 24h MILP baseline (3 test cases) |
| `scripts/optimize_stochastic.py` | Wait-and-see stochastic dispatch (40 scenarios) |
| `scripts/optimize_cvar.py` | Two-stage CVaR-constrained MILP with non-anticipativity |
| `scripts/backtest.py` | Out-of-sample validation on 2024 held-out data |
| `scripts/optimize_sizing.py` | NPV sweep across battery capacities 0.5–10 MWh |
| `scripts/optimize_multiproduct.py` | Energy arbitrage + PJM RegD co-optimization |
| `scripts/analyze_results.py` | EVPI, sensitivity, break-even post-processing |
| `scripts/visualize_all.py` | Two publication-quality summary figures |

### Data

| File | Description |
|------|-------------|
| `data/scenarios/scenarios.csv` | 40 representative 24-hour LMP profiles |
| `data/scenarios/scenario_metadata.csv` | Per-scenario statistics |
| `data/scenarios/cleaning_log.csv` | Data cleaning audit trail |
| `data/scenarios/scenario_fan.png` | Seasonal fanplot of price paths |
| `data/scenarios/scenario_grid.png` | 4×10 grid of all 40 scenarios |

### Documentation

| File | Description |
|------|-------------|
| `README.md` | Project title |
| `BESS_Project_Briefing.md` | Full agent/collaborator briefing (278 lines) |
| `tasks.md` | Task checklist |
| `report.md` | 12-minute presentation script (11 slides) |
| `Project-Mid-Term Review Report Template.docx` | Phase 2 deliverable template |

---

## Key Results & Findings

### Battery Parameters Used

| Parameter | Value | Source |
|-----------|-------|--------|
| Chemistry | LFP (Lithium Iron Phosphate) | NREL ATB 2024 |
| Energy capacity | 1 MWh (reference) | — |
| Power capacity | 0.5 MW (0.5C) | — |
| Round-trip efficiency | 93% charge, 93% discharge | — |
| SOC bounds | 10%–90% | — |
| CapEx | $334/kWh + $75k fixed BOS | NREL ATB 2024 |
| Cycle life | 6,000 cycles @ 80% DoD | Modern utility LFP |
| Degradation cost (arbitrage) | $27.83/MWh throughput | Xu et al. methodology |
| Degradation cost (regulation) | $3.48/MWh (~8× less, shallow DoD) | Xu et al. |
| Asset life | 15 years | — |
| Discount rate (WACC) | 7% | — |

### In-Sample Performance (40 scenarios, 2020–2023 training data)

| Metric | Value |
|--------|-------|
| Wait-and-see expected net revenue | $11.60/day ($4,236/yr) |
| Two-stage committed schedule E[Net] | $9.29/day ($3,393/yr) |
| EVPI (value of perfect daily foresight) | $2.31/day ($843/yr) |

The small EVPI ($843/yr) was a key insight: the 40-scenario distribution already captures most exploitable price variation. Better price forecasting would add only marginal value.

### Out-of-Sample Backtest (2024, 364 held-out days)

| Strategy | Mean Daily Net | Annual Total | % Positive Days |
|----------|---------------|--------------|-----------------|
| Optimized oracle (perfect daily hindsight) | $19.95 | $7,261 | 97.3% |
| Naive price-rank (degradation-aware) | $9.99 | $3,637 | 29.7% |
| Naive fixed hours (off-peak charge, on-peak discharge) | $1.98 | $721 | 4.1% |

Even with perfect daily hindsight, the oracle earns only $7,261/yr. The stochastic model's in-sample estimate ($3,393/yr) corresponds to capturing ~47% of the theoretical maximum.

### Economic Viability — Arbitrage Only

| Item | Annual Value |
|------|-------------|
| Two-stage stochastic revenue | $3,393 |
| Fixed O&M cost | -$5,000 |
| Annualized CapEx (1 MWh, 15yr, 7%) | -$44,856 |
| **NPV (15 years)** | **-$415,962** |

**Arbitrage alone does not justify the investment.** The break-even ancillary revenue needed is ~$49,906/yr, requiring $46,513/yr beyond arbitrage earnings.

### CVaR Risk-Return Tradeoff

The 25-point sweep across α ∈ {0.90, 0.95, 0.99} showed a smooth efficient frontier:
- Unconstrained optimum: $9.29/day expected net revenue
- Most conservative constraint: $0.23/day expected net revenue
- Tradeoff rate: roughly 1% reduction in expected revenue per $0.5 increase in CVaR floor

### Battery Sizing (Arbitrage Only)

All sizes from 0.5 MWh to 10 MWh produce negative NPV under arbitrage-only revenue:
- 0.5 MWh: NPV = -$245,481
- 1.0 MWh: NPV = -$415,962
- 10.0 MWh: NPV = -$3,484,620

### Multi-Product Co-Optimization (Energy + PJM RegD Regulation)

Adding RegD regulation co-optimization fundamentally changes the investment case:
- Breakeven RegD clearing price: ~$25/MWh (at 1 MWh)
- At $30/MWh (historical PJM average): 1 MWh NPV ≈ +$162,000
- At $30/MWh, 10 MWh scale: NPV ≈ +$2.3M

**Conclusion: Regulation market participation is necessary for a viable business case.**

### Deterministic Verification

Revenue comparison across all 40 scenarios between deterministic (per-scenario oracle) and stochastic formulations: absolute error < $0.000001 across all scenarios. Solver consistency confirmed.

---

## Pipeline Execution Order

```
PJM Raw Data (2020–2023 RT LMP)
         │
         ▼
generate_scenarios.py
  → 40 season-stratified scenarios (probabilities sum to 1.00)
  → scenario_fan.png, scenario_grid.png
         │
    ┌────┴────────────────────────────────────────────┐
    ▼                                                 │
optimize_deterministic.py                             │
  → 3 test cases (S1 low-spread,                     │
    S10 high-spread, S24 medium)                      │
  → deterministic_cases.csv                          │
  → deterministic_dispatch_s{1,10,24}.png            │
    │                                                 │
    ▼                                                 │
optimize_stochastic.py                               │
  → wait-and-see dispatch (40 scenarios)             │
  → stochastic_results.csv, summary.csv              │
  → stochastic_dispatch.png, soc.png, revenue_dist  │
    │                                                 │
    ▼                                                 │
optimize_cvar.py                                     │
  → two-stage CVaR sweep (25 points)                │
  → cvar_frontier.csv                               │
  → cvar_frontier.png, cvar_dispatch_comparison.png │
    │                                                 │
    ├──────────────────────────────────────────────┐  │
    ▼                                              ▼  │
optimize_sizing.py               optimize_multiproduct.py
  → sizing_sweep.csv               → multiproduct_sweep.csv
  → sizing_npv.png                 → multiproduct_npv.png
    │                                              │
    └──────────────────┬───────────────────────────┘
                       ▼
                 backtest.py
              (2024 held-out data)
                 → backtest_daily.csv
                 → backtest_summary.csv
                 → backtest_cumulative.png
                 → backtest_monthly.png
                       │
                       ▼
               analyze_results.py
                 → analysis_summary.csv
                 → analysis_sensitivity.csv
                 → analysis_evpi.png
                 → analysis_breakeven.png
                 → analysis_sensitivity.png
                       │
                       ▼
               visualize_all.py
                 → figure_1_model_overview.png (6-panel)
                 → figure_2_economics.png (4-panel)
                       │
                       ▼
                  report.md
            (12-min presentation script)
```

---

## Conclusions

1. **Pure energy arbitrage is not economically viable** for a 1 MWh LFP system in PJM at current capital costs ($334/kWh NREL ATB 2024). NPV is strongly negative at any system size.

2. **Regulation market participation changes the picture.** At historical PJM RegD clearing prices (~$30/MWh), even a 1 MWh system reaches positive NPV. A 10 MWh system reaches ~$2.3M NPV.

3. **Perfect price information is worth very little.** EVPI is only $843/yr, indicating the 40-scenario distribution already captures most of the price variation that can be exploited. Investing in better price forecasting has limited financial upside.

4. **The stochastic model captures ~47% of the theoretical maximum.** The two-stage committed schedule earns $3,393/yr vs. $7,261/yr for the perfect-hindsight oracle — a reasonable real-world performance given the commitment structure.

5. **CVaR efficiently encodes risk aversion.** The efficient frontier is smooth; a risk-averse operator can reduce downside exposure at a modest cost to expected revenue (~1% per $0.5 floor increase).

6. **The formulation is market-agnostic.** The two-stage MILP with non-anticipativity constraints is parameterized for PJM but applicable to CAISO, ERCOT, or NYISO with product definition changes.

---

## Literature Used

| Paper | Authors | Role |
|-------|---------|------|
| Factoring Cycle Aging Cost in Electricity Markets | Xu, Zhao, Zheng, Litvinov, Kirschen | Primary degradation cost model (C_DEG calibration) |
| Hybrid Stochastic-Robust Storage Arbitrage | Akbari-Dibavar, Zare, Nojavan | Two-stage uncertainty structure |
| CVaR Framework for Renewable Management | Wu, Wu, Wu, Tang, Mao | CVaR hard-constraint formulation, alpha calibration |
| Battery Capacity Determination in PV Systems | Gitizadeh, Fakharzadegan | Sizing co-optimization methodology |
| Energy Trading Strategy for Storage-Based Renewables | Miseta, Fodor, Vathy-Fogarassy | Multi-product ancillary service structure |

---

*Generated 2026-04-27.*
