# Testing

Every function of Cement Calc, how it was tested and the result. Browser checks ran against the published form of the page: `git archive HEAD`, publish placeholders filled, `docs/` served under `/cement-calc/` on localhost, headless Chromium at 1280 px and 400 px (touch), light and dark.

## How to rerun

```bash
pip install -e .[dev]
pytest -q                                   # library, parser, CLI
python tests/make_vectors.py && node web/parity.test.mjs   # JS core matches Python
python web/build_pages.py                   # rebuild docs/index.html
pip install playwright && python -m playwright install chromium
pytest -q tests/test_published_browser.py   # published page under /cement-calc/, main workflows
```

`tests/test_published_browser.py` copies `docs/`, fills the publish placeholders, serves the copy under `/cement-calc/` and fails on page errors, console errors, CSP violations, sideways scroll or leftover placeholders. It skips itself without Playwright; CI runs it in the `browser` job.

Suite size: 64 pytest + 2,031 parity checks before this pass; 80 pytest (8 browser) + 2,493 parity checks after.

## Function inventory

### Browser page

| Function | What was done | Result |
|---|---|---|
| Page load, published form | Opened `/cement-calc/` | Pass: primary example valid, no errors or CSP violations |
| Layout 1280 / 400 px, light and dark, both tabs | Scroll width | Pass |
| Touch targets | 400 px touch | Pass (the 22 px TVD = MD checkbox sits in a 44 px label) |
| Tabs: primary / balanced plug | Click, arrow keys, remembered after reload | Pass |
| Primary inputs (27 boxes) | Casing ID above OD, OD above hole, float collar at shoe, tops out of order, excess 600, density 0, yield 0, impossible TVD, blank shoe | Pass: refused, the box is marked |
| Negative spacer | -1 bbl | Fail before (message shown but no box marked); pass after fix |
| Error wording | Density 0 | Fail before (`lead_density_ppg must be ...`); pass after fix ("Lead slurry density must be ...") |
| TVD = MD checkbox | Tick disables the TVD boxes | Pass |
| Pump output blank | | Pass: strokes n/a |
| Spacer larger than the annulus above the lead | 5,000 bbl | Pass: warning |
| Data tag | Example label, "Your inputs" after an edit | Pass |
| Load example data (both tabs) | Click | Pass |
| Result tiles, tables, schematic, stamps | Read | Pass: 715 and 1,302 sacks, 346.9 bbl displacement |
| Plug inputs | Pipe OD above hole, pipe ID above OD, bottom above length, excess -1, yield 0, under-displace 100 | Pass |
| Under-displacement warning | 2 bbl | Pass |
| Copy results as CSV (both tabs) | Clipboard | Pass |
| Copy after an input error | Click | Fail before (copied the last good result); pass after fix (button disabled) |
| Copy fallback | No clipboard | Pass |
| Load job file: example primary CSV, plug JSON (switches tab), quoted `"15,000"` | | Pass |
| Load: `lead_density_ppg,11,5` unquoted | | Fail before (read as 11 ppg, "Inputs valid"); pass after fix (refused) |
| Load: `"11,5"` quoted | | Fail before (read as 115, caught only by the range check); pass after fix (refused as a decimal comma) |
| Load: empty, bad JSON, array JSON, bad mode, partial file, over 5 MB | | Pass: message |
| Load a primary file with no TVDs | | Before: stopped on "Missing input: tvd_top_lead_ft"; after: read as vertical with a note (new) |
| Method and limits | Expand | Pass |
| Network | `fetch` from the page | Pass: blocked by CSP; no network features |
| Print | Print to PDF | Pass |
| `web/app.html` via file:// | Opened directly | Pass |

### CLI

| Command | Result |
|---|---|
| `--example primary`, `--example plug` | Pass |
| `examples/primary.csv`, `examples/plug.json --json` | Pass |
| No input, missing file, comma-split number, bad mode, binary file | Pass: message and exit 2 |
| Primary file without TVDs | Pass (new): vertical well assumed, note on stderr |

### Library

`capacity_bbl_ft`, `annular_capacity_bbl_ft`, `bbl_to_ft3`, `sacks_for`, `mix_water_bbl`, `hydrostatic_psi`, `primary_job`, `balanced_plug`, `evaluate`, `parse_text`, `EXAMPLE_PRIMARY`, `EXAMPLE_PLUG`: covered by pytest and parity vectors. Pass.

## Correctness checks

Standard oilfield volumetrics recomputed by hand outside the repo (capacity = D^2/1029.4 bbl/ft, 5.6146 ft3/bbl, 0.052 psi/ft/ppg, balanced plug h = V/(Ca + Cp), spacer behind = spacer ahead x Cp/Ca) and compared with both cores in the published page.

| Case | Hand calculation | Result |
|---|---|---|
| Primary example lead | 500 ft cased (0.046442 bbl/ft) + 5,000 ft open hole (0.044990 x 1.3) = 315.6546 bbl, 715 sacks, 243.44 bbl water | Pass |
| Primary example tail | 5,000 ft open hole + 80 ft shoe track (0.023248) = 294.2936 bbl, 1,302 sacks | Pass |
| Displacement and strokes | 0.023248 x 14,920 = 346.8627 bbl; 3,400.6 strokes at 0.102 | Pass |
| Spacer top | 4,500 - 40 / 0.046442 = 3,638.71 ft | Pass |
| U-tube at bump, example | Annulus 1,930.0 + 537.4 + 3,199.3 + 265.8 = 5,932.5 psi; inside 0.052 x 8.4 x 10,210 = 4,459.7; differential 1,473 psi | Pass |
| U-tube, cement to surface against water | 0.052 x (15.0 - 8.34) x 9,900 = 3,428.568 psi; shoe EMW 15.0 over a 14.5 frac flags | Pass |
| Balanced plug example | V = 44.6255 bbl, h = 638.445 ft, spacer behind 1.1879 bbl, displacement 60.8674 bbl, 237 sacks, equal heights inside and outside | Pass |
| Zero excess, 30,000 ft vertical | 248.17 bbl lead; 695.12 bbl displacement | Pass |
| Invalid geometry, order, ranges, decimal comma as a value | Refused | Pass |

## Automation audit

| Decision point | Before | After |
|---|---|---|
| Tab for a loaded file | Already switches to the file's mode | No change |
| TVD for a file with none | Dead end: "Missing input: tvd_top_lead_ft" | Vertical well assumed with a one-line note; untick to enter TVDs (browser and CLI) |
| Error wording | Raw keys | Plain labels, and the box is marked for "cannot be negative" errors too |
| Copy results | Copied stale results after an error | Disabled until inputs are valid |
| Pump output, mix water, under-displacement | Already optional | No change |
| Implausible inputs | Any positive yield or density under 30 ppg accepted (1e-300 ft3/sk gave astronomical sacks) | Physical limits refused (slurry 4 to 25 ppg, yield 0.5 to 15 ft3/sk and larger than its own water, fluids 5 to 25 ppg); unusual values warn (README table, API Specification 10A and Nelson and Guillot ranges) |

## Known limits

- Oilfield units only. Static volumetrics only (see README).
- Plausibility ranges are screening values (see README); a lab report for an unusual system can legitimately fall outside the warning band.
