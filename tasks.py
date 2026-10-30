"""Tareas (tickets Jira o trabajo interno) y tramos de tiempo imputado (Jornada 2.2).

Módulo puro, como core: recibe y devuelve diccionarios; app.py los guarda en
data/tasks.json con escritura atómica. El fichaje laboral (records.json) y las
horas imputadas son conceptos distintos: aquí nunca se modifica un fichaje.

data/tasks.json
  {"version": 1,
   "tasks":   {"t_…": {"id", "key", "title", "project", "estimate_minutes", "status", "color",
                        "favorite", "notes", "created_at", "completed_at"}},
   "entries": {"e_…": {"id", "task_id", "date", "start", "end", "seconds", "source", "note",
                        "booked", "created_at"}},
   "state":   {"resume_task_id": …}}

Un tramo con hora (start/end en ISO) dura end − start; `end` vacío = cronómetro en
marcha (como mucho uno). Un tramo manual sin hora solo tiene `date` y `seconds`.
Los tramos con hora nunca se solapan entre sí.
"""
from __future__ import annotations

import copy
import re
import uuid
from datetime import date, datetime, timedelta

import core
from core import Conflict, ValidationError

VERSION = 1
STATUSES = ("pending", "in_progress", "paused", "done")
COLORS = ("teal", "blue", "violet", "coral", "amber", "green", "pink", "slate")
SOURCES = ("timer", "manual")
MAX_TASKS = 2000
MAX_ENTRIES = 50000
MAX_KEY, MAX_TITLE, MAX_PROJECT, MAX_NOTES, MAX_NOTE = 32, 160, 60, 2000, 200
MAX_ENTRY_SECONDS = 24 * 3600
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
TASK_KEYS = {"id", "key", "title", "project", "estimate_minutes", "status", "color", "favorite", "notes",
             "created_at", "completed_at"}
ENTRY_KEYS = {"id", "task_id", "date", "start", "end", "seconds", "source", "note", "booked", "created_at"}


def default_data() -> dict:
    return {"version": VERSION, "tasks": {}, "entries": {}, "state": {"resume_task_id": None}}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ------------------------------------------------------------- validación

def _text(value, limit, code, required=False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValidationError(code)
    if len(text) > limit:
        raise ValidationError("task.e.too_long", max=limit)
    return text


def clean_key(value) -> str:
    key = str(value or "").strip().upper()
    if not key:
        return ""
    if len(key) > MAX_KEY or not _KEY_RE.match(key):
        raise ValidationError("task.e.bad_key", value=key[:40])
    return key


def _estimate(value):
    if value in (None, ""):
        return None
    return core._int_in_range(value, "@task.estimate", 0, 1000 * 60)


def clean_task(raw: dict, base: dict | None = None) -> dict:
    """Valida los campos editables de una tarea (sobre `base` si se edita)."""
    if not isinstance(raw, dict):
        raise ValidationError("err.bad_data")
    task = copy.deepcopy(base) if base else {
        "id": new_id("t"), "key": "", "title": "", "project": "", "estimate_minutes": None,
        "status": "pending", "color": "teal", "favorite": False, "notes": "",
        "created_at": None, "completed_at": None,
    }
    if "key" in raw:
        task["key"] = clean_key(raw["key"])
    if "title" in raw:
        task["title"] = _text(raw["title"], MAX_TITLE, "task.e.title")
    if "project" in raw:
        task["project"] = _text(raw["project"], MAX_PROJECT, "task.e.project")
    if "estimate_minutes" in raw:
        task["estimate_minutes"] = _estimate(raw["estimate_minutes"])
    if "color" in raw:
        if raw["color"] not in COLORS:
            raise ValidationError("err.bad_value", field="color")
        task["color"] = raw["color"]
    if "favorite" in raw:
        task["favorite"] = bool(raw["favorite"])
    if "notes" in raw:
        task["notes"] = _text(raw["notes"], MAX_NOTES, "task.e.notes")
    if "status" in raw:
        if raw["status"] not in STATUSES:
            raise ValidationError("err.bad_value", field="status")
        task["status"] = raw["status"]
    if not task["key"] and not task["title"]:
        raise ValidationError("task.e.need_name")
    return task


def _ts(value, where):
    try:
        return core.parse_ts(value)
    except (TypeError, ValueError):
        raise ValidationError("task.e.invalid", detail=where)


def normalize(raw) -> dict:
    """Valida tasks.json completo (al cargar o al restaurar una copia). No reinterpreta nada."""
    if raw is None:
        return default_data()
    if not isinstance(raw, dict) or set(raw) - {"version", "tasks", "entries", "state"}:
        raise ValidationError("task.e.invalid", detail="tasks.json")
    if raw.get("version", VERSION) != VERSION:
        raise ValidationError("task.e.invalid", detail="version")
    tasks, entries = raw.get("tasks") or {}, raw.get("entries") or {}
    if not isinstance(tasks, dict) or not isinstance(entries, dict) \
            or len(tasks) > MAX_TASKS or len(entries) > MAX_ENTRIES:
        raise ValidationError("task.e.invalid", detail="tasks/entries")
    out = default_data()
    keys = set()
    for tid, t in tasks.items():
        if not isinstance(t, dict) or set(t) - TASK_KEYS or t.get("id") != tid:
            raise ValidationError("task.e.invalid", detail=f"task {str(tid)[:20]}")
        clean = clean_task({k: t[k] for k in ("key", "title", "project", "estimate_minutes", "color",
                                              "favorite", "notes", "status") if k in t}, {**t})
        for field in ("created_at", "completed_at"):
            if clean.get(field):
                _ts(clean[field], f"{tid}.{field}")
        if clean["key"]:
            if clean["key"] in keys:
                raise ValidationError("task.e.dup_key", ticket=clean["key"])
            keys.add(clean["key"])
        out["tasks"][tid] = clean
    active = 0
    for eid, e in entries.items():
        if not isinstance(e, dict) or set(e) - ENTRY_KEYS or e.get("id") != eid \
                or e.get("task_id") not in out["tasks"] or e.get("source") not in SOURCES:
            raise ValidationError("task.e.invalid", detail=f"entry {str(eid)[:20]}")
        core._parse_date(e.get("date"), "@label.date")
        if e.get("start"):
            start = _ts(e["start"], f"{eid}.start")
            if e.get("end"):
                if _ts(e["end"], f"{eid}.end") <= start:
                    raise ValidationError("task.e.invalid", detail=f"{eid}.end")
            else:
                active += 1
        elif not isinstance(e.get("seconds"), (int, float)) or not 0 < e["seconds"] <= MAX_ENTRY_SECONDS:
            raise ValidationError("task.e.invalid", detail=f"{eid}.seconds")
        if not isinstance(e.get("note", ""), str) or len(e.get("note", "")) > MAX_NOTE:
            raise ValidationError("task.e.invalid", detail=f"{eid}.note")
        out["entries"][eid] = {**e, "booked": bool(e.get("booked"))}
    if active > 1:
        raise ValidationError("task.e.invalid", detail="active")
    _check_overlaps(out)
    state = raw.get("state") or {}
    resume = state.get("resume_task_id") if isinstance(state, dict) else None
    out["state"]["resume_task_id"] = resume if resume in out["tasks"] else None
    return out


# --------------------------------------------------------------- tramos

def entry_bounds(e: dict, now: datetime):
    """(inicio, fin) de un tramo con hora; el activo termina en `now`. None si no tiene hora."""
    if not e.get("start"):
        return None
    start = core.parse_ts(e["start"])
    end = core.parse_ts(e["end"]) if e.get("end") else max(now.astimezone(core.UTC), start)
    return start, end


def entry_seconds(e: dict, now: datetime) -> float:
    b = entry_bounds(e, now)
    return float(e.get("seconds") or 0) if b is None else max(0.0, core.seconds(*b))


def active_entry(data: dict) -> dict | None:
    return next((e for e in data["entries"].values() if e.get("start") and not e.get("end")), None)


def _check_overlaps(data: dict, now: datetime | None = None, ignore: set | None = None) -> None:
    now = now or datetime.now(core.UTC)
    spans = sorted((entry_bounds(e, now), e) for e in data["entries"].values()
                   if e.get("start") and e["id"] not in (ignore or set()))
    for (a, ea), (b, eb) in zip(spans, spans[1:]):
        if b[0] < a[1]:
            raise ValidationError("task.e.overlap", a=_hm_clock(ea), b=_hm_clock(eb))


def _hm_clock(e: dict) -> str:
    start = core.local_clock(core.parse_ts(e["start"]))[:5]
    end = core.local_clock(core.parse_ts(e["end"]))[:5] if e.get("end") else "…"
    return f"{e['date']} {start}–{end}"


def _task(data, task_id) -> dict:
    task = data["tasks"].get(task_id)
    if not task:
        raise ValidationError("task.e.not_found")
    return task


def _close(data: dict, now: datetime) -> dict | None:
    """Cierra el cronómetro activo en `now`. Si dura menos de 1 s, se descarta."""
    active = active_entry(data)
    if not active:
        return None
    start = core.parse_ts(active["start"])
    if now <= start + timedelta(seconds=1):
        del data["entries"][active["id"]]
    else:
        active["end"] = core.iso(now)
    task = data["tasks"].get(active["task_id"])
    if task and task["status"] == "in_progress":
        task["status"] = "paused"
    return active


# ------------------------------------------------------------ operaciones

def create_task(data: dict, raw: dict, now: datetime) -> tuple[dict, dict]:
    data = copy.deepcopy(data)
    task = clean_task(raw)
    task["created_at"] = core.iso(now)
    _unique_key(data, task)
    data["tasks"][task["id"]] = task
    return data, task


def _unique_key(data, task):
    if task["key"] and any(t["key"] == task["key"] and t["id"] != task["id"] for t in data["tasks"].values()):
        raise ValidationError("task.e.dup_key", ticket=task["key"])


def update_task(data: dict, task_id: str, raw: dict, now: datetime) -> tuple[dict, dict]:
    data = copy.deepcopy(data)
    old = _task(data, task_id)
    task = clean_task(raw, old)
    _unique_key(data, task)
    if task["status"] == "done" and old["status"] != "done":
        task["completed_at"] = core.iso(now)
        active = active_entry(data)
        if active and active["task_id"] == task_id:
            _close(data, now)
    elif task["status"] != "done":
        task["completed_at"] = None
    data["tasks"][task_id] = task
    return data, task


def delete_task(data: dict, task_id: str) -> tuple[dict, int]:
    data = copy.deepcopy(data)
    _task(data, task_id)
    gone = [eid for eid, e in data["entries"].items() if e["task_id"] == task_id]
    for eid in gone:
        del data["entries"][eid]
    del data["tasks"][task_id]
    if data["state"]["resume_task_id"] == task_id:
        data["state"]["resume_task_id"] = None
    return data, len(gone)


def start(data: dict, task_id: str, now: datetime) -> tuple[dict, dict]:
    """Empieza (o cambia a) una tarea: cierra el tramo activo y abre otro. Nunca hay dos a la vez."""
    data = copy.deepcopy(data)
    now = now.astimezone(core.UTC).replace(microsecond=0)
    task = _task(data, task_id)
    active = active_entry(data)
    if active and active["task_id"] == task_id:
        return data, active
    _close(data, now)
    task["status"] = "in_progress"
    task["completed_at"] = None
    entry = {"id": new_id("e"), "task_id": task_id, "date": core.local_date(now).isoformat(),
             "start": core.iso(now), "end": None, "source": "timer", "note": "", "booked": False,
             "created_at": core.iso(now)}
    data["entries"][entry["id"]] = entry
    data["state"]["resume_task_id"] = None
    return data, entry


def pause(data: dict, now: datetime, remember: bool = False) -> tuple[dict, dict | None]:
    """Detiene el cronómetro. `remember`: se ofrecerá continuar la misma tarea (vuelta del descanso)."""
    data = copy.deepcopy(data)
    now = now.astimezone(core.UTC).replace(microsecond=0)
    closed = _close(data, now)
    data["state"]["resume_task_id"] = closed["task_id"] if (closed and remember) else None
    return data, closed


def _parse_entry_times(day: date, raw: dict, now: datetime):
    start = core.combine(day, raw["start"], "@task.start") if raw.get("start") else None
    end = core.combine(day, raw["end"], "@task.end") if raw.get("end") else None
    if start and end and end <= start:
        end += timedelta(days=1)          # tramo que cruza la medianoche (22:00–01:00)
    if (start is None) != (end is None):
        raise ValidationError("task.e.need_both")
    if start and core.seconds(start, end) > MAX_ENTRY_SECONDS:
        raise ValidationError("task.e.too_long_entry")
    limit = now.astimezone(core.UTC) + core.FUTURE_TOLERANCE
    if end and end > limit:
        raise ValidationError("task.e.future")
    return start, end


def add_manual(data: dict, raw: dict, now: datetime) -> tuple[dict, dict]:
    """Tramo manual: con hora (start/end «HH:MM») o solo con duración (minutes)."""
    data = copy.deepcopy(data)
    if not isinstance(raw, dict):
        raise ValidationError("err.bad_data")
    _task(data, raw.get("task_id"))
    day = core._parse_date(raw.get("date"), "@label.date")
    if day > core.local_date(now):
        raise ValidationError("task.e.future")
    start, end = _parse_entry_times(day, raw, now)
    entry = {"id": new_id("e"), "task_id": raw["task_id"], "date": day.isoformat(), "start": None, "end": None,
             "source": "manual", "note": _text(raw.get("note"), MAX_NOTE, "task.e.note"),
             "booked": False, "created_at": core.iso(now)}
    if start:
        entry["start"], entry["end"] = core.iso(start), core.iso(end)
    else:
        entry["seconds"] = core._int_in_range(raw.get("minutes"), "@task.minutes", 1, 24 * 60) * 60
    data["entries"][entry["id"]] = entry
    _check_overlaps(data, now)
    return data, entry


def update_entry(data: dict, entry_id: str, raw: dict, now: datetime) -> tuple[dict, dict]:
    """Edita hora, duración, tarea (mover), nota o estado de imputación de un tramo."""
    data = copy.deepcopy(data)
    e = data["entries"].get(entry_id)
    if not e or not isinstance(raw, dict):
        raise ValidationError("task.e.entry_not_found")
    if "task_id" in raw:
        _task(data, raw["task_id"])
        e["task_id"] = raw["task_id"]
    if "note" in raw:
        e["note"] = _text(raw["note"], MAX_NOTE, "task.e.note")
    if "booked" in raw:
        e["booked"] = bool(raw["booked"])
    if "date" in raw or "start" in raw or "end" in raw or "minutes" in raw:
        if not e.get("end") and e.get("start"):
            if raw.get("end") or "date" in raw:
                raise ValidationError("task.e.active_edit")
        day = core._parse_date(raw.get("date", e["date"]), "@label.date")
        if day > core.local_date(now):
            raise ValidationError("task.e.future")
        e["date"] = day.isoformat()
        if raw.get("start") or raw.get("end"):
            if not e.get("end") and e.get("start"):           # activo: solo se corrige el inicio
                start = core.combine(day, raw["start"], "@task.start")
                if start > now:
                    raise ValidationError("task.e.future")
                e["start"] = core.iso(start)
            else:
                start, end = _parse_entry_times(day, raw, now)
                e["start"], e["end"] = core.iso(start), core.iso(end)
                e.pop("seconds", None)
        elif "minutes" in raw:
            e["start"] = e["end"] = None
            e["seconds"] = core._int_in_range(raw["minutes"], "@task.minutes", 1, 24 * 60) * 60
    _check_overlaps(data, now)
    return data, e


def delete_entry(data: dict, entry_id: str) -> dict:
    data = copy.deepcopy(data)
    if entry_id not in data["entries"]:
        raise ValidationError("task.e.entry_not_found")
    del data["entries"][entry_id]
    return data


def split_entry(data: dict, entry_id: str, raw: dict, now: datetime) -> tuple[dict, dict, dict]:
    """Divide un tramo cerrado en dos; la segunda parte puede ir a otra tarea.

    Con hora: se corta en `at` («HH:MM[:SS]»). Sin hora: `first_minutes` para la primera parte.
    La suma de ambas partes es exactamente la duración original.
    """
    data = copy.deepcopy(data)
    e = data["entries"].get(entry_id)
    if not e or not isinstance(raw, dict):
        raise ValidationError("task.e.entry_not_found")
    if e.get("start") and not e.get("end"):
        raise ValidationError("task.e.split_active")
    target = raw.get("task_id") or e["task_id"]
    _task(data, target)
    second = {**copy.deepcopy(e), "id": new_id("e"), "task_id": target, "created_at": core.iso(now),
              "booked": e.get("booked", False)}
    if e.get("start"):
        start, end = core.parse_ts(e["start"]), core.parse_ts(e["end"])
        at = core.combine(core.local_date(start), raw.get("at"), "@task.split_at")
        if at < start:                                 # tramo que cruzó la medianoche
            at += timedelta(days=1)
        if not start < at < end:
            raise ValidationError("task.e.split_range")
        e["end"] = second["start"] = core.iso(at)
        second["date"] = core.local_date(at).isoformat()
    else:
        first = core._int_in_range(raw.get("first_minutes"), "@task.minutes", 1, 24 * 60) * 60
        if first >= e["seconds"]:
            raise ValidationError("task.e.split_range")
        second["seconds"] = e["seconds"] - first
        e["seconds"] = first
    data["entries"][second["id"]] = second
    _check_overlaps(data, now)
    return data, e, second


def set_booked(data: dict, ids: list, booked: bool) -> tuple[dict, int]:
    data = copy.deepcopy(data)
    if not isinstance(ids, list):
        raise ValidationError("err.bad_data")
    n = 0
    for eid in ids:
        e = data["entries"].get(eid)
        if e and not (e.get("start") and not e.get("end")):     # el activo no se imputa todavía
            e["booked"] = bool(booked)
            n += 1
    return data, n


# ------------------------------------------------------------ resúmenes

def work_intervals(day: date, record: dict | None, now: datetime) -> list[tuple[datetime, datetime]]:
    """Intervalos de trabajo efectivo según el fichaje: entrada→salida menos descansos."""
    if not record or not record.get("clock_in"):
        return []
    c = core.compute_day(day, record, core.default_settings(), now)
    start = core.parse_ts(c["clock_in"])
    end = core.parse_ts(c["clock_out"]) if c["clock_out"] else (
        max(now.astimezone(core.UTC), start) if c["status"] in ("working", "on_break") else start)
    if c["status"] == "unclosed":
        stamps = [start] + [core.parse_ts(t) for b in c["breaks"] for t in (b["start"], b["end"]) if t]
        end = max(stamps)
    cuts = sorted((core.parse_ts(b["start"]), core.parse_ts(b["end"]) if b["end"] else end) for b in c["breaks"])
    out, cursor = [], start
    for bs, be in cuts:
        if bs > cursor:
            out.append((cursor, min(bs, end)))
        cursor = max(cursor, be)
    if end > cursor:
        out.append((cursor, end))
    return [(a, b) for a, b in out if b > a]


def _overlap(a: tuple, intervals: list) -> float:
    return sum(max(0.0, core.seconds(max(a[0], s), min(a[1], e))) for s, e in intervals)


def task_totals(data: dict, now: datetime) -> dict:
    """Segundos totales, de hoy y último uso de cada tarea."""
    today = core.local_date(now).isoformat()
    out = {tid: {"total_s": 0.0, "today_s": 0.0, "sessions": 0, "last_used": None} for tid in data["tasks"]}
    for e in data["entries"].values():
        t = out.get(e["task_id"])
        if t is None:
            continue
        s = entry_seconds(e, now)
        t["total_s"] += s
        t["sessions"] += 1
        if e["date"] == today:
            t["today_s"] += s
        stamp = e.get("end") or e.get("start") or e.get("created_at")
        if e.get("start") and not e.get("end"):
            stamp = core.iso(now)
        if stamp and (not t["last_used"] or core.parse_ts(stamp) > core.parse_ts(t["last_used"])):
            t["last_used"] = stamp
    return out


def progress(task: dict, total_s: float) -> dict:
    est = task.get("estimate_minutes")
    if not est:
        return {"estimate_s": None, "remaining_s": None, "over_s": 0.0, "pct": None}
    est_s = est * 60
    return {"estimate_s": est_s, "remaining_s": round(max(0.0, est_s - total_s), 3),
            "over_s": round(max(0.0, total_s - est_s), 3), "pct": round(total_s / est_s * 100, 2)}


def task_view(data: dict, now: datetime) -> list[dict]:
    totals = task_totals(data, now)
    active = active_entry(data)
    out = []
    for tid, t in data["tasks"].items():
        tot = totals[tid]
        out.append({**t, **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in tot.items()},
                    **progress(t, tot["total_s"]), "active": bool(active and active["task_id"] == tid)})
    out.sort(key=lambda t: (not t["active"], t["status"] == "done", -(core.parse_ts(t["last_used"]).timestamp()
                                                                       if t["last_used"] else 0), t["key"] or t["title"]))
    return out


def _entry_view(e: dict, data: dict, now: datetime) -> dict:
    t = data["tasks"].get(e["task_id"], {})
    return {**e, "seconds": round(entry_seconds(e, now), 3), "active": bool(e.get("start") and not e.get("end")),
            "key": t.get("key", ""), "title": t.get("title", ""), "project": t.get("project", ""),
            "color": t.get("color", "slate"),
            "local_start": core.local_clock(core.parse_ts(e["start"]))[:5] if e.get("start") else None,
            "local_end": core.local_clock(core.parse_ts(e["end"]))[:5] if e.get("end") else None}


def day_summary(day: date, data: dict, record: dict | None, settings: dict, now: datetime,
                calendar: dict | None = None) -> dict:
    """Trabajo efectivo (fichaje) frente a tiempo imputado en tareas, con avisos de discrepancias."""
    c = core.compute_day(day, record, settings, now, calendar)
    key = day.isoformat()
    entries = sorted((e for e in data["entries"].values() if e["date"] == key),
                     key=lambda e: (e.get("start") or "9", e["created_at"]))
    views = [_entry_view(e, data, now) for e in entries]
    imputed = sum(v["seconds"] for v in views)
    worked = c["worked_s"]
    intervals = work_intervals(day, record, now)
    issues = []
    if worked and imputed > worked + 60:
        issues.append({"type": "over_imputed", "seconds": round(imputed - worked, 3)})
    for e in entries:
        b = entry_bounds(e, now)
        if b is None:
            continue
        if e.get("start") and not e.get("end") and core.local_date(b[0]) < core.local_date(now):
            issues.append({"type": "stale_active", "entry_id": e["id"]})
        if intervals:
            outside = core.seconds(*b) - _overlap(b, intervals)
            if outside >= 60:
                issues.append({"type": "outside_work", "entry_id": e["id"], "seconds": round(outside, 3)})
        elif e["source"] == "timer":
            # Cronómetro usado un día sin fichaje: se avisa (el manual sin fichaje es legítimo).
            issues.append({"type": "no_clock", "entry_id": e["id"]})
    by_task: dict[str, float] = {}
    for v in views:
        by_task[v["task_id"]] = by_task.get(v["task_id"], 0.0) + v["seconds"]
    return {
        "date": key,
        "worked_s": worked,
        "status": c["status"],
        "imputed_s": round(imputed, 3),
        "unassigned_s": round(max(0.0, worked - imputed), 3),
        "over_s": round(max(0.0, imputed - worked), 3) if worked else 0.0,
        "entries": views,
        "tasks": [{"task_id": tid, "seconds": round(s, 3), **{k: data["tasks"][tid].get(k) for k in
                                                                ("key", "title", "project", "color")}}
                  for tid, s in sorted(by_task.items(), key=lambda kv: -kv[1])],
        "work_intervals": [[core.iso(a), core.iso(b)] for a, b in intervals],
        "issues": issues,
    }


def trim_plan(day: date, data: dict, record: dict | None, now: datetime) -> list[dict]:
    """Propuesta para ajustar los tramos al fichaje: se quita lo que cae fuera del trabajo efectivo
    (descansos, antes de la entrada o después de la salida). No se aplica sin confirmación."""
    intervals = work_intervals(day, record, now)
    if not intervals:
        return []
    plan = []
    for e in data["entries"].values():
        if e["date"] != day.isoformat() or not e.get("start") or not e.get("end"):
            continue
        b = entry_bounds(e, now)
        pieces = [(max(b[0], s), min(b[1], t)) for s, t in intervals if min(b[1], t) > max(b[0], s)]
        kept = sum(core.seconds(*p) for p in pieces)
        if core.seconds(*b) - kept >= 1:
            plan.append({"entry_id": e["id"], "before_s": round(core.seconds(*b), 3), "after_s": round(kept, 3),
                         "pieces": [[core.iso(p[0]), core.iso(p[1])] for p in pieces]})
    return plan


def apply_trim(data: dict, plan: list[dict], now: datetime) -> dict:
    data = copy.deepcopy(data)
    for item in plan:
        e = data["entries"].get(item["entry_id"])
        if not e:
            continue
        pieces = item["pieces"]
        if not pieces:
            del data["entries"][e["id"]]
            continue
        e["start"], e["end"] = pieces[0]
        for start, end in pieces[1:]:
            extra = {**copy.deepcopy(e), "id": new_id("e"), "start": start, "end": end,
                     "date": core.local_date(core.parse_ts(start)).isoformat(), "created_at": core.iso(now)}
            data["entries"][extra["id"]] = extra
    _check_overlaps(data, now)
    return data


def week_summary(day: date, data: dict, days: dict, settings: dict, now: datetime,
                 calendar: dict | None = None) -> dict:
    """Imputación semanal frente a su objetivo propio (no el de la jornada laboral) y al trabajo efectivo."""
    today = core.local_date(now)
    dates = core.week_dates(day)
    goal = settings.get("tasks", {}).get("weekly_goal_minutes", 2400) * 60
    per_day, by_project, by_task = [], {}, {}
    for d in dates:
        s = day_summary(d, data, days.get(d.isoformat()), settings, now, calendar)
        per_day.append({"date": s["date"], "weekday": d.weekday(), "imputed_s": s["imputed_s"],
                        "worked_s": s["worked_s"], "future": d > today, "today": d == today,
                        "issues": len(s["issues"])})
        for v in s["entries"]:
            proj = v["project"] or ""
            by_project[proj] = by_project.get(proj, 0.0) + v["seconds"]
            t = by_task.setdefault(v["task_id"], {"task_id": v["task_id"], "key": v["key"], "title": v["title"],
                                                  "project": v["project"], "color": v["color"], "seconds": 0.0})
            t["seconds"] += v["seconds"]
    imputed = sum(p["imputed_s"] for p in per_day)
    worked = sum(p["worked_s"] for p in per_day)
    closed = dates[-1] < today
    totals = task_totals(data, now)
    tickets = sorted(by_task.values(), key=lambda t: -t["seconds"])
    for t in tickets:
        t["seconds"] = round(t["seconds"], 3)
        t.update(progress(data["tasks"][t["task_id"]], totals[t["task_id"]]["total_s"]))
    return {
        "from": dates[0].isoformat(), "to": dates[-1].isoformat(),
        "goal_s": float(goal), "imputed_s": round(imputed, 3), "worked_s": round(worked, 3),
        "remaining_s": round(max(0.0, goal - imputed), 3),
        # Mientras la semana no termina, lo que falta es «pendiente», no déficit.
        "deficit_s": round(max(0.0, goal - imputed), 3) if closed else 0.0,
        "closed": closed,
        "diff_worked_s": round(imputed - worked, 3),
        "days": per_day,
        "projects": [{"project": p, "seconds": round(s, 3)} for p, s in sorted(by_project.items(), key=lambda kv: -kv[1])],
        "tickets": tickets,
    }


# ---------------------------------------------------- resumen para imputar

def decimal_hours(seconds: float) -> float:
    """1 h 30 min → 1.5 (redondeo a centésimas, como se imputa habitualmente)."""
    return round(seconds / 3600 + 1e-9, 2)


def hm_text(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"


def report(data: dict, now: datetime, start: date | None, end: date | None, group: str = "day") -> dict:
    """Filas para trasladar al sistema de la empresa: por día y ticket, o por ticket."""
    if start and end and end < start:
        raise ValidationError("err.bad_range")
    rows: dict[tuple, dict] = {}
    for e in data["entries"].values():
        if (start and e["date"] < start.isoformat()) or (end and e["date"] > end.isoformat()):
            continue
        if e.get("start") and not e.get("end"):
            continue                                   # el tramo en curso aún no se puede imputar
        t = data["tasks"][e["task_id"]]
        key = (e["date"], e["task_id"]) if group == "day" else (e["task_id"],)
        row = rows.setdefault(key, {"date": e["date"] if group == "day" else None, "task_id": e["task_id"],
                                    "key": t["key"], "title": t["title"], "project": t["project"],
                                    "seconds": 0.0, "entry_ids": [], "booked_n": 0, "manual": False})
        row["seconds"] += entry_seconds(e, now)
        row["entry_ids"].append(e["id"])
        row["booked_n"] += 1 if e.get("booked") else 0
        row["manual"] = row["manual"] or e["source"] == "manual"
    out = []
    for row in rows.values():
        n = len(row["entry_ids"])
        row["booked"] = "all" if row["booked_n"] == n else "none" if row["booked_n"] == 0 else "partial"
        row["seconds"] = round(row["seconds"], 3)
        row["hours"] = decimal_hours(row["seconds"])
        out.append(row)
    if group == "day":
        out.sort(key=lambda r: (r["date"], r["key"] or r["title"]))
    else:
        out.sort(key=lambda r: (-r["seconds"], r["key"]))
    total = sum(r["seconds"] for r in out)
    return {"group": group, "rows": out, "total_s": round(total, 3), "total_hours": decimal_hours(total),
            "pending_s": round(sum(r["seconds"] for r in out if r["booked"] != "all"), 3)}


def report_csv(rep: dict, fmt: str, lang: str) -> str:
    import csv
    import io
    from i18n import tr
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    head = [tr(lang, "rep.col_date")] if rep["group"] == "day" else []
    w.writerow(head + [tr(lang, "rep.col_ticket"), tr(lang, "rep.col_title"), tr(lang, "rep.col_project"),
                       tr(lang, "rep.col_time"), tr(lang, "rep.col_status")])
    comma = lang == "es"
    for r in rep["rows"]:
        value = f"{r['hours']:.2f}".replace(".", "," if comma else ".") if fmt == "decimal" else hm_text(r["seconds"])
        date_cell = [date.fromisoformat(r["date"]).strftime("%d/%m/%Y" if lang == "es" else "%Y-%m-%d")] \
            if rep["group"] == "day" else []
        w.writerow(date_cell + [_safe(r["key"] or "—"), _safe(r["title"]), _safe(r["project"]), value,
                                tr(lang, f"rep.booked_{r['booked']}")])
    return "﻿" + buf.getvalue()


def _safe(text: str) -> str:
    """Evita que Excel interprete un texto como fórmula (=, +, -, @)."""
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text
