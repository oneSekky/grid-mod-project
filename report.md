# ELEN 4510 — BESS Bidding Optimization
## Presentation Script & Slide Template
**Target length:** 10 minutes | **Slides:** 9

---

---

## SLIDE 1: Title
*[30 seconds]*

**ON THE SLIDE:**
```
Battery Energy Storage Bidding Optimization
Using Stochastic MILP with PJM Real-Time LMP Data

ELEN 4510 — Spring 2026
[Names]
```

**PRESENTER SAYS:**
"We optimized the daily dispatch schedule for a grid-scale lithium-iron-phosphate
battery operating in PJM's real-time energy market. The core idea is energy
arbitrage — buy cheap, sell dear — but the challenge is that prices are uncertain
when you have to commit. We built a stochastic mixed-integer program that handles
that uncertainty explicitly, validated it on 2024 data, and extended it to
co-optimize with ancillary services to answer the key commercial question: can this
battery actually make money?"

---

---

## SLIDE 2: Problem Setup & Motivation
*[60 seconds]*

**ON THE SLIDE:**
```
Why Battery Storage Arbitrage Is Hard

- PJM real-time LMP swings $20–$200+/MWh within a single day
- Battery must commit charge/discharge schedule before prices realize
- Physical constraints: power (MW), energy (MWh), round-trip efficiency, SOC
- Degradation: every MWh cycled consumes battery lifespan

Goal: maximize expected net revenue over uncertain price scenarios
      subject to all physical and degradation constraints
```

**PRESENTER SAYS:**
"PJM is the largest electricity market in North America. Real-time prices can swing
wildly — from near zero during high-wind overnight periods to over two hundred
dollars per MWh during peak demand. A battery can in principle earn money by
charging during troughs and discharging during peaks.

But here's the problem: you have to commit to a day-ahead schedule before you know
exactly what prices will do. And every megawatt-hour you cycle through the battery
physically wears it out. Our NREL ATB 2024 numbers put the all-in installed cost
at $334 per kilowatt-hour for utility-scale LFP, and modern batteries have a cycle
life of roughly 6,000 cycles at 80% depth of discharge. That works out to a
degradation cost of $27.83 per MWh cycled. So you can't just dispatch blindly —
you have to clear a spread of about $64 per MWh before trading is even worth it."

---

---

## SLIDE 3: Data Pipeline & Price Scenarios
*[60 seconds]*

**ON THE SLIDE:**
```
PJM RT LMP → 40 Representative Price Scenarios

Training data:   2020–2023 PJM system-wide RT LMP (hourly)
Scenario method: Season-stratified k-means clustering
                 10 scenarios per season × 4 seasons = 40 total
Backtest data:   Full 2024 (364 days, held out completely)
```

![Scenario fan — figure_1_model_overview.png panel A](results/figure_1_model_overview.png)
*Use panel (A) only — crop if possible*

**PRESENTER SAYS:**
"We pulled four years of hourly PJM real-time LMP data as our training set and held
out all of 2024 for out-of-sample validation — it never touches the model.

To represent price uncertainty, we ran season-stratified k-means clustering,
generating ten representative scenarios per season for forty total. Each scenario
is a full 24-hour price profile with an associated probability. You can see the fan
here — summer scenarios in orange have high midday peaks reflecting air-conditioning
load, winter in blue can spike dramatically during cold snaps, and spring and fall
are generally lower and flatter. The probabilities sum to one so we have a proper
probability distribution over possible days."

---

---

## SLIDE 4: Stochastic MILP Formulation & Dispatch
*[90 seconds]*

**ON THE SLIDE:**
```
Stochastic MILP — Key Structure

Variables (per scenario s, hour t):
  p_c[s,t], p_d[s,t]  charge / discharge power (MW)
  soc[s,t]             state of charge (MWh)
  u_c[s,t], u_d[s,t]  binary: can't charge AND discharge simultaneously

Degradation cost:  C_DEG = CapEx / (2 · E · N_cycles) = $27.83/MWh

Objective:
  max  Σ_s prob_s · Σ_t [ (λ_s,t − C_DEG)·p_d − (λ_s,t + C_DEG)·p_c ]
```

![Three dispatch cases](results/deterministic_dispatch_s10.png)
*Use the high-spread (S10) dispatch panel — charge overnight, discharge midday*

**PRESENTER SAYS:**
"The model is a mixed-integer linear program. For each of the forty scenarios we have
continuous charge and discharge power variables, a state-of-charge trajectory, and
binary variables enforcing that the battery can't charge and discharge at the same
time.

The degradation cost comes directly from the Xu et al. model — we divide the battery
capital cost by the total lifetime throughput to get a dollar-per-megawatt-hour
wearing cost. This gets added to the effective charge price and subtracted from the
effective discharge price, so the battery only trades when the spread is wide enough
to cover wear.

In the dispatch plot here, the high-spread scenario from a winter day shows exactly
what you'd expect: charging at a fraction of a cent overnight when prices are in the
twenties, then discharging during the morning and evening peaks when prices hit over
a hundred. The net revenue on this day is $66 after degradation — but that's the good
day. On a typical day it's much less, and on low-spread days the model correctly
decides not to trade at all."

---

---

## SLIDE 5: CVaR Risk Management
*[60 seconds]*

**ON THE SLIDE:**
```
Two-Stage CVaR: Managing Tail Risk

Two-stage formulation: single committed schedule across all scenarios
  (non-anticipativity — no peeking at which scenario realized)

CVaR_α = expected revenue in the worst (1−α)% of days

Risk-return tradeoff: tightening CVaR constraint sacrifices mean revenue
                      to protect against bad outcomes

α = 0.90 / 0.95 / 0.99  (90th, 95th, 99th percentile tail)
```

![CVaR efficient frontier](results/cvar_frontier.png)

**PRESENTER SAYS:**
"The wait-and-see stochastic model gives each scenario its own optimal dispatch —
it knows which scenario it's in. That's a useful upper bound but not how the real
world works. In the two-stage formulation we commit a single schedule before the
scenario reveals itself, which is the actual operating constraint.

We then introduce CVaR — Conditional Value-at-Risk — as a risk measure, using the
Rockafellar-Uryasev linearization. Each point on the frontier trades some expected
revenue for a guaranteed floor on tail performance. The stars mark the unconstrained
two-stage optimum. As we tighten the CVaR budget, expected revenue falls but the
worst-case days improve — the classic risk-return tradeoff. A risk-averse operator
running a merchant battery might sit somewhere in the middle of this curve."

---

---

## SLIDE 6: Backtest Validation — 2024 Out-of-Sample
*[60 seconds]*

**ON THE SLIDE:**
```
2024 Backtest — Three Strategies (364 days, held out)

  Oracle (perfect foresight MILP):   $7,261/yr   ($19.95/day)
  Price-rank heuristic:              $3,637/yr   ($9.99/day)
  Fixed peak hours:                  $0/yr        (spread never clears $64 threshold)

Naive benchmarks are degradation-aware — only trade if spread > 2·C_DEG/(η_C·η_D)
```

![Backtest cumulative revenue](results/backtest_cumulative.png)

**PRESENTER SAYS:**
"We ran three strategies over all of 2024 — data the model never saw. The oracle
strategy re-solves the deterministic MILP each day with perfect price foresight,
giving us the theoretical maximum arbitrage revenue. The price-rank heuristic charges
in the eight cheapest hours and discharges in the eight most expensive, subject to the
same degradation threshold. Both benchmarks only trade when the off-peak/on-peak
spread clears the $64 minimum threshold to cover round-trip losses and degradation.

The fixed peak-hours strategy — midnight to six charging, four to eight PM discharging
— never trades at all, because the average spread in PJM over 2024 never consistently
clears that threshold. The cumulative curves show oracle grinding out a steady positive
slope through the year with some flat stretches during low-spread months, while
price-rank earns roughly half."

---

---

## SLIDE 7: Economic Analysis — EVPI & Sizing Gap
*[75 seconds]*

**ON THE SLIDE:**
```
Two Key Economic Results

EVPI = $843/year
  Wait-and-see:  $11.60/day    (perfect information)
  Two-stage:     $9.29/day     (committed schedule)
  → Knowing prices in advance is worth $843/yr on a 1 MWh battery

The Profitability Gap (arbitrage alone):
  Break-even annual revenue (1 MWh):  $49,906/yr
  Arbitrage revenue (oracle 2024):    $7,261/yr
  → Arbitrage covers only 7% of what's needed for NPV = 0
```

![EVPI bar chart + sizing gap](results/analysis_evpi.png)

**PRESENTER SAYS:**
"Two important numbers fall out of the analysis. First, the Expected Value of Perfect
Information — the gap between what you'd earn knowing tomorrow's prices exactly versus
committing a schedule blindly. It's $843 per year on a one megawatt-hour battery.
That's small relative to what a perfect predictor would be worth, which tells us the
stochastic MILP is capturing most of the value just from the scenario distribution.

The bigger result is the profitability gap. Taking NREL ATB 2024 capital costs —
$334 per kilowatt-hour plus $75,000 in fixed project costs — and a standard 7% WACC
over 15 years, you need roughly $50,000 per year in net revenue to break even. Pure
price arbitrage from PJM RT LMP delivers about $7,000 — about 7 cents on the dollar.
Arbitrage alone cannot make this project viable. You need additional revenue streams."

---

---

## SLIDE 8: Multi-Product Co-Optimization — Adding PJM RegD
*[90 seconds]*

**ON THE SLIDE:**
```
Two-Stage MILP: Energy Arbitrage + PJM RegD Regulation

First-stage (committed day-ahead):
  r[t]  — regulation capacity bid (MW), same across all price scenarios

New constraints:
  Power headroom:   p_c[s,t] + r[t] ≤ P_MW   (arbitrage + reg ≤ rated power)
  SOC headroom:     soc[s,t] ≥ SOC_MIN·E + r[t]/η_D   (can respond to reg-up)
                    soc[s,t] ≤ SOC_MAX·E − r[t]·η_C   (can respond to reg-down)

RegD degradation:   C_DEG_reg = C_DEG / 8 = $3.48/MWh
  (regulation cycles at ~10% DoD → 8× better cycle life than arbitrage)

Net reg revenue:    P_REG − C_DEG_reg × mileage  ($/MW-h committed)
```

![Revenue stack vs break-even and NPV vs RegD price](results/multiproduct_revenue.png)

**PRESENTER SAYS:**
"PJM operates a real-time regulation market — RegD — that pays batteries to follow
a fast frequency regulation signal. The revenue has two components: a capacity payment
for the megawatts you commit, and a mileage payment based on how far the signal
actually travels.

We extend the MILP to a two-stage formulation where the regulation capacity bid r-of-t
is the first-stage decision — it's committed before prices realize and is the same
across all forty scenarios. The energy arbitrage dispatch remains second-stage. We add
two sets of constraints: power headroom, so the battery can always respond in either
direction, and SOC headroom so it has enough stored energy to follow the signal for a
full hour.

The key economics: regulation at 10% depth-of-discharge is eight times gentler on the
battery than arbitrage cycles. So the degradation cost per megawatt-hour drops from
$27.83 to $3.48. At a clearing price of $25 per megawatt-hour — which is around the
PJM RegD historical average — the net regulation revenue after degradation is positive,
and the combined project NPV crosses zero.

The right panel shows NPV vs clearing price for a one megawatt-hour battery. Below
about $25, still negative. Above $25, profitable. At $30, NPV is $162,000."

---

---

## SLIDE 9: Conclusions & Future Work
*[45 seconds]*

**ON THE SLIDE:**
```
Key Takeaways

1. Stochastic MILP captures arbitrage value efficiently
   — EVPI only $843/yr: most value comes from the price distribution, not perfect info

2. PJM arbitrage alone cannot justify BESS capital costs
   — Covers ~7% of break-even revenue at NREL ATB 2024 prices

3. PJM RegD changes the picture
   — Break-even at ~$25/MW-h clearing price (historically realistic)
   — At $30/MW-h: NPV = +$162k (1 MWh) → +$2.3M (10 MWh)

Future work:
  - Capacity market revenue (PJM RPM)
  - Stochastic RegD signal model (mileage uncertainty)
  - Battery lifespan endogeneity (regulation may exhaust battery in ~9 years)
```

**PRESENTER SAYS:**
"To summarize: the stochastic MILP works well, and the EVPI result tells us the
scenario distribution is capturing most of the available information. But arbitrage
alone — even with a perfect oracle — covers only 7% of the break-even revenue at
current capital costs. Adding PJM RegD as a co-optimized product changes the
investment case materially. At historically observed clearing prices around $25 to $30
per megawatt-hour, the project NPV turns positive.

Two caveats worth flagging: the regulation mileage is treated as deterministic here
— a fuller model would make it stochastic. And at our assumed regulation utilization,
the battery could be exhausted in roughly nine years rather than the fifteen-year life
we use for the NPV, which overstates later-year cash flows. Both are tractable
extensions. Thank you."

---

---

## Image Reference Guide

| Slide | Recommended Image | File |
|-------|------------------|------|
| 3 | Scenario fan (panel A) | `results/figure_1_model_overview.png` |
| 4 | High-spread dispatch (S10) | `results/deterministic_dispatch_s10.png` |
| 5 | CVaR efficient frontier | `results/cvar_frontier.png` |
| 6 | 2024 cumulative backtest | `results/backtest_cumulative.png` |
| 7 | EVPI bar chart | `results/analysis_evpi.png` |
| 8 | Revenue stack + NPV vs P_REG | `results/multiproduct_revenue.png` |

**Full composite figures** (for appendix or report body):
- `results/figure_1_model_overview.png` — 6-panel model overview
- `results/figure_2_economics.png` — 4-panel economic analysis (panel C now shows RegD NPV curves)

---

## Timing Guide

| Slide | Topic | Time |
|-------|-------|------|
| 1 | Title | 0:30 |
| 2 | Problem & motivation | 1:30 |
| 3 | Data & scenarios | 2:30 |
| 4 | MILP formulation & dispatch | 4:00 |
| 5 | CVaR risk management | 5:00 |
| 6 | Backtest 2024 | 6:00 |
| 7 | EVPI & sizing gap | 7:15 |
| 8 | Multi-product RegD | 9:00 (longest) |
| 9 | Conclusions | 9:45 |
