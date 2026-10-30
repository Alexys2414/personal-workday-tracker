"""Jornada — mini sistema de fichaje personal.

Ejecuta:  python app.py --open      (o haz doble clic en iniciar.bat / iniciar.sh)

Solo escucha en 127.0.0.1: no es accesible desde otros equipos de la red.
Las dependencias van incluidas en vendor/, así que basta con Python 3.10+.
"""
from __future__ import annotations

import os
import json
import shutil
import socket
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

BASE_DIR = Path(__file__).resolve().parent
# Primero las librerías incluidas en el proyecto: no hace falta pip ni instalar nada.
for _path in (BASE_DIR, BASE_DIR / "vendor"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

if sys.version_info < (3, 10):
    sys.exit("Jornada necesita Python 3.10 o superior (tienes %d.%d)." % sys.version_info[:2])

from flask import Flask, Response, abort, jsonify, render_template, request  # noqa: E402

import backup  # noqa: E402
import core  # noqa: E402
import csvio  # noqa: E402
import daymarks  # noqa: E402
import i18n  # noqa: E402
import insights  # noqa: E402
from storage import JsonStore, save_many  # noqa: E402

APP_ID = "jornada"
APP_VERSION = "2.1.0"
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
DEFAULT_PORT = 8765
PORT_ATTEMPTS = 20
RUN_FILE = ".jornada-run.json"      # PID y puerto de la instancia en marcha


def asset_build(base: Path = BASE_DIR) -> str:
    """Huella de la versión instalada: cambia si se modifica cualquier archivo de la app."""
    import hashlib
    files = sorted([*base.glob("*.py"), *base.glob("templates/*.html"),
                    *base.glob("static/**/*.js"), *base.glob("static/**/*.css"), *base.glob("static/i18n/*.json")])
    digest = hashlib.sha1()
    for path in files:
        stat = path.stat()
        digest.update(f"{path.relative_to(base)}:{stat.st_mtime_ns}:{stat.st_size};".encode())
    return digest.hexdigest()[:10]


def resolve_data_dir() -> Path:
    return Path(os.environ.get("WORKTIME_DATA_DIR") or BASE_DIR / "data")


def create_app(data_dir: str | Path | None = None,
               clock: Callable[[], datetime] | None = None) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    # La plantilla se lee siempre del disco, igual que CSS y JS: una instancia que lleva
    # tiempo abierta nunca mezcla HTML antiguo con scripts nuevos.
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True
    app.config["BUILD"] = asset_build()      # versión con la que arrancó este proceso

    # Copia de seguridad completa: hasta 10 MB de JSON (más margen para el envoltorio).
    app.config["MAX_CONTENT_LENGTH"] = backup.MAX_BYTES + 1024 * 1024

    data_dir = Path(data_dir or resolve_data_dir())
    records_store = JsonStore(data_dir / "records.json", lambda: {"version": 1, "days": {}})
    settings_store = JsonStore(data_dir / "settings.json", core.default_settings)
    calendar_store = JsonStore(data_dir / "calendar.json", core.default_calendar)
    lock = threading.Lock()
    clock = clock or (lambda: datetime.now(core.UTC))

    def now() -> datetime:
        return clock().astimezone(core.UTC)

    def load_settings() -> dict:
        return core.normalize_settings(settings_store.load())

    def load_days() -> dict:
        data = records_store.load()
        return data.setdefault("days", {})

    def save_days(days: dict) -> None:
        records_store.save({"version": 1, "days": days})

    def load_calendar() -> dict:
        return core.normalize_calendar(calendar_store.load())

    def parse_date(value: str) -> date:
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            raise core.ValidationError("err.bad_date", label="@label.date", value=value)

    def lang() -> str:
        return load_settings().get("language", i18n.DEFAULT)

    def tr(key: str, **params) -> str:
        return i18n.tr(lang(), key, **params)

    def date_range(days: dict):
        """Rango ?from=&to= (ISO). Sin parámetros: todo el historial."""
        start = parse_date(request.args["from"]) if request.args.get("from") else None
        end = parse_date(request.args["to"]) if request.args.get("to") else None
        if start and end and end < start:
            raise core.ValidationError("err.bad_range")
        return start, end

    def compute(dates, days, settings, current, calendar):
        return [core.compute_day(d, days.get(d.isoformat()), settings, current, calendar) for d in dates]

    def period(dates, days, settings, current, calendar):
        computed = compute(dates, days, settings, current, calendar)
        return {"from": dates[0].isoformat(), "to": dates[-1].isoformat(),
                "days": computed, "summary": core.summarize(computed, current)}

    def snapshot_folder(reason: str) -> Path:
        """Copia de los JSON actuales en data/backups/<motivo>-<fecha>/ (nunca se borran solas)."""
        folder = data_dir / "backups" / f"{reason}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("records.json", "settings.json", "calendar.json"):
            if (data_dir / name).exists():
                shutil.copy2(data_dir / name, folder / name)
        return folder

    # Crea los JSON al arrancar si no existen. Si los ajustes son de una versión
    # anterior, se guarda una copia antes de migrarlos (los valores existentes se conservan).
    with lock:
        if settings_store.path.exists():
            try:
                old_version = json.loads(settings_store.path.read_text(encoding="utf-8")).get("version", 1)
            except (OSError, ValueError, AttributeError):
                old_version = core.SETTINGS_VERSION
            if isinstance(old_version, int) and old_version < core.SETTINGS_VERSION:
                snapshot_folder(f"pre-migracion-ajustes-v{old_version}")
        settings_store.save(load_settings())
        load_days()
        load_calendar()

    @app.before_request
    def _only_local():
        # Rechaza peticiones con otro nombre de host (protección frente a DNS rebinding).
        if request.host.rsplit(":", 1)[0] not in LOCAL_HOSTS:
            abort(403)
        app.config["LAST_SEEN"] = time.time()

    @app.errorhandler(core.ValidationError)
    def _bad_request(exc):
        return jsonify(error=exc.message(lang()), code=exc.code), 400

    @app.errorhandler(core.Conflict)
    def _conflict(exc):
        return jsonify(error=exc.message(lang()), code=exc.code), 409

    @app.get("/")
    def index():
        # La página llega ya traducida: sin parpadeos al cargar en otro idioma.
        code = lang()
        return render_template("index.html", lang=code, i18n=i18n.catalog(code), build=asset_build(),
                               t=lambda key, **kw: i18n.tr(code, key, **kw))

    @app.get("/api/state")
    def state():
        current = now()
        today = core.local_date(current)
        settings = load_settings()
        days = load_days()
        calendar = load_calendar()
        unclosed = []
        for key in sorted(days, reverse=True)[:60]:
            d = date.fromisoformat(key)
            if today - timedelta(days=45) <= d < today:
                rec = days[key]
                if rec.get("clock_in") and not rec.get("clock_out"):
                    unclosed.append(key)
        month = core.month_dates(today.year, today.month)
        # Balance acumulado de todas las jornadas registradas (informativo).
        history = sorted(d for d in map(date.fromisoformat, days) if d <= today)
        return jsonify(
            server_time=core.iso(current),
            server_ms=int(current.timestamp() * 1000),
            build=app.config["BUILD"],
            disk_build=asset_build(),
            version=APP_VERSION,
            settings=settings,
            today=core.compute_day(today, days.get(today.isoformat()), settings, current, calendar),
            week=core.summarize(compute(core.week_dates(today), days, settings, current, calendar), current),
            month=core.summarize(compute(month, days, settings, current, calendar), current),
            total={**core.summarize(compute(history, days, settings, current, calendar), current),
                   "since": history[0].isoformat() if history else None},
            weekly=insights.weekly_goal(today, days, settings, current, calendar),
            upcoming=insights.upcoming_marks(calendar, settings, today),
            unclosed=unclosed,
        )

    @app.get("/api/today")
    def today_light():
        """Estado mínimo para la vista compacta: hoy, ajustes y hora del servidor."""
        current = now()
        today = core.local_date(current)
        return jsonify(
            server_ms=int(current.timestamp() * 1000),
            build=app.config["BUILD"],
            settings=load_settings(),
            today=core.compute_day(today, load_days().get(today.isoformat()), load_settings(), current,
                                   load_calendar()),
        )

    @app.get("/api/ping")
    def ping():
        return jsonify(app=APP_ID, pid=os.getpid())

    @app.post("/api/shutdown")
    def shutdown():
        # Exige JSON: un formulario de otra web no puede enviarlo sin permiso CORS.
        if not request.is_json:
            abort(400)
        # Espera a que termine cualquier escritura en curso; todo lo demás ya está guardado.
        with lock:
            stop = app.config.get("JORNADA_STOP")
            if stop:
                threading.Timer(0.3, stop).start()
        return jsonify(ok=True)

    @app.post("/api/clock")
    def clock_action():
        body = request.get_json(silent=True) or {}
        action = body.get("action")
        with lock:
            current = now()
            today = core.local_date(current)
            settings = load_settings()
            days = load_days()
            calendar = load_calendar()
            key = today.isoformat()
            before = core.compute_day(today, days.get(key), settings, current, calendar)["status"]
            # Protección frente a doble clic y a dos ventanas (panel y vista compacta):
            # si el estado ya cambió, la acción no se repite.
            if body.get("expect") and body["expect"] != before:
                raise core.Conflict("conflict.state_changed")
            days[key] = core.apply_action(action, today, days.get(key), settings, current, calendar)
            save_days(days)
            return jsonify(today=core.compute_day(today, days[key], settings, current, calendar))

    @app.get("/api/month/<int:year>-<int:month>")
    def month_view(year: int, month: int):
        if not 1 <= month <= 12 or not 2000 <= year <= 2100:
            raise core.ValidationError("err.bad_month")
        current = now()
        return jsonify(period(core.month_dates(year, month), load_days(), load_settings(), current, load_calendar()))

    @app.get("/api/week/<day>")
    def week_view(day: str):
        current = now()
        return jsonify(period(core.week_dates(parse_date(day)), load_days(), load_settings(), current,
                              load_calendar()))

    @app.get("/api/days/<day>")
    def get_day(day: str):
        d = parse_date(day)
        days = load_days()
        return jsonify(core.compute_day(d, days.get(day), load_settings(), now(), load_calendar()))

    @app.put("/api/days/<day>")
    def put_day(day: str):
        d = parse_date(day)
        body = request.get_json(silent=True)
        with lock:
            current = now()
            settings = load_settings()
            days = load_days()
            calendar = load_calendar()
            days[d.isoformat()] = core.build_record(d, body, days.get(d.isoformat()), settings, current, calendar)
            save_days(days)
            return jsonify(core.compute_day(d, days[d.isoformat()], settings, current, calendar))

    @app.delete("/api/days/<day>")
    def delete_day(day: str):
        d = parse_date(day)
        with lock:
            days = load_days()
            if days.pop(d.isoformat(), None) is None:
                return jsonify(error=tr("err.not_found")), 404
            save_days(days)
        return jsonify(ok=True)

    @app.post("/api/days/<day>/note")
    def put_note(day: str):
        """Nota del día (target='day') o de un descanso (target=índice). No toca tiempos."""
        d = parse_date(day)
        body = request.get_json(silent=True) or {}
        with lock:
            current = now()
            settings = load_settings()
            days = load_days()
            calendar = load_calendar()
            record = days.get(d.isoformat()) or core.new_record(d, settings, calendar)
            days[d.isoformat()] = core.set_note(record, body.get("target"), body.get("text"))
            save_days(days)
            return jsonify(core.compute_day(d, days[d.isoformat()], settings, current, calendar))

    # ------------------------------------------------------ exportación

    @app.get("/api/export.csv")
    def export_csv():
        days = load_days()
        start, end = date_range(days)
        text = csvio.export_csv(days, load_settings(), lang(), now(), start, end)
        name = f"jornada_{start or 'inicio'}_{end or 'hoy'}.csv" if (start or end) else "jornada_historial.csv"
        return Response(text, mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/report")
    def report():
        days = load_days()
        start, end = date_range(days)
        code = lang()
        return render_template("report.html", lang=code, t=lambda key, **kw: i18n.tr(code, key, **kw),
                               **report_context(days, load_settings(), code, now(), start, end))

    # ------------------------------------------------------- importación

    @app.post("/api/import/preview")
    def import_preview():
        body = request.get_json(silent=True) or {}
        code = lang()
        text = csvio.decode_upload(body.get("file", ""), code)
        result = csvio.parse_import(text, load_days(), load_settings(), now(), code)
        result.pop("records")
        return jsonify(result)

    @app.post("/api/import/commit")
    def import_commit():
        body = request.get_json(silent=True) or {}
        code = lang()
        text = csvio.decode_upload(body.get("file", ""), code)
        with lock:
            days = load_days()
            # Si los datos cambiaron desde la vista previa, se repite la revisión.
            if body.get("fingerprint") != csvio.fingerprint(days):
                raise core.Conflict("imp.e.not_found")
            result = csvio.parse_import(text, days, load_settings(), now(), code)
            overwrite = {d for d in body.get("overwrite", []) if isinstance(d, str)}
            merged, imported = csvio.merge(days, result["records"], overwrite)
            backup = None
            if imported:
                backup = backup_records()
                save_days(merged)        # una sola escritura atómica
        return jsonify(imported=imported, backup=backup)

    def backup_records() -> str | None:
        source = data_dir / "records.json"
        if not source.exists():
            return None
        folder = data_dir / "backups"
        folder.mkdir(exist_ok=True)
        name = f"records-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        shutil.copy2(source, folder / name)
        return f"data/backups/{name}"

    @app.get("/api/shortcuts/defaults")
    def shortcut_defaults():
        return jsonify(core.DEFAULT_SHORTCUTS)

    @app.get("/api/settings")
    def get_settings():
        return jsonify(load_settings())

    @app.put("/api/settings")
    def put_settings():
        body = request.get_json(silent=True)
        with lock:
            settings = core.normalize_settings(body, load_settings())
            settings_store.save(settings)
            # La jornada abierta de hoy y los días planificados adoptan los nuevos
            # perfiles; las jornadas cerradas y pasadas conservan los suyos.
            today = core.local_date(now()).isoformat()
            days = load_days()
            calendar = load_calendar()
            changed = False
            for key, record in days.items():
                if key >= today:
                    changed |= core.refresh_open_record(record, date.fromisoformat(key), settings, calendar)
            if changed:
                save_days(days)
        return jsonify(settings)

    # --------------------------------------------------- vista compacta

    @app.get("/compact")
    def compact():
        code = lang()
        return render_template("compact.html", lang=code, i18n=i18n.catalog(code), build=asset_build(),
                               t=lambda key, **kw: i18n.tr(code, key, **kw))

    # ------------------------------------------- simulador (solo lectura)

    @app.post("/api/simulate")
    def simulate():
        """Nunca escribe: calcula sobre una copia de la jornada."""
        body = request.get_json(silent=True) or {}
        d = parse_date(body["date"]) if body.get("date") else core.local_date(now())
        days = load_days()
        return jsonify(insights.simulate(d, days.get(d.isoformat()), load_settings(), now(),
                                         body.get("params"), load_calendar()))

    @app.post("/api/compensation")
    def compensation():
        body = request.get_json(silent=True) or {}
        d = parse_date(body["date"]) if body.get("date") else None
        return jsonify(insights.compensation(d, body.get("minutes"), load_days(), load_settings(), now(),
                                             load_calendar()))

    @app.get("/api/weekly/<day>")
    def weekly(day: str):
        return jsonify(insights.weekly_goal(parse_date(day), load_days(), load_settings(), now(), load_calendar()))

    # ----------------------------------------------------- estadísticas

    @app.get("/api/stats")
    def stats():
        current = now()
        today = core.local_date(current)
        month = request.args.get("month") or f"{today.year:04d}-{today.month:02d}"
        try:
            year, mon = map(int, month.split("-"))
            if not 1 <= mon <= 12 or not 2000 <= year <= 2100:
                raise ValueError
        except ValueError:
            raise core.ValidationError("err.bad_month")
        scope = "all" if request.args.get("scope") == "all" else "month"
        weeks = request.args.get("weeks", 12)
        try:
            weeks = int(weeks)
        except ValueError:
            weeks = 12
        return jsonify(insights.advanced_stats(load_days(), load_settings(), current, load_calendar(),
                                               year, mon, weeks, scope))

    # ------------------------------------------- festivos y ausencias

    @app.get("/api/calendar")
    def get_calendar():
        today = core.local_date(now())
        settings = load_settings()
        calendar = load_calendar()
        return jsonify(calendar=calendar, upcoming=insights.upcoming_marks(calendar, settings, today, limit=8))

    def conflict_payload(keys, days, settings, current):
        return [{"date": k, "status": core.compute_day(date.fromisoformat(k), days[k], settings, current)["status"]}
                for k in keys]

    def save_marks(calendar: dict, dates: list[str], mark: dict, apply_to_records: bool | None):
        """Guarda marcas. Si algún día tiene fichajes, el usuario debe decidir antes."""
        current = now()
        settings = load_settings()
        days = load_days()
        conflicts = [k for k in dates if k in days and (days[k].get("clock_in") or days[k].get("mode") == "off")]
        if conflicts and apply_to_records is None:
            return jsonify(error=tr("cal.conflict", n=len(conflicts)), code="cal.conflict",
                           conflicts=conflict_payload(conflicts, days, settings, current)), 409
        new_calendar = daymarks.apply_marks(calendar, dates, mark)
        if conflicts and apply_to_records:
            snapshot_folder("pre-tipo-de-dia")
            for k in conflicts:
                days[k] = daymarks.adopt_mark(days[k], date.fromisoformat(k), mark, settings)
            save_many([(calendar_store, new_calendar), (records_store, {"version": 1, "days": days})])
        else:
            calendar_store.save(new_calendar)
        return jsonify(ok=True, marked=len(dates), adopted=len(conflicts) if apply_to_records else 0)

    def apply_flag(body):
        value = body.get("apply")
        return None if value is None else bool(value)

    @app.put("/api/calendar/days/<day>")
    def put_mark(day: str):
        d = parse_date(day)
        body = request.get_json(silent=True) or {}
        mark = core.clean_mark(body)
        with lock:
            return save_marks(load_calendar(), [d.isoformat()], mark, apply_flag(body))

    @app.delete("/api/calendar/days/<day>")
    def delete_mark(day: str):
        d = parse_date(day)
        with lock:
            calendar = load_calendar()
            if calendar["days"].pop(d.isoformat(), None) is None:
                return jsonify(error=tr("err.not_found")), 404
            calendar_store.save(calendar)
        return jsonify(ok=True)

    @app.put("/api/calendar/recurring/<md>")
    def put_recurring(md: str):
        key = core.valid_month_day(md)
        body = request.get_json(silent=True) or {}
        label = core.clean_label(body.get("label"))
        with lock:
            calendar = load_calendar()
            calendar["recurring"][key] = {"label": label} if label else {}
            calendar_store.save(core.normalize_calendar(calendar))
        return jsonify(ok=True)

    @app.delete("/api/calendar/recurring/<md>")
    def delete_recurring(md: str):
        key = core.valid_month_day(md)
        with lock:
            calendar = load_calendar()
            if calendar["recurring"].pop(key, None) is None:
                return jsonify(error=tr("err.not_found")), 404
            calendar_store.save(calendar)
        return jsonify(ok=True)

    def range_from(body):
        start = parse_date(body.get("from"))
        end = parse_date(body.get("to"))
        return daymarks.range_plan(start, end, {"type": body.get("type"), "label": body.get("label")},
                                   load_settings(), load_calendar(), load_days(),
                                   bool(body.get("include_nonworking")))

    @app.post("/api/calendar/range/preview")
    def range_preview():
        return jsonify(range_from(request.get_json(silent=True) or {}))

    @app.post("/api/calendar/range")
    def range_commit():
        body = request.get_json(silent=True) or {}
        with lock:
            plan = range_from(body)
            # Lo confirmado debe coincidir con lo que se mostró.
            if body.get("count") is not None and body["count"] != plan["count"]:
                raise core.Conflict("conflict.state_changed")
            if not plan["count"]:
                raise core.ValidationError("cal.e.nothing")
            return save_marks(load_calendar(), plan["dates"], plan["mark"], apply_flag(body))

    @app.post("/api/calendar/import/preview")
    def calendar_import_preview():
        body = request.get_json(silent=True) or {}
        result = daymarks.parse_import(body.get("text", ""), body.get("filename", ""))
        code = lang()
        result["errors"] = [{**e, "message": i18n.tr(code, e["code"])} for e in result["errors"]]
        return jsonify(result)

    @app.post("/api/calendar/import")
    def calendar_import():
        body = request.get_json(silent=True) or {}
        result = daymarks.parse_import(body.get("text", ""), body.get("filename", ""))
        if not result["items"]:
            raise core.ValidationError("cal.e.nothing")
        with lock:
            merged, n = daymarks.merge_import(load_calendar(), result["items"])
            calendar_store.save(merged)
        return jsonify(imported=n, errors=len(result["errors"]))

    # ---------------------------------------------- copias de seguridad

    @app.get("/api/backup")
    def export_backup():
        current = now()
        with lock:
            payload = backup.build(records_store.load(), load_settings(), load_calendar(), APP_VERSION, current)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        return Response(text, mimetype="application/json; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{backup.filename(current)}"',
                                 "Cache-Control": "no-store"})

    def current_fingerprint() -> str:
        return backup.checksum({"records": records_store.load(), "settings": load_settings(),
                                "calendar": load_calendar()})

    @app.post("/api/backup/preview")
    def backup_preview():
        body = request.get_json(silent=True) or {}
        parsed = backup.parse(body.get("text", ""))
        current = backup.counts({"records": records_store.load(), "calendar": load_calendar()})
        return jsonify(meta=parsed["meta"], counts=parsed["counts"], current=current,
                       overwrites=bool(current["days"] or current["calendar_days"] or current["recurring"]),
                       fingerprint=parsed["fingerprint"], state=current_fingerprint(),
                       language=parsed["data"]["settings"]["language"])

    @app.post("/api/backup/restore")
    def backup_restore():
        body = request.get_json(silent=True) or {}
        if body.get("confirm") is not True:
            raise core.ValidationError("bk.e.confirm")
        parsed = backup.parse(body.get("text", ""))
        with lock:
            # Lo restaurado debe ser exactamente lo revisado, y los datos no deben
            # haber cambiado desde la vista previa (p. ej. un fichaje en otra ventana).
            if body.get("fingerprint") != parsed["fingerprint"] or body.get("state") != current_fingerprint():
                raise core.Conflict("bk.e.changed")
            folder = snapshot_folder("pre-restauracion")
            data = parsed["data"]
            save_many([(records_store, data["records"]), (settings_store, data["settings"]),
                       (calendar_store, data["calendar"])])
        return jsonify(ok=True, counts=parsed["counts"],
                       backup=str(folder.relative_to(data_dir.parent)) if folder.is_relative_to(data_dir.parent)
                       else str(folder))

    return app


def _hm(seconds: float) -> str:
    m = int(round(abs(seconds) / 60))
    return f"{m // 60}:{m % 60:02d}"


def report_context(days: dict, settings: dict, lang: str, now: datetime,
                   start: date | None, end: date | None) -> dict:
    """Datos del informe imprimible (solo días con registro dentro del rango)."""
    tr = lambda key, **kw: i18n.tr(lang, key, **kw)  # noqa: E731
    fmt_date = lambda d: d.strftime("%d/%m/%Y")  # noqa: E731
    keys = sorted(k for k in days if (not start or k >= start.isoformat()) and (not end or k <= end.isoformat()))
    computed = [core.compute_day(date.fromisoformat(k), days[k], settings, now) for k in keys]
    first = start or (date.fromisoformat(keys[0]) if keys else core.local_date(now))
    last = end or (date.fromisoformat(keys[-1]) if keys else core.local_date(now))

    rows = []
    plus = minus = 0.0
    for c in computed:
        loc = c["local"]
        if c["status"] == "finished":
            bal, cls = c["balance_s"], ("pos" if c["balance_s"] >= 60 else "neg" if c["balance_s"] <= -60 else "")
            plus += max(0.0, bal)
            minus += max(0.0, -bal)
            balance = ("+" if bal > 0 else "−" if bal < 0 else "") + _hm(bal)
        elif c["status"] in ("working", "on_break"):
            balance, cls = tr("report.pending"), "pend"
        else:
            balance, cls = "—", ""
        rows.append({
            "date": fmt_date(date.fromisoformat(c["date"])),
            "weekday": tr(f"weekday.{c['weekday']}"),
            "mode": tr(f"mode.{c['mode']}"),
            "profile": tr(f"profile.{c['profile']}") if c["profile"] and c["mode"] != "off" else "",
            "in_out": f"{(loc['clock_in'] or '')[:5]} – {(loc['clock_out'] or '')[:5]}" if loc["clock_in"] else "—",
            "breaks": [{"range": f"{(b['start'] or '')[:5]}–{(b['end'] or '')[:5]}", "note": b.get("note")}
                       for b in loc["breaks"]],
            "notes": c["notes"],
            "worked": _hm(c["worked_s"]) if c["clock_in"] else "—",
            "target": _hm(c["target_s"]) if c["target_s"] else "—",
            "balance": balance,
            "balance_cls": cls,
        })
    worked_days = [c for c in computed if c["clock_in"]]
    # Los totales cuentan solo jornadas cerradas para que trabajado − objetivo = balance.
    closed = [c for c in computed if c["status"] == "finished"]
    total_bal = plus - minus
    summary = {
        "days": len(worked_days),
        "worked": _hm(sum(c["worked_s"] for c in closed)),
        "target": _hm(sum(c["target_s"] for c in closed)),
        "breaks": _hm(sum(c["break_s"] for c in worked_days)),
        "has_open": any(c["status"] in ("working", "on_break", "unclosed") for c in computed),
        "plus": "+" + _hm(plus),
        "minus": "−" + _hm(minus),
        "balance_s": total_bal,
        "balance": ("+" if total_bal > 0 else "−" if total_bal < 0 else "") + _hm(total_bal),
        "balance_cls": "pos" if total_bal >= 60 else "neg" if total_bal <= -60 else "",
        "avg": _hm(sum(c["worked_s"] for c in closed) / len(closed)) if closed else "0:00",
    }
    local_now = now.astimezone(core.TZ)
    return {
        "rows": rows,
        "summary": summary,
        "period": tr("report.period", **{"from": fmt_date(first), "to": fmt_date(last)}),
        "generated": local_now.strftime("%d/%m/%Y %H:%M"),
    }


def _local_get(url: str, timeout: float = 2.0):
    """GET a 127.0.0.1 sin pasar por ningún proxy configurado en el sistema."""
    from urllib.request import ProxyHandler, build_opener
    with build_opener(ProxyHandler({})).open(url, timeout=timeout) as res:
        return json.load(res)


def running_instance(data_dir: Path) -> int | None:
    """Puerto de la Jornada ya abierta con estos datos, o None.

    Se identifica por el archivo de control (PID + puerto) y se confirma
    preguntando a ese puerto: así nunca se confunde con otro programa.
    """
    try:
        info = json.loads((data_dir / RUN_FILE).read_text(encoding="utf-8"))
        port, pid = int(info["port"]), int(info["pid"])
        answer = _local_get(f"http://127.0.0.1:{port}/api/ping")
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return port if answer.get("app") == APP_ID and answer.get("pid") == pid else None


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if os.name == "posix":   # igual que Werkzeug; en Windows permitiría "robar" el puerto
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def main(argv: list[str] | None = None) -> int:
    import argparse
    import logging
    import signal
    import webbrowser

    from werkzeug.serving import make_server

    parser = argparse.ArgumentParser(description="Jornada: fichaje personal (solo 127.0.0.1).")
    parser.add_argument("--open", action="store_true", help="abre el navegador al arrancar")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", DEFAULT_PORT)),
                        help=f"puerto preferido (por defecto {DEFAULT_PORT})")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535 - PORT_ATTEMPTS:
        parser.error("el puerto debe estar entre 1024 y 65515 (sin privilegios)")

    data_dir = resolve_data_dir()
    existing = running_instance(data_dir)
    if existing:
        url = f"http://127.0.0.1:{existing}"
        print(f"Jornada ya estaba abierta en {url}", flush=True)
        if args.open:
            webbrowser.open(url)
        return 0

    # Puertos ocupados por otros programas se saltan; nunca se tocan.
    port = next((p for p in range(args.port, args.port + PORT_ATTEMPTS) if _port_free(p)), None)
    if port is None:
        print(f"No hay ningún puerto libre entre {args.port} y {args.port + PORT_ATTEMPTS - 1}.", flush=True)
        return 1
    if port != args.port:
        print(f"  El puerto {args.port} está ocupado por otro programa; uso el {port}.", flush=True)

    app = create_app(data_dir)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    server = make_server("127.0.0.1", port, app, threaded=True)   # ya escucha al crearse
    stopping = threading.Event()

    def stop():
        if not stopping.is_set():
            stopping.set()
            server.shutdown()

    app.config["JORNADA_STOP"] = stop
    app.config["LAST_SEEN"] = time.time()
    run_file = data_dir / RUN_FILE
    run_file.write_text(json.dumps({"pid": os.getpid(), "port": port}), encoding="utf-8")

    def on_signal(signum, frame):
        raise KeyboardInterrupt
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), on_signal)

    # Se cierra sola si nadie la usa en mucho tiempo (por defecto 12 h; 0 = nunca).
    idle_hours = float(os.environ.get("JORNADA_IDLE_HOURS", 12))
    if idle_hours > 0:
        def watch_idle():
            while not stopping.wait(60):
                if time.time() - app.config["LAST_SEEN"] > idle_hours * 3600:
                    print("  Sin uso durante %g h: cerrando Jornada." % idle_hours, flush=True)
                    threading.Thread(target=stop, daemon=True).start()
                    return
        threading.Thread(target=watch_idle, daemon=True).start()

    url = f"http://127.0.0.1:{port}"
    print(f"\n  Jornada en marcha → {url}", flush=True)
    print("  Para detenerla: botón «Cerrar Jornada» (⏻), Ctrl+C o cierra esta ventana.\n", flush=True)
    if args.open:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stopping.set()
        server.server_close()           # libera el puerto
        try:
            if json.loads(run_file.read_text(encoding="utf-8")).get("pid") == os.getpid():
                run_file.unlink()
        except (OSError, ValueError):
            pass
    print("  Jornada detenida.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
