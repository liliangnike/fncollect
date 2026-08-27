"""Reusable value processors.

Turns raw device output into exact values. Each processor is a *named*
transform referenced from YAML (``extract`` / ``probe.mappings``), so "get
value" steps stay declarative while the parsing logic lives once in code.

Supported processors:
  * ``regex`` -- capture one/many groups via a regular expression.
  * ``kv``    -- parse ``key : value`` / ``key=value`` lines.
  * ``grid``  -- parse an ASCII/pipe table into rows of column dicts.
  * ``json``  -- extract a JSON document from the output.
  * ``line``  -- select a line (by index or substring) / count lines.
"""

from __future__ import annotations

import re
from typing import Any


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def regexp(output: str, spec: dict) -> str | dict | None:
    match = re.search(spec["regex"], output, re.IGNORECASE)
    if match is None:
        return None
    named = spec.get("named_groups")
    if named:
        return {name: match.group(group) for name, group in named.items()}
    group = spec.get("group", 1)
    try:
        return match.group(group)
    except IndexError:
        return match.group(0)


def kv(output: str, spec: dict) -> str | None:
    key = spec["key"]
    value = None
    for line in output.splitlines():
        found = re.match(r"\s*" + re.escape(key) + r"\s*[:=]\s*(.+)", line)
        if found:
            value = found.group(1).strip()
    return value


def grid(output: str, spec: dict) -> Any:
    """Parse a table; return the requested cell, a column, a row or the count."""
    lines = output.splitlines()
    header_idx = _as_int(spec.get("header_row"), 0)
    sep_idx = header_idx + 1
    if header_idx >= len(lines):
        return None
    header = _split_row(lines[header_idx])
    # skip the separator line (e.g. ---+---) if present
    data_lines = [
        lines[i] for i in range(sep_idx, len(lines))
        if lines[i].strip() and not _is_separator(lines[i])
    ]
    rows: list[dict] = []
    for line in data_lines:
        cells = _split_row(line)
        if len(cells) >= len(header):
            rows.append(dict(zip(header, cells)))
    kind = spec.get("kind", "cell")
    if kind == "count":
        return len(rows)
    if kind == "rows":
        return rows
    if kind == "column":
        col = spec["column"]
        return [r[col] for r in rows if col in r]
    # cell
    row = _as_int(spec.get("row"), 0)
    col = spec.get("column")
    if 0 <= row < len(rows) and col in rows[row]:
        return rows[row][col]
    return None


def lines(output: str, spec: dict) -> Any:
    kind = spec.get("kind", "match")
    if kind == "count":
        return len([l for l in output.splitlines() if l.strip()])
    for line in output.splitlines():
        if spec.get("contains", "") in line:
            return line.strip()
    return None


def json(output: str, spec: dict) -> Any:
    import json as _json

    match = re.search(r"\{.*\}|\[.*\]", output, re.DOTALL)
    if match is None:
        return None
    try:
        return _json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return None
    return None


_PARSERS = {
    "regex": regexp,
    "kv": kv,
    "grid": grid,
    "json": json,
    "line": lines,
}


def parse(output: str, process_spec: dict) -> Any:
    """Apply a named processor to raw output, returning a structured value."""
    name = process_spec.get("parser", "regex")
    parser = _PARSERS.get(name)
    if parser is None:
        raise ValueError(f"unknown value processor {name!r}; known: {sorted(_PARSERS)}")
    return parser(output, process_spec)


def extract_values(output: str, specs: list[dict], variables=None) -> dict[str, Any]:
    """Run a list of ``extract`` specs and return ``{name: value}``.

    Each spec maps a value: ``{name, parser?, ...processor args, expr?}``.
    An optional safe ``expr`` can transform the processed value using the
    passed variable context.
    """
    from fncollect.variables import safe_eval

    result: dict[str, Any] = {}
    for spec in specs:
        name = spec["name"]
        value = parse(output, spec)
        expr = spec.get("expr")
        if expr and variables is not None:
            if name in result:
                variables.set(name, value, via="extract")
            value = safe_eval(expr, variables)
        result[name] = value
    return result


def _split_row(line: str) -> list[str]:
    if "|" in line:
        return [c.strip() for c in line.split("|")]
    return [c.strip() for c in re.split(r"\s{2,}", line) if c.strip()]


def _is_separator(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return bool(re.fullmatch(r"[\s|+=._~-]+", stripped)) and "-" in stripped
