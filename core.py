"""Lógica de jornadas: cálculos, validación, fichajes y estadísticas.

Módulo puro (sin Flask ni disco) para poder probarlo de forma aislada.
Todas las operaciones con instantes se hacen en UTC; Europe/Madrid solo se
usa para interpretar las horas que escribe el usuario y para mostrarlas.
Así los cambios de horario de verano/invierno no alteran las duraciones.
"""
from __future__ import annotations

import copy
import re
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone

from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")
UTC = timezone.utc

MODES = ("office", "remote", "off")
THEMES = ("system", "light", "dark")
TIME_FORMATS = ("24h", "12h")
DURATION_FORMATS = ("hms", "hm")
TARGET_KEYS = ("target_minutes", "min_break_minutes", "optional_break_minutes")
FUTURE_TOLERANCE = timedelta(seconds=60)
MAX_NOTES = 2000

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$")


class ValidationError(ValueError):
    """Datos incoherentes enviados por el usuario (HTTP 400)."""


class Conflict(ValueError):
    """Acción no permitida en el estado actual de la jornada (HTTP 409)."""


# ---------------------------------------------------------------- ajustes

PROFILES = ("normal", "friday", "summer")
PROFILE_NAMES = {"normal": "Horario normal", "friday": "Viernes intensivo",
                 "summer": "Intensivo de verano"}
PROFILE_FIELDS = ("start", "end", *TARGET_KEYS)
WEEKDAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MAX_PERIODS = 30


def _profile(start, end, target, min_break, optional):
    return {"start": start, "end": end, "target_minutes": target,
            "min_break_minutes": min_break, "optional_break_minutes": optional}


def default_settings() -> dict:
    weekday = lambda workday, profile, mode="office": {  # noqa: E731
        "workday": workday, "profile": profile, "mode": mode}
    return {
        "version": 2,
        "profiles": {
            "normal": _profile("08:00", "18:00", 510, 60, 30),
            "friday": _profile("08:00", "15:00", 420, 0, 0),
            "summer": _profile("08:00", "15:00", 420, 0, 0),
        },
        "weekdays": {
            "0": weekday(True, "normal"),
            "1": weekday(True, "normal"),
            "2": weekday(True, "normal", "remote"),
            "3": weekday(True, "normal"),
            "4": weekday(True, "friday"),
            "5": weekday(False, "normal"),
            "6": weekday(False, "normal"),
        },
        # Intensivo de verano por fechas (ambos extremos incluidos).
        "summer": {"periods": [], "weekdays": [0, 1, 2, 3, 4]},
        "theme": "system",
        "time_format": "24h",
        "duration_format": "hms",
    }


def _int_in_range(value, label, lo=0, hi=1440) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label}: debe ser un número entero de minutos.")
    if isinstance(value, float) and value != number:
        raise ValidationError(f"{label}: debe ser un número entero de minutos.")
    if not lo <= number <= hi:
        raise ValidationError(f"{label}: debe estar entre {lo} y {hi} minutos.")
    return number


def _migrate_v1(raw: dict) -> dict:
    """Ajustes de la versión 1 (horario por día de la semana) -> perfiles."""
    weekdays = raw.get("weekdays") or {}
    if "profiles" in raw or not any(isinstance(w, dict) and "target_minutes" in w
                                    for w in weekdays.values()):
        return raw
    profiles = {}
    for name, keys in (("normal", ("0", "1", "2", "3")), ("friday", ("4",))):
        source = next((weekdays[k] for k in keys
                       if isinstance(weekdays.get(k), dict) and weekdays[k].get("workday", True)
                       and "target_minutes" in weekdays[k]), None)
        if source:
            profiles[name] = {f: source[f] for f in PROFILE_FIELDS if f in source}
    migrated = {k: {"workday": w.get("workday", True), "mode": w.get("mode", "office"),
                    "profile": "friday" if k == "4" else "normal"}
                for k, w in weekdays.items() if isinstance(w, dict)}
    return {**raw, "profiles": profiles, "weekdays": migrated}


def _parse_date(value, label) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValidationError(f"{label}: «{value}» no es una fecha válida.")


def normalize_settings(raw: dict | None, base: dict | None = None) -> dict:
    """Combina `raw` sobre `base` (o los valores por defecto) y lo valida."""
    result = copy.deepcopy(base) if base else default_settings()
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ValidationError("Formato de ajustes no válido.")
    raw = _migrate_v1(raw)

    for key, values in (raw.get("profiles") or {}).items():
        if key not in PROFILES or not isinstance(values, dict):
            continue
        profile = result["profiles"][key]
        label = PROFILE_NAMES[key]
        for field in ("start", "end"):
            if field in values:
                parse_clock(values[field], f"{label}: hora de referencia")
                profile[field] = _hhmm(values[field])
        for field in TARGET_KEYS:
            if field in values:
                profile[field] = _int_in_range(values[field], label)
        if parse_clock(profile["end"]) <= parse_clock(profile["start"]):
            raise ValidationError(f"{label}: la salida de referencia debe ser posterior a la entrada.")

    for key, values in (raw.get("weekdays") or {}).items():
        if key not in result["weekdays"] or not isinstance(values, dict):
            continue
        day = result["weekdays"][key]
        label = WEEKDAY_NAMES[int(key)]
        if "workday" in values:
            day["workday"] = bool(values["workday"])
        if "profile" in values:
            if values["profile"] not in PROFILES:
                raise ValidationError(f"{label}: perfil no válido.")
            day["profile"] = values["profile"]
        if "mode" in values:
            if values["mode"] not in ("office", "remote"):
                raise ValidationError(f"{label}: modalidad no válida.")
            day["mode"] = values["mode"]

    summer = raw.get("summer")
    if isinstance(summer, dict):
        if "periods" in summer:
            periods = summer["periods"] or []
            if not isinstance(periods, list) or len(periods) > MAX_PERIODS:
                raise ValidationError("Lista de períodos de verano no válida.")
            clean = []
            for i, period in enumerate(periods, start=1):
                period = period if isinstance(period, dict) else {}
                first = _parse_date(period.get("start"), f"Período {i}, inicio")
                last = _parse_date(period.get("end"), f"Período {i}, fin")
                if last < first:
                    raise ValidationError(f"Período {i}: la fecha de fin es anterior a la de inicio.")
                clean.append({"start": first.isoformat(), "end": last.isoformat()})
            result["summer"]["periods"] = sorted(clean, key=lambda p: p["start"])
        if "weekdays" in summer:
            days = summer["weekdays"]
            if not isinstance(days, list) or any(d not in range(7) for d in days):
                raise ValidationError("Días del horario de verano no válidos.")
            result["summer"]["weekdays"] = sorted(set(days))

    for field, allowed in (("theme", THEMES), ("time_format", TIME_FORMATS),
                           ("duration_format", DURATION_FORMATS)):
        if field in raw:
            if raw[field] not in allowed:
                raise ValidationError(f"Valor no válido para {field}.")
            result[field] = raw[field]
    result["version"] = 2
    return result


# ------------------------------------------------------------ horas y fechas

def parse_clock(value, label="Hora") -> time:
    """'HH:MM' o 'HH:MM:SS' -> time."""
    match = _TIME_RE.match(str(value).strip()) if value is not None else None
    if not match:
        raise ValidationError(f"{label}: «{value}» no es una hora válida (HH:MM).")
    hour, minute, second = match.groups()
    return time(int(hour), int(minute), int(second or 0))


def _hhmm(value) -> str:
    return parse_clock(value).strftime("%H:%M")


def combine(day: date, value, label="Hora") -> datetime:
    """Fecha + hora local de Madrid -> instante en UTC."""
    t = parse_clock(value, label)
    local = datetime(day.year, day.month, day.day, t.hour, t.minute, t.second, tzinfo=TZ)
    return local.astimezone(UTC)


def parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(UTC)


def iso(dt: datetime) -> str:
    """Instante -> ISO 8601 con desfase de Madrid (legible en el JSON)."""
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def local_clock(dt: datetime | None) -> str | None:
    return dt.astimezone(TZ).strftime("%H:%M:%S") if dt else None


def local_date(now: datetime) -> date:
    return now.astimezone(TZ).date()


def seconds(a: datetime, b: datetime) -> float:
    return (b.astimezone(UTC) - a.astimezone(UTC)).total_seconds()


def week_dates(day: date) -> list[date]:
    monday = day - timedelta(days=day.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def month_dates(year: int, month: int) -> list[date]:
    return [date(year, month, d) for d in range(1, monthrange(year, month)[1] + 1)]


# --------------------------------------------------------------- registros

def resolve_profile(day: date, settings: dict, override: str | None = None) -> tuple[str, str]:
    """Perfil de un día. Prioridad: manual > período de verano > semanal."""
    if override in PROFILES:
        return override, "manual"
    weekday = settings["weekdays"][str(day.weekday())]
    summer = settings["summer"]
    key = day.isoformat()
    if (weekday["workday"] and day.weekday() in summer["weekdays"]
            and any(p["start"] <= key <= p["end"] for p in summer["periods"])):
        return "summer", "period"
    return weekday["profile"], "weekly"


def snapshot_for(day: date, settings: dict, override: str | None = None) -> dict:
    """Perfil y objetivos que corresponden a una fecha según los ajustes actuales."""
    weekday = settings["weekdays"][str(day.weekday())]
    key, source = resolve_profile(day, settings, override)
    profile = settings["profiles"][key]
    # Un día no laborable no tiene objetivo, salvo que se le asigne un perfil a mano.
    active = weekday["workday"] or source == "manual"
    return {
        "profile": key,
        "profile_source": source,
        **{field: profile[field] if active else 0 for field in TARGET_KEYS},
        "ref_start": profile["start"],
        "ref_end": profile["end"],
        "mode": weekday["mode"],
    }


def new_record(day: date, settings: dict) -> dict:
    return {
        **snapshot_for(day, settings),
        "clock_in": None,
        "clock_out": None,
        "breaks": [],
        "notes": "",
        "custom_targets": False,
    }


def refresh_open_record(record: dict, day: date, settings: dict) -> bool:
    """Aplica ajustes nuevos a una jornada aún abierta (no a las cerradas)."""
    if record.get("clock_out") or record.get("custom_targets"):
        return False
    override = record.get("profile") if record.get("profile_source") == "manual" else None
    snap = snapshot_for(day, settings, override)
    changed = False
    for key in (*TARGET_KEYS, "ref_start", "ref_end", "profile", "profile_source"):
        if record.get(key) != snap[key]:
            record[key] = snap[key]
            changed = True
    return changed


# ---------------------------------------------------------------- cálculo

def _completion_instant(clock_in, breaks, end, target) -> datetime | None:
    """Instante en que el trabajo acumulado alcanza `target` segundos."""
    acc, cursor = 0.0, clock_in
    for start, stop in [*breaks, (end, end)]:
        segment_end = min(start, end)
        if segment_end > cursor:
            span = seconds(cursor, segment_end)
            if acc + span >= target:
                return cursor + timedelta(seconds=target - acc)
            acc += span
        cursor = max(cursor, min(stop or end, end))
    return None


def compute_day(day: date, record: dict | None, settings: dict, now: datetime) -> dict:
    """Calcula el estado completo de una jornada en el instante `now`."""
    now = now.astimezone(UTC)
    today = local_date(now)
    weekday = settings["weekdays"][str(day.weekday())]
    registered = record is not None
    auto = snapshot_for(day, settings)
    params = record if registered else auto

    mode = params.get("mode", "office")
    off = mode == "off"
    target = 0 if off else int(params.get("target_minutes", 0)) * 60
    min_break = 0 if off else int(params.get("min_break_minutes", 0)) * 60
    optional_break = 0 if off else int(params.get("optional_break_minutes", 0)) * 60

    clock_in = parse_ts(record["clock_in"]) if registered and record.get("clock_in") else None
    clock_out = parse_ts(record["clock_out"]) if registered and record.get("clock_out") else None
    breaks = sorted(
        ((parse_ts(b["start"]), parse_ts(b["end"]) if b.get("end") else None)
         for b in (record.get("breaks", []) if registered else [])),
        key=lambda item: item[0],
    )

    worked = break_total = current_break = 0.0
    current_break_start = None
    end = None
    flags = []

    if clock_in is None:
        if registered and off:
            status = "off"
        elif not registered and not weekday["workday"]:
            status = "nonworking"
        elif day > today:
            status = "future"
        elif day == today:
            status = "not_started"
        else:
            status = "none"
    else:
        open_break = next((b for b in breaks if b[1] is None), None)
        if clock_out is not None:
            end, status = clock_out, "finished"
        elif day == today:
            end = max(now, clock_in)
            status = "on_break" if open_break else "working"
        else:
            # Jornada pasada sin salida: se cuenta hasta la última marca conocida.
            stamps = [clock_in] + [t for b in breaks for t in b if t is not None]
            end, status = max(stamps), "unclosed"
            flags.append("unclosed")

        for start, stop in breaks:
            s = max(start, clock_in)
            e = min(stop or end, end)
            if e > s:
                break_total += seconds(s, e)
        if status == "on_break":
            current_break_start = open_break[0]
            current_break = max(0.0, seconds(open_break[0], end))
        worked = max(0.0, seconds(clock_in, end) - break_total)

    in_progress = status in ("working", "on_break")
    remaining = max(0.0, target - worked)
    extra = max(0.0, worked - target)
    pending_break = max(0.0, min_break - break_total) if target else 0.0

    exit_at = exit_min_at = exit_optional_at = completed_at = None
    if in_progress:
        exit_min_at = now + timedelta(seconds=remaining)
        exit_at = exit_min_at + timedelta(seconds=pending_break)
        exit_optional_at = exit_min_at + timedelta(
            seconds=max(0.0, min_break + optional_break - break_total) if target else 0.0)
    elif status == "not_started" and target:
        exit_min_at = now + timedelta(seconds=target)
        exit_at = exit_min_at + timedelta(seconds=min_break)
        exit_optional_at = exit_min_at + timedelta(seconds=min_break + optional_break)
    elif status == "finished":
        exit_at = clock_out
    if clock_in is not None and target and worked >= target:
        completed_at = _completion_instant(clock_in, breaks, end, target)

    if clock_in is not None and target and status in ("finished", "unclosed") and break_total < min_break:
        flags.append("break_short")
    if clock_in is not None and target and break_total > min_break + optional_break:
        flags.append("break_long")

    # Balance: solo cuenta lo cerrado. Una jornada en curso aporta su tiempo
    # extra, pero lo que le falta es "pendiente", no déficit.
    counted = status == "finished" or in_progress
    if status == "finished":
        balance = worked - target
    elif in_progress:
        balance = extra
    else:
        balance = 0.0

    if clock_in is None:
        color = "gray"
    elif status == "finished":
        color = "green" if worked >= target else "red"
    elif in_progress:
        color = "green" if worked >= target else "yellow"
    else:
        color = "yellow"

    r = lambda x: round(x, 3)  # noqa: E731
    return {
        "date": day.isoformat(),
        "weekday": day.weekday(),
        "registered": registered,
        "workday": weekday["workday"],
        "mode": mode,
        "status": status,
        "color": color,
        "clock_in": iso(clock_in) if clock_in else None,
        "clock_out": iso(clock_out) if clock_out else None,
        "breaks": [
            {"start": iso(s), "end": iso(e) if e else None,
             "duration_s": r(max(0.0, seconds(s, e or end or s)))}
            for s, e in breaks
        ],
        "local": {
            "clock_in": local_clock(clock_in),
            "clock_out": local_clock(clock_out),
            "breaks": [{"start": local_clock(s), "end": local_clock(e)} for s, e in breaks],
        },
        "target_s": target,
        "target_minutes": int(params.get("target_minutes", 0)),
        "min_break_s": min_break,
        "optional_break_s": optional_break,
        "min_break_minutes": int(params.get("min_break_minutes", 0)),
        "optional_break_minutes": int(params.get("optional_break_minutes", 0)),
        "ref_start": params.get("ref_start"),
        "ref_end": params.get("ref_end"),
        "profile": params.get("profile"),
        "profile_source": params.get("profile_source"),
        "auto": {k: auto[k] for k in ("profile", "profile_source", *TARGET_KEYS)},
        "worked_s": r(worked),
        "break_s": r(break_total),
        "current_break_s": r(current_break),
        "current_break_start": iso(current_break_start) if current_break_start else None,
        "remaining_s": r(remaining),
        "extra_s": r(extra),
        "pending_break_s": r(pending_break),
        "progress": r(min(1.0, worked / target)) if target else (1.0 if clock_in else 0.0),
        "exit_at": iso(exit_at) if exit_at else None,
        "exit_min_at": iso(exit_min_at) if exit_min_at else None,
        "exit_optional_at": iso(exit_optional_at) if exit_optional_at else None,
        "completed_at": iso(completed_at) if completed_at else None,
        "counted": counted,
        "balance_s": r(balance),
        "pending_s": r(remaining) if in_progress else 0.0,
        "deficit_s": r(remaining) if status == "finished" else 0.0,
        "flags": flags,
        "notes": (record or {}).get("notes", ""),
        "custom_targets": bool((record or {}).get("custom_targets")),
    }


def summarize(days: list[dict], now: datetime) -> dict:
    """Totales de un conjunto de días ya calculados (semana o mes)."""
    today = local_date(now)
    worked = target = balance = pending = 0.0
    completed = worked_days = 0
    for c in days:
        day = date.fromisoformat(c["date"])
        has_clock = c["clock_in"] is not None
        if has_clock:
            worked += c["worked_s"]
            worked_days += 1
            if c["target_s"] and c["worked_s"] >= c["target_s"]:
                completed += 1
        # Objetivo: días fichados + días laborables que aún no han llegado.
        # Los pasados sin registrar no se cuentan (ni en objetivo ni en déficit).
        if c["target_s"] and (has_clock or day >= today):
            target += c["target_s"]
        if c["counted"]:
            balance += c["balance_s"]
        pending += c["pending_s"]
    return {
        "worked_s": round(worked, 3),
        "target_s": round(target, 3),
        "balance_s": round(balance, 3),
        "pending_s": round(pending, 3),
        "completed_days": completed,
        "worked_days": worked_days,
        "average_s": round(worked / worked_days, 3) if worked_days else 0.0,
    }


# ------------------------------------------------------- edición manual

def build_record(day: date, payload: dict, existing: dict | None, settings: dict,
                 now: datetime) -> dict:
    """Valida una edición completa de jornada y devuelve el registro a guardar."""
    if not isinstance(payload, dict):
        raise ValidationError("Datos no válidos.")
    record = copy.deepcopy(existing) if existing else new_record(day, settings)
    limit = now.astimezone(UTC) + FUTURE_TOLERANCE

    mode = payload.get("mode", record.get("mode", "office"))
    if mode not in MODES:
        raise ValidationError("Modalidad no válida.")
    record["mode"] = mode

    notes = payload.get("notes", record.get("notes", "")) or ""
    if len(str(notes)) > MAX_NOTES:
        raise ValidationError(f"Las observaciones no pueden superar {MAX_NOTES} caracteres.")
    record["notes"] = str(notes)

    # Perfil: "" o None = automático (período de verano o semanal); si no, manual.
    # Un registro existente conserva su perfil (y sus objetivos) salvo que se elija otro.
    current = record.get("profile") if record.get("profile_source") == "manual" else None
    override = payload.get("profile", current) or None
    if override is not None and override not in PROFILES:
        raise ValidationError("Perfil no válido.")
    profile_changed = existing is None or override != current
    snap = snapshot_for(day, settings, override)
    previous = {key: record.get(key) for key in TARGET_KEYS}
    if profile_changed:
        # Nuevo perfil: se parte de sus valores (y de sus horas de referencia).
        for key in (*TARGET_KEYS, "ref_start", "ref_end", "profile", "profile_source"):
            record[key] = snap[key]

    labels = {"target_minutes": "Horas objetivo", "min_break_minutes": "Descanso mínimo",
              "optional_break_minutes": "Descanso opcional"}
    for key in TARGET_KEYS:
        if key in payload:
            record[key] = _int_in_range(payload[key], labels[key])
    if profile_changed:
        record["custom_targets"] = any(record[k] != snap[k] for k in TARGET_KEYS)
    elif any(record[k] != previous[k] for k in TARGET_KEYS):
        record["custom_targets"] = True

    def stamp(value, label):
        if value in (None, ""):
            return None
        return combine(day, value, label)

    def current(key):
        return parse_ts(record[key]) if record.get(key) else None

    clock_in = stamp(payload["clock_in"], "Entrada") if "clock_in" in payload else current("clock_in")
    clock_out = stamp(payload["clock_out"], "Salida") if "clock_out" in payload else current("clock_out")

    if "breaks" in payload:
        if not isinstance(payload["breaks"], list):
            raise ValidationError("Formato de descansos no válido.")
        breaks = []
        for i, item in enumerate(payload["breaks"], start=1):
            item = item or {}
            start = stamp(item.get("start"), f"Inicio del descanso {i}")
            stop = stamp(item.get("end"), f"Fin del descanso {i}")
            if start is None and stop is None:
                continue
            if start is None:
                raise ValidationError(f"El descanso {i} no tiene hora de inicio.")
            breaks.append((start, stop))
    else:
        breaks = [(parse_ts(b["start"]), parse_ts(b["end"]) if b.get("end") else None)
                  for b in record.get("breaks", [])]
    breaks.sort(key=lambda b: b[0])

    fmt = lambda dt: local_clock(dt)[:5]  # noqa: E731
    if clock_in is None and (clock_out or breaks):
        raise ValidationError("Indica la hora de entrada antes de la salida o los descansos.")
    if clock_in and clock_out and clock_out <= clock_in:
        raise ValidationError("La salida debe ser posterior a la entrada.")
    for stamp_value, label in ((clock_in, "La entrada"), (clock_out, "La salida")):
        if stamp_value and stamp_value > limit:
            raise ValidationError(f"{label} ({fmt(stamp_value)}) está en el futuro.")

    open_breaks = 0
    for i, (start, stop) in enumerate(breaks, start=1):
        where = f"El descanso de las {fmt(start)}"
        if start < clock_in:
            raise ValidationError(f"{where} empieza antes de la entrada.")
        if start > limit or (stop and stop > limit):
            raise ValidationError(f"{where} está en el futuro.")
        if stop is None:
            open_breaks += 1
            if clock_out:
                raise ValidationError(f"{where} no tiene fin y la jornada está cerrada.")
        else:
            if stop <= start:
                raise ValidationError(f"{where} debe terminar después de empezar.")
            if clock_out and stop > clock_out:
                raise ValidationError(f"{where} termina después de la salida.")
        if clock_out and start >= clock_out:
            raise ValidationError(f"{where} empieza después de la salida.")
        if i < len(breaks):
            nxt = breaks[i][0]
            if stop is None or stop > nxt:
                raise ValidationError(f"{where} se solapa con el de las {fmt(nxt)}.")
    if open_breaks > 1:
        raise ValidationError("Solo puede haber un descanso abierto.")

    record["clock_in"] = iso(clock_in) if clock_in else None
    record["clock_out"] = iso(clock_out) if clock_out else None
    record["breaks"] = [{"start": iso(s), "end": iso(e) if e else None} for s, e in breaks]
    return record


# ----------------------------------------------------------------- fichaje

ACTIONS = ("start", "break_start", "break_end", "stop", "resume")


def apply_action(action: str, day: date, record: dict | None, settings: dict,
                 now: datetime) -> dict:
    """Aplica un botón de fichaje sobre la jornada de `day` con la hora `now`."""
    if action not in ACTIONS:
        raise ValidationError("Acción desconocida.")
    now = now.astimezone(UTC).replace(microsecond=0)
    record = copy.deepcopy(record) if record else None
    status = compute_day(day, record, settings, now)["status"]
    stamp = iso(now)

    if action == "start":
        if record and record.get("clock_in"):
            if record.get("clock_out"):
                raise Conflict("La jornada de hoy ya está finalizada. Usa «Reanudar jornada».")
            raise Conflict("La jornada de hoy ya está iniciada.")
        record = record or new_record(day, settings)
        if record.get("mode") == "off":
            record["mode"] = settings["weekdays"][str(day.weekday())]["mode"]
        record["clock_in"] = stamp

    elif action == "break_start":
        if status != "working":
            raise Conflict("Solo puedes iniciar un descanso mientras estás trabajando.")
        record["breaks"].append({"start": stamp, "end": None})

    elif action == "break_end":
        if status != "on_break":
            raise Conflict("No hay ningún descanso en curso.")
        open_break = next(b for b in record["breaks"] if not b.get("end"))
        if now > parse_ts(open_break["start"]):
            open_break["end"] = stamp
        else:
            record["breaks"].remove(open_break)

    elif action == "stop":
        if status not in ("working", "on_break"):
            raise Conflict("No hay ninguna jornada en curso que finalizar.")
        for b in record["breaks"]:
            if not b.get("end"):
                b["end"] = stamp
        if now <= parse_ts(record["clock_in"]):
            raise Conflict("La salida debe ser posterior a la entrada.")
        record["breaks"] = [b for b in record["breaks"] if parse_ts(b["end"]) > parse_ts(b["start"])]
        record["clock_out"] = stamp

    elif action == "resume":
        if status != "finished":
            raise Conflict("Solo se puede reanudar una jornada finalizada hoy.")
        clock_out = parse_ts(record["clock_out"])
        if now > clock_out:
            # El tiempo fuera se registra como descanso para no duplicar trabajo.
            record["breaks"].append({"start": record["clock_out"], "end": stamp})
        record["clock_out"] = None

    return record
