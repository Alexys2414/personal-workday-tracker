"""Exportación e importación de jornadas en CSV.

Formato pensado para Excel y LibreOffice: UTF-8 con BOM, separador «;»,
fin de línea CRLF y una columna por dato. Cada descanso ocupa tres columnas
(inicio, fin y nota), así que exportar e importar conserva todo.
La importación acepta cabeceras en cualquiera de los idiomas disponibles,
separador «;», «,» o tabulador, y fechas ISO o día/mes/año.
"""
from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
import re
from datetime import date, datetime

import core
from i18n import LANGUAGES, catalog, tr

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000
FIELDS = ("date", "weekday", "mode", "profile", "profile_manual", "clock_in", "clock_out",
          "worked", "breaks_total", "target", "min_break", "opt_break", "balance", "status", "notes")
REQUIRED = ("date",)
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


# ------------------------------------------------------------------ utilidades

def _hms(seconds: float) -> str:
    s = int(round(abs(seconds)))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _signed(seconds: float) -> str:
    if abs(seconds) < 1:
        return "0:00:00"
    return ("+" if seconds > 0 else "-") + _hms(seconds)


def _safe_text(text: str) -> str:
    """Evita que Excel interprete una nota como fórmula."""
    return "'" + text if text and text.startswith(_FORMULA_START) else text


def _unsafe_text(text: str) -> str:
    return text[1:] if text.startswith("'") and text[1:2] in _FORMULA_START and text[1:2] else text


def fingerprint(days: dict) -> str:
    return hashlib.sha256(json.dumps(days, sort_keys=True).encode()).hexdigest()[:16]


# ------------------------------------------------------------------ exportar

def export_csv(days: dict, settings: dict, lang: str, now: datetime,
               start: date | None = None, end: date | None = None) -> str:
    keys = sorted(k for k in days if (not start or k >= start.isoformat()) and (not end or k <= end.isoformat()))
    computed = [core.compute_day(date.fromisoformat(k), days[k], settings, now) for k in keys]
    max_breaks = max([len(c["breaks"]) for c in computed] + [1])

    header = [tr(lang, f"csv.{f}") for f in FIELDS]
    for n in range(1, max_breaks + 1):
        header += [tr(lang, "csv.break_start", n=n), tr(lang, "csv.break_end", n=n), tr(lang, "csv.break_note", n=n)]

    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(header)
    for c in computed:
        status = c["status"] if c["status"] in ("finished", "working", "on_break", "unclosed", "off") else "none"
        manual = c["profile_source"] == "manual"
        row = [
            c["date"],
            tr(lang, f"weekday.{c['weekday']}"),
            tr(lang, f"mode.{c['mode']}"),
            tr(lang, f"profile.{c['profile']}") if c["profile"] else "",
            tr(lang, "csv.yes" if manual else "csv.no"),
            c["local"]["clock_in"] or "",
            c["local"]["clock_out"] or "",
            _hms(c["worked_s"]) if c["clock_in"] else "",
            _hms(c["break_s"]) if c["clock_in"] else "",
            _hms(c["target_minutes"] * 60),
            _hms(c["min_break_minutes"] * 60),
            _hms(c["optional_break_minutes"] * 60),
            _signed(c["balance_s"]) if c["status"] == "finished" else "",
            tr(lang, f"csv.st.{status}"),
            _safe_text(c["notes"] or ""),
        ]
        for i in range(max_breaks):
            if i < len(c["local"]["breaks"]):
                b = c["local"]["breaks"][i]
                row += [b["start"] or "", b["end"] or "", _safe_text(b.get("note") or "")]
            else:
                row += ["", "", ""]
        writer.writerow(row)
    return "﻿" + out.getvalue()


# ------------------------------------------------------------------ importar

def _vocabulary():
    """Etiquetas de todos los idiomas -> clave interna (cabeceras y valores)."""
    headers, modes, profiles, yes = {}, {}, {}, {"1", "true", "x"}
    for lang in LANGUAGES:
        cat = catalog(lang)
        for f in FIELDS:
            headers[cat[f"csv.{f}"].lower()] = f
        for m in core.MODES:
            modes[cat[f"mode.{m}"].lower()] = m
        modes[cat["mode.remote_short"].lower()] = "remote"
        for p in core.PROFILES:
            profiles[cat[f"profile.{p}"].lower()] = p
        yes.add(cat["csv.yes"].lower())
    for m in core.MODES:
        modes[m] = m
    for p in core.PROFILES:
        profiles[p] = p
    headers.update({f: f for f in FIELDS})
    return headers, modes, profiles, yes


def _break_column(name: str):
    """'descanso_2_inicio' / 'break_2_start' -> (2, 'start')."""
    for lang in LANGUAGES:
        cat = catalog(lang)
        for part in ("start", "end", "note"):
            pattern = re.escape(cat[f"csv.break_{part}"].lower()).replace(r"\{n\}", r"(\d+)")
            m = re.fullmatch(pattern, name)
            if m:
                return int(m.group(1)), part
    return None


def _parse_date(value: str) -> date | None:
    value = value.strip()
    for pattern, order in ((r"(\d{4})-(\d{1,2})-(\d{1,2})", "ymd"), (r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", "dmy")):
        m = re.fullmatch(pattern, value)
        if m:
            a, b, c = map(int, m.groups())
            try:
                return date(a, b, c) if order == "ymd" else date(c, b, a)
            except ValueError:
                return None
    return None


def _parse_minutes(value: str):
    """'8:30', '8:30:00' o '510' -> minutos (None si vacío; ValueError si no válido)."""
    value = value.strip()
    if not value:
        return None
    m = re.fullmatch(r"(\d{1,3}):(\d{2})(?::(\d{2}))?", value)
    if m:
        h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        if mi > 59 or s > 59:
            raise ValueError
        return h * 60 + mi + round(s / 60)
    if value.isdigit():
        return int(value)
    raise ValueError


def decode_upload(data_b64: str, lang: str) -> str:
    try:
        raw = base64.b64decode(data_b64 or "", validate=True)
    except (binascii.Error, ValueError):
        raise core.ValidationError("imp.e.empty")
    if len(raw) > MAX_BYTES:
        raise core.ValidationError("imp.e.too_big", max=MAX_BYTES // (1024 * 1024))
    for encoding in ("utf-8-sig", "cp1252"):   # Excel en Windows guarda en cp1252
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise core.ValidationError("imp.e.bad_encoding")


def parse_import(text: str, days: dict, settings: dict, now: datetime, lang: str) -> dict:
    """Valida todo el archivo sin modificar nada. Devuelve vista previa y registros."""
    text = text.lstrip("﻿")
    if not text.strip():
        raise core.ValidationError("imp.e.empty")
    first = text.splitlines()[0]
    delimiter = max((";", ",", "\t"), key=first.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader)
    except (StopIteration, csv.Error):
        raise core.ValidationError("imp.e.empty")

    headers, modes, profiles, yes = _vocabulary()
    columns, break_cols = {}, {}
    for i, name in enumerate(header):
        name = name.strip().lstrip("﻿").lower()
        if name in headers:
            columns[headers[name]] = i
        else:
            found = _break_column(name)
            if found:
                break_cols.setdefault(found[0], {})[found[1]] = i
    missing = [tr(lang, f"csv.{f}") for f in REQUIRED if f not in columns]
    if "clock_in" not in columns and "notes" not in columns:
        missing.append(tr(lang, "csv.clock_in"))
    if missing:
        raise core.ValidationError("imp.e.missing_cols", cols=", ".join(missing))

    rows, records, seen = [], {}, set()
    for line_no, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue
        if len(rows) >= MAX_ROWS:
            raise core.ValidationError("imp.e.too_many", max=MAX_ROWS)
        get = lambda f: cells[columns[f]].strip() if f in columns and columns[f] < len(cells) else ""  # noqa: E731
        row = {"line": line_no, "date": get("date"), "status": "error", "errors": []}
        rows.append(row)

        day = _parse_date(get("date"))
        if not day:
            row["errors"].append(tr(lang, "imp.e.bad_row_date", value=get("date")))
            continue
        key = row["date"] = day.isoformat()
        if key in seen:
            row["errors"].append(tr(lang, "imp.e.dup_in_file", date=key))
            continue
        seen.add(key)

        payload = {"notes": _unsafe_text(get("notes")), "clock_in": get("clock_in"), "clock_out": get("clock_out")}
        mode = get("mode").lower()
        if mode:
            if mode not in modes:
                row["errors"].append(tr(lang, "imp.e.bad_mode", value=get("mode")))
            else:
                payload["mode"] = modes[mode]
        profile = None
        if get("profile"):
            profile = profiles.get(get("profile").lower())
            if not profile:
                row["errors"].append(tr(lang, "imp.e.bad_profile", value=get("profile")))
        manual = get("profile_manual").lower() in yes
        if manual and profile:
            payload["profile"] = profile
        for field, target in (("target", "target_minutes"), ("min_break", "min_break_minutes"),
                              ("opt_break", "optional_break_minutes")):
            try:
                minutes = _parse_minutes(get(field))
            except ValueError:
                row["errors"].append(tr(lang, "imp.e.bad_duration", label=tr(lang, f"csv.{field}"), value=get(field)))
                continue
            if minutes is not None:
                payload[target] = minutes
        cell = lambda i: cells[i].strip() if i is not None and i < len(cells) else ""  # noqa: E731
        payload["breaks"] = [
            {"start": cell(parts.get("start")), "end": cell(parts.get("end")),
             "note": _unsafe_text(cell(parts.get("note")))}
            for _, parts in sorted(break_cols.items())
        ]
        if row["errors"]:
            continue
        try:
            record = core.build_record(day, payload, None, settings, now)
        except core.ValidationError as exc:
            row["errors"].append(exc.message(lang))
            continue
        if profile and not manual:
            # Conserva el perfil que tenía el día aunque los ajustes actuales digan otro.
            record["profile"] = profile
            record["profile_source"] = "period" if profile == "summer" else "weekly"
        records[key] = record
        computed = core.compute_day(day, record, settings, now)
        row.update({
            "status": "dup" if key in days else "new",
            "mode": record["mode"],
            "profile": record.get("profile"),
            "clock_in": computed["local"]["clock_in"],
            "clock_out": computed["local"]["clock_out"],
            "breaks": len(record["breaks"]),
            "worked_s": computed["worked_s"],
            "has_notes": computed["has_notes"],
        })

    if not rows:
        raise core.ValidationError("imp.e.empty")
    count = lambda s: sum(r["status"] == s for r in rows)  # noqa: E731
    return {
        "rows": rows,
        "records": records,
        "counts": {"new": count("new"), "dup": count("dup"), "error": count("error")},
        "fingerprint": fingerprint(days),
    }


def merge(days: dict, records: dict, overwrite: set[str]) -> tuple[dict, int]:
    """Nuevo diccionario de jornadas: añade las nuevas y sobrescribe solo las elegidas."""
    merged = dict(days)
    imported = 0
    for key, record in records.items():
        if key in days and key not in overwrite:
            continue
        merged[key] = record
        imported += 1
    return merged, imported
