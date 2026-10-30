"""Festivos, vacaciones y ausencias: rangos e importación (Jornada 2.1).

Módulo puro: recibe y devuelve diccionarios; app.py guarda el resultado en
calendar.json. Nunca toca records.json: marcar un día con fichajes exige una
decisión explícita del usuario (ver app.py, «conflicto»).
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, timedelta

import core
from core import ValidationError

MAX_RANGE_DAYS = 366
MAX_IMPORT_ROWS = 400
_DMY = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_TRUE = {"1", "true", "yes", "si", "sí", "x", "y", "s", "recurrente", "recurring", "anual", "yearly"}


def range_dates(start: date, end: date, settings: dict, include_nonworking: bool = False) -> list[date]:
    if end < start:
        raise ValidationError("err.bad_range")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValidationError("err.range_too_long", max=MAX_RANGE_DAYS)
    out = []
    d = start
    while d <= end:
        if include_nonworking or settings["weekdays"][str(d.weekday())]["workday"]:
            out.append(d)
        d += timedelta(days=1)
    return out


def range_plan(start: date, end: date, mark: dict, settings: dict, calendar: dict, days: dict,
               include_nonworking: bool = False) -> dict:
    """Qué días se marcarían. Respeta los no laborables y no pisa festivos."""
    mark = core.clean_mark(mark)
    selected, skipped_holiday, replaced, conflicts = [], [], [], []
    for d in range_dates(start, end, settings, include_nonworking):
        current = core.day_mark(d, calendar)
        if current and current["type"] == "holiday" and mark["type"] != "holiday":
            skipped_holiday.append(d.isoformat())
            continue
        key = d.isoformat()
        selected.append(key)
        if current and current != mark:
            replaced.append(key)
        record = days.get(key)
        if record and (record.get("clock_in") or record.get("mode") == "off"):
            conflicts.append(key)
    total_days = (end - start).days + 1
    return {
        "dates": selected,
        "count": len(selected),
        "skipped_nonworking": total_days - len(selected) - len(skipped_holiday),
        "skipped_holiday": skipped_holiday,
        "replaced": replaced,
        "conflicts": conflicts,
        "mark": mark,
    }


def apply_marks(calendar: dict, dates: list[str], mark: dict) -> dict:
    result = core.normalize_calendar(calendar)
    for key in dates:
        result["days"][key] = dict(mark)
    return result


def adopt_mark(record: dict, day: date, mark: dict, settings: dict) -> dict:
    """El usuario decide que una jornada ya registrada adopte el tipo de día.

    Solo cambia los objetivos (las marcas de entrada, salida y descansos quedan
    igual). Si el tipo conserva el objetivo, la jornada no cambia de objetivos.
    """
    record = dict(record)
    record["day_type"] = mark["type"]
    if record.get("custom_targets") or record.get("profile_source") == "manual":
        return record
    if core.mark_frees_day(mark, settings):
        for key in core.TARGET_KEYS:
            record[key] = 0
    return record


# ------------------------------------------------------------ importación

def _parse_any_date(value: str):
    """'2026-12-25' → date · '25/12/2026' → date · '12-25' o '--12-25' → 'MM-DD' (recurrente)."""
    text = str(value or "").strip()
    if text.startswith("--"):
        text = text[2:]
    if re.match(r"^\d{2}-\d{2}$", text):
        return core.valid_month_day(text)
    m = _DMY.match(text)
    if m:
        text = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return date.fromisoformat(text)


def _rows_from_json(text: str) -> list[dict]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("holidays", data.get("festivos"))
    if not isinstance(data, list):
        raise ValueError("lista")
    return [r if isinstance(r, dict) else {"date": r} for r in data]


def _rows_from_csv(text: str) -> list[dict]:
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        class dialect(csv.excel):   # noqa: N801  (sin tocar csv.excel global)
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        return []
    names = {"fecha": "date", "date": "date", "dia": "date", "día": "date",
             "nombre": "label", "label": "label", "name": "label", "descripcion": "label",
             "descripción": "label", "festivo": "label",
             "recurrente": "recurring", "recurring": "recurring", "anual": "recurring",
             "tipo": "type", "type": "type"}
    header = [names.get(c.strip().lower()) for c in rows[0]]
    if "date" in header:
        rows = rows[1:]
    else:
        header = ["date", "label", "recurring", "type"][:max(len(r) for r in rows)]
    return [{header[i]: cell.strip() for i, cell in enumerate(r) if i < len(header) and header[i]}
            for r in rows]


def parse_import(text: str, filename: str = "") -> dict:
    """Lee festivos en JSON ([{date, label, recurring?, type?}]) o CSV (fecha;nombre;recurrente)."""
    text = (text or "").lstrip("﻿")
    if not text.strip():
        raise ValidationError("cal.e.empty")
    is_json = filename.lower().endswith(".json") or text.lstrip()[:1] in "[{"
    try:
        rows = _rows_from_json(text) if is_json else _rows_from_csv(text)
    except (ValueError, csv.Error):
        raise ValidationError("cal.e.format")
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValidationError("cal.e.too_many", max=MAX_IMPORT_ROWS)
    items, errors = [], []
    for n, row in enumerate(rows, start=1):
        try:
            when = _parse_any_date(row.get("date"))
            label = core.clean_label(row.get("label") or row.get("name") or row.get("nombre"))
            kind = str(row.get("type") or "holiday").strip().lower() or "holiday"
            if kind not in core.DAY_TYPES:
                raise ValidationError("err.bad_day_type")
            recurring = isinstance(when, str) or str(row.get("recurring", "")).strip().lower() in _TRUE \
                or row.get("recurring") is True
            if recurring and kind != "holiday":
                raise ValidationError("cal.e.recurring_type")
            key = when if isinstance(when, str) else (when.strftime("%m-%d") if recurring else when.isoformat())
            items.append({"key": key, "recurring": recurring, "type": kind, "label": label})
        except (ValueError, TypeError, ValidationError) as exc:
            errors.append({"row": n, "value": str(row.get("date", ""))[:40],
                           "code": getattr(exc, "code", "cal.e.bad_date")})
    return {"items": items, "errors": errors}


def merge_import(calendar: dict, items: list[dict]) -> tuple[dict, int]:
    result = core.normalize_calendar(calendar)
    for item in items:
        if item["recurring"]:
            result["recurring"][item["key"]] = {"label": item["label"]} if item["label"] else {}
        else:
            mark = {"type": item["type"]}
            if item["label"]:
                mark["label"] = item["label"]
            result["days"][item["key"]] = mark
    return core.normalize_calendar(result), len(items)
