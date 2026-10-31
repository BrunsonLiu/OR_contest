# Computational experiments (r2, fixed-cost results)

This section supersedes the old Section 5. All numbers below come from the `*-r2-20261031`
experiments after the return-leg and unserved-penalty fixes. The old numbers are invalid.

## 5.1 Experimental setup

**Instances and data.** Synthetic instances with 8, 12 and 20 stores and three candidate
warehouses. Store coordinates are uniform on [0,300]^2; shelf life is 6 days; warehouse ages are
0, 2.5 and 4.5 days; store thresholds are 1, 2 or 3 days; vehicle capacity is four stores;
opening cost is 100; vehicle fixed cost is 50; transport cost is 0.5 per km; speed is 100 km per
day; the unserved penalty is 200, varied in the sensitivity analysis. The real-network
illustration uses three contest regional warehouses (Guangzhou, Dongguan, Chengdu), the twelve
nearest contest cities and the contest last-leg rate of 1.45 per ton-km; it is an illustration
on real geography, not a case study.

**Computing environment.** Python 3.12, single process, no parallelization. Gurobi 13.0.1 with
an academic licence is used for the MILP, one thread and a 30 s limit. The exact DP and all
heuristics are pure Python.

**Criteria.** Solution quality measured as the gap to the exact optimum where available, or to
the best known bound otherwise; wall-clock runtime; number of optimal solutions; win/tie/loss
counts; and 95% confidence intervals over ten instances.

**Comparisons.** Age-blind exact plan; three assignment policies; a freshest-first rule with
2-opt and relocate; simulated annealing, tabu search and a genetic algorithm under the same
number of solution evaluations; Gurobi MILP at 8, 12 and 20 stores; and the LP relaxation at
20 stores.

## 5.2 Model and method validation

The exact DP and the Gurobi MILP agree to the last digit at eight stores (917.798, 926.561 and
904.552 on seeds 0–2) and at twelve stores on seeds 0 and 1 (1009.103 and 989.495). On twelve-store
seed 2 the MILP reaches the 30 s limit with a 12.31% gap, and at twenty stores it reaches 30 s
with an 18.81% gap (feasible 1722.35). The DP is therefore the exact reference for 8 and 12
stores; the MILP is an independent check, not a competitor at 20 stores.

## 5.3 Overall performance

At eight and twelve stores the age-aware plan is better than the age-blind plan in **10 of 10**
instances, with no ties and no losses. The mean advantage is 895.5 at eight stores and 1370.2 at
twelve stores. The corresponding 95% intervals are [498.6, 1292.5] and [696.0, 2044.5].

With the destroy size selected on development seeds 5–9 (4–6: mean 3.99, 4/5 optima; default
2–4: 23.47, 2/5; 1–2: 96.43, 2/5), the ALNS reaches a mean gap of **17.12** on held-out seeds
10–19, with 7/10 optima and a maximum of 71.28. The default setting reaches 39.40 with 5/10
optima. The held-out gap interval is [-4.06, 38.30], which includes zero; the paired difference
(default minus tuned) is 22.28 with interval [-11.83, 56.39]. The ALNS is therefore better than
the default and than the alternatives, but it is not near-optimal on held-out instances.

## 5.4 Comparison with existing methods

| Method (12 stores) | Mean gap | Optima |
| --- | --- | --- |
| Age-blind exact | 1370.2 | 0/10 |
| Freshest + 2-opt/relocate | 388.5 | 0/10 |
| Simulated annealing | 91.3 | 3/10 |
| Genetic algorithm | 81.3 | 4/10 |
| Tabu search | 263.5 | 0/10 |
| ALNS (destroy 4–6) | 3.95 | 8/10 |

The rule-plus-local-search baseline is far from optimal at both sizes: 280.2 at eight stores
(0/10 optima) and 388.5 at twelve (0/10). The three alternative metaheuristics are also far
behind the ALNS under the same evaluation budget; they are basic implementations and are not
tuned, which is stated as a limitation. The age-blind exact plan is the strongest informed
baseline on solution quality only when age is ignored; evaluated under the real ages it is the
worst plan in the table.

## 5.5 Component analysis

At twelve stores with the default destroy size, the greedy construction has mean gap 794.1, the
ALNS without unserved-store retry 518.9, and the full ALNS 326.5. The retry is the largest single
component. The gap drops to 3.95 when the destroy size is set to 4–6, so the component ranking
is reported under the default setting and the tuned setting is reported separately; the two
should not be conflated.

## 5.6 Sensitivity analysis

**Rejection penalty.** The penalty is varied from 0 to 800. At penalty 0 the age-aware plan is
worse by 116.5 because it pays extra transport; at 50 it is better by 133.5 (4/5), at 100 by
383.5 (4/5), and at 200, 400 and 800 by 883.5, 1883.5 and 3883.5 (5/5). The break-even lies
between 0 and 50 per delivery.

**Problem size.** The exact DP is used at 8 and 12 stores; the ALNS is used at 20 stores, where
it improves the greedy plan in 10/10 instances by 1083.6 on average. The MILP does not close the
gap at 20 stores within 30 s.

## 5.7 Robustness analysis

Two one-dimensional shocks are applied to the nominal plans without re-optimization, 50
scenarios per instance over ten instances.

| Shock | Age-aware mean | Age-blind mean | Wins | Infeasible deliveries |
| --- | --- | --- | --- | --- |
| Warehouse age ±0.5 days | 1140.9 | 3136.3 | 100% | 0.41 vs 8.41 |
| Travel speed ±10% | 1131.7 | 3138.7 | 100% | 0.36 vs 8.43 |

The age-aware plan is more robust in both shocks. Demand remains deterministic and the shocks
are global, so this is a plan-robustness check, not a stochastic optimization model.

## 5.8 Computational interpretation

The experiments support four claims. First, the age-aware plan is better in every tested exact
instance, and the advantage is statistically clear at 8 and 12 stores. Second, the mechanism is
an interaction: the age+MLOR difference is 874.5, larger than MLOR-only 195.6 plus age-only
579.5. Third, the ALNS is clearly better than the rule-plus-local-search baseline and the three
alternative metaheuristics, but its held-out gap is 17.12, not near-zero. Fourth, the age-aware
plan is more robust to age and speed errors than the age-blind plan.

They do not support claims of near-optimality, of optimality at 20 stores, of real demand, or of
a stochastic model. The runtime table is reported separately; the exact DP takes 14.86 s at 12
stores, while the heuristics remain below 0.5 s.
