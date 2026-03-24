**Data Pipeline**
- Explore and understand the LMP data schema (columns, resolution, node structure)
- Decide which node/zone to use for optimization (or use system-wide average)
- Clean price data: handle negative spikes, outliers, missing intervals
- Aggregate RT LMP to hourly if not already done
- Check for and handle DST transitions and duplicate timestamps

**Scenario Generation**
- Build daily 24h price profile matrix from training data (2022–2023)
- Apply k-means clustering to generate 20–50 representative scenarios
- Assign scenario probabilities (cluster weights)
- Visualize scenario fan to sanity-check spread

**Deterministic MILP (baseline)**
- Implement SOC dynamics, power bounds, mutual exclusivity constraints
- Implement degradation cost in objective (piecewise-linear DoD model from Xu et al.)
- Solve a single 24h instance and verify the dispatch schedule makes physical sense
- Test with a high-price-spread day and a low-spread day

**Stochastic EV Extension**
- Extend model to S scenarios with scenario-indexed dispatch variables
- Maximize probability-weighted expected revenue across all scenarios
- Verify scenario results are consistent with deterministic runs

**CVaR Extension**
- Add Rockafellar-Uryasev auxiliary variables (η, z_s)
- Implement CVaR as a hard constraint on scenario revenue tail
- Parametric sweep over α ∈ {0.90, 0.95, 0.99} and CVaR budget levels
- Build risk-return efficient frontier from sweep results

**Backtesting**
- Hold out 2024 data completely during model development
- Run optimized policy on 2024 price realizations
- Compare against naive benchmarks (always charge off-peak, always discharge peak)
- Report realized vs. in-sample revenue gap

**Battery Sizing**
- Parameterize E (MWh) and P (MW) as decision variables or sweep inputs
- Run optimization across capacity range 0.5–10 MWh
- Compute NPV for each size using annualized CapEx and optimized revenue
- Identify optimal sizing point

**Results & Visualization**
- SOC trajectory plots for representative scenarios (with scenario bands)
- Bid curve / dispatch schedule plots (MW vs. hour, overlaid with price)
- Risk-return efficient frontier (expected revenue vs. CVaR)
- NPV vs. capacity sizing curve
- Backtest comparison bar chart (optimized vs. naive benchmarks)

**Report & Presentation**
- Final report (template due 3/25/26, report due 5/13/26)
- Final presentation/demo (PPT due 4/26/26)
