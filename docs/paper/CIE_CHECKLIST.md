# CIE submission checklist

Status date: 2026-10-31. Target: *Computers & Industrial Engineering* (Elsevier).

Legend: ✅ satisfied; ⚠️ satisfied with a stated limitation; ❌ not satisfied.

## 1. Manuscript architecture

| Item | Status | Evidence / note |
| --- | --- | --- |
| Problem-driven introduction | ✅ | §1 starts from warehouse age, store MLOR and route time; no Industry 4.0 preamble |
| Related work by scientific category | ✅ | §2: perishable IRP, two-echelon IRP/LRP, MLOR |
| Problem gap vs method gap separated | ✅ | §2.4 |
| Model section with assumptions and notation | ✅ | §3.1, Tables 1–2 |
| Method section tied to problem structure | ✅ | §4.2 explains cross-warehouse reassignment |
| Computational section organized by claims | ✅ | §5.1–5.9 |
| Managerial implications only where supported | ✅ | §5.9, every point marked conditional |
| Conclusions with limitations | ✅ | §6 |

## 2. Method–problem alignment

| Item | Status | Evidence / note |
| --- | --- | --- |
| Exact method for small/medium instances | ✅ | subset DP, 8 and 12 stores |
| Heuristic for larger instances | ✅ | age-feasible ALNS, 20 stores |
| Method choice justified by structure | ✅ | §4.2; destroy–repair contains cross-warehouse reassignment |
| Feasibility maintenance, termination, cost | ✅ | §4.2 final paragraph |
| No claim of theoretical optimality for the heuristic | ✅ | LP bound at 20 stores is loose; stated |

## 3. Computational evidence

| Item | Status | Evidence / note |
| --- | --- | --- |
| Strong baseline (not only a straw man) | ✅ | age-blind exact, rule + 2-opt/relocate |
| Alternative metaheuristics | ⚠️ | SA, tabu, GA under equal evaluation budget; all untuned, stated as indicative |
| Component ablation | ✅ | greedy / no-retry / full ALNS |
| Sensitivity analysis | ✅ | rejection penalty 0–800; break-even ≈ 7 |
| Size sensitivity | ✅ | 8, 12, 20 stores |
| Statistical variability | ✅ | 95% intervals; non-significant results reported as such |
| Runtime table | ❌ | only DP 12 ≈ 19 s is reported; no systematic runtime comparison |
| Robustness under uncertainty | ❌ | deterministic model; no scenario analysis |
| Real industrial data | ❌ | synthetic instances plus a real-geography illustration with unit demand |
| Tuning separated from testing | ✅ | development seeds 5–9, test seeds 10–19; earlier in-sample run documented as superseded |
| Failed runs retained | ✅ | demand-weighted trial reverted and documented |

## 4. CIE/Elsevier formal items

| Item | Status | Evidence / note |
| --- | --- | --- |
| Highlights | ✅ | 5 items, 62–79 characters each |
| Abstract self-contained | ✅ | 230 words, includes numbers and scope |
| Keywords | ✅ | 5 keywords |
| Declaration of competing interest | ✅ | present |
| Data availability statement | ✅ | present; synthetic generator and repository outputs |
| Cover letter | ✅ | `MLOR_COVER_LETTER.md`; author fields are placeholders |
| Author names, affiliations, corresponding author | ❌ | placeholders `Author Name` / `Affiliation` |
| CRediT author statement | ❌ | not added; depends on actual author roles |
| Funding statement | ❌ | not added; cannot be asserted without information |
| Reference metadata | ✅ | all six verified against DOI/Crossref records |
| Full texts of all cited works | ⚠️ | Crama and Rohmer read; Coelho and Govindan abstracts; Qiu and Singh closed |
| Current CIE Guide for Authors formatting | ❌ | publisher pages returned HTTP 403 in this environment; not verified |

## 5. Highest-risk items for review

1. **No runtime comparison.** CIE computational papers commonly report solution time. Add a runtime table at 8/12/20 stores before submission.
2. **Synthetic data only.** The real-network illustration is geography, not demand. Frame the paper as a model-based study, or add a real case.
3. **Alternative metaheuristics are basic versions.** The equal-budget comparison is indicative; a reviewer may ask for tuned GA/tabu or a second budget level.
4. **Full-text coverage.** Qiu et al. (2019) and Singh and Kuthambalayan (2022) remain closed; the MLOR-in-LRP gap is stated as "to be verified", not confirmed.
5. **Author-dependent items.** Names, affiliations, CRediT and funding cannot be completed without the authors.

## 6. What is already defensible

- The age–distance–threshold mechanism is stated as an arrival deadline and proved to make the route-feasibility subproblem NP-complete.
- The age-aware plan is never worse than the age-blind plan in the tested exact instances, and the difference is statistically clear at 8 and 12 stores.
- The ALNS is compared with exact, rule-plus-local-search and three alternative metaheuristics under a stated budget.
- The paper does not claim a new problem class, field savings or optimality at 20 stores.
