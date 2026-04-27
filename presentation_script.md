# ELEN 4510 — BESS Bidding Optimization
## Comprehensive Presentation Script
**Target length:** 12 minutes | **11 slides across 6 sections**

Design principle: slides are visual anchors only. One idea per slide. Script carries the content.

---

## Timing Summary

| Section | Slides | Cumulative Time |
|---------|--------|----------------|
| 1 — Introduction | 1 | 0:00 – 1:00 |
| 2 — Scope | 2, 3 | 1:00 – 3:30 |
| 3 — State of the Art | 4 | 3:30 – 5:00 |
| 4 — Methodology | 5, 6, 7 | 5:00 – 8:30 |
| 5 — Tools, Data & Backtest | 8 | 8:30 – 10:00 |
| 6 — Results & Roadmap | 9, 10, 11 | 10:00 – 12:00 |

---

---

## SECTION 1 — Introduction

### SLIDE 1: Title & Team
*[~1 min]*

**ON THE SLIDE:**
```
Battery Energy Storage Bidding Optimization

Sekander Ali
Gianna Gong

ELEN 4510  ·  Spring 2026
```

**PRESENTER SAYS:**

"We're Sekander and Gianna. The question we tackled is one that every grid-scale battery
operator wakes up to each morning: given that you don't know what electricity prices will do
today, how do you schedule your battery to make money — without grinding it into the ground?

We built an end-to-end computational pipeline that answers that question. It goes from four
years of raw wholesale price data, through a mathematical optimization model that commits
a charge-and-discharge schedule under price uncertainty, through a formal risk framework,
all the way to an economic verdict: can this business actually make money?

The short answer is: not on arbitrage alone. The longer answer is what the next eleven
minutes are about."

---

---

## SECTION 2 — Scope of the Project

### SLIDE 2: The Core Problem
*[~1.5 min]*

**ON THE SLIDE:**
```
Buy low.  Sell high.
But you have to decide now.
How do you know what's low and what's high?
```
![Scenario price fan — 40 seasonal price paths](results/figure_1_model_overview.png)
*(crop to scenario fan panel)*

**PRESENTER SAYS:**

"This fan chart shows forty plausible price paths for a single day in PJM — the largest
wholesale electricity market in North America. Each line is one scenario our model
considers. Prices range from near zero overnight — that's surplus wind flooding the
grid — to over $150 during a summer peak demand event. The money is in the spread:
charge at the trough, discharge at the peak.

The catch is timing. PJM's day-ahead market closes the morning before delivery. You have
to submit a complete 24-hour charge-and-discharge schedule before a single hour of that
day has played out. You're committing to a plan for a future you can't see yet.

There's a second layer: every megawatt-hour you push through the battery physically
wears it down. The cells degrade. A utility-scale LFP system costs over $300 per
kilowatt-hour installed. If you trade too aggressively on a flat-price day, you lose
money twice — once from the thin spread, and again from the wear. The degradation cost
has to be priced into every dispatch decision.

That is the precise problem: maximize expected net revenue over uncertain price
futures, in real time, subject to physics and battery wear."

---

### SLIDE 3: Objective & Class Connection
*[~1 min]*

**ON THE SLIDE:**
```
Objective
  Maximize expected net revenue over uncertain price scenarios
  subject to physical and degradation constraints

  → extend to co-optimize energy arbitrage + ancillary services

Class connection
  Two-stage stochastic MILP  ·  CVaR risk management  ·  NPV / EVPI analysis
```

**PRESENTER SAYS:**

"Formally: we maximize probability-weighted net revenue across a distribution of
possible price days, minus degradation cost, subject to power limits, energy capacity,
round-trip efficiency losses, and a hard mutual-exclusivity constraint — the battery
cannot charge and discharge at the same time, which requires binary decision variables,
making this a mixed-integer program.

The extension co-optimizes a second revenue stream — PJM's RegD regulation market —
alongside energy arbitrage. That's where the commercial viability story unfolds.

This project uses the class toolkit directly. The two-stage stochastic MILP handles
the day-ahead commitment under uncertainty. CVaR manages tail risk. NPV frames the
investment question, and EVPI tells us how much better price forecasting would actually
be worth. These aren't decorative — each one generates a concrete number that drives
the conclusion."

---

---

## SECTION 3 — State of the Art

### SLIDE 4: What the Literature Says
*[~1.5 min]*

**ON THE SLIDE:**
```
Battery degradation
  Xu et al. (2018)    →  electrochemical $/MWh cycle cost
  NREL ATB 2024       →  $334/kWh installed (LFP utility-scale)

Stochastic optimization
  Rockafellar & Uryasev (2000)  →  CVaR linearization
  Akbari-Dibavar et al.          →  hybrid stochastic-robust storage dispatch

Ancillary services
  Miseta et al.      →  multi-product bid structure for storage
  FERC Order 841     →  opened ancillary markets to battery storage

Gap we fill:
  End-to-end pipeline  ·  true out-of-sample 2024 backtest  ·  commercial viability answer
```

**PRESENTER SAYS:**

"Three threads of prior work anchor our approach.

On battery economics: Xu et al.'s 2018 paper gives us a rigorous electrochemical model
that converts cycling depth and frequency into a dollar cost per megawatt-hour. We use
this to derive the $27.83-per-MWh degradation penalty embedded in the objective — it's
not a rule of thumb, it's physics. NREL's Annual Technology Baseline gives us the $334
per kilowatt-hour capital cost, which is the 2024 industry standard for utility LFP.

On optimization: Rockafellar and Uryasev's CVaR linearization is the mathematical
foundation for our risk constraint — it lets us impose a tail-revenue floor without
leaving the linear framework. Akbari-Dibavar's hybrid stochastic-robust formulation
informed how we structure the two-stage commitment.

On markets: FERC Order 841, issued in 2018, is the regulatory event that made the
RegD co-optimization a real commercial option. Before that ruling, batteries couldn't
participate in ancillary service markets on equal terms with generators.

The gap we fill: most papers present in-sample results. We hold out all of 2024 as
a genuine test set — never touched during development. And we go further than
'the model works' — we close the loop and answer whether it makes money."

---

---

## SECTION 4 — Methodology

### SLIDE 5: Pipeline Overview
*[~1 min]*

**ON THE SLIDE:**
```
2020–2023 PJM RT LMP  (~35,000 daily profiles)
           ↓
  Season-stratified k-means clustering
  40 scenarios · 10 per season · probabilities sum to 1.00
           ↓
  Two-stage stochastic MILP
  + CVaR risk constraint sweep
           ↓
  2024 out-of-sample backtest · EVPI · break-even analysis
           ↓
  RegD co-optimization · NPV sweep · sizing recommendation
```

**PRESENTER SAYS:**

"The pipeline has four stages, each one's output feeding the next.

Stage one converts raw hourly price data into forty representative 24-hour scenarios.
We iterate on this — I'll come back to the design decisions. Stage two runs the
optimization models against those scenarios. Stage three validates everything on
held-out 2024 data and computes the economic summary. Stage four adds the regulation
market and answers the sizing question.

A few design choices worth flagging: we used season-stratified k-means — clustering
within each season separately — rather than global clustering. Without that, the
algorithm would over-represent summer and under-represent winter, since summer has
more price variation. We also deliberately reduced from fifty to forty scenarios after
seeing that the marginal scenarios were nearly identical duplicates that added solve
time without adding information."

---

### SLIDE 6: The MILP — Dispatch in Action
*[~1.5 min]*

**ON THE SLIDE:**

![High-spread dispatch — charge overnight, discharge peaks](results/deterministic_dispatch_s10.png)

**PRESENTER SAYS:**

"This is what the model actually produces on a high-spread winter day — scenario ten,
one of the more favorable days in our training set. Top panel shows the price. Bottom
panel shows the battery's response.

Overnight, prices sit in the twenties. The model fills the battery to 90% of capacity
— the upper SOC limit we impose to protect longevity. Then it holds. When the morning
peak hits $120, it discharges hard. Prices dip through midday, so it charges back up.
Then the evening peak fires and it discharges again to its 10% floor.

The MILP mechanics behind this: we have continuous variables for charge power and
discharge power at each of 24 hours, a state-of-charge trajectory that links them
hour by hour via the energy balance equation, and binary variables that prevent
simultaneous charging and discharging. The degradation cost — $27.83 per megawatt-hour
— is added to the effective buy price and subtracted from the effective sell price.
The battery only trades when the spread clears that hurdle.

Net revenue on this day after degradation is $66. On a typical scenario it's closer
to $9. On flat-price days the model correctly decides not to trade at all — the binary
variables go to zero and the battery sits idle. That's the right answer."

---

### SLIDE 7: Managing Risk — CVaR Frontier
*[~1 min]*

**ON THE SLIDE:**

![CVaR efficient frontier](results/cvar_frontier.png)

**PRESENTER SAYS:**

"The stochastic model maximizes expected net revenue — the probability-weighted average
across all forty scenarios. But an operator running a merchant asset may care as much
about bad days as average days. A string of low-revenue scenarios in a bad season can
stress project finances even if the annual average looks acceptable.

We add a CVaR constraint using the Rockafellar-Uryasev linearization. CVaR at the
ninety-fifth percentile means: guarantee a floor on the average revenue of the worst
five percent of scenarios. We sweep that floor across twenty-five budget levels and
three confidence values — 90, 95, and 99 percent.

Each point on this curve is an optimal solution at a different risk tolerance. The
starred point is the unconstrained expected-value optimum at $9.29 per day. Moving
left along the frontier, you give up expected revenue to protect against tail losses.
The rate of exchange is roughly one percent of expected revenue per half-dollar
increase in the CVaR floor. A risk-neutral operator sits at the star; a risk-averse
operator accepts a small reduction in expected return for meaningful downside
protection."

---

---

## SECTION 5 — Tools, Data & Backtest

### SLIDE 8: Tools & Data
*[~1.5 min]*

**ON THE SLIDE:**
```
Data
  PJM RT LMP 2020–2023  (training)    ~35,000 daily profiles · clipped p01=$10.32 / p99=$152.91
  PJM RT LMP 2024        (backtest)   364 days, locked away before development began
  NREL ATB 2024          (costs)      $334/kWh LFP · $75k fixed BOS
  PJM RegD               (regulation) historical clearing prices & mileage ratios

Software
  CVXPY + HiGHS        MILP solver (open-source)
  scikit-learn         k-means scenario generation
  pandas / NumPy       data pipeline
  matplotlib           visualization

Battery (reference system)
  0.5 MW / 1 MWh LFP  ·  93% one-way efficiency  ·  SOC bounds [10%, 90%]
  C_DEG $27.83/MWh (arbitrage)  ·  $3.48/MWh (RegD, 8× lower)
```

![2024 out-of-sample backtest — cumulative revenue, three strategies](results/backtest_cumulative.png)

**PRESENTER SAYS:**

"Everything runs on publicly available data. PJM publishes hourly real-time LMP going
back years — we pulled 2020 through 2023 for training. Before writing a single line
of optimization code, we locked 2024 away completely. That discipline is what makes
the backtest meaningful: no lookahead, no tuning, no second chances.

The cleaning step clips price outliers to the 1st-and-99th-percentile band —
$10.32 to $152.91 per megawatt-hour — and linearly interpolates four missing hours.
One audit log entry confirmed the cleaning was clean.

We originally planned to use Gurobi as the solver — it's the standard in academia
for this class of problem. We substituted CVXPY with the open-source HiGHS backend.
Everything is reproducible with no license requirements.

This backtest chart is the payoff of the holdout discipline. Three strategies on the
same 364 days in 2024: the oracle with perfect daily price foresight earns $7,261
over the year; a degradation-aware price-rank heuristic earns $3,637; a fixed
off-peak-charge, on-peak-discharge schedule earns only $721. The gap between those
three lines tells you how much structure in the optimization is actually worth — and
it's real performance, not fit to training data."

---

---

## SECTION 6 — Results & Roadmap

### SLIDE 9: EVPI & The Profitability Gap
*[~1 min]*

**ON THE SLIDE:**

![EVPI bar and scenario revenue CDF](results/analysis_evpi.png)

**PRESENTER SAYS:**

"Two numbers define the project's conclusion before we get to the RegD result.

First: Expected Value of Perfect Information. EVPI is the maximum you would pay for
a perfect price forecast — it's the gap between knowing tomorrow's prices exactly
and having to commit a schedule blindly. For a one-megawatt-hour battery in PJM,
that number is $843 per year. Our forty-scenario distribution is already capturing
most of the exploitable price variation. A dramatically better forecasting model
would move the needle less than a thousand dollars annually — not worth investing in.

Second: the profitability gap. At NREL capital costs and a 7% cost of capital, a one
megawatt-hour system needs roughly $50,000 per year in revenue to break even. Our
two-stage stochastic model earns $3,393 in-sample. The 2024 oracle — perfect daily
hindsight, an upper bound no real operator can achieve — earns $7,261. Either way,
arbitrage revenue covers less than 15 cents on the dollar of what's needed. Something
else has to pay the bill."

---

### SLIDE 10: Adding RegD Changes the Picture
*[~1 min]*

**ON THE SLIDE:**

![Revenue stack and NPV vs RegD clearing price](results/multiproduct_revenue.png)

**PRESENTER SAYS:**

"That something else is PJM's RegD regulation market. RegD pays a battery to follow
a fast-response signal that balances frequency on the grid — the battery charges and
discharges in small, shallow cycles rather than the deep daily swings of arbitrage.

Because those regulation cycles are roughly 10% depth-of-discharge — compared to
the 80% of a full arbitrage cycle — the per-megawatt-hour degradation cost is eight
times lower: $3.48 versus $27.83. The battery earns revenue without grinding itself
down at the same rate.

The right panel is the key result: NPV as a function of the RegD clearing price.
Below $25 per megawatt-hour, still negative. Above $25 — which is near the
historical PJM average — the project turns viable. At $30 per megawatt-hour,
NPV on a one-megawatt-hour system is positive $162,000. Scale to ten megawatt-hours
and NPV reaches $2.3 million. The stochastic MILP handles this naturally: regulation
capacity is the first-stage committed decision; energy arbitrage adapts to whichever
price scenario actually realizes."

---

### SLIDE 11: Roadmap
*[~1 min]*

**ON THE SLIDE:**
```
Weeks 1–2    Data pipeline      PJM LMP acquisition, cleaning, scenario generation
Weeks 3–4    Baseline MILP      Deterministic formulation, dispatch verification
Weeks 5–6    Stochastic MILP    Two-stage model + CVaR efficient frontier
Weeks 7–8    Backtest           2024 holdout validation, EVPI, break-even analysis
Weeks 9–10   RegD extension     Multi-product co-optimization, NPV & sizing sweep
Week  11     Figures & script   Final visualizations, presentation

Sekander   MILP formulation · CVaR extension · RegD co-optimization
Gianna     Data pipeline · scenario generation · backtest · economic analysis
```

**PRESENTER SAYS:**

"We ran five two-week sprints with natural handoffs. The data pipeline output fed
the scenario generator; scenarios fed the optimizer; optimizer results fed the
backtest and economic analysis; the validated model fed the RegD extension. Work
divided along two specializations — optimization modeling and data/economics — with
the scenario format as the agreed-upon interface between the two halves.

One honest reflection: the RegD extension turned out to be the most commercially
significant result in the entire project, but we only reached it in weeks nine and
ten. If we had run that thread in parallel with the stochastic MILP — rather than
sequentially after it — we would have had more time to stress-test the regulation
assumptions and explore sensitivity to mileage ratios and capacity allocation rules.
Starting with the commercial question earlier would have sharpened every decision
upstream.

That said: the pipeline is complete, the results are reproducible on public data,
and the conclusion is definitive. Thank you."

---

---

## Image Reference Guide

| Slide | Visual | File |
|-------|--------|------|
| 2 | Scenario price fan (40 seasonal paths) | `results/figure_1_model_overview.png` (crop) |
| 6 | High-spread dispatch, Scenario 10 | `results/deterministic_dispatch_s10.png` |
| 7 | CVaR efficient frontier | `results/cvar_frontier.png` |
| 8 | 2024 cumulative backtest, 3 strategies | `results/backtest_cumulative.png` |
| 9 | EVPI bar + scenario revenue CDF | `results/analysis_evpi.png` |
| 10 | Revenue stack + NPV vs P_REG | `results/multiproduct_revenue.png` |

**Appendix / backup slides:**
`figure_1_model_overview.png` (full 6-panel) · `figure_2_economics.png` (4-panel economics)
`analysis_breakeven.png` · `backtest_monthly.png` · `cvar_dispatch_comparison.png`
`stochastic_revenue_dist.png` · `stochastic_soc.png` · `sizing_npv.png`

---

## Key Numbers Quick-Reference (for Q&A)

| Number | What it is |
|--------|-----------|
| 40 | Representative price scenarios (10 per season, k-means centroids) |
| 35,000 | Approximate daily profiles in 2020–2023 training data |
| $10.32 – $152.91/MWh | Cleaned price range (p01–p99 clip) |
| $27.83/MWh | Degradation cost for arbitrage cycling (Xu et al. model) |
| $3.48/MWh | Degradation cost for RegD regulation (~10% DoD cycles) |
| $334/kWh | LFP CapEx (NREL ATB 2024, utility-scale, all-in) |
| $9.29/day | In-sample two-stage expected net revenue (1 MWh) |
| $843/year | EVPI — value of perfect price foresight |
| $7,261/year | 2024 backtest oracle (upper bound, perfect daily foresight) |
| $3,637/year | 2024 backtest price-rank heuristic |
| -$415,962 | NPV, 1 MWh arbitrage-only, NREL costs, 7% WACC, 15yr |
| $49,906/year | Break-even annual revenue needed for 1 MWh system |
| ~$25/MWh | RegD clearing price threshold for positive NPV |
| +$162,000 | NPV at $30/MWh RegD clearing, 1 MWh |
| +$2.3M | NPV at $30/MWh RegD clearing, 10 MWh |
| 6,000 cycles | LFP cycle life at 80% DoD |
| 93% | One-way round-trip efficiency (charge and discharge both) |
