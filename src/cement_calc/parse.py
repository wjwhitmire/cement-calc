"""Parse a job input file: JSON object, or key/value CSV or TSV.

CSV form: one `key,value` pair per row. An optional header row (`key,value`
or `name,value`) is skipped. Blank lines, `#` comments and extra columns are
ignored. Comma or tab separated. Booleans accept true/false/yes/no/1/0.
"""

from __future__ import annotations

import json
import math
import re

from .core import InputError

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 50_000
TEXT_KEYS = {"mode", "label"}
BOOL_KEYS = {"tvd_equals_md"}


_GROUPED = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d*)?$", re.ASCII)
_INT = re.compile(r"^[+-]?\d+$", re.ASCII)
_DIGITS = re.compile(r"^\d+(\.\d*)?$", re.ASCII)


def _number(raw: str, key: str, line_no: int) -> float:
    s = raw.strip()
    if "," in s and not _GROUPED.match(s):
        # "1,5" is a decimal comma (or a typo), never 15
        raise InputError("file", f"Line {line_no}: value for {key} has a comma that is not a thousands separator ({s[:40]!r}). Use a decimal point.")
    s = s.replace(",", "").replace("_", "")
    if not s.isascii():
        # Same rule as the browser parser: ASCII digits only.
        raise InputError("file", f"Line {line_no}: value for {key} is not a number ({raw.strip()[:40]!r}).")
    try:
        x = float(s)
    except ValueError:
        raise InputError("file", f"Line {line_no}: value for {key} is not a number ({raw.strip()[:40]!r}).") from None
    if not math.isfinite(x):
        raise InputError("file", f"Line {line_no}: value for {key} is not a finite number.")
    return x


def parse_text(text: str) -> dict:
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise InputError("file", "File is larger than 5 MB.")
    stripped = text.lstrip("﻿").strip()
    if not stripped:
        raise InputError("file", "File is empty.")
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise InputError("file", f"JSON could not be read: {exc.msg} at line {exc.lineno}.") from None
        if not isinstance(obj, dict):
            raise InputError("file", "JSON must be an object of named inputs.")
        return obj
    lines = stripped.splitlines()
    if len(lines) > MAX_ROWS:
        raise InputError("file", "File has more than 50,000 rows.")
    out: dict = {}
    for i, line in enumerate(lines, start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        sep = "\t" if "\t" in line else ","
        if sep == ",":
            # split key from the rest so numbers like 15,000 survive when quoted
            parts = [p.strip().strip('"') for p in _split_csv(line)]
        else:
            parts = [p.strip().strip('"') for p in line.split("\t")]
        if len(parts) < 2:
            raise InputError("file", f"Line {i}: expected key and value separated by a comma or tab.")
        key, raw = parts[0].lower(), parts[1]
        if len(parts) > 2 and _INT.match(raw.strip()) and _DIGITS.match(parts[2].strip()):
            # unquoted "lead_density_ppg,11,5" would otherwise be read as 11
            raise InputError(
                "file",
                f"Line {i}: '{raw.strip()},{parts[2].strip()}' looks like one number split by a comma. "
                "Quote it (\"15,000\"), drop the thousands comma, or use a decimal point.",
            )
        if i == 1 and key in ("key", "name", "input", "parameter") and raw.lower() in ("value", "val"):
            continue
        if not key:
            raise InputError("file", f"Line {i}: empty key.")
        if key in TEXT_KEYS:
            out[key] = raw
        elif key in BOOL_KEYS:
            out[key] = raw.lower() in ("1", "true", "yes", "y")
        elif raw == "":
            continue
        else:
            out[key] = _number(raw, key, i)
    if not out:
        raise InputError("file", "No inputs found in file.")
    return out


def _split_csv(line: str) -> list:
    parts, cur, q = [], [], False
    for ch in line:
        if ch == '"':
            q = not q
        elif ch == "," and not q:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts
