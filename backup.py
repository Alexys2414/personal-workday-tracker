"""Copia de seguridad completa en un único JSON (Jornada 2.1).

Formato (schema_version 1):

    {
      "format": "jornada-backup",
      "schema_version": 1,
      "app_version": "2.1.0",
      "created_at": "2026-10-30T18:05:00+01:00",
      "checksum": "sha256:…",            ← de «data» serializado de forma canónica
      "counts": {"days": 120, "calendar_days": 14, "recurring": 9},
      "data": {
        "records":  { contenido de records.json },
        "settings": { contenido de settings.json },
        "calendar": { contenido de calendar.json }
      }
    }

Compatibilidad: una versión futura de Jornada podrá leer este archivo y migrarlo;
esta versión rechaza copias con un schema_version mayor que el suyo.
La validación es completa antes de escribir nada (ver app.py, restauración).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

import core
from core import ValidationError

FORMAT = "jornada-backup"
SCHEMA_VERSION = 1
MAX_BYTES = 10 * 1024 * 1024
TOP_KEYS = {"format", "schema_version", "app_version", "created_at", "checksum", "counts", "data"}
DATA_KEYS = {"records", "settings", "calendar"}
RECORD_KEYS = {"clock_in", "clock_out", "breaks", "notes", "mode", "custom_targets", "profile",
               "profile_source", "ref_start", "ref_end", "day_type", *core.TARGET_KEYS}
BREAK_KEYS = {"start", "end", "note"}


def checksum(data: dict) -> str:
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build(records: dict, settings: dict, calendar: dict, app_version: str, now: datetime) -> dict:
    data = {"records": records, "settings": settings, "calendar": calendar}
    return {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "app_version": app_version,
        "created_at": core.iso(now),
        "checksum": checksum(data),
        "counts": counts(data),
        "data": data,
    }


def filename(now: datetime) -> str:
    return f"jornada-backup-{core.local_date(now).isoformat()}.json"


def counts(data: dict) -> dict:
    days = data["records"].get("days", {})
    calendar = data.get("calendar") or {}
    return {
        "days": len(days),
        "clocked_days": sum(1 for r in days.values() if r.get("clock_in")),
        "breaks": sum(len(r.get("breaks") or []) for r in days.values()),
        "notes": sum(1 for r in days.values() if r.get("notes")) +
        sum(1 for r in days.values() for b in (r.get("breaks") or []) if b.get("note")),
        "calendar_days": len(calendar.get("days", {})),
        "recurring": len(calendar.get("recurring", {})),
        "first": min(days) if days else None,
        "last": max(days) if days else None,
    }


# ------------------------------------------------------------- validación

def _fail(detail: str):
    raise ValidationError("bk.e.invalid", detail=detail)


def _ts(value, where):
    try:
        return core.parse_ts(value)
    except (TypeError, ValueError):
        _fail(where)


def validate_records(records) -> dict:
    """Comprueba la estructura de records.json sin reinterpretar nada."""
    if not isinstance(records, dict) or set(records) - {"version", "days"}:
        _fail("records")
    if records.get("version", 1) != 1:
        _fail("records.version")
    days = records.get("days", {})
    if not isinstance(days, dict):
        _fail("records.days")
    for key, rec in days.items():
        try:
            date.fromisoformat(key)
        except (TypeError, ValueError):
            _fail(f"records.days.{str(key)[:20]}")
        if not isinstance(rec, dict) or set(rec) - RECORD_KEYS:
            _fail(key)
        if rec.get("mode", "office") not in core.MODES:
            _fail(f"{key}.mode")
        for field in core.TARGET_KEYS:
            if field in rec and (not isinstance(rec[field], int) or isinstance(rec[field], bool)
                                 or not 0 <= rec[field] <= 1440):
                _fail(f"{key}.{field}")
        if not isinstance(rec.get("notes", ""), str) or len(rec.get("notes", "")) > core.MAX_NOTES:
            _fail(f"{key}.notes")
        if rec.get("day_type") is not None and rec["day_type"] not in core.DAY_TYPES:
            _fail(f"{key}.day_type")
        if rec.get("profile") is not None and rec["profile"] not in core.PROFILES:
            _fail(f"{key}.profile")
        clock_in = _ts(rec["clock_in"], f"{key}.clock_in") if rec.get("clock_in") else None
        clock_out = _ts(rec["clock_out"], f"{key}.clock_out") if rec.get("clock_out") else None
        if clock_out and (not clock_in or clock_out <= clock_in):
            _fail(f"{key}.clock_out")
        breaks = rec.get("breaks", [])
        if not isinstance(breaks, list):
            _fail(f"{key}.breaks")
        for b in breaks:
            if not isinstance(b, dict) or set(b) - BREAK_KEYS or not clock_in:
                _fail(f"{key}.breaks")
            start = _ts(b.get("start"), f"{key}.breaks")
            end = _ts(b["end"], f"{key}.breaks") if b.get("end") else None
            if end and end < start:
                _fail(f"{key}.breaks")
            if not isinstance(b.get("note", ""), str) or len(b.get("note", "")) > core.MAX_BREAK_NOTE:
                _fail(f"{key}.breaks.note")
    return {"version": 1, "days": days}


def parse(text: str) -> dict:
    """Valida una copia completa. Devuelve los datos listos para guardar y un resumen."""
    if not isinstance(text, str) or not text.strip():
        raise ValidationError("bk.e.empty")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValidationError("bk.e.too_big", mb=MAX_BYTES // (1024 * 1024))
    try:
        raw = json.loads(text.lstrip("﻿"))
    except ValueError:
        raise ValidationError("bk.e.not_json")
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        raise ValidationError("bk.e.not_backup")
    version = raw.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValidationError("bk.e.not_backup")
    if version > SCHEMA_VERSION:
        raise ValidationError("bk.e.newer", version=version, supported=SCHEMA_VERSION)
    if set(raw) - TOP_KEYS:
        _fail(", ".join(sorted(set(raw) - TOP_KEYS))[:60])
    data = raw.get("data")
    if not isinstance(data, dict) or set(data) - DATA_KEYS or not {"records", "settings"} <= set(data):
        _fail("data")
    if raw.get("checksum") and raw["checksum"] != checksum(data):
        raise ValidationError("bk.e.checksum")

    records = validate_records(data["records"])
    if not isinstance(data["settings"], dict):
        _fail("settings")
    settings = core.normalize_settings(data["settings"])      # migra ajustes antiguos y valida
    calendar = core.normalize_calendar(data.get("calendar"))
    clean = {"records": records, "settings": settings, "calendar": calendar}
    return {
        "data": clean,
        "meta": {"app_version": str(raw.get("app_version", "?"))[:20],
                 "created_at": str(raw.get("created_at", ""))[:40],
                 "schema_version": version, "has_checksum": bool(raw.get("checksum"))},
        "counts": counts(clean),
        "fingerprint": checksum(clean),
    }
