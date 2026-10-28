# Age-aware cold-chain location-routing with store minimum remaining shelf life

> 草稿，2026-10-28。文献：COR 2019 与 TRSC 2018 已读全文，Omega 2019 未读；在 Omega 核对前，不宣称“首次”。

## Abstract（草稿）

Fresh-food warehouses hold batches of different ages, and stores often reject deliveries whose remaining shelf life is below a store-specific minimum (MLOR). We study a cold-chain location-routing problem in which opening warehouses, assigning stores, routing vehicles, and using inventory of different ages are decided together. The key relation is that travel time consumes shelf life: an old batch can only serve nearby stores or stores with a low MLOR. We formulate a mixed-integer program, solve small and medium instances exactly by subset dynamic programming, and develop an age-feasible adaptive large neighbourhood search (ALNS) for larger instances. On 8- and 12-store synthetic instances, age-aware planning is never worse than an age-blind plan and is better in 9/10 and 7/10 cases; the ALNS reaches the exact optimum in 7/10 twelve-store instances with a mean relative gap of 2.14%. A penalty sensitivity shows that age-aware planning pays once the per-delivery rejection cost exceeds about 7 in the synthetic scale. All parameters are synthetic; the results are conditional, not field estimates.

## 1. Background

Two-echelon cold-chain networks move fresh products from a central warehouse or supplier to regional warehouses and then to stores. Warehouses hold inventory, and inventory is not homogeneous: batches have different production dates and therefore different remaining shelf life. Stores commonly impose a minimum remaining shelf life (MLOR) at delivery, either as a contractual acceptance rule or as a markdown trigger. A delivery that arrives too late, or after a long route, may be rejected even if the vehicle arrives within the time window.

The operational decision is therefore not only where to open warehouses and how to route vehicles, but also which inventory age serves which store. Travel time is a shelf-life tax: if a batch of age a leaves warehouse i and reaches store j after t minutes, the remaining shelf life is L − a − t, and it must be at least MLOR_j. Old inventory has a shorter effective service radius.

## 2. Literature and gap

We compare the three closest works by full text where available.

| Work | What it models | What it does not |
| --- | --- | --- |
| Rohmer, Claassen, Laporte (2019, COR 107:156–172) | Two-echelon inventory-routing: supplier, depot storage, customer delivery patterns; transport and holding costs; MILP and ALNS | Full text has no “shelf life” and no remaining-shelf-life state; no store delivery threshold |
| Crama, Rezaei, Savelsbergh, Van Woensel (2018, TRSC) | Stochastic perishable inventory-routing with a fixed depot; store inventory by remaining shelf life k, FIFO; stockout-probability service level (TSL); freshness and waste metrics | No store-specific minimum remaining shelf life at delivery; no location decision |
| Qiu, Qiao, Pardalos (2019, Omega) | Integrated production, replenishment, delivery, routing and inventory for perishable products | Full text closed access (OpenAIRE CLOSED; only a Mendeley dataset is open); residual risk |

The specific relation studied here—store-specific MLOR at delivery, warehouse inventory age, and location-routing decided together—is not present in the two full texts we read. We treat it as a **difference to be verified**, not as a confirmed blank: the Omega paper has not been read.

## 3. Problem definition and model

### Sets and parameters

- I: candidate warehouses; J: stores; V: vehicles, each based at one warehouse i(v).
- L: shelf life; a_i: age of the batch held at warehouse i; m_j: store j's MLOR.
- d_j: demand; Q: vehicle capacity (stores); τ_kj: travel time; c_kj: travel cost.
- F_i: opening cost; G: vehicle fixed cost; P: penalty per unserved or rejected delivery.

### Variables

- y_i ∈ {0,1}: warehouse i open.
- r_v ∈ {0,1}: vehicle v used.
- x_kjv ∈ {0,1}: vehicle v travels from k to j (k = 0 is its warehouse, j ∈ J).
- T_j ≥ 0: arrival time at store j.
- s_j ∈ {0,1}: store j served.

### Constraints

Visit each served store once:

```text
Σ_v Σ_{k∈J∪{0}} x_kjv = s_j,   j ∈ J.
```

Flow conservation at stores and at the depot (x_j0v denotes the return arc to the vehicle's warehouse):

```text
Σ_{k∈J∪{0}} x_kjv = Σ_{k∈J∪{0}} x_jkv,   j ∈ J, v ∈ V.
```

Capacity and vehicle activation:

```text
Σ_j d_j Σ_k x_kjv ≤ Q r_v,   v ∈ V,
y_i(v) ≥ r_v,   v ∈ V.
```

Time propagation (MTZ; positive travel times eliminate subtours):

```text
T_j ≥ T_k + τ_kj − M(1 − x_kjv),   j,k ∈ J, v ∈ V,
T_j ≥ τ_i(v),j − M(1 − x_0jv),   j ∈ J, v ∈ V.
```

Remaining shelf life at delivery, applied only for the vehicle that serves j:

```text
T_j ≤ L − a_i(v) − m_j + M(1 − Σ_{k∈J∪{0}} x_kjv),   j ∈ J, v ∈ V.
```

Objective:

```text
min Σ_i F_i y_i + G Σ_v r_v + Σ_{k,j,v} c_kj x_kjv + P Σ_j (1 − s_j).
```

All x_kjv with k = j are fixed to zero.

**Lemma 1.** For a fixed serving vehicle v and store j, the shelf-life constraint is equivalent to the arrival deadline T_j ≤ L − a_i(v) − m_j. The maximum inventory age that can serve j is L − m_j − T_j, which decreases one-for-one with travel time.

The model is a multi-depot vehicle-routing problem with an age-dependent arrival deadline. Without the shelf-life constraint it reduces to a standard location-routing problem; with a_i = 0 and m_j = 0 it becomes an LRP with a common deadline L; with a single warehouse and fixed routes it becomes a perishable inventory-routing problem with store-specific deadlines.

## 4. Algorithm

Exact subset dynamic programming is used for small and medium instances: enumerate feasible routes per warehouse, then a DP over covered store subsets and opened warehouses. It solves 8 stores quickly and 12 stores in about 19 seconds per instance.

For larger instances we use an age-feasible ALNS:

- Initial solution: greedy insertion by MLOR, respecting remaining shelf life.
- Destroy: remove 2–4 served stores and 1–2 currently unserved stores.
- Repair: reinsert each removed store at the cheapest age-feasible position across warehouses and routes; allow a new route; keep unserved if no feasible position exists.
- Acceptance: accept only improving solutions in the current implementation.
- Cost: opening, vehicle, transport and a penalty for unserved stores.

## 5. Experiments (summary)

All instances are synthetic; parameters are illustrative.

| Experiment | Result |
| --- | --- |
| Minimal 2-warehouse 3-store check | Age-blind plan 220, execution 420 with one infeasible store; age-aware 260, zero infeasible |
| Exact DP, 8 stores | Age-aware better 9/10, never worse |
| Exact DP, 12 stores | Age-aware better 7/10, 0 worse, 3 ties |
| ALNS vs exact, 12 stores | 7/10 optimal, mean gap 15.85, mean relative gap 2.14%, max 124.45 |
| ALNS, 20 stores | Improves greedy 10/10, mean 1280.1 |
| Ablation, 12 stores | Greedy gap 473.4; no unserved retry 280.9; full ALNS 15.85 |
| Penalty sensitivity, 8 stores | Age-blind cheaper by 36.4 at penalty 0; age-aware better from penalty 50; break-even about 7 per infeasible delivery |

The ablation supports the role of the unserved-retry component: old warehouses leave high-MLOR stores unserved, and only reinsertion can place them at a fresh warehouse.

## 6. Discussion and limitations

- The gap is not fully verified: Omega 2019 has not been read. If it contains a store-level remaining-shelf-life constraint, the contribution must be repositioned or withdrawn.
- The model uses one temperature zone, one product, one age class per warehouse, and a single period. Multi-temperature, multi-product and multi-period extensions are open.
- All parameters are synthetic. The break-even penalty is a model quantity, not an observed markdown cost; no field recommendation follows.
- The ALNS is a standard destroy-repair scheme with an age-feasible insertion; its contribution is the feasibility logic, not a new metaheuristic.
- The 20-store experiments have no lower bound; the 12-store exact comparison is the current quality evidence.

## 7. Status

Draft only. The next steps are: obtain Omega 2019 (currently closed access; only a Mendeley dataset is open); if the gap holds, complete the experiments section, add the exact DP formulation details and the ALNS pseudo-code, and prepare the figures. No submission before the Omega check.
