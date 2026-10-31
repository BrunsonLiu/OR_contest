# Parameter audit

The current experiments use normalized, illustrative parameters. Some are defensible as
structural choices; others are not realistic and must be either relabelled as normalized units
or recalibrated. This note separates the two.

## What can be tied to the literature

| Modelling element | Literature anchor | What we borrow |
| --- | --- | --- |
| Age-dependent perishable inventory | Coelho and Laporte (2014), COR 47, 42–52 | Inventory age as a state; age changes cost and feasible service |
| Remaining shelf life, FIFO issuing | Crama et al. (2018), Transportation Science 52(3), 526–546 | Shelf life consumed in transit; store-level freshness matters |
| Two-echelon perishable IRP | Rohmer et al. (2019), COR 107, 156–172 | Perishable products in a two-echelon setting; depot storage |
| Two-echelon LRP with time windows for perishable food | Govindan et al. (2014), IJPE 152, 9–28 | Location-routing with perishability and time windows |
| Minimum remaining shelf life (MLOR) | Singh and Kuthambalayan (2022), CIE 163, 107812 | MLOR as a target freshness threshold |

These papers support the **structure** of the model, not the numerical magnitudes below. None of
them uses our exact instance parameters, and the paper must not imply that they do.

## Current values and verdict

| Parameter | Current value | Verdict | Action |
| --- | --- | --- | --- |
| Shelf life | 6 days | Plausible for fresh dairy/produce; literature uses days | Keep; cite the age/remaining-shelf-life literature |
| Warehouse ages | 0, 2.5, 4.5 days | Constructed to create fresh/old contrast | Keep; call it illustrative |
| Store MLOR | 1, 2, 3 days | Plausible ordering; MLOR definition anchored | Keep; cite Singh and Kuthambalayan |
| Vehicle capacity | 4 stores | Not a real payload; a city store needs tons, not one unit | Relabel as "four normalized demand units" or recalibrate |
| Demand | 1 per store | Unit-demand abstraction; cannot carry a city's daily demand | Relabel as normalized; do not call it real demand |
| Opening cost | 100 | Arbitrary cost unit | Relabel as normalized cost |
| Vehicle fixed cost | 50 | Arbitrary | Relabel as normalized cost |
| Transport cost | 0.5 per km | Arbitrary; real cold-chain rates are several yuan per ton-km | Relabel as normalized; do not call it yuan |
| Speed | 100 km/day | Too slow for real road transport (40–60 km/h) | Relabel as normalized or recalibrate |
| Unserved penalty | 200 | Model device; equals two openings | Keep as device; sensitivity 0–800 |
| Coordinates | [0,300]^2 | Regional scale; acceptable | Keep |
| Warehouses | 3 | Contest-driven; one fresh, two old | Keep; state it |

## The honest position

Two options are defensible.

**Option A (recommended for the current paper).** Keep the normalized instance but relabel every
unit: "cost units", "normalized demand units", "normalized speed". Delete "per km", "km per day"
and "yuan" wherever they imply real magnitudes. Add a parameter-provenance table and say
explicitly that the numbers are illustrative and chosen to create the age–distance–threshold
tension, not calibrated to a firm. Cite the five papers above only for structure.

**Option B (stronger, expensive).** Recalibrate to real scale: demand in tons, vehicle capacity
8–12 t, transport 3–6 yuan per ton-km, vehicle 200–500 yuan per trip, opening 5,000–20,000 yuan,
speed 40 km/h, shelf life and MLOR from a real category. This requires split delivery or
multi-trip, so it changes the model and forces a full rerun.

Option A is honest but weaker on industrial relevance. Option B is what a CIE reviewer would
prefer, but it is a new model, not a parameter tweak.

## What not to do

Do not keep "0.5 per km", "100 km per day" and "capacity 4 stores" while calling the instance a
cold-chain distribution case. That is the specific overclaim a reviewer will catch.
