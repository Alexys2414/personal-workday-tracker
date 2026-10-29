"""Regresiones de la auditoría: versiones mezcladas, contrato DOM y reloj."""
import json
import os
import re
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import i18n
from app import asset_build, create_app

ROOT = Path(__file__).resolve().parent.parent
JS = sorted((ROOT / "static/js").glob("*.js"))
DYNAMIC_IDS = {"tlExit", "daylineScale", "scHud"}      # elementos que crea el propio JS


def template_ids():
    return re.findall(r'\bid="([^"]+)"', (ROOT / "templates/index.html").read_text(encoding="utf-8"))


class DomContract(unittest.TestCase):
    """El error «reading 'dataset' of null» venía de buscar elementos que la página no tenía."""

    def test_every_element_used_by_js_exists(self):
        ids = set(template_ids())
        for path in JS:
            src = path.read_text(encoding="utf-8")
            used = set(re.findall(r"""\$\(\s*['"`]#([\w-]+)""", src)) \
                | set(re.findall(r"""getElementById\(\s*['"]([\w-]+)""", src)) \
                | set(re.findall(r"""querySelector(?:All)?\(\s*['"`]#([\w-]+)""", src))
            missing = sorted(used - ids - DYNAMIC_IDS)
            self.assertEqual(missing, [], f"{path.name} usa ids que no existen en index.html")

    def test_no_duplicate_ids(self):
        ids = template_ids()
        self.assertEqual(sorted({i for i in ids if ids.count(i) > 1}), [])

    def test_tick_reschedules_before_painting(self):
        src = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
        loop = re.search(r"const loop = \(\) => \{(.+?)\};", src).group(1)
        self.assertLess(loop.index("setTimeout"), loop.index("tick()"),
                        "si tick() falla antes de reprogramarse, el reloj se detiene")


class Versions(unittest.TestCase):
    """Una instancia abierta durante una actualización no debe mezclar versiones."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = create_app(self.tmp.name).test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_template_is_always_read_from_disk(self):
        app = create_app(self.tmp.name)
        self.assertTrue(app.config["TEMPLATES_AUTO_RELOAD"])
        self.assertTrue(app.jinja_env.auto_reload)

    def test_assets_are_versioned(self):
        html = self.client.get("/").get_data(as_text=True)
        build = re.search(r'data-build="(\w+)"', html).group(1)
        for asset in ("css/style.css", "js/i18n.js", "js/app.js", "js/shortcuts.js", "js/datatools.js"):
            self.assertIn(f"/static/{asset}?v={build}", html)

    def test_state_reports_process_and_disk_build(self):
        state = self.client.get("/api/state").get_json()
        self.assertEqual(state["build"], state["disk_build"])

    def test_build_changes_when_a_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "static/js").mkdir(parents=True)
            (base / "templates").mkdir()
            js = base / "static/js/app.js"
            js.write_text("a")
            (base / "templates/index.html").write_text("<html>")
            before = asset_build(base)
            time.sleep(0.01)
            js.write_text("ab")
            self.assertNotEqual(asset_build(base), before)

    def test_restart_needed_is_detected(self):
        app = create_app(self.tmp.name)
        app.config["BUILD"] = "antiguo"           # proceso arrancado con otra versión
        state = app.test_client().get("/api/state").get_json()
        self.assertNotEqual(state["build"], state["disk_build"])


class FreshTranslations(unittest.TestCase):
    def test_catalog_reloads_when_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            for lang in i18n.LANGUAGES:
                shutil.copy(ROOT / f"static/i18n/{lang}.json", Path(tmp) / f"{lang}.json")
            with mock.patch.object(i18n, "_DIR", Path(tmp)), mock.patch.dict(i18n._CACHE, clear=True):
                self.assertEqual(i18n.tr("es", "hist.title"), "Historial")
                path = Path(tmp) / "es.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                data["hist.title"] = "Historial nuevo"
                path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                os.utime(path, ns=(time.time_ns(), time.time_ns() + 10_000_000))
                self.assertEqual(i18n.tr("es", "hist.title"), "Historial nuevo")


if __name__ == "__main__":
    unittest.main()
