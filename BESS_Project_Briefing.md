# BESS Bidding Optimization — Complete Project Briefing

> This document is a full briefing for an AI agent taking over or assisting with this project. Read everything before acting. Do not assume prior knowledge.

---

## 0. Quick Reference

| Field | Detail |
|---|---|
| Course | ELEN 4510 — Grid Modernization & Clean Tech, Columbia University |
| Project Title | BESS Bidding Optimization |
| Team | Sekander Ali, Gianna Gong |
| Phase 1 (One-Slider) | Submitted 2/17/2026 |
| Phase 2 (Midterm Progress Report) | Due 3/25/2026 — one page |
| Phase 3 (Final Presentation / Demo) | Due 4/26/2026 — PPT template shared by 3/25/26 |
| Phase 4 (Final Report) | Due 5/13/2026 — report template shared by 3/25/26 |
| Primary Language | Python |
| Solver | Gurobi (gurobipy) |
| Market Focus | PJM wholesale electricity market |

---

## 1. Project Objective

Build an **optimal bidding strategy** for a battery energy storage system (BESS) participating in electricity wholesale markets, specifically targeting electricity price arbitrage across day-ahead (DA) and real-time (RT) market products.

The project has two intertwined goals:

1. **Strategy goal** — determine the charge/discharge schedule that maximizes risk-adjusted revenue from price arbitrage, comparing an expected-value (EV) objective against a CVaR-constrained formulation.
2. **Sizing goal** — identify specific battery hardware configurations (capacity in MWh, power in MW) whose economics are justified by the projected arbitrage revenues.

The formulation must be general enough to apply to any ISO/RTO market structure, using PJM as the primary case study.

---

## 2. Background and Motivation

Battery energy storage is increasingly participating in wholesale electricity markets by buying cheap energy during low-price periods and selling it back during high-price periods (arbitrage). The challenge is that future prices are uncertain, operational costs are non-trivial, and battery degradation from cycling is an economic factor that must be internalized.

Standard expected-value optimization ignores downside risk. CVaR (Conditional Value-at-Risk) addresses this by constraining or penalizing the worst-tail outcomes. The project quantifies the return-risk tradeoff between these two paradigms in the context of storage dispatch.

Key physical and economic constraints that make this non-trivial:

- Battery state of charge (SOC) is a dynamic state variable — charging and discharging decisions couple across time periods.
- Round-trip efficiency losses mean energy out is always less than energy in.
- Depth-of-discharge (DoD) limits protect battery longevity — the SOC cannot freely range from 0 to 100%.
- Charge and discharge cannot occur simultaneously — requires binary (MILP) logic.
- Degradation cost from cycling must be priced into the objective; otherwise the optimizer will over-cycle and destroy the battery for short-term profit.
- Capital and installation costs must be recovered over the asset's operating life to justify the investment.

---

## 3. Mathematical Formulation

### 3.1 Decision Variables

| Variable | Description |
|---|---|
| `p_c(t)` | Charging power at hour t (MW) |
| `p_d(t)` | Discharging power at hour t (MW) |
| `s(t)` | State of charge at hour t (MWh) |
| `u_c(t)` | Binary: 1 if charging at hour t |
| `u_d(t)` | Binary: 1 if discharging at hour t |
| `E` | Battery energy capacity (MWh) — for sizing subproblem |
| `P` | Battery power capacity (MW) — for sizing subproblem |

### 3.2 Objective Function (Expected Value version)

Maximize expected revenue minus operational and degradation costs across all scenarios:

```
max  E[ sum_t ( lambda(t) * p_d(t) - lambda(t) * p_c(t) ) ] - C_deg * Throughput - C_cap
```

Where:
- `lambda(t)` is the LMP (locational marginal price) at hour t
- `C_deg` is the per-MWh degradation cost derived from the cycle-life curve (Xu et al. methodology)
- `Throughput` is total energy cycled over the scheduling horizon
- `C_cap` is amortized capital cost (annualized CapEx / operating hours)

### 3.3 CVaR Extension

The CVaR-constrained variant adds:

```
CVaR_alpha( Revenue ) >= CVaR_budget
```

Where alpha is the confidence level (e.g., 95%) and CVaR_budget is a minimum acceptable tail revenue. This is implemented via the standard Rockafellar-Uryasev linearization using an auxiliary variable `eta` (Value-at-Risk threshold) and scenario-level shortfall variables `z(s)`:

```
CVaR = eta - (1/(1-alpha)) * E[max(0, eta - Revenue(s))]
```

### 3.4 Core Constraints

```
# Energy balance (SOC dynamics)
s(t) = s(t-1) + eta_c * p_c(t) - (1/eta_d) * p_d(t)   for all t

# SOC bounds
SOC_min * E <= s(t) <= SOC_max * E

# Power bounds
0 <= p_c(t) <= P * u_c(t)
0 <= p_d(t) <= P * u_d(t)

# Mutual exclusivity (no simultaneous charge and discharge)
u_c(t) + u_d(t) <= 1

# Ramp limits (if applicable)
|p_c(t) - p_c(t-1)| <= RampRate
|p_d(t) - p_d(t-1)| <= RampRate

# Boundary conditions
s(0) = s_init
s(T) >= s_final_min   (optional: return-to-initial constraint)
```

### 3.5 Parameters (Representative Values)

| Parameter | Symbol | Value / Range |
|---|---|---|
| Round-trip efficiency (charge) | eta_c | 0.92-0.95 |
| Round-trip efficiency (discharge) | eta_d | 0.92-0.95 |
| Minimum SOC fraction | SOC_min | 0.10 |
| Maximum SOC fraction | SOC_max | 0.90 |
| Degradation cost | C_deg | Calibrated from Xu et al. cycle-life curves |
| CVaR confidence level | alpha | 0.90-0.95 (parametric sweep) |
| Scenario count | S | 20-50 (baseline); 200+ (extended) |

---

## 4. Literature Base

All five papers below have been read and are actively informing the model. Do not suggest replacing them — augment if needed.

### Paper 1 — Hybrid Stochastic-Robust Storage Arbitrage
**Authors:** Alireza Akbari-Dibavar, Kazem Zare, Sayyad Nojavan
**Role in project:** Informs the two-stage uncertainty treatment. The first stage sets the day-ahead bid schedule; the second stage handles real-time deviations. The hybrid structure balances scenario-based stochastic optimization against worst-case robustness.

### Paper 2 — CVaR Framework for Renewable Management with DGs and EVs
**Authors:** Jiekang Wu, Zhijiang Wu, Fan Wu, Huiling Tang, Xiaoming Mao
**Role in project:** Supplies the mathematical structure for embedding CVaR as a hard constraint (not just a penalty). Calibration guidance for the risk-aversion parameter alpha comes from this paper.

### Paper 3 — Battery Capacity Determination in Grid-Tied PV Systems
**Authors:** Mohsen Gitizadeh, Hamid Fakharzadegan
**Role in project:** Guides the capacity sizing methodology — specifically how to co-optimize dispatch scheduling and hardware specification. The interaction between the operational dispatch model and the sizing decision is adapted from this work.

### Paper 4 — Energy Trading Strategy for Storage-Based Renewables
**Authors:** Tamás Miseta, Attila Fodor, Ágnes Vathy-Fogarassy
**Role in project:** Extends the market product scope beyond pure energy arbitrage to include ancillary services. Informs the multi-product bid structure and how to represent different revenue streams within one formulation.

### Paper 5 — Factoring Cycle Aging Cost of Batteries in Electricity Markets
**Authors:** Bolun Xu, Jinye Zhao, Tongxin Zheng, Eugene Litvinov, Daniel S. Kirschen
**Role in project:** The primary source for the degradation cost model. Provides the per-cycle penalty derivation tied to depth-of-discharge and cycle count, which is embedded as an endogenous cost in the objective function.

---

## 5. Data

### 5.1 Price Data
- **Source:** PJM Data Miner 2 API
- **Type:** Day-ahead LMP (locational marginal price) and real-time LMP
- **Period:** 2022-2024 (3 years of hourly data)
- **Nodes:** Selected PJM nodes (specific node TBD based on congestion characteristics)
- **Format:** Hourly, $/MWh
- **Known issues:** Negative price spikes and anomalous congestion-driven outliers in some hours; a cleaning and imputation procedure is in development.

### 5.2 Load Data
- **Source:** PJM historical load data (same window as price data)
- **Use:** Auxiliary feature for price forecast / scenario generation; not directly in the optimization constraints.

### 5.3 Battery Technical Parameters
- **Source:** Manufacturer datasheets for representative LFP (lithium iron phosphate) systems
- **Sizes evaluated:** 1 MWh and 4 MWh reference systems
- **Parameters collected:** Round-trip efficiency, max C-rate, DoD limits, cycle-life curves at various DoD levels

---

## 6. Tools and Stack

| Tool | Purpose |
|---|---|
| Python 3.x | All modeling, data processing, and analysis |
| gurobipy | Primary optimization solver (MILP and stochastic extensions) |
| pandas / numpy | Data handling and numerical computation |
| matplotlib / seaborn | Visualizations (SOC trajectories, bid curves, risk-return frontier) |
| scikit-learn | k-means clustering for scenario generation |
| PJM Data Miner 2 API | Historical LMP and load data retrieval |

Fallback solver if Gurobi licensing becomes an issue: PuLP with CBC, or CVXPY with open-source solvers (CLARABEL, ECOS). Performance will degrade on large stochastic instances.

---

## 7. Current Status (as of 3/25/2026)

### Completed
- Full literature review of all five papers; synthesis notes exist.
- PJM day-ahead and real-time LMP data pulled for 2022-2024.
- Load data acquired for the same window.
- Battery parameter collection complete for 1 MWh and 4 MWh LFP systems.
- Baseline deterministic MILP formulation is coded in Python with Gurobi.
- Baseline model solves a 24-hour single-day instance successfully, returning an optimal dispatch schedule and objective value.
- Scenario generation framework started: k-means clustering approach applied to historical LMP sequences; target is 20-50 representative scenarios.

### In Progress
- Stochastic two-stage extension of the Gurobi model (integrating scenario tree).
- Data cleaning pipeline for anomalous price spikes.
- Degradation cost calibration (piecewise-linear approximation of manufacturer cycle-life curves across partial DoD values).

### Not Yet Started
- CVaR constraint implementation and parametric sweep over alpha.
- Out-of-sample backtesting on 2024 price data.
- Joint capacity-dispatch sizing optimization (0.5 MWh to 10 MWh range).
- Final visualizations: SOC trajectory plots, bid curves, efficient frontier chart.
- Final report and presentation preparation.

---

## 8. Known Challenges and Open Issues

### 8.1 Price Data Noise
Several hours in the PJM dataset contain negative or anomalously high LMP spikes driven by transmission congestion events. These outliers distort the scenario tree if included raw. A cleaning step (cap at percentile threshold + linear interpolation for missing intervals) is being developed.

### 8.2 Scenario Count vs. Solve Time
Finer scenario trees improve accuracy but increase solve time. Initial tests with 50 scenarios run in approximately 3 minutes per instance. Scaling to 200+ scenarios will require decomposition — Benders decomposition or sample average approximation (SAA) are the leading candidates.

### 8.3 Degradation Model Calibration
Manufacturer cycle-life curves are specified at fixed DoD values (e.g., 80%, 60%, 40%). The optimizer dispatches at continuous intermediate DoD levels, requiring a piecewise-linear approximation. This adds auxiliary binary variables and increases problem size. The approximation accuracy vs. solve time tradeoff is still being calibrated.

### 8.4 CVaR Parameter Selection
The appropriate confidence level (alpha) and minimum CVaR budget are not obvious for a storage asset in a volatile ISO market. The plan is a grid search across alpha in {0.90, 0.95, 0.99} and several CVaR budget levels, presenting the full efficient frontier rather than a single configuration.

### 8.5 Market Structure Generalizability
The formulation uses PJM-specific product definitions (DA energy, RT energy, and potentially RegD ancillary). To make the model genuinely portable to CAISO, ERCOT, or NYISO, the bid structure needs to be parameterized as inputs rather than hardcoded. Time is allocated to document this cleanly in the final report.

---

## 9. Deliverables Schedule

| Date | Deliverable | Weight | Status |
|---|---|---|---|
| 2/17/2026 | One-slider (concept, literature, approach, data & tools) | 10% | Submitted |
| 3/25/2026 | Midterm progress report — one page (summary, work done, future work, challenges) | 10% | Submitted |
| 4/26/2026 | Final presentation / demo — PPT (template provided 3/25/26) | 10% | Pending |
| 5/13/2026 | Final project report (template provided 3/25/26) | 10% | Pending |

Note: The four deliverables above total 40% of the project grade. The remaining 60% is allocated to components not detailed in the provided rubric (likely implementation quality, analysis depth, and results).

---

## 10. Expected Final Outputs

The final project should produce all of the following:

1. **Optimal dispatch schedules** — hourly charge/discharge power and SOC trajectories for representative price scenarios under both EV and CVaR formulations.
2. **Risk-return efficient frontier** — a curve plotting expected revenue vs. CVaR across the alpha parametric sweep, clearly showing the cost of risk aversion.
3. **Battery sizing recommendation** — an NPV analysis across system sizes (0.5-10 MWh) identifying the capacity that maximizes net present value given the optimized dispatch strategy.
4. **Backtesting results** — out-of-sample realized performance on 2024 price data, comparing the optimized policy against naive heuristics (e.g., always charge off-peak, always discharge peak).
5. **Generalizable formulation** — a clearly documented mathematical model with parameterized market product inputs, applicable beyond PJM.

---

## 11. Agent Instructions

When assisting with this project, follow these rules:

- All code should be written in Python unless explicitly asked otherwise.
- Use gurobipy as the primary solver. If Gurobi is unavailable, fall back to CVXPY with an appropriate open-source solver and note the substitution.
- Variable naming should be consistent with Section 3.1 of this document.
- When generating optimization code, always include constraint comments explaining the physical meaning.
- When touching data pipelines, preserve the raw PJM data files and operate on copies.
- CVaR should be implemented using the Rockafellar-Uryasev linearization (not approximations).
- Do not simplify the degradation model to a fixed constant without flagging it — the endogenous per-cycle cost is a core contribution of the project.
- When generating plots, label axes with units (MW, MWh, $/MWh) and include scenario bands where applicable.
- The project must remain reproducible: seed all random operations, log all parameter choices, and document any hardcoded values.
