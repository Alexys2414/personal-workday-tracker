"""Personalización (tema, acento, densidad, animaciones, tarjetas), avisos y vista compacta."""
import json
import re
import unittest
from pathlib import Path

import core
from app import create_app
from tests.helpers import THU, AppCase

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "static/css/style.css").read_text(encoding="utf-8")


class Validation(unittest.TestCase):
    def test_defaults(self):
        s = core.default_settings()
        self.assertEqual((s["accent"], s["density"], s["motion"]), ("teal", "comfortable", "normal"))
        self.assertTrue(all(s["cards"].values()))
        self.assertFalse(s["notifications"]["desktop"])        # nunca se activa sin permiso explícito
        self.assertEqual(s["shortcuts"]["open_simulator"], "Alt+Shift+KeyS")

    def test_valid_values(self):
        s = core.normalize_settings({"accent": "coral", "density": "compact", "motion": "expressive",
                                     "cards": {"history": False, "unknown": False},
                                     "notifications": {"leads": [5, 30, 5, 120], "sound": True}})
        self.assertEqual((s["accent"], s["density"], s["motion"]), ("coral", "compact", "expressive"))
        self.assertFalse(s["cards"]["history"])
        self.assertNotIn("unknown", s["cards"])
        self.assertEqual(s["notifications"]["leads"], [120, 30, 5])

    def test_invalid_values(self):
        for raw in ({"accent": "fucsia"}, {"density": "xl"}, {"motion": "loco"}, {"cards": []},
                    {"notifications": {"leads": [0]}}, {"notifications": {"leads": list(range(1, 20))}},
                    {"notifications": {"break_pending_after": 5}}, {"weekly_goal": {"mode": "x"}},
                    {"weekly_goal": {"custom_minutes": -1}}, {"day_types": {"holiday": "maybe"}}):
            with self.subTest(raw), self.assertRaises(core.ValidationError):
                core.normalize_settings(raw)

    def test_new_defaults_do_not_overwrite_old_values(self):
        old = {"version": 2, "theme": "dark", "time_format": "12h", "language": "en",
               "profiles": {"normal": {"target_minutes": 480}}, "shortcuts": {"toggle_theme": None}}
        s = core.normalize_settings(old)
        self.assertEqual((s["theme"], s["time_format"], s["language"]), ("dark", "12h", "en"))
        self.assertEqual(s["profiles"]["normal"]["target_minutes"], 480)
        self.assertIsNone(s["shortcuts"]["toggle_theme"])
        self.assertEqual(s["version"], core.SETTINGS_VERSION)


class Persistence(AppCase, unittest.TestCase):
    def test_preferences_survive_restart(self):
        body = {"theme": "light", "accent": "violet", "density": "compact", "motion": "reduced",
                "cards": {"quick_stats": False, "holidays": False},
                "notifications": {"in_app": False, "desktop": True, "leads": [10], "break_over": True},
                "weekly_goal": {"mode": "custom", "custom_minutes": 2280, "compensation": False},
                "day_types": {"permit": "target"}}
        self.assertEqual(self.client.put("/api/settings", json=body).status_code, 200)
        raw = json.loads((self.data / "settings.json").read_text())
        self.assertEqual(raw["accent"], "violet")
        restarted = create_app(self.data, self.clock).test_client()
        s = restarted.get("/api/settings").get_json()
        self.assertEqual((s["theme"], s["accent"], s["density"], s["motion"]), ("light", "violet", "compact", "reduced"))
        self.assertEqual((s["cards"]["quick_stats"], s["cards"]["history"]), (False, True))
        self.assertEqual(s["notifications"]["leads"], [10])
        self.assertTrue(s["notifications"]["break_over"])
        self.assertEqual(s["weekly_goal"]["custom_minutes"], 2280)
        self.assertEqual(s["day_types"]["permit"], "target")

    def test_partial_update_keeps_other_preferences(self):
        self.client.put("/api/settings", json={"accent": "amber", "motion": "expressive"})
        self.client.put("/api/settings", json={"theme": "dark"})      # el botón de tema solo envía esto
        s = self.client.get("/api/settings").get_json()
        self.assertEqual((s["accent"], s["motion"], s["theme"]), ("amber", "expressive", "dark"))


class StyleContract(unittest.TestCase):
    """Comprobaciones estáticas del CSS: cada acento existe en ambos temas y se respeta el movimiento reducido."""

    def test_every_accent_in_both_themes(self):
        for accent in core.ACCENTS[1:]:
            for theme in ("light", "dark"):
                self.assertRegex(CSS, rf':root\[data-theme="{theme}"\]\[data-accent="{accent}"\]\s*\{{[^}}]*--work:')

    def test_accent_text_contrast(self):
        """El color de acento como texto debe tener contraste ≥ 4.5:1 sobre la superficie del tema."""
        def lum(hexcolor):
            rgb = [int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
            return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

        def ratio(a, b):
            hi, lo = sorted((lum(a), lum(b)), reverse=True)
            return (hi + 0.05) / (lo + 0.05)
        surfaces = {"light": "#ffffff", "dark": "#121b18"}
        for theme, surface in surfaces.items():
            base = re.search(rf':root\[data-theme="{theme}"\] \{{(.*?)\}}', CSS, re.S).group(1)
            colors = {"teal": re.search(r"--work: (#[0-9a-f]{6})", base).group(1)}
            for accent in core.ACCENTS[1:]:
                block = re.search(rf':root\[data-theme="{theme}"\]\[data-accent="{accent}"\]\s*\{{([^}}]*)\}}', CSS).group(1)
                colors[accent] = re.search(r"--work: (#[0-9a-f]{6})", block).group(1)
            for accent, color in colors.items():
                with self.subTest(theme=theme, accent=accent):
                    self.assertGreaterEqual(ratio(color, surface), 4.5)

    def test_density_and_motion_rules(self):
        self.assertIn(':root[data-density="compact"]', CSS)
        self.assertIn('[data-motion="reduced"] *', CSS)
        self.assertIn("@media (prefers-reduced-motion: reduce)", CSS)
        common = (ROOT / "static/js/common.js").read_text(encoding="utf-8")
        # El sistema siempre manda: con movimiento reducido en el sistema, nunca se anima.
        self.assertIn("root.dataset.motion = reducedMotion.matches ? 'reduced'", common)
        self.assertIn("reducedMotion.matches || state.settings?.motion === 'reduced'", common)
        for page in ("index.html", "compact.html"):
            html = (ROOT / "templates" / page).read_text(encoding="utf-8")
            self.assertIn("prefers-reduced-motion: reduce)').matches ? 'reduced'", html, page)

    def test_hidden_cards_never_include_main_panel(self):
        html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
        cards = set(re.findall(r'data-card="([\w_]+)"', html))
        self.assertEqual(cards, {"week", "holidays", "history"})       # estadísticas: por panel, en JS
        hero = html[html.index('id="hero"'):html.index('class="card today-card"')]
        self.assertNotIn("data-card", hero)


class CompactAndSync(AppCase, unittest.TestCase):
    def test_compact_page_and_light_state(self):
        html = self.client.get("/compact").get_data(as_text=True)
        self.assertIn('id="widget"', html)
        self.assertIn("js/compact.js", html)
        today = self.client.get("/api/today").get_json()
        self.assertEqual(today["today"]["status"], "not_started")
        self.assertIn("settings", today)

    def test_two_windows_never_duplicate_an_action(self):
        """Panel y vista compacta pulsan «Iniciar descanso» con el mismo estado esperado: solo uno vale."""
        self.act("start", "08:00", expect="not_started")
        first = self.act("break_start", "11:00", expect="working")
        second = self.act("break_start", "11:00", expect="working")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        rec = json.loads((self.data / "records.json").read_text())["days"][THU.isoformat()]
        self.assertEqual(len(rec["breaks"]), 1)
        # La otra ventana, al resincronizar, ve el descanso en curso.
        self.assertEqual(self.client.get("/api/today").get_json()["today"]["status"], "on_break")
        self.assertEqual(self.act("break_end", "11:20", expect="on_break").status_code, 200)
        self.assertEqual(self.act("break_end", "11:20", expect="on_break").status_code, 409)

    def test_sync_code_paths(self):
        common = (ROOT / "static/js/common.js").read_text(encoding="utf-8")
        compact = (ROOT / "static/js/compact.js").read_text(encoding="utf-8")
        app = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
        self.assertIn("new BroadcastChannel('jornada-sync')", common)
        self.assertIn("'storage'", common)                                     # alternativa sin BroadcastChannel
        self.assertIn("expect: state.today.status", compact)
        self.assertIn("syncSend()", compact)
        self.assertIn("onSync(() => refreshAll())", app)
        # Sin peticiones cada segundo: el contador es local y la foto del servidor se pide cada 30 s.
        self.assertIn("setInterval(() => { if (!document.hidden) load(); }, 30000)", compact)
        self.assertNotIn("api('/api/today')", compact.split("function tick")[1].split("async function doAction")[0])

    def test_notification_permission_only_on_request(self):
        js = "".join((ROOT / "static/js" / f).read_text(encoding="utf-8") for f in ("app.js", "common.js", "compact.js"))
        calls = [m.start() for m in re.finditer(r"requestDesktopPermission\(\)", js)]
        self.assertEqual(len(calls), 1)                                 # solo en el interruptor de Ajustes
        self.assertIn("$('#nDesktop').addEventListener('change'", js[max(0, calls[0] - 400):calls[0]])
        self.assertNotIn("Notification.requestPermission", js)


if __name__ == "__main__":
    unittest.main()
