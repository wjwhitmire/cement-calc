"""Command line: cement-calc JOBFILE [--json]

JOBFILE is JSON or key/value CSV/TSV (see README). Use `--example primary`
or `--example plug` to run the built-in example data instead.
"""

from __future__ import annotations

import argparse
import json
import sys

from .core import EXAMPLE_PLUG, EXAMPLE_PRIMARY, InputError, evaluate
from .parse import MAX_BYTES, parse_text


def _f(x, nd=2):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def _print_primary(r: dict) -> None:
    c = r["capacities"]
    print("Capacities                          bbl/ft      ft3/ft")
    for k, label in (("casing_inside", "Casing inside"), ("cased_annulus", "Cased hole annulus"),
                     ("open_hole_annulus", "Open hole annulus (gauge)"),
                     ("open_hole_annulus_with_excess", "Open hole annulus + excess")):
        print(f"  {label:<32}{c[k]['bbl_ft']:>9.5f}  {c[k]['ft3_ft']:>10.4f}")
    print("Annular intervals")
    for iv in r["intervals"]:
        print(f"  {iv['fluid']:<5} {iv['geometry']:<6} {iv['top_md_ft']:>9,.0f} to {iv['bottom_md_ft']:>9,.0f} ft"
              f"  excess {iv['excess_pct']:>5.1f}%  {iv['vol_bbl']:>9.2f} bbl")
    st = r["shoe_track"]
    print(f"Shoe track: {st['length_ft']:,.0f} ft, {st['vol_bbl']:.2f} bbl")
    for name in ("lead", "tail"):
        s = r[name]
        print(f"{name.title()}: {s['vol_bbl']:.2f} bbl, {s['vol_ft3']:.1f} ft3, {s['sacks']:,} sk, mix water {s['mix_water_bbl']:.2f} bbl")
    d = r["displacement"]
    print(f"Displacement to float collar: {d['vol_bbl']:.2f} bbl, strokes {_f(d['strokes'], 0)}")
    p = r["pressure"]
    print(f"Annulus hydrostatic at shoe: {p['annulus_psi']:,.0f} psi  (EMW {p['shoe_emw_ppg']:.2f} ppg vs frac {p['frac_emw_ppg']:.2f} ppg)")
    print(f"At float collar: annulus {p['annulus_at_fc_psi']:,.0f} psi, inside {p['inside_at_fc_psi']:,.0f} psi")
    print(f"Differential (U-tube) at bump: {p['differential_psi']:,.0f} psi")


def _print_plug(r: dict) -> None:
    c = r["capacities"]
    for k in ("hole", "pipe_inside", "annulus"):
        print(f"Capacity {k:<12} {c[k]['bbl_ft']:.5f} bbl/ft  {c[k]['ft3_ft']:.4f} ft3/ft")
    s = r["slurry"]
    print(f"Slurry: {s['vol_bbl']:.2f} bbl, {s['vol_ft3']:.1f} ft3, {s['sacks']:,} sk, mix water {_f(s['mix_water_bbl'])} bbl")
    print(f"Balanced column height, pipe in: {r['column_height_ft']:.1f} ft (top {r['top_with_pipe_in_md_ft']:,.1f} ft MD)")
    print(f"Spacer behind to balance: {r['spacer_behind']['vol_bbl']:.2f} bbl")
    d = r["displacement"]
    print(f"Displacement: {d['vol_bbl']:.2f} bbl, strokes {_f(d['strokes'], 0)}")
    print(f"Top after pulling pipe (gauge hole): {r['top_after_pull_gauge_md_ft']:,.1f} ft MD")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cement-calc", description="Cementing volumetrics cross-check. The service company's job design governs.")
    ap.add_argument("jobfile", nargs="?", help="JSON or key,value CSV/TSV input file")
    ap.add_argument("--example", choices=["primary", "plug"], help="run built-in example data")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    a = ap.parse_args(argv)
    try:
        if a.example:
            case = dict(EXAMPLE_PRIMARY if a.example == "primary" else EXAMPLE_PLUG)
        elif a.jobfile:
            with open(a.jobfile, "rb") as fh:
                raw = fh.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise InputError("file", "File is larger than 5 MB.")
            case = parse_text(raw.decode("utf-8", errors="replace"))
            tvd_keys = ("tvd_top_lead_ft", "tvd_top_tail_ft", "tvd_float_collar_ft", "tvd_shoe_ft")
            if case.get("mode", "primary") == "primary" and "tvd_equals_md" not in case and not any(k in case for k in tvd_keys):
                # same rule as the browser tool: a file with no TVDs is read as a vertical well
                case["tvd_equals_md"] = True
                print("note: the file has no TVDs, so TVD = MD (vertical well) is assumed. Add tvd_equals_md,no and the TVDs to change it.", file=sys.stderr)
        else:
            ap.error("give a JOBFILE or --example")
        r = evaluate(case)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: could not read file: {exc.strerror}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        (_print_primary if r["mode"] == "primary" else _print_plug)(r)
        for w in r["warnings"]:
            print(f"WARNING: {w['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
