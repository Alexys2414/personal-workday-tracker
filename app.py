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

import core  # noqa: E402
import csvio  # noqa: E402
import i18n  # noqa: E402
from storage import JsonStore  # noqa: E402

APP_ID = "jornada"
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
DEFAULT_PORT = 8765
PORT_ATTEMPTS = 20
RUN_FILE = ".jornada-run.json"      # PID y puerto de la instancia en marcha


def resolve_data_dir() -> Path:
    return Path(os.environ.get("WORKTIME_DATA_DIR") or BASE_DIR / "data")


def create_app(data_dir: str | Path | None = None,
               clock: Callable[[], datetime] | None = None) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    data_dir = Path(data_dir or resolve_data_dir())
    records_store = JsonStore(data_dir / "records.json", lambda: {"version": 1, "days": {}})
    settings_store = JsonStore(data_dir / "settings.json", core.default_settings)
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

    def compute(dates, days, settings, current):
        return [core.compute_day(d, days.get(d.isoformat()), settings, current) for d in dates]

    def period(dates, days, settings, current):
        computed = compute(dates, days, settings, current)
        return {"from": dates[0].isoformat(), "to": dates[-1].isoformat(),
                "days": computed, "summary": core.summarize(computed, current)}

    # Crea los JSON al arrancar si no existen.
    with lock:
        settings_store.save(load_settings())
        load_days()

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
        return render_template("index.html", lang=code, i18n=i18n.catalog(code),
                               t=lambda key, **kw: i18n.tr(code, key, **kw))

    @app.get("/api/state")
    def state():
        current = now()
        today = core.local_date(current)
        settings = load_settings()
        days = load_days()
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
            settings=settings,
            today=core.compute_day(today, days.get(today.isoformat()), settings, current),
            week=core.summarize(compute(core.week_dates(today), days, settings, current), current),
            month=core.summarize(compute(month, days, settings, current), current),
            total={**core.summarize(compute(history, days, settings, current), current),
                   "since": history[0].isoformat() if history else None},
            unclosed=unclosed,
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
            key = today.isoformat()
            before = core.compute_day(today, days.get(key), settings, current)["status"]
            # Protección frente a doble clic: si el estado ya cambió, no se repite.
            if body.get("expect") and body["expect"] != before:
                raise core.Conflict("conflict.state_changed")
            days[key] = core.apply_action(action, today, days.get(key), settings, current)
            save_days(days)
            return jsonify(today=core.compute_day(today, days[key], settings, current))

    @app.get("/api/month/<int:year>-<int:month>")
    def month_view(year: int, month: int):
        if not 1 <= month <= 12 or not 2000 <= year <= 2100:
            raise core.ValidationError("err.bad_month")
        current = now()
        return jsonify(period(core.month_dates(year, month), load_days(), load_settings(), current))

    @app.get("/api/week/<day>")
    def week_view(day: str):
        current = now()
        return jsonify(period(core.week_dates(parse_date(day)), load_days(), load_settings(), current))

    @app.get("/api/days/<day>")
    def get_day(day: str):
        d = parse_date(day)
        days = load_days()
        return jsonify(core.compute_day(d, days.get(day), load_settings(), now()))

    @app.put("/api/days/<day>")
    def put_day(day: str):
        d = parse_date(day)
        body = request.get_json(silent=True)
        with lock:
            current = now()
            settings = load_settings()
            days = load_days()
            days[d.isoformat()] = core.build_record(d, body, days.get(d.isoformat()), settings, current)
            save_days(days)
            return jsonify(core.compute_day(d, days[d.isoformat()], settings, current))

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
            record = days.get(d.isoformat()) or core.new_record(d, settings)
            days[d.isoformat()] = core.set_note(record, body.get("target"), body.get("text"))
            save_days(days)
            return jsonify(core.compute_day(d, days[d.isoformat()], settings, current))

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
            changed = False
            for key, record in days.items():
                if key >= today:
                    changed |= core.refresh_open_record(record, date.fromisoformat(key), settings)
            if changed:
                save_days(days)
        return jsonify(settings)

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
