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

from i18n import LANGUAGES, Translatable

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


class ValidationError(Translatable):
    """Datos incoherentes enviados por el usuario (HTTP 400). Código traducible."""


class Conflict(Translatable):
    """Acción no permitida en el estado actual de la jornada (HTTP 409)."""


MAX_BREAK_NOTE = 200


# ---------------------------------------------------------------- ajustes

PROFILES = ("normal", "friday", "summer")
PROFILE_NAMES = {"normal": "Horario normal", "friday": "Viernes intensivo",
                 "summer": "Intensivo de verano"}
PROFILE_FIELDS = ("start", "end", *TARGET_KEYS)
WEEKDAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MAX_PERIODS = 30

# Atajos de teclado: acción -> combinación «Ctrl+Alt+Shift+Meta+<KeyboardEvent.code>».
SHORTCUT_ACTIONS = ("start_day", "break_start", "break_end", "stop_day", "open_calendar",
                    "open_stats", "open_settings", "toggle_theme", "edit_today", "open_simulator")
DEFAULT_SHORTCUTS = {
    "start_day": "Alt+Shift+KeyI",
    "break_start": "Alt+Shift+KeyD",
    "break_end": "Alt+Shift+KeyV",
    "stop_day": "Alt+Shift+KeyF",
    "open_calendar": "Alt+Shift+KeyC",
    "open_stats": "Alt+Shift+KeyB",
    "open_settings": "Alt+Shift+KeyA",
    "toggle_theme": "Alt+Shift+KeyT",
    "edit_today": "Alt+Shift+KeyE",
    "open_simulator": "Alt+Shift+KeyS",
}
_MODIFIERS = ("Ctrl", "Alt", "Shift", "Meta")
_KEY_CODE_RE = re.compile(
    r"^(Key[A-Z]|Digit[0-9]|F([1-9]|1[0-2])|Arrow(Up|Down|Left|Right)|Space|Enter|Backspace|Delete|"
    r"Home|End|PageUp|PageDown|Insert|Minus|Equal|BracketLeft|BracketRight|Semicolon|Quote|"
    r"Backquote|Backslash|Comma|Period|Slash|IntlBackslash|Numpad[0-9]|NumpadAdd|NumpadSubtract|"
    r"NumpadMultiply|NumpadDivide|NumpadDecimal|NumpadEnter)$")


def valid_shortcut(combo: str) -> bool:
    """Modificadores en orden canónico, sin repetir, seguidos de un código de tecla."""
    if not isinstance(combo, str) or not combo:
        return False
    *mods, code = combo.split("+")
    order = [_MODIFIERS.index(m) for m in mods if m in _MODIFIERS]
    return (len(order) == len(mods) and order == sorted(set(order))
            and bool(_KEY_CODE_RE.match(code)))


# Apariencia (2.1)
ACCENTS = ("teal", "blue", "violet", "coral", "amber")
DENSITIES = ("comfortable", "compact")
MOTIONS = ("reduced", "normal", "expressive")
CARD_KEYS = ("quick_stats", "balance", "week", "holidays", "history")

# Tipos de día (2.1). Cómo computa cada uno lo decide el usuario:
#   "none"   → sin objetivo: no genera déficit y reduce el objetivo semanal.
#   "target" → conserva el objetivo: si no se trabaja, cuenta como déficit.
DAY_TYPES = ("holiday", "vacation", "dayoff", "permit", "sick", "custom")
DAY_TYPE_MODES = ("none", "target")
MAX_LABEL = 80

# Avisos (2.1): minutos antes de completar la jornada.
MAX_LEADS = 8
WEEKLY_GOAL_MODES = ("auto", "custom")
SETTINGS_VERSION = 3


def _profile(start, end, target, min_break, optional):
    return {"start": start, "end": end, "target_minutes": target,
            "min_break_minutes": min_break, "optional_break_minutes": optional}


def default_settings() -> dict:
    weekday = lambda workday, profile, mode="office": {  # noqa: E731
        "workday": workday, "profile": profile, "mode": mode}
    return {
        "version": SETTINGS_VERSION,
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
        "language": "es",
        "shortcuts": dict(DEFAULT_SHORTCUTS),
        "accent": "teal",
        "density": "comfortable",
        "motion": "normal",
        "cards": {key: True for key in CARD_KEYS},
        "weekly_goal": {"mode": "auto", "custom_minutes": 2400, "compensation": True},
        "day_types": {key: "none" for key in DAY_TYPES},
        "notifications": {
            "in_app": True, "desktop": False, "sound": False,
            "leads": [], "done": True,
            "break_pending": False, "break_pending_after": 300,
            "break_min_done": False, "break_over": False,
        },
    }


def _int_in_range(value, label, lo=0, hi=1440) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError("err.int_minutes", label=label)
    if isinstance(value, float) and value != number:
        raise ValidationError("err.int_minutes", label=label)
    if not lo <= number <= hi:
        raise ValidationError("err.range_minutes", label=label, lo=lo, hi=hi)
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


def _parse_date(value, label, **label_params) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValidationError("err.bad_date", label=label, value=value, **label_params)


def normalize_settings(raw: dict | None, base: dict | None = None) -> dict:
    """Combina `raw` sobre `base` (o los valores por defecto) y lo valida."""
    result = copy.deepcopy(base) if base else default_settings()
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ValidationError("err.bad_settings")
    raw = _migrate_v1(raw)

    for key, values in (raw.get("profiles") or {}).items():
        if key not in PROFILES or not isinstance(values, dict):
            continue
        profile = result["profiles"][key]
        label = f"@profile.{key}"
        for field in ("start", "end"):
            if field in values:
                parse_clock(values[field], label)
                profile[field] = _hhmm(values[field])
        for field in TARGET_KEYS:
            if field in values:
                profile[field] = _int_in_range(values[field], label)
        if parse_clock(profile["end"]) <= parse_clock(profile["start"]):
            raise ValidationError("err.ref_order", label=label)

    for key, values in (raw.get("weekdays") or {}).items():
        if key not in result["weekdays"] or not isinstance(values, dict):
            continue
        day = result["weekdays"][key]
        label = f"@weekday.{key}"
        if "workday" in values:
            day["workday"] = bool(values["workday"])
        if "profile" in values:
            if values["profile"] not in PROFILES:
                raise ValidationError("err.bad_profile_for", label=label)
            day["profile"] = values["profile"]
        if "mode" in values:
            if values["mode"] not in ("office", "remote"):
                raise ValidationError("err.bad_mode_for", label=label)
            day["mode"] = values["mode"]

    summer = raw.get("summer")
    if isinstance(summer, dict):
        if "periods" in summer:
            periods = summer["periods"] or []
            if not isinstance(periods, list) or len(periods) > MAX_PERIODS:
                raise ValidationError("err.bad_periods")
            clean = []
            for i, period in enumerate(periods, start=1):
                period = period if isinstance(period, dict) else {}
                first = _parse_date(period.get("start"), "@label.period_n", n=i)
                last = _parse_date(period.get("end"), "@label.period_n", n=i)
                if last < first:
                    raise ValidationError("err.period_order", n=i)
                clean.append({"start": first.isoformat(), "end": last.isoformat()})
            result["summer"]["periods"] = sorted(clean, key=lambda p: p["start"])
        if "weekdays" in summer:
            days = summer["weekdays"]
            if not isinstance(days, list) or any(d not in range(7) for d in days):
                raise ValidationError("err.bad_summer_days")
            result["summer"]["weekdays"] = sorted(set(days))

    for field, allowed in (("theme", THEMES), ("time_format", TIME_FORMATS),
                           ("duration_format", DURATION_FORMATS)):
        if field in raw:
            if raw[field] not in allowed:
                raise ValidationError("err.bad_value", field=field)
            result[field] = raw[field]

    if "language" in raw:
        if raw["language"] not in LANGUAGES:
            raise ValidationError("err.bad_language")
        result["language"] = raw["language"]

    shortcuts = raw.get("shortcuts")
    if isinstance(shortcuts, dict):
        for action, combo in shortcuts.items():
            if action not in SHORTCUT_ACTIONS:
                continue
            if combo in (None, ""):
                result["shortcuts"][action] = None
            elif valid_shortcut(combo):
                result["shortcuts"][action] = combo
            else:
                raise ValidationError("err.bad_shortcut", action=f"@sc.a.{action}")
    used = [c for c in result["shortcuts"].values() if c]
    for combo in used:
        if used.count(combo) > 1:
            raise ValidationError("err.dup_shortcut", combo=combo)

    for field, allowed in (("accent", ACCENTS), ("density", DENSITIES), ("motion", MOTIONS)):
        if field in raw:
            if raw[field] not in allowed:
                raise ValidationError("err.bad_value", field=field)
            result[field] = raw[field]

    cards = raw.get("cards")
    if cards is not None:
        if not isinstance(cards, dict):
            raise ValidationError("err.bad_value", field="cards")
        for key, value in cards.items():
            if key in CARD_KEYS:
                result["cards"][key] = bool(value)

    goal = raw.get("weekly_goal")
    if goal is not None:
        if not isinstance(goal, dict):
            raise ValidationError("err.bad_value", field="weekly_goal")
        if "mode" in goal:
            if goal["mode"] not in WEEKLY_GOAL_MODES:
                raise ValidationError("err.bad_value", field="weekly_goal.mode")
            result["weekly_goal"]["mode"] = goal["mode"]
        if "custom_minutes" in goal:
            result["weekly_goal"]["custom_minutes"] = _int_in_range(
                goal["custom_minutes"], "@label.weekly_goal", 0, 7 * 1440)
        if "compensation" in goal:
            result["weekly_goal"]["compensation"] = bool(goal["compensation"])

    types = raw.get("day_types")
    if types is not None:
        if not isinstance(types, dict):
            raise ValidationError("err.bad_value", field="day_types")
        for key, value in types.items():
            if key not in DAY_TYPES:
                continue
            if value not in DAY_TYPE_MODES:
                raise ValidationError("err.bad_value", field=f"day_types.{key}")
            result["day_types"][key] = value

    notes = raw.get("notifications")
    if notes is not None:
        if not isinstance(notes, dict):
            raise ValidationError("err.bad_value", field="notifications")
        target = result["notifications"]
        for key in ("in_app", "desktop", "sound", "done", "break_pending", "break_min_done", "break_over"):
            if key in notes:
                target[key] = bool(notes[key])
        if "break_pending_after" in notes:
            target["break_pending_after"] = _int_in_range(
                notes["break_pending_after"], "@label.break_pending_after", 15, 720)
        if "leads" in notes:
            leads = notes["leads"]
            if not isinstance(leads, list) or len(leads) > MAX_LEADS:
                raise ValidationError("err.bad_leads", max=MAX_LEADS)
            target["leads"] = sorted({_int_in_range(m, "@label.lead", 1, 480) for m in leads}, reverse=True)

    result["version"] = SETTINGS_VERSION
    return result


# ------------------------------------------------------------ horas y fechas

def parse_clock(value, label="@label.time", **label_params) -> time:
    """'HH:MM' o 'HH:MM:SS' -> time."""
    match = _TIME_RE.match(str(value).strip()) if value is not None else None
    if not match:
        raise ValidationError("err.bad_time", label=label, value=value, **label_params)
    hour, minute, second = match.groups()
    return time(int(hour), int(minute), int(second or 0))


def _hhmm(value) -> str:
    return parse_clock(value).strftime("%H:%M")


def combine(day: date, value, label="@label.time", **label_params) -> datetime:
    """Fecha + hora local de Madrid -> instante en UTC."""
    t = parse_clock(value, label, **label_params)
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


# ------------------------------------------------- calendario (tipos de día)
#
# calendar.json guarda los días especiales, separados de los fichajes:
#   {"version": 1,
#    "days": {"2026-12-08": {"type": "holiday", "label": "Inmaculada"}, ...},
#    "recurring": {"12-25": {"label": "Navidad"}, ...}}     ← festivos de cada año
# Un día concreto tiene prioridad sobre un festivo recurrente.

CALENDAR_VERSION = 1
MAX_CALENDAR_DAYS = 5000
_MD_RE = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


def default_calendar() -> dict:
    return {"version": CALENDAR_VERSION, "days": {}, "recurring": {}}


def clean_label(value) -> str:
    label = str(value or "").strip()
    if len(label) > MAX_LABEL:
        raise ValidationError("err.label_too_long", max=MAX_LABEL)
    return label


def valid_month_day(value) -> str:
    text = str(value or "")
    if not _MD_RE.match(text):
        raise ValidationError("err.bad_month_day", value=value)
    month, day = map(int, text.split("-"))
    if day > monthrange(2024, month)[1]:          # 2024 es bisiesto: admite el 29 de febrero
        raise ValidationError("err.bad_month_day", value=value)
    return text


def clean_mark(raw) -> dict:
    """Valida una marca de día: {"type", "label"?}."""
    if not isinstance(raw, dict) or raw.get("type") not in DAY_TYPES:
        raise ValidationError("err.bad_day_type")
    mark = {"type": raw["type"]}
    label = clean_label(raw.get("label"))
    if label:
        mark["label"] = label
    return mark


def normalize_calendar(raw) -> dict:
    """Valida calendar.json completo (al cargarlo o al restaurar una copia)."""
    if raw is None:
        return default_calendar()
    if not isinstance(raw, dict):
        raise ValidationError("err.bad_calendar")
    version = raw.get("version", CALENDAR_VERSION)
    if not isinstance(version, int) or not 1 <= version <= CALENDAR_VERSION:
        raise ValidationError("err.bad_calendar")
    days, recurring = raw.get("days") or {}, raw.get("recurring") or {}
    if not isinstance(days, dict) or not isinstance(recurring, dict) \
            or len(days) + len(recurring) > MAX_CALENDAR_DAYS:
        raise ValidationError("err.bad_calendar")
    result = default_calendar()
    for key, mark in days.items():
        result["days"][_parse_date(key, "@label.date").isoformat()] = clean_mark(mark)
    for key, item in recurring.items():
        if not isinstance(item, dict):
            raise ValidationError("err.bad_calendar")
        entry = {}
        label = clean_label(item.get("label"))
        if label:
            entry["label"] = label
        result["recurring"][valid_month_day(key)] = entry
    return result


def day_mark(day: date, calendar: dict | None) -> dict | None:
    """Marca que corresponde a un día (concreta o festivo recurrente), o None."""
    if not calendar:
        return None
    mark = calendar.get("days", {}).get(day.isoformat())
    if mark:
        return mark
    rec = calendar.get("recurring", {}).get(day.strftime("%m-%d"))
    if rec is not None:
        return {"type": "holiday", "recurring": True, **rec}
    return None


def mark_frees_day(mark: dict | None, settings: dict) -> bool:
    """¿Este tipo de día elimina el objetivo (según la configuración del usuario)?"""
    return bool(mark) and settings.get("day_types", {}).get(mark["type"], "none") == "none"


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


def snapshot_for(day: date, settings: dict, override: str | None = None, mark: dict | None = None) -> dict:
    """Perfil y objetivos que corresponden a una fecha según los ajustes actuales.

    `mark` (festivo, vacaciones…) solo se pasa cuando debe aplicarse: entonces un
    tipo configurado como «sin objetivo» deja el día sin objetivo.
    """
    weekday = settings["weekdays"][str(day.weekday())]
    key, source = resolve_profile(day, settings, override)
    profile = settings["profiles"][key]
    # Un día no laborable no tiene objetivo, salvo que se le asigne un perfil a mano.
    active = (weekday["workday"] or source == "manual") and not (
        source != "manual" and mark_frees_day(mark, settings))
    return {
        "profile": key,
        "profile_source": source,
        **{field: profile[field] if active else 0 for field in TARGET_KEYS},
        "ref_start": profile["start"],
        "ref_end": profile["end"],
        "mode": weekday["mode"],
    }


def new_record(day: date, settings: dict, calendar: dict | None = None) -> dict:
    """Jornada nueva. En un día marcado (festivo, vacaciones…) adopta las reglas de su tipo
    y lo anota en «day_type», para que la jornada conserve esa decisión."""
    mark = day_mark(day, calendar)
    record = {
        **snapshot_for(day, settings, mark=mark),
        "clock_in": None,
        "clock_out": None,
        "breaks": [],
        "notes": "",
        "custom_targets": False,
    }
    if mark:
        record["day_type"] = mark["type"]
    return record


def refresh_open_record(record: dict, day: date, settings: dict, calendar: dict | None = None) -> bool:
    """Aplica ajustes nuevos a una jornada aún abierta (no a las cerradas)."""
    if record.get("clock_out") or record.get("custom_targets"):
        return False
    override = record.get("profile") if record.get("profile_source") == "manual" else None
    # Solo se respeta el tipo de día que la propia jornada ya adoptó.
    mark = day_mark(day, calendar) if record.get("day_type") else None
    if mark and mark["type"] != record["day_type"]:
        mark = {"type": record["day_type"]}
    snap = snapshot_for(day, settings, override, mark)
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


def compute_day(day: date, record: dict | None, settings: dict, now: datetime,
                calendar: dict | None = None) -> dict:
    """Calcula el estado completo de una jornada en el instante `now`.

    Un día sin registro marcado como festivo, vacaciones… sigue las reglas de su
    tipo. Un día con registro usa los objetivos guardados en él (que ya reflejan
    el tipo si la jornada lo adoptó): marcar un día nunca reescribe el pasado.
    """
    now = now.astimezone(UTC)
    today = local_date(now)
    weekday = settings["weekdays"][str(day.weekday())]
    registered = record is not None
    mark = day_mark(day, calendar)
    auto = snapshot_for(day, settings)
    params = record if registered else (snapshot_for(day, settings, mark=mark) if mark else auto)

    mode = params.get("mode", "office")
    off = mode == "off"
    target = 0 if off else int(params.get("target_minutes", 0)) * 60
    min_break = 0 if off else int(params.get("min_break_minutes", 0)) * 60
    optional_break = 0 if off else int(params.get("optional_break_minutes", 0)) * 60

    clock_in = parse_ts(record["clock_in"]) if registered and record.get("clock_in") else None
    clock_out = parse_ts(record["clock_out"]) if registered and record.get("clock_out") else None
    raw_breaks = sorted((record.get("breaks", []) if registered else []),
                        key=lambda b: parse_ts(b["start"]))
    breaks = [(parse_ts(b["start"]), parse_ts(b["end"]) if b.get("end") else None) for b in raw_breaks]
    break_notes = [b.get("note", "") for b in raw_breaks]

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
    # Ausencia ya pasada de un tipo que conserva el objetivo: cuenta como déficit.
    absence_deficit = bool(mark and not registered and target and day < today and clock_in is None)
    if status == "finished":
        balance = worked - target
    elif in_progress:
        balance = extra
    elif absence_deficit:
        counted, balance = True, -float(target)
    else:
        balance = 0.0

    if absence_deficit:
        color = "red"
    elif clock_in is None:
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
            {"start": iso(s), "end": iso(e) if e else None, "note": note,
             "duration_s": r(max(0.0, seconds(s, e or end or s)))}
            for (s, e), note in zip(breaks, break_notes)
        ],
        "local": {
            "clock_in": local_clock(clock_in),
            "clock_out": local_clock(clock_out),
            "breaks": [{"start": local_clock(s), "end": local_clock(e), "note": note}
                       for (s, e), note in zip(breaks, break_notes)],
        },
        "has_notes": bool((record or {}).get("notes")) or any(break_notes),
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
        "deficit_s": r(remaining) if status == "finished" else (r(target) if absence_deficit else 0.0),
        "flags": flags,
        "day_type": mark["type"] if mark else (record or {}).get("day_type"),
        "day_label": (mark or {}).get("label", ""),
        "day_recurring": bool((mark or {}).get("recurring")),
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
        # Los pasados sin registrar no se cuentan (ni en objetivo ni en déficit),
        # salvo las ausencias configuradas para conservar el objetivo.
        if c["target_s"] and (has_clock or day >= today or c["counted"]):
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
                 now: datetime, calendar: dict | None = None) -> dict:
    """Valida una edición completa de jornada y devuelve el registro a guardar."""
    if not isinstance(payload, dict):
        raise ValidationError("err.bad_data")
    record = copy.deepcopy(existing) if existing else new_record(day, settings, calendar)
    limit = now.astimezone(UTC) + FUTURE_TOLERANCE

    mode = payload.get("mode", record.get("mode", "office"))
    if mode not in MODES:
        raise ValidationError("err.bad_mode")
    record["mode"] = mode

    notes = payload.get("notes", record.get("notes", "")) or ""
    if len(str(notes)) > MAX_NOTES:
        raise ValidationError("err.notes_too_long", max=MAX_NOTES)
    record["notes"] = str(notes)

    # Perfil: "" o None = automático (período de verano o semanal); si no, manual.
    # Un registro existente conserva su perfil (y sus objetivos) salvo que se elija otro.
    current = record.get("profile") if record.get("profile_source") == "manual" else None
    override = payload.get("profile", current) or None
    if override is not None and override not in PROFILES:
        raise ValidationError("err.bad_profile")
    profile_changed = existing is None or override != current
    applied = {"type": record["day_type"]} if record.get("day_type") else None
    snap = snapshot_for(day, settings, override, applied)
    previous = {key: record.get(key) for key in TARGET_KEYS}
    if profile_changed:
        # Nuevo perfil: se parte de sus valores (y de sus horas de referencia).
        for key in (*TARGET_KEYS, "ref_start", "ref_end", "profile", "profile_source"):
            record[key] = snap[key]

    labels = {"target_minutes": "@label.target", "min_break_minutes": "@label.min_break",
              "optional_break_minutes": "@label.opt_break"}
    for key in TARGET_KEYS:
        if key in payload:
            record[key] = _int_in_range(payload[key], labels[key])
    if profile_changed:
        record["custom_targets"] = any(record[k] != snap[k] for k in TARGET_KEYS)
    elif any(record[k] != previous[k] for k in TARGET_KEYS):
        record["custom_targets"] = True

    def stamp(value, label, **label_params):
        if value in (None, ""):
            return None
        return combine(day, value, label, **label_params)

    def current(key):
        return parse_ts(record[key]) if record.get(key) else None

    clock_in = stamp(payload["clock_in"], "@label.clock_in") if "clock_in" in payload else current("clock_in")
    clock_out = stamp(payload["clock_out"], "@label.clock_out") if "clock_out" in payload else current("clock_out")

    if "breaks" in payload:
        if not isinstance(payload["breaks"], list):
            raise ValidationError("err.bad_breaks")
        breaks = []
        for i, item in enumerate(payload["breaks"], start=1):
            item = item if isinstance(item, dict) else {}
            start = stamp(item.get("start"), "@label.break_start_n", n=i)
            stop = stamp(item.get("end"), "@label.break_end_n", n=i)
            note = _clean_note(item.get("note"))
            if start is None and stop is None:
                continue
            if start is None:
                raise ValidationError("err.break_no_start", n=i)
            breaks.append((start, stop, note))
    else:
        breaks = [(parse_ts(b["start"]), parse_ts(b["end"]) if b.get("end") else None, b.get("note", ""))
                  for b in record.get("breaks", [])]
    breaks.sort(key=lambda b: b[0])

    fmt = lambda dt: local_clock(dt)[:5]  # noqa: E731
    if clock_in is None and (clock_out or breaks):
        raise ValidationError("err.in_first")
    if clock_in and clock_out and clock_out <= clock_in:
        raise ValidationError("err.out_after_in")
    if clock_in and clock_in > limit:
        raise ValidationError("err.clock_in_future", time=fmt(clock_in))
    if clock_out and clock_out > limit:
        raise ValidationError("err.clock_out_future", time=fmt(clock_out))

    open_breaks = 0
    for i, (start, stop, _note) in enumerate(breaks, start=1):
        at = fmt(start)
        if start < clock_in:
            raise ValidationError("err.break_before_in", time=at)
        if start > limit or (stop and stop > limit):
            raise ValidationError("err.break_future", time=at)
        if stop is None:
            open_breaks += 1
            if clock_out:
                raise ValidationError("err.break_open_closed", time=at)
        else:
            if stop <= start:
                raise ValidationError("err.break_order", time=at)
            if clock_out and stop > clock_out:
                raise ValidationError("err.break_after_out", time=at)
        if clock_out and start >= clock_out:
            raise ValidationError("err.break_starts_after_out", time=at)
        if i < len(breaks):
            nxt = breaks[i][0]
            if stop is None or stop > nxt:
                raise ValidationError("err.break_overlap", time=at, next=fmt(nxt))
    if open_breaks > 1:
        raise ValidationError("err.one_open_break")

    record["clock_in"] = iso(clock_in) if clock_in else None
    record["clock_out"] = iso(clock_out) if clock_out else None
    record["breaks"] = [_break_dict(s, e, n) for s, e, n in breaks]
    return record


def _clean_note(value) -> str:
    note = str(value or "").strip()
    if len(note) > MAX_BREAK_NOTE:
        raise ValidationError("err.break_note_too_long", max=MAX_BREAK_NOTE)
    return note


def _break_dict(start, stop, note="") -> dict:
    item = {"start": iso(start), "end": iso(stop) if stop else None}
    if note:
        item["note"] = note
    return item


def set_note(record: dict, target, text) -> dict:
    """Cambia solo una nota (del día o de un descanso). Nunca toca los tiempos."""
    record = copy.deepcopy(record)
    if target == "day":
        text = str(text or "").strip()
        if len(text) > MAX_NOTES:
            raise ValidationError("err.notes_too_long", max=MAX_NOTES)
        record["notes"] = text
        return record
    try:
        index = int(target)
        item = record.get("breaks", [])[index]
    except (TypeError, ValueError, IndexError):
        raise ValidationError("err.bad_note_target")
    note = _clean_note(text)
    if note:
        item["note"] = note
    else:
        item.pop("note", None)
    return record


# ----------------------------------------------------------------- fichaje

ACTIONS = ("start", "break_start", "break_end", "stop", "resume")


def apply_action(action: str, day: date, record: dict | None, settings: dict,
                 now: datetime, calendar: dict | None = None) -> dict:
    """Aplica un botón de fichaje sobre la jornada de `day` con la hora `now`."""
    if action not in ACTIONS:
        raise ValidationError("err.unknown_action")
    now = now.astimezone(UTC).replace(microsecond=0)
    record = copy.deepcopy(record) if record else None
    status = compute_day(day, record, settings, now, calendar)["status"]
    stamp = iso(now)

    if action == "start":
        if record and record.get("clock_in"):
            if record.get("clock_out"):
                raise Conflict("conflict.finished")
            raise Conflict("conflict.started")
        record = record or new_record(day, settings, calendar)
        if record.get("mode") == "off":
            record["mode"] = settings["weekdays"][str(day.weekday())]["mode"]
        record["clock_in"] = stamp

    elif action == "break_start":
        if status != "working":
            raise Conflict("conflict.break_needs_work")
        record["breaks"].append({"start": stamp, "end": None})

    elif action == "break_end":
        if status != "on_break":
            raise Conflict("conflict.no_break")
        open_break = next(b for b in record["breaks"] if not b.get("end"))
        if now > parse_ts(open_break["start"]):
            open_break["end"] = stamp
        else:
            record["breaks"].remove(open_break)

    elif action == "stop":
        if status not in ("working", "on_break"):
            raise Conflict("conflict.nothing_to_stop")
        for b in record["breaks"]:
            if not b.get("end"):
                b["end"] = stamp
        if now <= parse_ts(record["clock_in"]):
            raise Conflict("err.out_after_in")
        record["breaks"] = [b for b in record["breaks"] if parse_ts(b["end"]) > parse_ts(b["start"])]
        record["clock_out"] = stamp

    elif action == "resume":
        if status != "finished":
            raise Conflict("conflict.resume_only_finished")
        clock_out = parse_ts(record["clock_out"])
        if now > clock_out:
            # El tiempo fuera se registra como descanso para no duplicar trabajo.
            record["breaks"].append({"start": record["clock_out"], "end": stamp})
        record["clock_out"] = None

    return record
