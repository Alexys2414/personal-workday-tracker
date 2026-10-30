"""Simulador, objetivo semanal y estadísticas avanzadas (Jornada 2.1).

Módulo puro, como core: no toca disco ni Flask. Nada de lo que hay aquí
escribe registros. Todos los resultados salen de core.compute_day y
core.summarize, así que siguen exactamente las mismas reglas que el panel.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import core
from core import ValidationError

MAX_SIM_BREAK = 600          # minutos
MAX_STATS_WEEKS = 52


# ------------------------------------------------------------- simulador

def _minutes(value, label, lo, hi) -> int:
    return core._int_in_range(value, label, lo, hi)


def _scenario(day: date, clock_in: datetime, target_s: int, min_break_s: int, optional_s: int,
              taken_s: float, use_optional: bool, settings: dict, exit_at: datetime | None) -> dict:
    """Jornada hipotética cerrada, calculada con core.compute_day.

    Si no se fija la salida, se calcula como el panel: trabajo objetivo más el
    descanso que falte para cumplir el mínimo (y el opcional si se pide).
    """
    required = min_break_s + (optional_s if use_optional else 0) if target_s else 0
    pause = max(taken_s, required)
    added = pause - taken_s                  # descanso obligatorio aún no hecho que se da por hecho
    if exit_at is None:
        exit_at = clock_in + timedelta(seconds=target_s + pause)
    span = core.seconds(clock_in, exit_at)
    if span <= 0:
        raise ValidationError("err.out_after_in")
    pause = min(pause, span)
    # El descanso se coloca en mitad de la jornada (solo importa su duración).
    break_start = clock_in + timedelta(seconds=(span - pause) / 2)
    breaks = [{"start": core.iso(break_start),
               "end": core.iso(break_start + timedelta(seconds=pause))}] if pause >= 1 else []
    record = {
        "mode": "office", "profile": None, "profile_source": "manual",
        "target_minutes": target_s // 60, "min_break_minutes": min_break_s // 60,
        "optional_break_minutes": optional_s // 60,
        "clock_in": core.iso(clock_in), "clock_out": core.iso(exit_at), "breaks": breaks,
    }
    c = core.compute_day(day, record, settings, exit_at)
    return {
        "clock_in": c["clock_in"],
        "exit": c["clock_out"],
        "local_in": c["local"]["clock_in"][:5],
        "local_exit": c["local"]["clock_out"][:5],
        "worked_s": c["worked_s"],
        "break_s": c["break_s"],
        "added_break_s": round(min(added, pause), 3),
        "target_s": c["target_s"],
        "balance_s": c["balance_s"],
        "flags": c["flags"],
        "span_s": round(span, 3),
        "break_offset_s": round(core.seconds(clock_in, break_start), 3) if breaks else None,
    }


def simulate(day: date, record: dict | None, settings: dict, now: datetime,
             params: dict | None = None, calendar: dict | None = None) -> dict:
    """Compara la jornada prevista con una variante hipotética. No modifica nada.

    params (todos opcionales):
      clock_in "HH:MM"      hora de entrada (por defecto, la real o la de referencia)
      target_minutes        horas objetivo
      breaks_minutes        descanso ya realizado
      extra_break_minutes   descanso adicional simulado
      use_optional          contar el descanso opcional completo
      exit "HH:MM"          salida deseada (si falta, se calcula)
    """
    params = params if isinstance(params, dict) else {}
    real = core.compute_day(day, record, settings, now, calendar)
    real_in = core.parse_ts(real["clock_in"]) if real["clock_in"] else None
    ref_in = core.combine(day, real["ref_start"] or "08:00")

    target_s = real["target_s"]
    min_b, opt_b = real["min_break_s"], real["optional_break_s"]

    # Base: lo que ocurrirá si sigo como voy (o lo que ocurrió, si ya cerré).
    base_in = real_in or ref_in
    if real["status"] == "finished":
        base = _scenario(day, base_in, target_s, min_b, opt_b, real["break_s"], False, settings,
                         core.parse_ts(real["clock_out"]))
    else:
        base = _scenario(day, base_in, target_s, min_b, opt_b, real["break_s"], False, settings, None)

    sim_target = _minutes(params["target_minutes"], "@label.target", 0, 1440) * 60 \
        if params.get("target_minutes") not in (None, "") else target_s
    sim_in = core.combine(day, params["clock_in"], "@label.clock_in") if params.get("clock_in") else base_in
    taken = _minutes(params["breaks_minutes"], "@label.sim_breaks", 0, 900) * 60 \
        if params.get("breaks_minutes") not in (None, "") else real["break_s"]
    extra = _minutes(params.get("extra_break_minutes") or 0, "@label.sim_extra", 0, MAX_SIM_BREAK) * 60
    exit_at = core.combine(day, params["exit"], "@label.clock_out") if params.get("exit") else None
    use_optional = bool(params.get("use_optional"))
    sim = _scenario(day, sim_in, sim_target, min_b, opt_b, taken + extra, use_optional, settings, exit_at)

    diff = {
        "exit_s": round(core.seconds(core.parse_ts(base["exit"]), core.parse_ts(sim["exit"])), 3),
        "worked_s": round(sim["worked_s"] - base["worked_s"], 3),
        "balance_s": round(sim["balance_s"] - base["balance_s"], 3),
        "break_s": round(sim["break_s"] - base["break_s"], 3),
    }
    return {
        "date": day.isoformat(),
        "status": real["status"],
        "defaults": {
            "clock_in": core.local_clock(base_in)[:5],
            "target_minutes": target_s // 60,
            "breaks_minutes": int(real["break_s"] // 60),
            "min_break_minutes": min_b // 60,
            "optional_break_minutes": opt_b // 60,
            "real_clock_in": bool(real_in),
        },
        "base": base,
        "sim": sim,
        "diff": diff,
        "readonly": True,
    }


# -------------------------------------------------------- objetivo semanal

def _computed(dates, days, settings, now, calendar):
    return [core.compute_day(d, days.get(d.isoformat()), settings, now, calendar) for d in dates]


def weekly_goal(day: date, days: dict, settings: dict, now: datetime, calendar: dict | None = None) -> dict:
    """Objetivo de la semana de `day`, horas hechas y balance de jornadas cerradas.

    · Automático: suma de los objetivos de cada día (perfil, jornada guardada o tipo de día).
    · Personalizado: la cifra elegida, menos lo que dejan sin objetivo festivos y vacaciones.
    El progreso (horas hechas / objetivo) es distinto del balance, que solo cuenta jornadas cerradas.
    """
    dates = core.week_dates(day)
    computed = _computed(dates, days, settings, now, calendar)
    today = core.local_date(now)
    cfg = settings["weekly_goal"]
    auto = sum(c["target_s"] for c in computed)
    # Lo que habría tocado trabajar sin festivos/vacaciones (para el objetivo personalizado).
    excused = 0
    for d, c in zip(dates, computed):
        if c["day_type"] and not c["registered"] and not c["target_s"]:
            excused += core.snapshot_for(d, settings)["target_minutes"] * 60
    goal = auto if cfg["mode"] == "auto" else max(0, cfg["custom_minutes"] * 60 - excused)
    worked = sum(c["worked_s"] for c in computed)
    closed = [c for c in computed if c["status"] == "finished" or (c["counted"] and not c["clock_in"])]
    open_days = [c for c in computed if c["status"] in ("working", "on_break")]
    # Lo que aún se planea trabajar: días laborables desde hoy sin cerrar.
    planned_left = sum(max(0.0, c["target_s"] - c["worked_s"]) for c, d in zip(computed, dates)
                       if d >= today and c["status"] not in ("finished",) and c["target_s"])
    return {
        "from": dates[0].isoformat(),
        "to": dates[-1].isoformat(),
        "mode": cfg["mode"],
        "goal_s": round(float(goal), 3),
        "auto_s": round(float(auto), 3),
        "excused_s": round(float(excused), 3),
        "worked_s": round(worked, 3),
        "remaining_s": round(max(0.0, goal - worked), 3),
        "extra_s": round(max(0.0, worked - goal), 3),
        "closed_balance_s": round(sum(c["balance_s"] for c in closed), 3),
        "closed_days": len(closed),
        "open_extra_s": round(sum(c["extra_s"] for c in open_days), 3),
        "planned_left_s": round(planned_left, 3),
        "progress": round(min(1.0, worked / goal), 4) if goal else (1.0 if worked else 0.0),
        "days": [{"date": c["date"], "weekday": c["weekday"], "target_s": c["target_s"],
                  "worked_s": c["worked_s"], "status": c["status"], "day_type": c["day_type"],
                  "balance_s": c["balance_s"], "counted": c["counted"]} for c in computed],
    }


def next_workday(after: date, days: dict, settings: dict, now: datetime, calendar: dict | None = None,
                 limit: int = 14) -> date | None:
    for i in range(1, limit + 1):
        d = after + timedelta(days=i)
        if core.compute_day(d, days.get(d.isoformat()), settings, now, calendar)["target_s"]:
            return d
    return None


def compensation(day: date | None, minutes, days: dict, settings: dict, now: datetime,
                 calendar: dict | None = None) -> dict:
    """«Si salgo N minutos antes ese día, ¿cómo queda la semana?». Solo informativo."""
    today = core.local_date(now)
    day = day or next_workday(today, days, settings, now, calendar)
    if day is None:
        raise ValidationError("err.no_workday")
    week = weekly_goal(today, days, settings, now, calendar)
    minutes = week["closed_balance_s"] // 60 if minutes in (None, "") else minutes
    minutes = _minutes(max(0, minutes), "@label.minutes", 0, 600)
    plan = simulate(day, days.get(day.isoformat()), settings, now, calendar=calendar)
    base_exit = core.parse_ts(plan["base"]["exit"])
    sim = simulate(day, days.get(day.isoformat()), settings, now, calendar=calendar, params={
        "exit": core.local_clock(base_exit - timedelta(minutes=minutes))[:5],
    }) if minutes else plan
    same_week = core.week_dates(day)[0] == core.week_dates(today)[0]
    return {
        "date": day.isoformat(),
        "minutes": minutes,
        "same_week": same_week,
        "base_exit": plan["base"]["exit"],
        "exit": sim["sim"]["exit"],
        "worked_s": sim["sim"]["worked_s"],
        "day_balance_s": sim["sim"]["balance_s"],
        "week_closed_before_s": week["closed_balance_s"],
        "week_closed_after_s": round(week["closed_balance_s"] + sim["sim"]["balance_s"], 3) if same_week else None,
        "readonly": True,
    }


# ------------------------------------------------------ estadísticas

def _category(c: dict) -> str:
    """Categoría visual de un día para el mapa de actividad."""
    if c["registered"] and c["mode"] == "off":
        return "off"
    if c["day_type"] and not c["clock_in"]:
        return "absence_deficit" if c["counted"] else "absence"
    if c["status"] == "finished":
        return "complete" if c["worked_s"] + 0.5 >= c["target_s"] else "incomplete"
    if c["status"] in ("working", "on_break"):
        return "progress"
    if c["status"] == "unclosed":
        return "unclosed"
    if c["status"] == "nonworking":
        return "nonworking"
    if c["status"] == "future":
        return "future"
    return "none"


def _mean(values):
    return round(sum(values) / len(values), 3) if values else None


def _local_seconds(iso_value: str) -> int:
    t = core.parse_ts(iso_value).astimezone(core.TZ)
    return t.hour * 3600 + t.minute * 60 + t.second


def advanced_stats(days: dict, settings: dict, now: datetime, calendar: dict | None,
                   year: int, month: int, weeks: int = 12, scope: str = "month") -> dict:
    today = core.local_date(now)
    weeks = max(4, min(MAX_STATS_WEEKS, int(weeks)))

    # Mapa de actividad del mes.
    month_days = _computed(core.month_dates(year, month), days, settings, now, calendar)
    heatmap = [{"date": c["date"], "weekday": c["weekday"], "category": _category(c),
                "worked_s": c["worked_s"], "target_s": c["target_s"], "balance_s": c["balance_s"],
                "day_type": c["day_type"], "label": c["day_label"]} for c in month_days]

    # Promedios: solo días con fichaje; salida, trabajo y descansos solo de jornadas cerradas.
    if scope == "all":
        keys = sorted(k for k in days if k <= today.isoformat())
        pool = [core.compute_day(date.fromisoformat(k), days[k], settings, now, calendar) for k in keys]
    else:
        pool = month_days
    clocked = [c for c in pool if c["clock_in"]]
    closed = [c for c in clocked if c["status"] == "finished"]
    ranked = sorted(closed, key=lambda c: (c["worked_s"], c["date"]))
    top = sorted(closed, key=lambda c: (-c["worked_s"], c["date"]))
    pick = lambda c: {"date": c["date"], "worked_s": c["worked_s"], "target_s": c["target_s"]}  # noqa: E731
    averages = {
        "clock_in_s": _mean([_local_seconds(c["clock_in"]) for c in clocked]),
        "clock_out_s": _mean([_local_seconds(c["clock_out"]) for c in closed]),
        "worked_s": _mean([c["worked_s"] for c in closed]),
        "break_s": _mean([c["break_s"] for c in closed]),
        "days": len(closed),
        "open_days": len(clocked) - len(closed),
        "most": [pick(c) for c in top[:3]],
        "least": [pick(c) for c in ranked[:3]],
    }

    # Semanas: objetivo, hecho y balance; más el balance acumulado.
    this_monday = core.week_dates(today)[0]
    mondays = [this_monday - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    history = sorted(date.fromisoformat(k) for k in days if k <= today.isoformat())
    before = [d for d in history if d < mondays[0]]
    running = core.summarize(_computed(before, days, settings, now, calendar), now)["balance_s"] if before else 0.0
    weekly = []
    for monday in mondays:
        dates = core.week_dates(monday)
        summary = core.summarize(_computed(dates, days, settings, now, calendar), now)
        goal = weekly_goal(monday, days, settings, now, calendar)
        running += summary["balance_s"]
        weekly.append({"from": monday.isoformat(), "goal_s": goal["goal_s"], "worked_s": summary["worked_s"],
                       "balance_s": summary["balance_s"], "cumulative_s": round(running, 3),
                       "current": monday == this_monday, "pending_s": summary["pending_s"]})

    # Meses: últimos 12, con balance acumulado.
    months = []
    y, m = today.year, today.month
    for _ in range(12):
        months.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    months.reverse()
    first_month = date(*months[0], 1)
    before = [d for d in history if d < first_month]
    running = core.summarize(_computed(before, days, settings, now, calendar), now)["balance_s"] if before else 0.0
    monthly = []
    for y, m in months:
        dates = [d for d in core.month_dates(y, m) if d <= today]
        summary = core.summarize(_computed(dates, days, settings, now, calendar), now) if dates else \
            {"balance_s": 0.0, "worked_s": 0.0, "target_s": 0.0}
        running += summary["balance_s"]
        monthly.append({"month": f"{y:04d}-{m:02d}", "balance_s": summary["balance_s"],
                        "worked_s": summary["worked_s"], "cumulative_s": round(running, 3),
                        "current": (y, m) == (today.year, today.month)})

    return {
        "month": f"{year:04d}-{month:02d}",
        "scope": scope,
        "heatmap": heatmap,
        "averages": averages,
        "weekly": weekly,
        "monthly": monthly,
        "has_data": bool(history),
    }


def upcoming_marks(calendar: dict | None, settings: dict, today: date, limit: int = 5,
                   horizon_days: int = 366) -> list[dict]:
    """Próximos festivos, vacaciones y ausencias (agrupando días seguidos del mismo tipo)."""
    if not calendar:
        return []
    out: list[dict] = []
    for i in range(horizon_days):
        d = today + timedelta(days=i)
        mark = core.day_mark(d, calendar)
        if not mark:
            continue
        last = out[-1] if out else None
        if last and last["type"] == mark["type"] and last.get("label", "") == mark.get("label", "") \
                and date.fromisoformat(last["to"]) + timedelta(days=1) >= d - timedelta(days=3) \
                and all(not settings["weekdays"][str((date.fromisoformat(last["to"]) + timedelta(days=k)).weekday())]["workday"]
                        for k in range(1, (d - date.fromisoformat(last["to"])).days)):
            last["to"] = d.isoformat()
            last["days"] += 1
            continue
        if len(out) >= limit:
            break
        out.append({"from": d.isoformat(), "to": d.isoformat(), "type": mark["type"],
                    "label": mark.get("label", ""), "recurring": bool(mark.get("recurring")), "days": 1})
    return out
