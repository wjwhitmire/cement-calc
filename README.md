# Cement Calc

Free, open cementing volumetrics for a primary casing job and a balanced cement plug. Capacities, annular and shoe track volumes, sacks, mix water, displacement and strokes, the static U-tube differential at bump, and shoe hydrostatic against a fracture gradient.

Live tool: https://wjwhitmire.github.io/cement-calc/

The browser tool runs entirely on your device. Nothing you enter is uploaded. The Python library has no runtime dependencies.

**This is a planning cross-check. The service company's job design governs.** Use it to check the arithmetic on a cementing program, not to replace one. It is written from standard oilfield volumetrics and is not affiliated with any service company or app vendor.

## Quick start

```
pip install -e .[dev]
pytest -q
cement-calc --example primary
cement-calc --example plug
cement-calc examples/primary.csv
cement-calc examples/plug.json --json
```

Python:

```python
from cement_calc import evaluate, EXAMPLE_PRIMARY, EXAMPLE_PLUG
r = evaluate(EXAMPLE_PRIMARY)
r["lead"]["sacks"], r["tail"]["sacks"], r["displacement"]["vol_bbl"], r["pressure"]["differential_psi"]
p = evaluate(EXAMPLE_PLUG)
p["column_height_ft"], p["spacer_behind"]["vol_bbl"], p["displacement"]["vol_bbl"]
```

## Input file

A JSON object of named inputs, or one `key,value` pair per row (comma or tab separated, optional `key,value` header, `#` comments, blank lines and extra columns ignored, quoted thousands separators accepted; a comma that is not a thousands separator, such as `11,5`, is refused rather than read as 11 or 115). A primary job file with no TVD keys and no `tvd_equals_md` is read as a vertical well (TVD = MD) and the tool says so. Set `mode` to `primary` (default) or `plug`. Files over 5 MB or 50,000 rows are refused.

Primary job keys (units in the name):

| Key | Meaning |
|---|---|
| `casing_od_in`, `casing_id_in` | Casing OD and ID |
| `shoe_md_ft`, `float_collar_md_ft` | Shoe and float collar MD (shoe track between them) |
| `prev_casing_id_in`, `prev_shoe_md_ft` | Previous casing ID and shoe MD. `prev_shoe_md_ft = 0` means no previous casing |
| `open_hole_in`, `oh_excess_pct` | Open hole diameter (bit size or caliper average) and excess, open hole only |
| `top_lead_md_ft`, `top_tail_md_ft` | Top of lead and top of tail |
| `lead_density_ppg`, `lead_yield_ft3_sk`, `lead_water_gal_sk` | Lead slurry |
| `tail_density_ppg`, `tail_yield_ft3_sk`, `tail_water_gal_sk` | Tail slurry |
| `spacer_bbl`, `spacer_density_ppg` | Spacer ahead of the lead |
| `mud_density_ppg`, `disp_density_ppg` | Mud in the annulus, displacement fluid inside |
| `pump_output_bbl_stk` | Optional, for strokes |
| `frac_emw_ppg` | Fracture gradient at the shoe as EMW |
| `tvd_equals_md` | true for a vertical well |
| `tvd_top_lead_ft`, `tvd_top_tail_ft`, `tvd_float_collar_ft`, `tvd_shoe_ft` | TVD stations when `tvd_equals_md` is false. Float collar is optional |

Balanced plug keys: `hole_id_in` (hole size or casing ID), `pipe_od_in`, `pipe_id_in`, `plug_length_ft`, `plug_bottom_md_ft`, `excess_pct`, `spacer_ahead_bbl`, `slurry_yield_ft3_sk`, and optional `slurry_water_gal_sk`, `pump_output_bbl_stk`, `underdisplace_bbl`.

## Method

### Constants

| Constant | Value | Source |
|---|---|---|
| Capacity divisor | 1029.4 | bbl/ft of a circle of D inches = (pi/4)(D/12)^2 ft^2 / 5.6146 ft^3/bbl = D^2 / 1029.4 |
| Cubic feet per barrel | 5.6146 | 42 gal x 231 in^3/gal / 1728 in^3/ft^3 = 5.6146 |
| Hydrostatic factor | 0.052 psi/ft/ppg | 1 ft^3 = 7.4805 gal; 7.4805 lb/ft^3 / 144 in^2/ft^2 = 0.05195, rounded to 0.052 as used in the field |
| Gallons per barrel | 42 | US oil barrel definition |

### Primary casing job

```
Casing capacity         Ci  = ID^2 / 1029.4                           bbl/ft
Cased annulus           Cc  = (prev ID^2 - OD^2) / 1029.4             bbl/ft, no excess
Open hole annulus       Co  = (hole^2 - OD^2) / 1029.4                bbl/ft
With excess             Co' = Co x (1 + excess% / 100)                open hole only
ft3/ft                  = bbl/ft x 5.6146

Interval volume         V = C x length                                each slurry interval is split at the previous shoe
Shoe track              Vst = Ci x (shoe MD - float collar MD)        filled with tail
Lead                    annulus from top of lead to top of tail
Tail                    annulus from top of tail to shoe, plus Vst
Sacks                   ceil(V_ft3 / yield)                           per slurry, rounded up
Mix water               sacks x water gal/sk / 42                     bbl
Displacement            Ci x float collar MD                          bbl, to the float collar
Strokes                 displacement / pump output
```

Spacer sits directly above the top of lead. Its top is found by filling the annulus upward from the top of lead (cased annulus with no excess above the previous shoe, open hole annulus with excess below it). Mud fills the annulus above the spacer.

Static pressures at bump, by TVD:

```
P = 0.052 x density x (TVD bottom - TVD top), summed over each fluid column
Annulus at float collar = mud + spacer + lead + tail, surface to float collar
Inside at float collar  = displacement fluid, surface to float collar
Differential (U-tube)   = annulus - inside                  positive means the annulus is heavier
Shoe EMW                = annulus hydrostatic at shoe / (0.052 x shoe TVD)
```

The annulus at the float collar is each annulus column cut at the float collar TVD, so lead that sits below the float collar (top of tail set below it) is counted at lead density. When the top of tail is at or above the float collar, the shoe track and the annulus both hold tail below the float collar over the same TVD span, so taking the differential at the float collar or at the shoe gives the same number. The tool reports annulus and inside at the float collar, the annulus total at the shoe, and the shoe EMW against the fracture gradient you enter. When the shoe EMW exceeds it, the result carries a `frac_exceeded` warning and the page shows a red chip.

TVD: with `tvd_equals_md` true, TVD = MD. Otherwise TVD is linear in MD between surface (0, 0) and the stations you enter. Stations must not decrease in TVD and cannot gain more TVD than MD. Every fluid boundary is an entered station except the spacer top (and the float collar when its TVD is left blank), which is interpolated between the surface (or previous station) and the top of lead. In a well that kicks off above the top of lead, the spacer top TVD is therefore approximate, and the pressure error is 0.052 x (spacer density - mud density) x the TVD error. Take station TVDs from the survey.

### Balanced plug

Pipe is open ended with its end at the plug bottom. Spacer ahead is pumped first, then slurry, then spacer behind, then displacement.

```
Hole capacity           Ch = hole^2 / 1029.4
Pipe capacity           Cp = pipe ID^2 / 1029.4
Annular capacity        Ca = (hole^2 - pipe OD^2) / 1029.4
Slurry volume           V  = plug length x Ch x (1 + excess% / 100)
Sacks                   ceil(V x 5.6146 / yield)
Balanced height         h  = V / (Ca + Cp)                       same inside and outside with pipe in
Spacer behind           Vb = spacer ahead x Cp / Ca              equal spacer heights inside and outside
Displacement            Vd = Cp x (bottom MD - h) - Vb - under-displacement
Top with pipe in        bottom MD - h
Top after pulling pipe  bottom MD - V / Ch                        gauge hole
```

The cement heights inside and outside are each recomputed from the volumes and returned so the balance can be checked (`cement_height_inside_ft` equals `cement_height_outside_ft`). With excess in a gauge hole the plug top after pulling sits above the design top by the excess fraction; in a hole washed out by exactly the excess it lands on the design top (`top_after_pull_design_md_ft`).

## Plausibility checks

Values outside physical limits are refused; values that are possible but unusual compute with a warning. Typical ranges follow API Specification 10A neat slurries (Class G: 15.8 ppg, 1.15 ft3/sk, 5.0 gal/sk; Class H: 16.4 ppg, 1.06 ft3/sk, 4.3 gal/sk) and the extended, foamed and weighted systems described in Nelson and Guillot, *Well Cementing*, 2nd ed. (Schlumberger, 2006).

| Input | Refused outside | Warning outside |
|---|---|---|
| Slurry density | 4 to 25 ppg | 11 to 19 ppg (foamed or specially weighted slurries are legitimately outside) |
| Mud, spacer, displacement density | 5 to 25 ppg | 6.5 to 20 ppg |
| Slurry yield | 0.5 to 15 ft3/sk, or not larger than its own mix water (gal/sk / 7.48) | 0.9 to 4.0 ft3/sk |
| Mix water | | 3.5 to 25 gal/sk |
| Open hole excess | 0 to 500 percent | above 100 percent |
| Hole or previous casing ID minus casing OD | | under 0.75 in |
| Pump output | | 0.02 to 0.5 bbl/stk |

## Limits

- Static volumetrics only. No friction pressure, ECD while pumping, free fall or U-tubing during placement, temperature, compressibility, gel strength, or slurry thickening.
- Open hole is one uniform diameter. Use a caliper average and an excess suited to the hole. Excess applies to open hole only; cased overlap uses none.
- Casing is one size from surface to shoe. Tapered strings, liners hung off, stage tools, cross-overs and landing strings are not modeled.
- Shoe track is filled with tail. Rat hole below the shoe, cement left on top of the plug, and surface line volumes are not added.
- Displacement ignores casing stretch, mud compressibility, and pump efficiency. Strokes use the pump output entered.
- Hydrostatics use the 0.052 field factor and densities as entered. TVD between stations is linear in MD, which is approximate in a curve. Only the spacer top (and a float collar entered without TVD) falls between stations, so only those TVDs carry that error.
- The balanced plug assumes open-ended pipe at the plug bottom, a stable base, and pipe pulled slowly. Contamination, slurry left on the pipe wall, and stingers or tail pipe of a different size are not modeled.
- Sacks are rounded up per slurry. Blend design, additives, bulk density and job extras are the service company's call.

## Validation

- `tests/test_core.py` (pytest): hand-computed capacities, annular and shoe track volumes with and without excess, the cased overlap with no excess, sacks rounding including floating-point edge cases, mix water, displacement and strokes, the U-tube sign and value for simple two-fluid cases (cement to surface against water: 0.052 x (15.0 - 8.34) x 9,900 = 3,428.568 psi), spacer placement across the previous shoe, TVD interpolation, frac warning, the balanced plug identity (equal heights inside and outside, equal spacer heights), and input validation (pipe OD at or above hole, float collar at or below shoe, tops out of order, bad TVD, bad numbers).
- `tests/make_vectors.py` writes `tests/vectors.json` from the Python library. `web/parity.test.mjs` extracts the JavaScript core from `web/app.html`, runs every vector in Node and checks every output field to 1e-9 relative, plus error codes and the file parser.

```
python tests/make_vectors.py
node web/parity.test.mjs
python web/build_pages.py      # writes docs/index.html for GitHub Pages
```

## Example data

- Primary: 5-1/2 in, 4.892 in ID production casing in 8-3/4 in hole to 15,000 ft MD (10,212 ft TVD), float collar 14,920 ft, previous 9-5/8 in casing (8.835 in ID) to 5,000 ft. Lead 11.5 ppg from 4,500 ft, tail 14.2 ppg from 10,000 ft, 30% open hole excess, 40 bbl of 12.0 ppg spacer, 10.2 ppg mud, 8.4 ppg displacement.
- Plug: 500 ft balanced plug in 8-3/4 in open hole through 3-1/2 in drill pipe (2.764 in ID), bottom at 9,000 ft, 20% excess, 10 bbl spacer ahead.

These are illustrative inputs, not a job design.

## License

MIT. Copyright 2026 Will Whitmire. See `LICENSE`.
