"""Table, CSV and JSON writers."""

from __future__ import annotations

import csv
import io
import json

from .reports import Report

FORMATS = ("table", "csv", "json", "html")
MAX_CELL = 60


def render(report: Report, fmt: str) -> str:
    if fmt == "table":
        return to_table(report)
    if fmt == "csv":
        return to_csv(report)
    if fmt == "json":
        return to_json(report)
    raise ValueError(f"Unknown format {fmt!r}")


def to_table(report: Report) -> str:
    if not report.rows:
        return "No matching events."
    cells = [[_cell(v, truncate=True) for v in row] for row in report.rows]
    widths = [max(len(h), *(len(r[i]) for r in cells)) for i, h in enumerate(report.columns)]
    lines = [
        "  ".join(h.ljust(w) for h, w in zip(report.columns, widths)).rstrip(),
        "  ".join("-" * w for w in widths),
    ]
    lines += ["  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip() for row in cells]
    return "\n".join(lines)


def to_csv(report: Report) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(report.columns)
    writer.writerows([[_cell(v) for v in row] for row in report.rows])
    return buf.getvalue()


def to_json(report: Report) -> str:
    return json.dumps([dict(zip(report.columns, row)) for row in report.rows], indent=2, default=str)


def _cell(value, truncate: bool = False) -> str:
    if isinstance(value, dict):
        text = "; ".join(f"{k}={_cell(v)}" for k, v in value.items())
    elif isinstance(value, list):
        text = ", ".join(_cell(v) for v in value)
    elif isinstance(value, bool):
        text = "yes" if value else "no"
    else:
        text = "" if value is None else str(value)
    text = " ".join(text.split())
    if truncate and len(text) > MAX_CELL:
        text = text[: MAX_CELL - 1] + "…"
    return text
