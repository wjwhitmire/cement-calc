"""Cementing volumetrics: primary casing job and balanced plug.

Standard oilfield volumetrics in US field units. Every constant and equation
is listed in README.md under "Method". This is a planning cross-check. The
service company's job design governs.
"""

from __future__ import annotations

import math

# Constants (see README "Constants").
CAP_DIVISOR = 1029.4      # bbl/ft = D^2 / 1029.4, D in inches
FT3_PER_BBL = 5.6146      # cubic feet per barrel
PSI_PER_FT_PPG = 0.052    # hydrostatic gradient factor, psi/ft per lb/gal
GAL_PER_BBL = 42.0        # US gallons per barrel
SACK_EPS = 1e-9           # tolerance before rounding sacks up

MAX_DENSITY_PPG = 30.0
MAX_EXCESS_PCT = 500.0
TVD_TOL_FT = 1e-6


# Plausibility limits (see README "Plausibility checks"). Typical ranges follow API Specification 10A neat
# slurries (Class G 15.8 ppg, 1.15 ft3/sk, 5.0 gal/sk; Class H 16.4 ppg, 1.06 ft3/sk, 4.3 gal/sk) and
# the extended, foamed and weighted systems in Nelson and Guillot, Well Cementing, 2nd ed. (2006).
GAL_PER_FT3 = 7.48052
SLURRY_PPG_HARD = (4.0, 25.0)     # foamed slurries go down to about 4 ppg; weighted systems top out near 22 to 23
SLURRY_PPG_TYPICAL = (11.0, 19.0)  # extended lead to weighted tail without foam or special weighting
FLUID_PPG_HARD = (5.0, 25.0)      # mud, spacer and displacement fluid
FLUID_PPG_TYPICAL = (6.5, 20.0)   # oil-base mud at the light end, heavily weighted mud at the heavy end
YIELD_HARD = (0.5, 15.0)          # ft3/sk; a neat slurry cannot yield much under 1, foam rarely tops 6
YIELD_TYPICAL = (0.9, 4.0)
WATER_TYPICAL = (3.5, 25.0)       # gal/sk
OH_EXCESS_TYPICAL_MAX = 100.0     # percent
MIN_CLEARANCE_IN = 0.75           # hole or casing ID minus casing OD; below this placement is doubtful
PUMP_TYPICAL = (0.02, 0.5)        # bbl/stk for rig and cementing unit pumps


class InputError(ValueError):
    """Bad input. `code` is stable and shared with the browser tool."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def capacity_bbl_ft(d_in: float) -> float:
    """Capacity of a circle of diameter d_in inches, bbl per ft."""
    return d_in * d_in / CAP_DIVISOR


def annular_capacity_bbl_ft(hole_in: float, pipe_od_in: float) -> float:
    """Annular capacity between hole (or casing ID) and pipe OD, bbl per ft."""
    return (hole_in * hole_in - pipe_od_in * pipe_od_in) / CAP_DIVISOR


def bbl_to_ft3(bbl: float) -> float:
    return bbl * FT3_PER_BBL


def sacks_for(vol_ft3: float, yield_ft3_sk: float) -> int:
    """Whole sacks, rounded up. A tiny tolerance stops 100.0000000001 becoming 101."""
    if vol_ft3 <= 0:
        return 0
    n = vol_ft3 / yield_ft3_sk - SACK_EPS
    if not math.isfinite(n):
        raise InputError("bad_yield", "Sack count is too large to compute. Check the slurry yield (ft3/sk) and the depths.")
    return int(math.ceil(n))


def mix_water_bbl(sacks: int, water_gal_sk: float) -> float:
    return sacks * water_gal_sk / GAL_PER_BBL


def hydrostatic_psi(density_ppg: float, tvd_ft: float) -> float:
    return PSI_PER_FT_PPG * density_ppg * tvd_ft


def _cap(bbl_ft: float) -> dict:
    return {"bbl_ft": bbl_ft, "ft3_ft": bbl_ft * FT3_PER_BBL}


def _num(case: dict, key: str, required: bool = True):
    if key not in case or case[key] is None or case[key] == "":
        if required:
            raise InputError("missing", f"Missing input: {key}.")
        return None
    v = case[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise InputError("not_number", f"{key} must be a number.")
    try:
        v = float(v)
    except OverflowError:
        raise InputError("not_number", f"{key} must be a finite number.") from None
    if not math.isfinite(v):
        raise InputError("not_number", f"{key} must be a finite number.")
    return v


def _flag(case: dict, key: str) -> bool:
    v = case.get(key, False)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y")
    return bool(v)


PRIMARY_KEYS = [
    "casing_od_in", "casing_id_in", "shoe_md_ft", "float_collar_md_ft",
    "prev_casing_id_in", "prev_shoe_md_ft", "open_hole_in", "oh_excess_pct",
    "top_lead_md_ft", "top_tail_md_ft",
    "lead_density_ppg", "lead_yield_ft3_sk", "lead_water_gal_sk",
    "tail_density_ppg", "tail_yield_ft3_sk", "tail_water_gal_sk",
    "spacer_bbl", "spacer_density_ppg", "mud_density_ppg", "disp_density_ppg",
    "frac_emw_ppg",
]


def _g(x: float) -> str:
    """Number for a message, same text as the browser core: rounded to 6 decimals, no trailing .0."""
    r = math.floor(x * 1e6 + 0.5) / 1e6
    return str(int(r)) if r == int(r) else repr(r)


def _slurry_checks(name: str, prefix: str, density, yld: float, water, warnings: list) -> None:
    """Refuse physically impossible slurries and warn on unusual ones."""
    if density is not None:
        lo, hi = SLURRY_PPG_HARD
        if not (lo <= density <= hi):
            raise InputError("implausible", f"{prefix}_density_ppg must be between {_g(lo)} and {_g(hi)} ppg for a cement slurry.")
        lo, hi = SLURRY_PPG_TYPICAL
        if not (lo <= density <= hi):
            warnings.append({"code": "unusual_density", "message": f"{name} density {_g(density)} ppg is outside the usual {_g(lo)} to {_g(hi)} ppg. Fine for a foamed or specially weighted slurry; otherwise check it."})
    lo, hi = YIELD_HARD
    if not (lo <= yld <= hi):
        raise InputError("implausible", f"{prefix}_yield_ft3_sk must be between {_g(lo)} and {_g(hi)} ft3/sk.")
    if water is not None and water / GAL_PER_FT3 >= yld:
        raise InputError(
            "implausible",
            f"{prefix}_yield_ft3_sk must be larger than its mix water ({_g(water)} gal/sk = {water / GAL_PER_FT3:.2f} ft3/sk). "
            "A sack of slurry cannot be smaller than the water in it.",
        )
    lo, hi = YIELD_TYPICAL
    if not (lo <= yld <= hi):
        warnings.append({"code": "unusual_yield", "message": f"{name} yield {_g(yld)} ft3/sk is outside the usual {_g(lo)} to {_g(hi)} ft3/sk. Check it against the lab report."})
    if water is not None:
        lo, hi = WATER_TYPICAL
        if not (lo <= water <= hi):
            warnings.append({"code": "unusual_water", "message": f"{name} mix water {_g(water)} gal/sk is outside the usual {_g(lo)} to {_g(hi)} gal/sk. Check it against the lab report."})


def _pump_check(pump, warnings: list) -> None:
    lo, hi = PUMP_TYPICAL
    if pump is not None and not (lo <= pump <= hi):
        warnings.append({"code": "unusual_pump", "message": f"Pump output {_g(pump)} bbl/stk is outside the usual {_g(lo)} to {_g(hi)} bbl/stk. Check the units."})


def _validate_primary(case: dict) -> dict:
    v = {k: _num(case, k) for k in PRIMARY_KEYS}
    v["pump_output_bbl_stk"] = _num(case, "pump_output_bbl_stk", required=False)
    if v["casing_od_in"] <= 0 or v["casing_id_in"] <= 0:
        raise InputError("bad_value", "Casing OD and ID must be greater than zero.")
    if v["casing_id_in"] >= v["casing_od_in"]:
        raise InputError("casing_id_ge_od", "Casing ID must be smaller than casing OD.")
    if v["casing_od_in"] >= v["open_hole_in"]:
        raise InputError("pipe_od_ge_hole", "Casing OD must be smaller than the open hole diameter.")
    if v["shoe_md_ft"] <= 0 or v["float_collar_md_ft"] <= 0:
        raise InputError("bad_value", "Shoe and float collar depths must be greater than zero.")
    if v["float_collar_md_ft"] >= v["shoe_md_ft"]:
        raise InputError("float_collar_below_shoe", "Float collar must be above the shoe (float collar MD less than shoe MD).")
    if v["prev_shoe_md_ft"] < 0 or v["prev_shoe_md_ft"] >= v["shoe_md_ft"]:
        raise InputError("prev_shoe_order", "Previous casing shoe must be at or below surface and above the new shoe. Use 0 for no previous casing.")
    if v["prev_shoe_md_ft"] > 0 and v["prev_casing_id_in"] <= v["casing_od_in"]:
        raise InputError("prev_id_le_casing_od", "Previous casing ID must be larger than the new casing OD.")
    if not (0 <= v["top_lead_md_ft"] <= v["top_tail_md_ft"] < v["shoe_md_ft"]):
        raise InputError("tops_order", "Tops out of order. Need 0 <= top of lead <= top of tail < shoe MD.")
    if not (0 <= v["oh_excess_pct"] <= MAX_EXCESS_PCT):
        raise InputError("bad_excess", f"Open hole excess must be between 0 and {MAX_EXCESS_PCT:g} percent.")
    for k in ("lead_density_ppg", "tail_density_ppg", "spacer_density_ppg", "mud_density_ppg", "disp_density_ppg"):
        if not (0 < v[k] < MAX_DENSITY_PPG):
            raise InputError("bad_density", f"{k} must be between 0 and {MAX_DENSITY_PPG:g} ppg.")
    for k in ("lead_yield_ft3_sk", "tail_yield_ft3_sk"):
        if v[k] <= 0:
            raise InputError("bad_yield", f"{k} must be greater than zero.")
    for k in ("lead_water_gal_sk", "tail_water_gal_sk", "spacer_bbl"):
        if v[k] < 0:
            raise InputError("bad_value", f"{k} cannot be negative.")
    if v["frac_emw_ppg"] <= 0:
        raise InputError("bad_frac", "Fracture gradient EMW must be greater than zero.")
    if v["pump_output_bbl_stk"] is not None and v["pump_output_bbl_stk"] <= 0:
        raise InputError("bad_value", "Pump output must be greater than zero, or left blank.")

    # TVD stations.
    v["tvd_equals_md"] = _flag(case, "tvd_equals_md")
    pts = [(0.0, 0.0)]
    if v["tvd_equals_md"]:
        stations = []
    else:
        stations = [
            (v["top_lead_md_ft"], _num(case, "tvd_top_lead_ft")),
            (v["top_tail_md_ft"], _num(case, "tvd_top_tail_ft")),
        ]
        fc_tvd = _num(case, "tvd_float_collar_ft", required=False)
        if fc_tvd is not None:
            stations.append((v["float_collar_md_ft"], fc_tvd))
        stations.append((v["shoe_md_ft"], _num(case, "tvd_shoe_ft")))
    for md, tvd in stations:
        last_md, last_tvd = pts[-1]
        if tvd < 0 or tvd < last_tvd - TVD_TOL_FT or (tvd - last_tvd) > (md - last_md) + TVD_TOL_FT:
            raise InputError(
                "tvd_inconsistent",
                f"TVD {tvd:g} ft at MD {md:g} ft is not possible. TVD must not decrease with depth and cannot gain more than MD gains.",
            )
        if md - last_md <= TVD_TOL_FT:
            continue  # duplicate station (for example top of lead at surface), already consistent
        pts.append((md, tvd))
    v["stations"] = pts

    # Plausibility: refuse the impossible, warn on the unusual.
    plaus: list = []
    _slurry_checks("Lead", "lead", v["lead_density_ppg"], v["lead_yield_ft3_sk"], v["lead_water_gal_sk"], plaus)
    _slurry_checks("Tail", "tail", v["tail_density_ppg"], v["tail_yield_ft3_sk"], v["tail_water_gal_sk"], plaus)
    for k, label in (("spacer_density_ppg", "Spacer"), ("mud_density_ppg", "Mud"), ("disp_density_ppg", "Displacement fluid")):
        lo, hi = FLUID_PPG_HARD
        if not (lo <= v[k] <= hi):
            raise InputError("implausible", f"{k} must be between {_g(lo)} and {_g(hi)} ppg.")
        lo, hi = FLUID_PPG_TYPICAL
        if not (lo <= v[k] <= hi):
            plaus.append({"code": "unusual_density", "message": f"{label} density {_g(v[k])} ppg is outside the usual {_g(lo)} to {_g(hi)} ppg. Check it."})
    if v["oh_excess_pct"] > OH_EXCESS_TYPICAL_MAX:
        plaus.append({"code": "unusual_excess", "message": f"Open hole excess of {_g(v['oh_excess_pct'])} percent is above {_g(OH_EXCESS_TYPICAL_MAX)} percent. Use a caliper if the hole is that washed out."})
    if v["open_hole_in"] - v["casing_od_in"] < MIN_CLEARANCE_IN:
        plaus.append({"code": "tight_clearance", "message": f"Open hole is only {v['open_hole_in'] - v['casing_od_in']:.3f} in larger than the casing OD (under {_g(MIN_CLEARANCE_IN)} in). Running casing and placing cement are doubtful."})
    if v["prev_shoe_md_ft"] > 0 and v["prev_casing_id_in"] - v["casing_od_in"] < MIN_CLEARANCE_IN:
        plaus.append({"code": "tight_clearance", "message": f"Previous casing ID is only {v['prev_casing_id_in'] - v['casing_od_in']:.3f} in larger than the casing OD (under {_g(MIN_CLEARANCE_IN)} in)."})
    _pump_check(v["pump_output_bbl_stk"], plaus)
    v["plausibility"] = plaus
    return v


def _tvd_at(stations, md: float) -> float:
    """Linear interpolation of TVD between entered stations. TVD = MD when only the surface station exists."""
    if len(stations) == 1:
        return md
    for i in range(1, len(stations)):
        m0, t0 = stations[i - 1]
        m1, t1 = stations[i]
        if md <= m1 + TVD_TOL_FT:
            return t0 + (t1 - t0) * (md - m0) / (m1 - m0)
    m0, t0 = stations[-2]
    m1, t1 = stations[-1]
    return t0 + (t1 - t0) * (md - m0) / (m1 - m0)


def primary_job(case: dict) -> dict:
    """Primary casing cement job volumetrics, displacement and static pressures at bump."""
    v = _validate_primary(case)
    warnings = list(v["plausibility"])
    od = v["casing_od_in"]
    shoe = v["shoe_md_ft"]
    fc = v["float_collar_md_ft"]
    prev = v["prev_shoe_md_ft"]
    ex = v["oh_excess_pct"] / 100.0

    cap_in = capacity_bbl_ft(v["casing_id_in"])
    cap_cased = annular_capacity_bbl_ft(v["prev_casing_id_in"], od) if prev > 0 else 0.0
    cap_oh = annular_capacity_bbl_ft(v["open_hole_in"], od)
    cap_oh_ex = cap_oh * (1.0 + ex)

    if prev > 0 and v["open_hole_in"] > v["prev_casing_id_in"]:
        warnings.append({"code": "hole_larger_than_prev_id", "message": "Open hole diameter is larger than the previous casing ID. Check the hole size (underreamed hole is possible)."})
    if v["top_tail_md_ft"] > fc:
        warnings.append({"code": "tail_top_below_float_collar", "message": "Top of tail is below the float collar. Most of the tail is in the shoe track."})

    def segments(top: float, bottom: float):
        """Split an annular interval at the previous shoe. Returns (geometry, top, bottom, eff_cap, excess)."""
        out = []
        if bottom <= top:
            return out
        if top < prev:
            out.append(("cased", top, min(bottom, prev), cap_cased, 0.0))
        if bottom > prev:
            out.append(("open", max(top, prev), bottom, cap_oh_ex, ex))
        return out

    intervals = []
    totals = {"lead": 0.0, "tail": 0.0}
    for fluid, top, bottom in (("lead", v["top_lead_md_ft"], v["top_tail_md_ft"]), ("tail", v["top_tail_md_ft"], shoe)):
        for geom, t, b, cap, e in segments(top, bottom):
            vol = cap * (b - t)
            totals[fluid] += vol
            intervals.append({
                "fluid": fluid, "geometry": geom, "top_md_ft": t, "bottom_md_ft": b,
                "length_ft": b - t, "cap_bbl_ft": cap, "excess_pct": e * 100.0,
                "vol_bbl": vol, "vol_ft3": vol * FT3_PER_BBL,
            })

    st_len = shoe - fc
    st_vol = cap_in * st_len

    def slurry(prefix: str, vol_bbl: float) -> dict:
        ft3 = vol_bbl * FT3_PER_BBL
        sk = sacks_for(ft3, v[prefix + "_yield_ft3_sk"])
        return {
            "vol_bbl": vol_bbl, "vol_ft3": ft3, "sacks": sk,
            "mix_water_bbl": mix_water_bbl(sk, v[prefix + "_water_gal_sk"]),
            "density_ppg": v[prefix + "_density_ppg"],
        }

    lead = slurry("lead", totals["lead"])
    tail = slurry("tail", totals["tail"] + st_vol)
    tail["annulus_bbl"] = totals["tail"]
    tail["shoe_track_bbl"] = st_vol

    disp = cap_in * fc
    pump = v["pump_output_bbl_stk"]
    strokes = disp / pump if pump else None

    # Spacer sits directly above the top of lead in the annulus.
    remaining = v["spacer_bbl"]
    spacer_top = v["top_lead_md_ft"]
    for geom, t, b, cap, e in reversed(segments(0.0, v["top_lead_md_ft"])):
        seg_vol = cap * (b - t)
        if remaining <= seg_vol:
            spacer_top = b - remaining / cap if cap > 0 else b
            remaining = 0.0
            break
        remaining -= seg_vol
        spacer_top = t
    spacer_truncated = remaining > 1e-9
    if spacer_truncated:
        spacer_top = 0.0
        warnings.append({"code": "spacer_above_surface", "message": "Spacer volume is more than the annulus above the top of lead. Pressures assume spacer to surface."})

    st = v["stations"]

    def col(name: str, density: float, top: float, bottom: float) -> dict:
        t_tvd = _tvd_at(st, top)
        b_tvd = _tvd_at(st, bottom)
        return {
            "fluid": name, "density_ppg": density, "top_md_ft": top, "bottom_md_ft": bottom,
            "top_tvd_ft": t_tvd, "bottom_tvd_ft": b_tvd,
            "psi": hydrostatic_psi(density, b_tvd - t_tvd),
        }

    annulus = [
        col("mud", v["mud_density_ppg"], 0.0, spacer_top),
        col("spacer", v["spacer_density_ppg"], spacer_top, v["top_lead_md_ft"]),
        col("lead", v["lead_density_ppg"], v["top_lead_md_ft"], v["top_tail_md_ft"]),
        col("tail", v["tail_density_ppg"], v["top_tail_md_ft"], shoe),
    ]
    inside = [
        col("displacement", v["disp_density_ppg"], 0.0, fc),
        col("tail", v["tail_density_ppg"], fc, shoe),
    ]
    p_ann = sum(c["psi"] for c in annulus)
    p_in = sum(c["psi"] for c in inside)
    # Reference depth for the U-tube is the float collar. Each annulus column is
    # cut at the float collar, so lead below the float collar (top of tail below
    # it) is counted at lead density, not tail.
    fc_tvd = _tvd_at(st, fc)
    p_ann_fc = sum(
        hydrostatic_psi(c["density_ppg"], _tvd_at(st, min(c["bottom_md_ft"], fc)) - _tvd_at(st, min(c["top_md_ft"], fc)))
        for c in annulus if c["top_md_ft"] < fc
    )
    p_in_fc = inside[0]["psi"]
    shoe_tvd = _tvd_at(st, shoe)
    emw = p_ann / (PSI_PER_FT_PPG * shoe_tvd)
    margin = v["frac_emw_ppg"] - emw
    exceeded = emw > v["frac_emw_ppg"]
    if exceeded:
        warnings.append({"code": "frac_exceeded", "message": "Static hydrostatic at the shoe exceeds the entered fracture gradient."})

    return {
        "mode": "primary",
        "capacities": {
            "casing_inside": _cap(cap_in),
            "cased_annulus": _cap(cap_cased),
            "open_hole_annulus": _cap(cap_oh),
            "open_hole_annulus_with_excess": _cap(cap_oh_ex),
        },
        "intervals": intervals,
        "shoe_track": {"length_ft": st_len, "vol_bbl": st_vol, "vol_ft3": st_vol * FT3_PER_BBL},
        "lead": lead,
        "tail": tail,
        "total_cement_bbl": lead["vol_bbl"] + tail["vol_bbl"],
        "displacement": {"vol_bbl": disp, "strokes": strokes},
        "spacer": {"vol_bbl": v["spacer_bbl"], "top_md_ft": spacer_top, "bottom_md_ft": v["top_lead_md_ft"], "truncated": spacer_truncated},
        "pressure": {
            "annulus_columns": annulus,
            "inside_columns": inside,
            "annulus_psi": p_ann,
            "inside_psi": p_in,
            "annulus_at_fc_psi": p_ann_fc,
            "inside_at_fc_psi": p_in_fc,
            "differential_psi": p_ann_fc - p_in_fc,
            "shoe_tvd_ft": shoe_tvd,
            "float_collar_tvd_ft": fc_tvd,
            "shoe_emw_ppg": emw,
            "frac_emw_ppg": v["frac_emw_ppg"],
            "frac_margin_ppg": margin,
            "frac_exceeded": exceeded,
        },
        "warnings": warnings,
    }


PLUG_KEYS = [
    "hole_id_in", "pipe_od_in", "pipe_id_in", "plug_length_ft", "plug_bottom_md_ft",
    "excess_pct", "spacer_ahead_bbl", "slurry_yield_ft3_sk",
]


def balanced_plug(case: dict) -> dict:
    """Balanced cement plug placed through open-ended pipe with the pipe end at the plug bottom."""
    v = {k: _num(case, k) for k in PLUG_KEYS}
    water = _num(case, "slurry_water_gal_sk", required=False)
    pump = _num(case, "pump_output_bbl_stk", required=False)
    under = _num(case, "underdisplace_bbl", required=False) or 0.0
    if v["hole_id_in"] <= 0 or v["pipe_od_in"] <= 0 or v["pipe_id_in"] <= 0:
        raise InputError("bad_value", "Hole size, pipe OD and pipe ID must be greater than zero.")
    if v["pipe_id_in"] >= v["pipe_od_in"]:
        raise InputError("pipe_id_ge_od", "Pipe ID must be smaller than pipe OD.")
    if v["pipe_od_in"] >= v["hole_id_in"]:
        raise InputError("pipe_od_ge_hole", "Pipe OD must be smaller than the hole size or casing ID.")
    if v["plug_length_ft"] <= 0:
        raise InputError("bad_value", "Plug length must be greater than zero.")
    if v["plug_bottom_md_ft"] <= v["plug_length_ft"]:
        raise InputError("plug_above_surface", "Bottom of plug must be deeper than the plug length.")
    if not (0 <= v["excess_pct"] <= MAX_EXCESS_PCT):
        raise InputError("bad_excess", f"Excess must be between 0 and {MAX_EXCESS_PCT:g} percent.")
    if v["spacer_ahead_bbl"] < 0 or under < 0:
        raise InputError("bad_value", "Spacer and under-displacement volumes cannot be negative.")
    if v["slurry_yield_ft3_sk"] <= 0:
        raise InputError("bad_yield", "Slurry yield must be greater than zero.")
    if water is not None and water < 0:
        raise InputError("bad_value", "Mix water cannot be negative.")
    if pump is not None and pump <= 0:
        raise InputError("bad_value", "Pump output must be greater than zero, or left blank.")

    warnings = []
    _slurry_checks("Slurry", "slurry", None, v["slurry_yield_ft3_sk"], water, warnings)
    _pump_check(pump, warnings)
    ch = capacity_bbl_ft(v["hole_id_in"])
    cp = capacity_bbl_ft(v["pipe_id_in"])
    ca = annular_capacity_bbl_ft(v["hole_id_in"], v["pipe_od_in"])
    bottom = v["plug_bottom_md_ft"]
    ex = v["excess_pct"] / 100.0

    vol = v["plug_length_ft"] * ch * (1.0 + ex)
    ft3 = vol * FT3_PER_BBL
    sk = sacks_for(ft3, v["slurry_yield_ft3_sk"])
    h = vol / (ca + cp)                      # balanced column height, pipe in, same inside and outside
    top_pipe_in = bottom - h
    behind = v["spacer_ahead_bbl"] * cp / ca  # balances spacer ahead height
    h_spacer_ann = v["spacer_ahead_bbl"] / ca
    h_spacer_pipe = behind / cp if cp > 0 else 0.0
    if top_pipe_in - h_spacer_ann < 0:
        raise InputError("plug_above_surface", "Cement plus spacer column would reach above surface. Check depths and volumes.")
    disp = cp * (bottom - h) - behind - under
    if disp <= 0:
        raise InputError("bad_value", "Displacement volume is zero or negative. Check spacer and under-displacement volumes.")
    if under > 0:
        warnings.append({"code": "underdisplaced", "message": "Under-displacement leaves fluid in the pipe above balance. The plug is no longer exactly balanced."})

    return {
        "mode": "plug",
        "capacities": {"hole": _cap(ch), "pipe_inside": _cap(cp), "annulus": _cap(ca)},
        "slurry": {
            "vol_bbl": vol, "vol_ft3": ft3, "sacks": sk,
            "mix_water_bbl": mix_water_bbl(sk, water) if water is not None else None,
        },
        "column_height_ft": h,
        "cement_height_inside_ft": (vol - ca * h) / cp,
        "cement_height_outside_ft": (vol - cp * h) / ca,
        "top_with_pipe_in_md_ft": top_pipe_in,
        "top_after_pull_gauge_md_ft": bottom - vol / ch,
        "top_after_pull_design_md_ft": bottom - v["plug_length_ft"],
        "spacer_ahead": {"vol_bbl": v["spacer_ahead_bbl"], "height_annulus_ft": h_spacer_ann},
        "spacer_behind": {"vol_bbl": behind, "height_pipe_ft": h_spacer_pipe},
        "displacement": {"vol_bbl": disp, "strokes": disp / pump if pump else None},
        "pipe_end_md_ft": bottom,
        "warnings": warnings,
    }


def evaluate(case: dict) -> dict:
    """Dispatch on case["mode"]: "primary" (default) or "plug"."""
    if not isinstance(case, dict):
        raise InputError("bad_value", "Input must be an object of named values.")
    mode = case.get("mode", "primary")
    if mode == "primary":
        return primary_job(case)
    if mode == "plug":
        return balanced_plug(case)
    raise InputError("bad_mode", 'mode must be "primary" or "plug".')


EXAMPLE_PRIMARY = {
    "label": "Example data: 5-1/2 in production casing in 8-3/4 in hole to 15,000 ft MD, lead and tail",
    "mode": "primary",
    "casing_od_in": 5.5, "casing_id_in": 4.892,
    "shoe_md_ft": 15000, "float_collar_md_ft": 14920,
    "prev_casing_id_in": 8.835, "prev_shoe_md_ft": 5000,
    "open_hole_in": 8.75, "oh_excess_pct": 30,
    "top_lead_md_ft": 4500, "top_tail_md_ft": 10000,
    "lead_density_ppg": 11.5, "lead_yield_ft3_sk": 2.48, "lead_water_gal_sk": 14.3,
    "tail_density_ppg": 14.2, "tail_yield_ft3_sk": 1.27, "tail_water_gal_sk": 5.8,
    "spacer_bbl": 40, "spacer_density_ppg": 12.0,
    "mud_density_ppg": 10.2, "disp_density_ppg": 8.4,
    "pump_output_bbl_stk": 0.102, "frac_emw_ppg": 14.5,
    "tvd_equals_md": False,
    "tvd_top_lead_ft": 4500, "tvd_top_tail_ft": 9850, "tvd_float_collar_ft": 10210, "tvd_shoe_ft": 10212,
}

EXAMPLE_PLUG = {
    "label": "Example data: 500 ft balanced plug in 8-3/4 in open hole through 3-1/2 in drill pipe, bottom at 9,000 ft MD",
    "mode": "plug",
    "hole_id_in": 8.75, "pipe_od_in": 3.5, "pipe_id_in": 2.764,
    "plug_length_ft": 500, "plug_bottom_md_ft": 9000, "excess_pct": 20,
    "spacer_ahead_bbl": 10, "slurry_yield_ft3_sk": 1.06, "slurry_water_gal_sk": 4.3,
    "pump_output_bbl_stk": 0.102, "underdisplace_bbl": 0,
}
