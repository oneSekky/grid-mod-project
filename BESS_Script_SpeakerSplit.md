# BESS Bidding Optimization — Presentation Script
**Speaker Split:** Sekander Ali  &  Gianna Gong
**Target length:** 12 minutes  ·  **12 slides**  ·  ELEN 4510, Spring 2026

> **Format note for the styling pass:**
> Each slide block contains (1) a title, (2) target time, (3) a suggested visual from `results/`, (4) on-slide bullets, and (5) the spoken script with explicit `SEKANDER:` / `GIANNA:` turn markers. Speaking time is balanced ~50/50 across the deck. Visuals are file references; do not embed at this stage.

---

## SLIDE 1 — Title & Team
**Time:** 0:00 – 0:50  (~50 s)
**Visual:** *(none — title card only)*  ·  optional decorative crop of `results/figure_1_model_overview.png` price-fan panel
**On the slide:**
- Battery Energy Storage Bidding Optimization
- Sekander Ali  ·  Gianna Gong
- ELEN 4510 — Grid Modernization & Clean Tech  ·  Spring 2026

**SEKANDER:** Hello, I'm Sekander.

**GIANNA:** And I'm Gianna.

**SEKANDER:** The question we tackled is one every grid-scale battery operator wakes up to: given that you don't know what electricity prices will do today, how do you schedule your battery to make money — without grinding it into the ground?

**GIANNA:** We built an end-to-end computational pipeline that answers that question. It goes from four years of raw wholesale price data, through a stochastic optimization model that commits a charge-and-discharge schedule under price uncertainty, through a formal risk framework, all the way to an economic verdict: can this business actually make money?

**SEKANDER:** The short answer is: not on energy arbitrage alone. The longer answer — including the one revenue stream that *does* make it work — is what the next eleven minutes are about.

---

## SLIDE 2 — The Core Problem
**Time:** 0:50 – 2:00  (~1:10)
**Visual:** `results/figure_1_model_overview.png` *(crop to scenario-fan panel)* — alternative: `data/scenarios/scenario_fan.png`
**On the slide:**
- Buy low. Sell high. *Commit before you can see either.*
- Prices range $0 → $150+ per MWh in a single day
- Every cycle physically wears the battery — degradation has a dollar cost

**GIANNA:** This fan chart shows forty plausible price paths for a single day in PJM — the largest wholesale electricity market in North America. Each line is one scenario our model considers. Prices range from near zero overnight — when surplus wind floods the grid — to over $150 per megawatt-hour during a summer peak. The money is in the spread: charge at the trough, discharge at the peak.

**SEKANDER:** The catch is timing. PJM's day-ahead market closes the morning *before* delivery. You have to submit a complete twenty-four-hour charge-and-discharge schedule before a single hour of that day has played out. You're committing to a plan for a future you can't yet see.

**GIANNA:** There's a second layer. Every megawatt-hour you push through the battery physically wears it down. Cells degrade. A utility-scale lithium iron phosphate system costs over $300 per kilowatt-hour installed. If you trade too aggressively on a flat-price day, you lose money twice — once from the thin spread, and again from the wear.

**SEKANDER:** So the precise problem we solve is: maximize expected net revenue under uncertain day-ahead prices, in real time, subject to physics and battery wear.

---

## SLIDE 3 — Formal Objective & Class Toolkit
**Time:** 2:00 – 2:45  (~45 s)
**Visual:** *(text-only formulation slide — no figure required)* ·  optional: `results/figure_1_model_overview.png` full panel as backdrop
**On the slide:**
- **Objective:**  max  E[ revenue − degradation ]  s.t.  power, energy, efficiency, charge ⊥ discharge
- Charge / discharge mutual exclusivity → **binary variables → MILP**
- **Extension:** co-optimize energy arbitrage  +  PJM RegD regulation
- **Class toolkit used:** two-stage stochastic MILP  ·  CVaR risk constraint  ·  NPV  ·  EVPI

**SEKANDER:** Formally, we maximize probability-weighted net revenue across a distribution of possible price days, minus degradation cost — subject to power limits, energy capacity, round-trip efficiency losses, and a hard mutual-exclusivity constraint. The battery cannot charge and discharge simultaneously. That requires binary decision variables, which makes this a mixed-integer linear program — an MILP.

**GIANNA:** The extension co-optimizes a second revenue stream — PJM's RegD regulation market — alongside energy arbitrage. That's where the commercial viability story unfolds, and we'll close on it.

**SEKANDER:** This project uses the class toolkit directly. The two-stage stochastic MILP handles day-ahead commitment under uncertainty. CVaR manages tail risk. NPV frames the investment question. And EVPI — Expected Value of Perfect Information — tells us how much better forecasting would actually be worth. Each one generates a concrete number that drives the conclusion.

---

## SLIDE 4 — State of the Art
**Time:** 2:45 – 3:45  (~1:00)
**Visual:** *(text-only literature slide — no figure)*
**On the slide:**
- **Battery degradation:**  Xu et al. (2018) — electrochemical $/MWh cycle cost  ·  NREL ATB 2024 — $334/kWh LFP CapEx
- **Stochastic optimization:**  Rockafellar & Uryasev (2000) — CVaR linearization  ·  Akbari-Dibavar et al. — hybrid stochastic-robust dispatch
- **Markets & ancillary services:**  FERC Order 841 (2018) — opened ancillary markets to storage  ·  Miseta et al. — multi-product bid structure
- **Sizing:**  Gitizadeh & Fakharzadegan — capacity co-optimization
- **Gap we fill:**  end-to-end pipeline  +  *true* 2024 out-of-sample backtest  +  commercial verdict

**GIANNA:** A few threads of prior work anchor our approach. On battery economics, Xu et al.'s 2018 paper gives us a rigorous model that converts cycling depth and frequency into a dollar cost per megawatt-hour. We use it to derive the $27.83-per-megawatt-hour degradation penalty embedded in the objective — that number isn't a rule of thumb, it's calibrated to electrochemistry.

**SEKANDER:** Fun side note: Professor Xu teaches here at Columbia and I took a class with him last semester. NREL's Annual Technology Baseline gives us the $334-per-kilowatt-hour CapEx — the 2024 industry standard for utility LFP — plus the $75,000 fixed balance-of-system cost.

**GIANNA:** On optimization: Rockafellar and Uryasev's CVaR linearization is the mathematical foundation for our risk constraint. It lets us impose a tail-revenue floor without leaving the linear framework — which means we can still reliably solve. Akbari-Dibavar's hybrid stochastic-robust formulation informed how we structured the two-stage commitment.

**SEKANDER:** On markets: FERC Order 841, issued in 2018, is the regulatory event that made the regulation co-optimization a real commercial option. Before that ruling, batteries couldn't participate in ancillary service markets on equal terms with generators. The gap most papers leave is that they stop at in-sample results. We hold all of 2024 out as a genuine test set, and we don't stop at "the model works" — we close the loop on whether it makes money.

---

## SLIDE 5 — Pipeline & Scenario Design
**Time:** 3:45 – 4:45  (~1:00)
**Visual:** `data/scenarios/scenario_grid.png` (4×10 grid of all 40 scenarios) — alternative: `data/scenarios/scenario_fan.png`
**On the slide:**
- 2020–2023 PJM RT LMP  →  ~35,000 daily profiles
- Cleaning: clip to p01–p99  ($10.32 – $152.91 / MWh)  ·  interpolate 4 missing hours
- **Season-stratified k-means**  →  10 scenarios per season  →  40 total
- 2024 held out untouched for backtesting

**SEKANDER:** The pipeline runs in four stages, each one feeding the next. Stage one converts roughly thirty-five thousand hourly LMP records into forty representative twenty-four-hour scenarios. Stage two runs the optimization models against those scenarios. Stage three validates everything on held-out 2024 data and computes the economic summary. Stage four adds the regulation market and answers the sizing question.

**GIANNA:** Two design choices on the scenarios are worth flagging. First: we used **season-stratified** k-means rather than global clustering. Without that, the algorithm over-represents summer — because summer has more price variation — and under-represents winter. Stratifying by season guarantees ten scenarios per season, with probabilities that reflect each season's actual day-frequency.

**SEKANDER:** Second: we deliberately reduced from fifty scenarios to forty after seeing the marginal scenarios were nearly identical duplicates. They added solve time without adding meaningful information. Forty is the sweet spot — enough to span seasonal price patterns, small enough to keep the MILP tractable.

---

## SLIDE 6 — The MILP in Action
**Time:** 4:45 – 5:45  (~1:00)
**Visual:** `results/deterministic_dispatch_s10.png` (high-spread winter day, 24-hour dispatch)
**On the slide:**
- Decision vars: charge, discharge, SOC, **binary** charge/discharge mode at every hour
- Energy balance:  SOC[t+1] = SOC[t] + η_c · charge[t] − discharge[t] / η_d
- Degradation $27.83/MWh enters objective:  +cost on charge,  −value on discharge
- **Trade only when spread ≥ $27.83**

**GIANNA:** This is what the model produces on a high-spread winter day — scenario ten, one of the more favorable days in our training set. The top panel shows price; the bottom panel shows the battery's response.

**SEKANDER:** Overnight, prices sit in the twenties. The model fills the battery to ninety percent of capacity — the upper SOC limit we impose to protect cycle life. When the morning peak hits one hundred twenty dollars, it discharges. Prices dip through midday, so it tops up. Then the evening peak fires and it discharges to the ten percent floor.

**GIANNA:** The MILP mechanics behind that behavior: continuous charge and discharge variables at each of twenty-four hours, a state-of-charge trajectory that links them via the energy balance equation, and binary variables that prevent simultaneous charging and discharging. The degradation cost — $27.83 per megawatt-hour throughput — is added to the effective buy price and subtracted from the effective sell price.

**SEKANDER:** The battery only trades when the spread clears that twenty-eight-dollar hurdle. Net revenue on this day after degradation is $66. On a typical scenario it's closer to $9. On flat-price days the model correctly decides not to trade at all — the binaries go to zero and the battery sits idle. That's the right answer, and it's the discipline the degradation term is enforcing.

---

## SLIDE 7 — Managing Risk: CVaR Frontier
**Time:** 5:45 – 6:30  (~45 s)
**Visual:** `results/cvar_frontier.png`  ·  appendix: `results/cvar_dispatch_comparison.png`
**On the slide:**
- CVaR_α(R) = expected revenue in the worst (1−α) fraction of scenarios
- Sweep:  α ∈ {0.90, 0.95, 0.99}  ×  25 budget levels  =  efficient frontier
- ★ unconstrained optimum: $9.29 / day expected
- Tradeoff: ~1% expected revenue per +$0.50 CVaR floor

**SEKANDER:** The stochastic model maximizes expected net revenue — the probability-weighted average across all forty scenarios. But an operator running a merchant asset cares as much about bad days as average days. A string of low-revenue days in a bad season can stress project finances even if the annual average looks fine.

**GIANNA:** We add a CVaR constraint using the Rockafellar-Uryasev linearization. CVaR at the ninety-fifth percentile is the average revenue over the worst five percent of scenarios — and we *guarantee a floor* on that average. We sweep that floor across twenty-five budget levels and three confidence values: ninety, ninety-five, and ninety-nine percent.

**SEKANDER:** Each point on this curve is an optimal solution at a different risk tolerance. The starred point is the unconstrained expected-value optimum at $9.29 per day. Moving left along the frontier, you give up expected revenue to protect against tail losses — roughly one percent of expected revenue per half-dollar increase in the CVaR floor. A risk-averse operator accepts a small reduction in expected return for meaningful downside protection.

---

## SLIDE 8 — Tools, Data & 2024 Backtest
**Time:** 6:30 – 8:00  (~1:30)
**Visual:** `results/backtest_cumulative.png` (three strategies, full year 2024)  ·  appendix: `results/backtest_monthly.png`
**On the slide:**
- **Data:**  PJM RT LMP 2020–23 train  ·  2024 held-out backtest (364 days)  ·  NREL ATB 2024 costs
- **Software:**  CVXPY + HiGHS (open-source MILP)  ·  scikit-learn  ·  pandas / NumPy  ·  matplotlib
- **Reference battery:**  0.5 MW / 1 MWh LFP  ·  η = 93% one-way  ·  SOC ∈ [10%, 90%]
- **2024 backtest annual totals:**  Oracle $7,261  ·  Price-rank heuristic $3,637  ·  Fixed-hours $721

**GIANNA:** Everything runs on publicly available data. PJM publishes hourly real-time LMP going back years — we pulled 2020 through 2023 for training. Before writing a single line of optimization code, we locked 2024 away. That discipline is what makes the backtest meaningful: no lookahead, no tuning, no second chances.

**SEKANDER:** The cleaning step clips price outliers to the first-and-ninety-ninth-percentile band — $10.32 to $152.91 per megawatt-hour — and linearly interpolates four missing hours. We originally planned Gurobi as the solver; we substituted CVXPY with the open-source HiGHS backend. Everything is reproducible with no license requirements.

**GIANNA:** This backtest chart is the payoff of that holdout discipline. Three strategies on the same 364 days in 2024. An oracle with perfect daily price foresight earns $7,261 over the year — an unattainable upper bound. A degradation-aware price-rank heuristic, which has no model at all, earns $3,637. A fixed off-peak-charge, on-peak-discharge schedule earns only $721.

**SEKANDER:** Two things to read off this. The gap between the fixed-hours strategy and the price-rank heuristic — five times the revenue — shows how much pricing structure matters. And the gap between price-rank and the oracle shows the headroom that better optimization could in principle capture. Real performance, on data the model never saw.

---

## SLIDE 9 — Wait-and-See vs. Two-Stage  →  EVPI
**Time:** 8:00 – 9:00  (~1:00)
**Visual:** `results/analysis_evpi.png`  ·  appendix: `results/stochastic_revenue_dist.png`, `results/stochastic_soc.png`
**On the slide:**
- **Wait-and-See:**  optimize each scenario in hindsight  →  $11.60 / day  ($4,236 / yr)
- **Two-Stage commitment:**  one schedule across all 40 scenarios  →  $9.29 / day  ($3,393 / yr)
- **EVPI = WS − TS  =  $2.31 / day  =  $843 / yr**
- ⇒ Better forecasting buys < $1k/yr.  Distribution already captures most exploitable variation.

**SEKANDER:** Two numbers here separate what perfect information would buy from what a real operator can actually do. The first is the **Wait-and-See** number: $11.60 per day. That's what you would earn if you could optimize *each* scenario after seeing it — twenty-four hours of perfect price knowledge, separately for every possible day. It's a hindsight upper bound.

**GIANNA:** The second is the **Two-Stage** number: $9.29 per day. That's what we earn when we commit one schedule before knowing which scenario will realize. Same model, same constraints — the only difference is the timing of information.

**SEKANDER:** The gap between them is **EVPI** — Expected Value of Perfect Information. It's $2.31 per day, or $843 per year on a one-megawatt-hour battery. That number is small on purpose: it tells us our forty-scenario distribution is already capturing most of the exploitable price variation. A dramatically better forecasting model would move the needle less than a thousand dollars annually. Better forecasting has limited upside — the constraint isn't information, it's commitment.

---

## SLIDE 10 — Sizing, Sensitivity & The Profitability Gap
**Time:** 9:00 – 10:00  (~1:00)
**Visual:** `results/sizing_npv.png`  +  `results/analysis_sensitivity.png`  ·  appendix: `results/analysis_breakeven.png`, `results/figure_2_economics.png`
**On the slide:**
- **Sizing sweep (arbitrage only, 0.5 → 10 MWh):**  every size is **negative-NPV**
- 1 MWh:  arbitrage $3,393 / yr  vs.  break-even $49,906 / yr  →  ~7 cents on the dollar
- Even 2024 oracle ($7,261 / yr) covers only ~15% of break-even
- **Sensitivity:**  NPV moves $50k per +$50/kWh CapEx  ·  effectively flat across cycle life
- ⇒ degradation cost binds *operationally* (model trades only when spread > $27.83), not lifetime
- ⇒ arbitrage alone cannot justify the investment at *any* size we tested

**GIANNA:** Now we close the economic loop. We swept battery size from half a megawatt-hour up to ten megawatt-hours, computing arbitrage revenue, CapEx, fixed O&M, and fifteen-year NPV at a seven percent cost of capital. **Every size is negative-NPV under arbitrage alone.** A one-megawatt-hour system loses about $416,000 of NPV over its life. A ten-megawatt-hour system loses $3.5 million. Scaling up doesn't fix the problem — it scales the problem.

**SEKANDER:** The break-even math makes that intuitive: a 1 MWh system needs roughly $49,906 per year in revenue to clear cost-of-capital. Our two-stage stochastic model earns $3,393 — about seven cents on the dollar. Even the 2024 oracle, with perfect daily foresight, earns $7,261 — about fifteen cents on the dollar. Either way, arbitrage covers a small fraction of what's needed.

**GIANNA:** One subtlety in the sensitivity grid: NPV drops about $50,000 for every $50-per-kilowatt-hour increase in CapEx, but it's effectively flat across cycle-life assumptions from 3,000 to 10,000 cycles. That's because the $27.83 degradation cost is already binding *per-trade* — the model only acts when the spread clears that hurdle, so the lifetime cycle limit never becomes the binding constraint. CapEx is the sensitivity that matters; cycle life is not.

**SEKANDER:** The conclusion is uncomfortable but clear. Pure energy arbitrage in PJM, even with optimization done well, doesn't pencil. *Something else has to pay the bill.*

---

## SLIDE 11 — RegD Co-Optimization Changes the Picture
**Time:** 10:00 – 11:00  (~1:00)
**Visual:** `results/multiproduct_npv.png` *(NPV vs RegD clearing price across capacities)*  ·  alternative or pair: `results/multiproduct_revenue.png`
**On the slide:**
- RegD = fast-response frequency regulation  ·  shallow ~10% DoD cycles  vs.  arbitrage's ~80%
- Degradation cost drops **8×**: $3.48 / MWh (RegD)  vs.  $27.83 / MWh (arbitrage)
- **Break-even RegD clearing price (1 MWh):  ≈ $25 / MWh**
- Historical PJM RegD avg ≈ $30 / MWh:  **NPV +$162,000 (1 MWh),  +$2.3 M (10 MWh)**
- Two-stage MILP handles it natively: regulation capacity = first-stage decision, arbitrage adapts to realized scenario

**SEKANDER:** That something else is PJM's RegD market. RegD pays a battery to follow a fast-response signal that balances frequency on the grid. The battery charges and discharges in small, shallow cycles — roughly ten percent depth-of-discharge — rather than the eighty percent swings of full arbitrage cycles.

**GIANNA:** Because the cycles are so shallow, the per-megawatt-hour degradation cost drops by about a factor of eight: $3.48 versus $27.83. The battery earns revenue without grinding itself down at the same rate.

**SEKANDER:** The chart shows NPV as a function of RegD clearing price across capacities. For a 1 MWh system, the break-even clearing price is just under $25 per megawatt-hour. **That's the threshold, not the realized average.** The historical PJM RegD clearing price runs around $30 per megawatt-hour — comfortably above break-even.

**GIANNA:** At $30 per megawatt-hour, NPV on a one-megawatt-hour system flips to **+$162,000**. Scale to ten megawatt-hours and NPV reaches **+$2.3 million**. The two-stage MILP handles this natively: regulation capacity is the first-stage committed decision, and energy arbitrage adapts to whichever price scenario actually realizes. Co-optimization — not arbitrage alone — is what makes the asset bankable.

---

## SLIDE 12 — Roadmap, Reflection & Conclusions
**Time:** 11:00 – 12:00  (~1:00)
**Visual:** *(text-only timeline / role split — no figure required)*  ·  optional: `results/figure_2_economics.png` as backdrop
**On the slide:**
- **Weeks 1–2:**  Data pipeline (PJM LMP, cleaning, scenarios)
- **Weeks 3–4:**  Deterministic MILP baseline
- **Weeks 5–6:**  Stochastic MILP + CVaR frontier
- **Weeks 7–8:**  2024 backtest, EVPI, break-even
- **Weeks 9–10:**  RegD co-optimization, NPV & sizing
- **Week 11:**  Figures & presentation
- **Sekander** — MILP formulation · CVaR · RegD co-optimization
- **Gianna** — Data pipeline · scenario generation · backtest · economic analysis

**GIANNA:** We ran five two-week sprints with natural handoffs. Data pipeline output fed scenario generation; scenarios fed the optimizer; optimizer results fed backtest and economics; the validated model fed the RegD extension. Work split along two specializations — optimization modeling and data-and-economics — with the scenario format as the agreed-upon interface between the two halves.

**SEKANDER:** One honest reflection: the RegD extension turned out to be the most commercially significant result in the entire project, but we only reached it in weeks nine and ten. If we had run that thread in parallel with the stochastic MILP — rather than sequentially after it — we would have had more time to stress-test the regulation assumptions and explore sensitivity to mileage ratios and capacity allocation rules. Starting with the commercial question earlier would have sharpened every decision upstream.

**GIANNA:** Three takeaways. **One:** pure arbitrage doesn't pencil at any size we tested — break-even revenue is roughly $50,000 per year, arbitrage delivers $3,400. **Two:** better forecasting won't save it — EVPI is only $843 per year. **Three:** RegD co-optimization is the path to a viable business case, with NPV positive above $25-per-megawatt-hour clearing prices and historical clearings well above that threshold.

**SEKANDER:** The pipeline is complete, the results are reproducible on public data, and the conclusion is definitive. Thank you.

---

## Appendix — Image Reference for Each Slide

| Slide | Primary Visual | Secondary / Backup |
|---|---|---|
| 1 | *(title card)* | `results/figure_1_model_overview.png` (decorative) |
| 2 | `results/figure_1_model_overview.png` *(crop: scenario fan)* | `data/scenarios/scenario_fan.png` |
| 3 | *(formulation text)* | `results/figure_1_model_overview.png` |
| 4 | *(literature text)* | — |
| 5 | `data/scenarios/scenario_grid.png` | `data/scenarios/scenario_fan.png` |
| 6 | `results/deterministic_dispatch_s10.png` | `results/deterministic_dispatch_s1.png`, `s24.png` |
| 7 | `results/cvar_frontier.png` | `results/cvar_dispatch_comparison.png` |
| 8 | `results/backtest_cumulative.png` | `results/backtest_monthly.png` |
| 9 | `results/analysis_evpi.png` | `results/stochastic_revenue_dist.png`, `results/stochastic_soc.png` |
| 10 | `results/sizing_npv.png`  +  `results/analysis_sensitivity.png` | `results/analysis_breakeven.png`, `results/figure_2_economics.png` |
| 11 | `results/multiproduct_npv.png` | `results/multiproduct_revenue.png` |
| 12 | *(timeline / roles text)* | `results/figure_2_economics.png` |

---

## Appendix — Key Numbers (Q&A reference)

| Number | What it is |
|---|---|
| **40** | Representative price scenarios (10 per season, k-means centroids) |
| **~35,000** | Daily profiles in 2020–2023 PJM training data |
| **$10.32 – $152.91 / MWh** | Cleaned price range (p01–p99 clip) |
| **$27.83 / MWh** | Arbitrage degradation cost (Xu et al. model) |
| **$3.48 / MWh** | RegD degradation cost (~10% DoD shallow cycles) |
| **$334 / kWh + $75k** | LFP CapEx + fixed BOS (NREL ATB 2024) |
| **$11.60 / day** | Wait-and-See expected revenue (1 MWh) |
| **$9.29 / day** | Two-stage committed expected revenue (1 MWh) |
| **$2.31 / day  ($843 / yr)** | EVPI (value of perfect daily foresight) |
| **$7,261 / yr** | 2024 backtest oracle (perfect daily hindsight, upper bound) |
| **$3,637 / yr** | 2024 backtest price-rank heuristic |
| **$721 / yr** | 2024 backtest fixed-hours strategy |
| **$49,906 / yr** | Break-even annual revenue (1 MWh, 7% WACC, 15 yr) |
| **−$415,962** | NPV, 1 MWh arbitrage-only |
| **−$3.48 M** | NPV, 10 MWh arbitrage-only |
| **~$25 / MWh** | RegD clearing price for break-even (1 MWh) |
| **~$30 / MWh** | Historical PJM RegD clearing price |
| **+$162,000** | NPV at $30/MWh RegD, 1 MWh |
| **+$2.3 M** | NPV at $30/MWh RegD, 10 MWh |
| **6,000 cycles @ 80% DoD** | LFP cycle life assumption |
| **93%** | One-way round-trip efficiency |
| **α ∈ {0.90, 0.95, 0.99}** | CVaR confidence levels swept |
| **25** | CVaR budget points per α |
