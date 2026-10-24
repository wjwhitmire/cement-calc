import copy
import json
import math

import pytest

from cement_calc import (
    EXAMPLE_PLUG, EXAMPLE_PRIMARY, InputError, annular_capacity_bbl_ft, balanced_plug,
    capacity_bbl_ft, evaluate, mix_water_bbl, parse_text, primary_job, sacks_for,
)
from cement_calc.cli import main as cli_main

REL = 1e-12


def approx(x):
    return pytest.approx(x, rel=1e-10, abs=1e-9)


def vertical_case(**over):
    """Simple vertical well, no previous casing unless overridden."""
    c = {
        "mode": "primary",
        "casing_od_in": 7.0, "casing_id_in": 6.276,
        "shoe_md_ft": 10000, "float_collar_md_ft": 9900,
        "prev_casing_id_in": 0, "prev_shoe_md_ft": 0,
        "open_hole_in": 8.5, "oh_excess_pct": 0,
        "top_lead_md_ft": 5000, "top_tail_md_ft": 8000,
        "lead_density_ppg": 13.0, "lead_yield_ft3_sk": 1.8, "lead_water_gal_sk": 9.5,
        "tail_density_ppg": 15.8, "tail_yield_ft3_sk": 1.15, "tail_water_gal_sk": 5.0,
        "spacer_bbl": 0, "spacer_density_ppg": 11.0,
        "mud_density_ppg": 10.0, "disp_density_ppg": 10.0,
        "frac_emw_ppg": 16.0, "tvd_equals_md": True,
    }
    c.update(over)
    return c


# ---- capacities, hand computed -------------------------------------------

def test_capacity_hand_values():
    # 8.75^2 = 76.5625 ; 76.5625 / 1029.4
    assert capacity_bbl_ft(8.75) == approx(0.07437585000971439)
    # 4.892^2 = 23.931664 ; / 1029.4
    assert capacity_bbl_ft(4.892) == approx(23.931664 / 1029.4)
    assert capacity_bbl_ft(4.892) == approx(0.023248167864775595)
    # annulus 8.75 x 5.5: (76.5625 - 30.25) / 1029.4 = 46.3125 / 1029.4
    assert annular_capacity_bbl_ft(8.75, 5.5) == approx(0.04498979988342724)
    # 1029.4 is the diameter whose capacity is 1 bbl/ft squared: sqrt(1029.4) in gives 1 bbl/ft
    assert capacity_bbl_ft(math.sqrt(1029.4)) == approx(1.0)


def test_capacity_ft3_conversion():
    r = primary_job(vertical_case())
    c = r["capacities"]["casing_inside"]
    assert c["ft3_ft"] == approx(c["bbl_ft"] * 5.6146)
    # 6.276^2 / 1029.4 = 39.388176 / 1029.4
    assert c["bbl_ft"] == approx(39.388176 / 1029.4)


# ---- volumes --------------------------------------------------------------

def test_open_hole_volumes_with_excess():
    case = vertical_case(oh_excess_pct=25)
    r = primary_job(case)
    ann = (8.5**2 - 7.0**2) / 1029.4  # 23.25/1029.4
    assert r["capacities"]["open_hole_annulus"]["bbl_ft"] == approx(ann)
    assert r["lead"]["vol_bbl"] == approx(ann * 1.25 * 3000)
    st = 6.276**2 / 1029.4 * 100
    assert r["shoe_track"]["vol_bbl"] == approx(st)
    assert r["tail"]["vol_bbl"] == approx(ann * 1.25 * 2000 + st)
    assert r["tail"]["shoe_track_bbl"] == approx(st)
    assert r["total_cement_bbl"] == approx(ann * 1.25 * 5000 + st)


def test_cased_overlap_gets_no_excess():
    r = primary_job(EXAMPLE_PRIMARY)
    cased = [iv for iv in r["intervals"] if iv["geometry"] == "cased"]
    assert len(cased) == 1 and cased[0]["excess_pct"] == 0
    assert cased[0]["top_md_ft"] == 4500 and cased[0]["bottom_md_ft"] == 5000
    assert cased[0]["vol_bbl"] == approx((8.835**2 - 5.5**2) / 1029.4 * 500)
    oh = (8.75**2 - 5.5**2) / 1029.4 * 1.30
    assert r["lead"]["vol_bbl"] == approx((8.835**2 - 5.5**2) / 1029.4 * 500 + oh * 5000)
    st = 4.892**2 / 1029.4 * 80
    assert r["tail"]["vol_bbl"] == approx(oh * 5000 + st)


def test_lead_split_at_previous_shoe_when_tail_also_cased():
    r = primary_job(vertical_case(prev_casing_id_in=8.921, prev_shoe_md_ft=9000, open_hole_in=8.5))
    tail = [iv for iv in r["intervals"] if iv["fluid"] == "tail"]
    assert [iv["geometry"] for iv in tail] == ["cased", "open"]
    assert tail[0]["bottom_md_ft"] == 9000 and tail[1]["top_md_ft"] == 9000


def test_displacement_and_strokes():
    r = primary_job(vertical_case(pump_output_bbl_stk=0.1))
    disp = 6.276**2 / 1029.4 * 9900
    assert r["displacement"]["vol_bbl"] == approx(disp)
    assert r["displacement"]["strokes"] == approx(disp / 0.1)
    assert primary_job(vertical_case())["displacement"]["strokes"] is None


# ---- sacks and mix water --------------------------------------------------

def test_sacks_round_up():
    assert sacks_for(100.0, 1.0) == 100
    assert sacks_for(100.01, 1.0) == 101
    assert sacks_for(99.99, 1.0) == 100
    assert sacks_for(0.0, 1.18) == 0
    # floating point: 118 / 1.18 is 100.00000000000001 in binary; must stay 100
    assert sacks_for(1.18 * 100, 1.18) == 100
    assert sacks_for(0.1 + 0.2, 0.3) == 1


def test_mix_water():
    assert mix_water_bbl(420, 5.0) == approx(50.0)  # 2100 gal / 42
    r = primary_job(EXAMPLE_PRIMARY)
    assert r["lead"]["sacks"] == math.ceil(r["lead"]["vol_ft3"] / 2.48)
    assert r["lead"]["mix_water_bbl"] == approx(r["lead"]["sacks"] * 14.3 / 42)
    assert r["tail"]["sacks"] == math.ceil(r["tail"]["vol_ft3"] / 1.27)


# ---- U-tube ---------------------------------------------------------------

def test_utube_two_fluid_hand_case():
    """Vertical, cement to surface in annulus, water inside. Diff = 0.052 (15 - 8.34) 9900."""
    case = vertical_case(top_lead_md_ft=0, top_tail_md_ft=0, tail_density_ppg=15.0,
                         lead_density_ppg=15.0, disp_density_ppg=8.34, spacer_bbl=0)
    p = primary_job(case)["pressure"]
    assert p["annulus_at_fc_psi"] == approx(0.052 * 15.0 * 9900)
    assert p["inside_at_fc_psi"] == approx(0.052 * 8.34 * 9900)
    assert p["differential_psi"] == approx(0.052 * (15.0 - 8.34) * 9900)
    assert p["differential_psi"] == approx(3428.568)  # 0.052 x 6.66 x 9900
    assert p["differential_psi"] > 0


def test_utube_mud_over_cement():
    """Mud over 2,000 ft of cement in annulus, mud inside as displacement fluid."""
    case = vertical_case(top_lead_md_ft=8000, top_tail_md_ft=8000, tail_density_ppg=16.0,
                         mud_density_ppg=10.0, disp_density_ppg=10.0)
    p = primary_job(case)["pressure"]
    # cement above float collar: 9900 - 8000 = 1900 ft
    assert p["differential_psi"] == approx(0.052 * (16.0 - 10.0) * 1900)


def test_utube_sign_negative_when_inside_heavier():
    case = vertical_case(top_lead_md_ft=8000, top_tail_md_ft=8000, tail_density_ppg=12.0,
                         mud_density_ppg=9.0, disp_density_ppg=14.0)
    p = primary_job(case)["pressure"]
    # annulus: 9*8000 + 12*1900 ; inside: 14*9900
    assert p["differential_psi"] == approx(0.052 * (9 * 8000 + 12 * 1900 - 14 * 9900))
    assert p["differential_psi"] < 0


def test_spacer_column_and_hydrostatic():
    ann = (8.5**2 - 7.0**2) / 1029.4
    case = vertical_case(spacer_bbl=ann * 500)  # exactly 500 ft of spacer
    r = primary_job(case)
    assert r["spacer"]["top_md_ft"] == approx(4500)
    p = r["pressure"]
    expect = 0.052 * (10.0 * 4500 + 11.0 * 500 + 13.0 * 3000 + 15.8 * 2000)
    assert p["annulus_psi"] == approx(expect)
    assert p["shoe_emw_ppg"] == approx(expect / (0.052 * 10000))


def test_spacer_crosses_previous_shoe():
    cased = (8.921**2 - 7.0**2) / 1029.4
    oh = (8.5**2 - 7.0**2) / 1029.4
    case = vertical_case(prev_casing_id_in=8.921, prev_shoe_md_ft=4800, spacer_bbl=oh * 200 + cased * 100)
    r = primary_job(case)
    assert r["spacer"]["top_md_ft"] == approx(4700)


def test_spacer_to_surface_warns():
    r = primary_job(vertical_case(spacer_bbl=5000))
    assert r["spacer"]["truncated"] is True
    assert any(w["code"] == "spacer_above_surface" for w in r["warnings"])


def test_tvd_interpolation_and_example():
    r = primary_job(EXAMPLE_PRIMARY)
    p = r["pressure"]
    assert p["shoe_tvd_ft"] == 10212
    assert p["float_collar_tvd_ft"] == 10210
    tops = {c["fluid"]: c for c in p["annulus_columns"]}
    assert tops["lead"]["bottom_tvd_ft"] == 9850
    # sum of annulus columns equals EMW times shoe TVD
    assert p["annulus_psi"] == approx(p["shoe_emw_ppg"] * 0.052 * 10212)


def test_frac_warning():
    r = primary_job(vertical_case(frac_emw_ppg=12.0))
    assert r["pressure"]["frac_exceeded"] is True
    assert any(w["code"] == "frac_exceeded" for w in r["warnings"])
    assert primary_job(vertical_case())["pressure"]["frac_exceeded"] is False


# ---- balanced plug --------------------------------------------------------

def test_balanced_plug_identity():
    r = balanced_plug(EXAMPLE_PLUG)
    h = r["column_height_ft"]
    assert r["cement_height_inside_ft"] == approx(h)
    assert r["cement_height_outside_ft"] == approx(h)
    cp = r["capacities"]["pipe_inside"]["bbl_ft"]
    ca = r["capacities"]["annulus"]["bbl_ft"]
    assert h * (cp + ca) == approx(r["slurry"]["vol_bbl"])
    # spacer heights balance too
    assert r["spacer_ahead"]["height_annulus_ft"] == approx(r["spacer_behind"]["height_pipe_ft"])


def test_balanced_plug_hand_values():
    r = balanced_plug(EXAMPLE_PLUG)
    ch = 8.75**2 / 1029.4
    cp = 2.764**2 / 1029.4
    ca = (8.75**2 - 3.5**2) / 1029.4
    vol = 500 * ch * 1.2
    assert r["slurry"]["vol_bbl"] == approx(vol)
    assert r["slurry"]["sacks"] == math.ceil(vol * 5.6146 / 1.06)
    h = vol / (ca + cp)
    assert r["column_height_ft"] == approx(h)
    assert r["spacer_behind"]["vol_bbl"] == approx(10 * cp / ca)
    assert r["displacement"]["vol_bbl"] == approx(cp * (9000 - h) - 10 * cp / ca)
    assert r["top_with_pipe_in_md_ft"] == approx(9000 - h)
    assert r["top_after_pull_gauge_md_ft"] == approx(9000 - vol / ch)
    assert r["top_after_pull_design_md_ft"] == 8500
    assert r["slurry"]["mix_water_bbl"] == approx(r["slurry"]["sacks"] * 4.3 / 42)


def test_balanced_plug_zero_excess_pulls_to_design_top():
    case = dict(EXAMPLE_PLUG, excess_pct=0)
    r = balanced_plug(case)
    assert r["top_after_pull_gauge_md_ft"] == approx(r["top_after_pull_design_md_ft"])


def test_underdisplacement():
    base = balanced_plug(EXAMPLE_PLUG)
    r = balanced_plug(dict(EXAMPLE_PLUG, underdisplace_bbl=2.0))
    assert r["displacement"]["vol_bbl"] == approx(base["displacement"]["vol_bbl"] - 2.0)
    assert any(w["code"] == "underdisplaced" for w in r["warnings"])


# ---- validation -----------------------------------------------------------

@pytest.mark.parametrize("over,code", [
    ({"casing_od_in": 9.0}, "pipe_od_ge_hole"),
    ({"casing_od_in": 8.5}, "pipe_od_ge_hole"),
    ({"casing_id_in": 7.0}, "casing_id_ge_od"),
    ({"float_collar_md_ft": 10000}, "float_collar_below_shoe"),
    ({"float_collar_md_ft": 10100}, "float_collar_below_shoe"),
    ({"top_lead_md_ft": 8500, "top_tail_md_ft": 8000}, "tops_order"),
    ({"top_tail_md_ft": 10000}, "tops_order"),
    ({"top_lead_md_ft": -1}, "tops_order"),
    ({"prev_shoe_md_ft": 10000, "prev_casing_id_in": 8.9}, "prev_shoe_order"),
    ({"prev_shoe_md_ft": 3000, "prev_casing_id_in": 6.5}, "prev_id_le_casing_od"),
    ({"oh_excess_pct": -5}, "bad_excess"),
    ({"mud_density_ppg": 0}, "bad_density"),
    ({"tail_yield_ft3_sk": 0}, "bad_yield"),
    ({"frac_emw_ppg": 0}, "bad_frac"),
    ({"pump_output_bbl_stk": -1}, "bad_value"),
    ({"shoe_md_ft": "abc"}, "not_number"),
    ({"shoe_md_ft": float("nan")}, "not_number"),
    ({"shoe_md_ft": None}, "missing"),
])
def test_primary_validation(over, code):
    with pytest.raises(InputError) as ei:
        primary_job(vertical_case(**over))
    assert ei.value.code == code


def test_tvd_validation():
    base = vertical_case(tvd_equals_md=False, tvd_top_lead_ft=5000, tvd_top_tail_ft=7900, tvd_shoe_ft=9800)
    primary_job(base)
    for bad in ({"tvd_top_tail_ft": 4900}, {"tvd_top_lead_ft": 5100}, {"tvd_shoe_ft": 7800}):
        with pytest.raises(InputError) as ei:
            primary_job(dict(base, **bad))
        assert ei.value.code == "tvd_inconsistent"
    with pytest.raises(InputError) as ei:
        primary_job(vertical_case(tvd_equals_md=False))
    assert ei.value.code == "missing"


@pytest.mark.parametrize("over,code", [
    ({"pipe_od_in": 8.75}, "pipe_od_ge_hole"),
    ({"pipe_od_in": 9.0}, "pipe_od_ge_hole"),
    ({"pipe_id_in": 3.5}, "pipe_id_ge_od"),
    ({"plug_length_ft": 0}, "bad_value"),
    ({"plug_bottom_md_ft": 400}, "plug_above_surface"),
    ({"excess_pct": 600}, "bad_excess"),
    ({"slurry_yield_ft3_sk": -1}, "bad_yield"),
    ({"spacer_ahead_bbl": -1}, "bad_value"),
])
def test_plug_validation(over, code):
    with pytest.raises(InputError) as ei:
        balanced_plug(dict(EXAMPLE_PLUG, **over))
    assert ei.value.code == code


def test_evaluate_dispatch():
    assert evaluate(EXAMPLE_PRIMARY)["mode"] == "primary"
    assert evaluate(EXAMPLE_PLUG)["mode"] == "plug"
    with pytest.raises(InputError):
        evaluate({"mode": "squeeze"})
    with pytest.raises(InputError):
        evaluate([1, 2])


# ---- parsing and CLI ------------------------------------------------------

def test_parse_csv_tsv_json():
    csv = 'key,value\n\n# comment\nmode,plug\nhole_id_in,8.75,extra\nplug_bottom_md_ft,"9,000"\ntvd_equals_md,yes\n'
    d = parse_text(csv)
    assert d == {"mode": "plug", "hole_id_in": 8.75, "plug_bottom_md_ft": 9000.0, "tvd_equals_md": True}
    assert parse_text("hole_id_in\t8.5\npipe_od_in\t3.5\n") == {"hole_id_in": 8.5, "pipe_od_in": 3.5}
    assert parse_text(json.dumps(EXAMPLE_PLUG))["plug_length_ft"] == 500


@pytest.mark.parametrize("text", ["", "   \n", "{bad json", "[1,2]", "hole_id_in,abc", "hole_id_in", "x,nan"])
def test_parse_bad(text):
    with pytest.raises(InputError) as ei:
        parse_text(text)
    assert ei.value.code == "file"


def test_cli(tmp_path, capsys):
    f = tmp_path / "plug.json"
    f.write_text(json.dumps(EXAMPLE_PLUG))
    assert cli_main([str(f)]) == 0
    assert "Balanced column height" in capsys.readouterr().out
    assert cli_main(["--example", "primary", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "primary"
    bad = tmp_path / "bad.csv"
    bad.write_text("mode,plug\nhole_id_in,5\npipe_od_in,6\n")
    assert cli_main([str(bad)]) == 2
    assert "error" in capsys.readouterr().err
    assert cli_main([str(tmp_path / "missing.csv")]) == 2


def test_example_does_not_mutate():
    before = copy.deepcopy(EXAMPLE_PRIMARY)
    primary_job(EXAMPLE_PRIMARY)
    assert EXAMPLE_PRIMARY == before


# ---- review fixes ---------------------------------------------------------

def test_utube_lead_below_float_collar_counts_as_lead():
    """Top of tail below the float collar: annulus at the float collar holds lead, not tail, between tail top and FC."""
    case = vertical_case(top_lead_md_ft=5000, top_tail_md_ft=9950, spacer_bbl=0,
                         mud_density_ppg=10.0, lead_density_ppg=13.0, tail_density_ppg=15.8, disp_density_ppg=10.0)
    p = primary_job(case)["pressure"]
    ann_fc = 0.052 * (10.0 * 5000 + 13.0 * (9900 - 5000))
    assert p["annulus_at_fc_psi"] == approx(ann_fc)
    assert p["inside_at_fc_psi"] == approx(0.052 * 10.0 * 9900)
    assert p["differential_psi"] == approx(ann_fc - 0.052 * 10.0 * 9900)
    # annulus at the shoe is unchanged: lead to 9950, tail to 10000
    assert p["annulus_psi"] == approx(0.052 * (10.0 * 5000 + 13.0 * 4950 + 15.8 * 50))


def test_utube_cut_at_fc_matches_old_rule_when_tail_above_fc():
    p = primary_job(EXAMPLE_PRIMARY)["pressure"]
    tail_below = 0.052 * 14.2 * (10212 - 10210)
    assert p["annulus_at_fc_psi"] == approx(p["annulus_psi"] - tail_below)


def test_sacks_overflow_is_input_error():
    with pytest.raises(InputError) as ei:
        sacks_for(100.0, 1e-320)
    assert ei.value.code == "bad_yield"
    with pytest.raises(InputError):
        balanced_plug(dict(EXAMPLE_PLUG, slurry_yield_ft3_sk=1e-320))


def test_huge_json_integer_is_input_error():
    with pytest.raises(InputError) as ei:
        primary_job(dict(EXAMPLE_PRIMARY, shoe_md_ft=10**400))
    assert ei.value.code == "not_number"


def test_parse_rejects_non_ascii_digits():
    with pytest.raises(InputError) as ei:
        parse_text("hole_id_in,٨.٧٥")
    assert ei.value.code == "file"


def test_cli_overflow_exits_cleanly(tmp_path, capsys):
    f = tmp_path / "ov.json"
    f.write_text(json.dumps(dict(EXAMPLE_PLUG, slurry_yield_ft3_sk=1e-320)))
    assert cli_main([str(f)]) == 2
    assert "error" in capsys.readouterr().err


@pytest.mark.parametrize("row", ["lead_density_ppg,11,5", 'lead_density_ppg,"11,5"', 'shoe_md_ft,"15,00"', "shoe_md_ft,1,5000"])
def test_decimal_and_split_commas_are_refused(row):
    # "11,5" used to be read as 11 (unquoted) or 115 (quoted)
    from cement_calc import parse_text

    with pytest.raises(InputError):
        parse_text(row + "\n")


def test_quoted_thousands_still_read():
    from cement_calc import parse_text

    assert parse_text('shoe_md_ft,"15,000"\n')["shoe_md_ft"] == 15000.0


def test_cli_reads_file_without_tvds_as_vertical(tmp_path, capsys):
    from cement_calc.cli import main

    keys = {k: v for k, v in EXAMPLE_PRIMARY.items() if not k.startswith("tvd") and k != "label"}
    f = tmp_path / "job.csv"
    f.write_text("".join(f"{k},{v}\n" for k, v in keys.items()))
    assert main([str(f), "--json"]) == 0
    out = capsys.readouterr()
    assert "TVD = MD (vertical well) is assumed" in out.err


def test_plausibility_refuses_physical_impossibilities():
    for over in ({"tail_density_ppg": 27.0}, {"lead_yield_ft3_sk": 0.3}, {"tail_water_gal_sk": 10.0}, {"mud_density_ppg": 3.0}):
        with pytest.raises(InputError) as ei:
            evaluate({**EXAMPLE_PRIMARY, **over})
        assert ei.value.code == "implausible"
    with pytest.raises(InputError):
        evaluate({**EXAMPLE_PLUG, "slurry_yield_ft3_sk": 0.55})  # 4.3 gal/sk of water is 0.575 ft3


def test_plausibility_warns_on_unusual_values():
    r = evaluate({**EXAMPLE_PRIMARY, "lead_density_ppg": 9.0, "lead_yield_ft3_sk": 5.5, "lead_water_gal_sk": 30.0})
    assert [w["code"] for w in r["warnings"]][:3] == ["unusual_density", "unusual_yield", "unusual_water"]
    r = evaluate({**EXAMPLE_PRIMARY, "open_hole_in": 6.0})
    assert "tight_clearance" in [w["code"] for w in r["warnings"]]
    assert not [w for w in evaluate(EXAMPLE_PRIMARY)["warnings"] if w["code"].startswith("unusual")]
