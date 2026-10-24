"""Generate tests/vectors.json from the Python library. Run: python tests/make_vectors.py"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from cement_calc import EXAMPLE_PLUG, EXAMPLE_PRIMARY, InputError, evaluate  # noqa: E402


def p(**over):
    c = dict(EXAMPLE_PRIMARY)
    c.pop("label", None)
    c.update(over)
    return c


def b(**over):
    c = dict(EXAMPLE_PLUG)
    c.pop("label", None)
    c.update(over)
    return c


CASES = [
    ("primary_example", p()),
    ("plaus_unusual_lead", p(lead_density_ppg=9.0, lead_yield_ft3_sk=5.5, lead_water_gal_sk=30.0)),
    ("plaus_unusual_fluids", p(mud_density_ppg=6.0, oh_excess_pct=150, pump_output_bbl_stk=1.2)),
    ("plaus_tight_clearance", p(open_hole_in=6.0)),
    ("plaus_err_slurry_density", p(tail_density_ppg=27.0)),
    ("plaus_err_yield_low", p(tail_yield_ft3_sk=0.3)),
    ("plaus_err_water_over_yield", p(tail_water_gal_sk=10.0)),
    ("plaus_err_mud_density", p(mud_density_ppg=3.0)),
    ("primary_vertical", p(tvd_equals_md=True)),
    ("primary_no_prev_casing", p(prev_shoe_md_ft=0, prev_casing_id_in=0, tvd_equals_md=True)),
    ("primary_tail_into_casing", p(prev_shoe_md_ft=11000, tvd_equals_md=True)),
    ("primary_lead_at_surface", p(top_lead_md_ft=0, tvd_equals_md=True, spacer_bbl=20)),
    ("primary_no_lead", p(top_lead_md_ft=10000, tvd_equals_md=True)),
    ("primary_no_fc_tvd", p(tvd_float_collar_ft=None)),
    ("primary_spacer_crosses_shoe", p(spacer_bbl=150)),
    ("primary_spacer_to_surface", p(spacer_bbl=900, tvd_equals_md=True)),
    ("primary_frac_exceeded", p(frac_emw_ppg=11.0)),
    ("primary_no_pump", p(pump_output_bbl_stk=None)),
    ("primary_heavy_disp", p(disp_density_ppg=16.0, tvd_equals_md=True)),
    ("primary_tail_below_fc", p(top_tail_md_ft=14960, top_lead_md_ft=9000, tvd_equals_md=True)),
    ("primary_tail_below_fc_deviated", p(top_tail_md_ft=14960, top_lead_md_ft=9000, tvd_top_lead_ft=8800, tvd_top_tail_ft=10211, tvd_float_collar_ft=None)),
    ("plug_example", b()),
    ("plaus_err_plug_water", b(slurry_yield_ft3_sk=0.55)),
    ("plaus_plug_unusual_yield", b(slurry_yield_ft3_sk=4.5)),
    ("plug_no_excess_no_spacer", b(excess_pct=0, spacer_ahead_bbl=0)),
    ("plug_in_casing", b(hole_id_in=6.276, pipe_od_in=2.875, pipe_id_in=2.441, plug_length_ft=300, plug_bottom_md_ft=12000, excess_pct=0)),
    ("plug_underdisplaced", b(underdisplace_bbl=2.5)),
    ("plug_no_water_no_pump", b(slurry_water_gal_sk=None, pump_output_bbl_stk=None)),
    ("err_casing_od_ge_hole", p(casing_od_in=8.75)),
    ("err_casing_id_ge_od", p(casing_id_in=5.6)),
    ("err_float_collar_below_shoe", p(float_collar_md_ft=15010)),
    ("err_tops_order", p(top_lead_md_ft=10500)),
    ("err_tail_at_shoe", p(top_tail_md_ft=15000)),
    ("err_prev_shoe_order", p(prev_shoe_md_ft=15000)),
    ("err_prev_id", p(prev_casing_id_in=5.0)),
    ("err_tvd", p(tvd_top_tail_ft=4000)),
    ("err_missing_tvd", p(tvd_shoe_ft=None)),
    ("err_density", p(mud_density_ppg=0)),
    ("err_excess", p(oh_excess_pct=-1)),
    ("err_yield", p(lead_yield_ft3_sk=0)),
    ("err_frac", p(frac_emw_ppg=0)),
    ("err_not_number", p(shoe_md_ft="x")),
    ("err_plug_pipe_od_ge_hole", b(pipe_od_in=8.75)),
    ("err_plug_pipe_id_ge_od", b(pipe_id_in=3.6)),
    ("err_plug_length", b(plug_length_ft=0)),
    ("err_plug_above_surface", b(plug_bottom_md_ft=300)),
    ("err_plug_yield", b(slurry_yield_ft3_sk=0)),
    ("err_mode", {"mode": "squeeze"}),
    ("err_sacks_overflow", b(slurry_yield_ft3_sk=1e-320)),
]


def main():
    out = {"generator": "tests/make_vectors.py", "tolerance_rel": 1e-9, "tolerance_abs": 1e-9, "cases": []}
    for name, case in CASES:
        case = {k: v for k, v in case.items() if v is not None}
        try:
            res = evaluate(case)
        except InputError as exc:
            out["cases"].append({"name": name, "input": case, "error": exc.code})
            continue
        out["cases"].append({"name": name, "input": case, "result": res})
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {len(out['cases'])} vectors to tests/vectors.json")


if __name__ == "__main__":
    main()
