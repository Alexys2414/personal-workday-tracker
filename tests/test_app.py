"""Pruebas de la API y de la persistencia (reinicio de la aplicación)."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import core
from app import create_app
from storage import JsonStore

D = date(2026, 10, 29)


class FakeClock:
    def __init__(self, value):
        self.set(value)

    def set(self, value):
        self.now = core.combine(D, value)

    def __call__(self):
        return self.now


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.clock = FakeClock("07:53")
        self.client = create_app(self.data, self.clock).test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def act(self, action, at, expect=None):
        self.clock.set(at)
        return self.client.post("/api/clock", json={"action": action, "expect": expect})

    def test_files_created_on_start(self):
        self.assertTrue((self.data / "records.json").exists())
        self.assertTrue((self.data / "settings.json").exists())

    def test_flow_survives_restart(self):
        self.assertEqual(self.act("start", "07:53").status_code, 200)
        self.assertEqual(self.act("break_start", "14:50").status_code, 200)
        self.assertEqual(self.act("break_end", "15:49").status_code, 200)

        # "Reinicio": nueva instancia de la app leyendo los mismos archivos.
        clock = FakeClock("15:49")
        client = create_app(self.data, clock).test_client()
        today = client.get("/api/state").get_json()["today"]
        self.assertEqual(today["status"], "working")
        self.assertEqual(today["local"]["clock_in"], "07:53:00")
        self.assertEqual(today["remaining_s"], 93 * 60)
        self.assertEqual(core.local_clock(core.parse_ts(today["exit_at"])), "17:23:00")

        raw = json.loads((self.data / "records.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["days"]["2026-10-29"]["clock_in"], "2026-10-29T07:53:00+01:00")

    def test_double_click_is_rejected(self):
        self.assertEqual(self.act("start", "08:00", expect="not_started").status_code, 200)
        r = self.act("start", "08:00", expect="not_started")
        self.assertEqual(r.status_code, 409)

    def test_manual_edit_and_delete(self):
        self.clock.set("20:00")
        r = self.client.put("/api/days/2026-10-28", json={
            "mode": "remote", "clock_in": "08:00", "clock_out": "17:30",
            "breaks": [{"start": "14:00", "end": "15:00"}], "notes": "Olvidé fichar"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["worked_s"], 510 * 60)

        r = self.client.put("/api/days/2026-10-28", json={"clock_in": "18:00", "clock_out": "17:00"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("posterior", r.get_json()["error"])

        week = self.client.get("/api/week/2026-10-28").get_json()
        self.assertEqual(week["summary"]["worked_s"], 510 * 60)

        self.assertEqual(self.client.delete("/api/days/2026-10-28").status_code, 200)
        self.assertEqual(self.client.delete("/api/days/2026-10-28").status_code, 404)

    def test_settings_roundtrip(self):
        r = self.client.put("/api/settings", json={"theme": "light", "profiles": {"friday": {"target_minutes": 390}}})
        self.assertEqual(r.status_code, 200)
        again = create_app(self.data, self.clock).test_client().get("/api/settings").get_json()
        self.assertEqual(again["theme"], "light")
        self.assertEqual(again["profiles"]["friday"]["target_minutes"], 390)

    def test_total_balance(self):
        self.clock.set("20:00")
        self.client.put("/api/days/2026-10-27", json={"clock_in": "08:00", "clock_out": "17:55",
                                                      "breaks": [{"start": "14:00", "end": "15:00"}]})
        self.client.put("/api/days/2026-09-15", json={"clock_in": "08:00", "clock_out": "17:15",
                                                      "breaks": [{"start": "14:00", "end": "15:00"}]})
        total = self.client.get("/api/state").get_json()["total"]
        self.assertEqual(total["balance_s"], 10 * 60)          # +25 −15
        self.assertEqual(total["since"], "2026-09-15")

    def test_only_local_host(self):
        self.assertEqual(self.client.get("/api/ping", headers={"Host": "evil.example:5000"}).status_code, 403)
        self.assertEqual(self.client.get("/api/ping", headers={"Host": "127.0.0.1:5000"}).status_code, 200)

    def test_shutdown_requires_json(self):
        self.assertEqual(self.client.post("/api/shutdown", data="x").status_code, 400)

    def test_month_endpoint(self):
        r = self.client.get("/api/month/2026-10")
        self.assertEqual(len(r.get_json()["days"]), 31)
        self.assertEqual(self.client.get("/api/month/2026-13").status_code, 400)


class StorageTests(unittest.TestCase):
    def test_corrupt_file_is_recovered_from_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.json"
            store = JsonStore(path, lambda: {"days": {}})
            store.save({"days": {"a": 1}})
            store.save({"days": {"a": 2}})          # .bak contiene {"a": 1}
            path.write_text("{ corrupto", encoding="utf-8")
            self.assertEqual(store.load(), {"days": {"a": 1}})
            self.assertEqual(len(list(Path(tmp).glob("records.corrupt-*.json"))), 1)
            self.assertFalse(list(Path(tmp).glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
