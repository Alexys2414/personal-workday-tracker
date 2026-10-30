"""Pruebas en un navegador real (Chrome/Chromium headless), si está instalado.

· notify.js: el planificador de avisos (tests/js/notify.html).
· Humo: el panel y la vista compacta cargan sin errores de JavaScript, con datos ficticios.
Si no hay Chrome, se omiten (no se instala nada).
"""
import json
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

import core
from app import create_app
from tests.helpers import THU, FakeClock, record

ROOT = Path(__file__).resolve().parent.parent
CHROME = next((shutil.which(n) for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
               if shutil.which(n)), None)


def chrome(url, *extra, budget=5000):
    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.run(
            [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
             f"--virtual-time-budget={budget}", "--enable-logging=stderr", "--v=0", *extra, "--dump-dom", url],
            capture_output=True, text=True, timeout=60)
    errors = [line for line in proc.stderr.splitlines() if "CONSOLE" in line and
              re.search(r"Uncaught|Error|TypeError|ReferenceError", line)]
    return proc.stdout, errors


@unittest.skipUnless(CHROME, "Chrome/Chromium no disponible")
class NotifyPlanner(unittest.TestCase):
    def test_plan_alerts(self):
        dom, errors = chrome((ROOT / "tests/js/notify.html").as_uri(), "--allow-file-access-from-files")
        self.assertEqual(errors, [])
        out = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S).group(1)
        self.assertIn("DONE", out)
        lines = [line for line in out.splitlines() if line.startswith(("PASS", "FAIL"))]
        self.assertGreaterEqual(len(lines), 16)
        self.assertEqual([line for line in lines if line.startswith("FAIL")], [])


@unittest.skipUnless(CHROME, "Chrome/Chromium no disponible")
class PagesLoadWithoutErrors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import logging

        from werkzeug.serving import make_server
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        cls.tmp = tempfile.TemporaryDirectory()
        data = Path(cls.tmp.name)
        days = {"2026-10-27": record(core.week_dates(THU)[1], "08:00", "17:30", [("14:00", "15:00")]),
                THU.isoformat(): record(THU, "07:53", None, [("14:00", "14:40")], now=core.combine(THU, "15:00"))}
        (data / "records.json").write_text(json.dumps({"version": 1, "days": days}))
        import tasks as tm
        tdata, task = tm.create_task(tm.default_data(), {"key": "DEMO-101", "title": "Tarea ficticia",
                                                         "estimate_minutes": 480}, core.combine(THU, "07:00"))
        tdata, _ = tm.add_manual(tdata, {"task_id": task["id"], "date": THU.isoformat(), "start": "07:53",
                                         "end": "10:00"}, core.combine(THU, "15:00"))
        tdata, _ = tm.start(tdata, task["id"], core.combine(THU, "14:40"))
        (data / "tasks.json").write_text(json.dumps(tdata))
        (data / "calendar.json").write_text(json.dumps({"version": 1, "days": {"2026-11-02": {"type": "vacation"}},
                                                        "recurring": {"12-25": {"label": "Navidad"}}}))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        app = create_app(data, FakeClock(THU, "15:00"))
        cls.server = make_server("127.0.0.1", cls.port, app, threaded=True)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.tmp.cleanup()

    def load(self, path):
        dom, errors = chrome(f"http://127.0.0.1:{self.port}{path}")
        self.assertEqual(errors, [], path)
        return dom

    def test_dashboard(self):
        dom = self.load("/")
        self.assertRegex(dom, r'id="countdown">\d\d:\d\d:\d\d<')
        self.assertRegex(dom, r'id="wkBody">\s*<div class="wk-top">')
        self.assertIn("Navidad", dom)
        self.assertIn('id="taskStrip" data-card="tasks"', dom)
        self.assertRegex(dom, r'data-mode="active"')                     # franja con la tarea en marcha
        self.assertIn("DEMO-101", dom)

    def test_views_from_links(self):
        for path, marker in (("/#/simulate", 'class="sim-hero"'), ("/#/stats", 'data-panel="heatmap"'),
                             ("/#/settings/calendar", 'class="hol-main"'), ("/#/settings/alerts", 'class="lead-chip'),
                             ("/#/tasks/tasks", 'class="tk-card'), ("/#/tasks/day", 'class="entry '),
                             ("/#/tasks/week", 'class="share-list"'), ("/#/tasks/report", 'class="data-table rp-table"'),
                             ("/#/picker", 'role="option"'), ("/#/tasks/new", 'data-value="teal"'),
                             ("/#/entry/new", '<option value="t_')):
            with self.subTest(path):
                self.assertIn(marker, self.load(path))

    def test_compact_view(self):
        dom = self.load("/compact")
        self.assertIn('data-status="working"', dom)
        self.assertIn('data-action="break_start"', dom)

    def test_english_and_dark(self):
        dom, errors = chrome(f"http://127.0.0.1:{self.port}/#/stats", "--force-dark-mode", "--lang=en")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
