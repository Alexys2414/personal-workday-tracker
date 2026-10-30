"""Copias de seguridad completas: exportación, restauración, compatibilidad y fallos."""
import json
import os
import unittest
from datetime import date
from unittest import mock

import backup
import core
import storage
from tests.helpers import THU, AppCase, record


class BackupApi(AppCase, unittest.TestCase):
    def populate(self):
        self.act("start", "07:53")
        self.act("break_start", "14:00")
        self.act("break_end", "14:45")
        self.client.post(f"/api/days/{THU}/note", json={"target": "day", "text": "Nota ficticia"})
        self.client.put("/api/settings", json={"accent": "violet", "language": "en", "density": "compact",
                                               "notifications": {"leads": [15, 5]},
                                               "weekly_goal": {"mode": "custom", "custom_minutes": 2400}})
        self.client.put("/api/calendar/recurring/12-25", json={"label": "Navidad"})
        self.client.put("/api/calendar/days/2026-12-08", json={"type": "holiday", "label": "Inmaculada"})

    def export(self):
        res = self.client.get("/api/backup")
        self.assertEqual(res.status_code, 200)
        return res, res.get_data(as_text=True)

    def restore(self, text, **extra):
        preview = self.client.post("/api/backup/preview", json={"text": text})
        if preview.status_code != 200:
            return preview
        p = preview.get_json()
        body = {"text": text, "fingerprint": p["fingerprint"], "state": p["state"], "confirm": True, **extra}
        return self.client.post("/api/backup/restore", json=body)

    def test_full_export_contains_everything(self):
        self.populate()
        res, text = self.export()
        self.assertIn('filename="jornada-backup-2026-10-29.json"', res.headers["Content-Disposition"])
        data = json.loads(text)
        self.assertEqual(data["format"], "jornada-backup")
        self.assertEqual(data["schema_version"], backup.SCHEMA_VERSION)
        self.assertTrue(data["created_at"].startswith("2026-10-29T"))
        self.assertEqual(data["checksum"], backup.checksum(data["data"]))
        rec = data["data"]["records"]["days"][THU.isoformat()]
        self.assertEqual(rec["notes"], "Nota ficticia")
        self.assertEqual(len(rec["breaks"]), 1)
        s = data["data"]["settings"]
        self.assertEqual((s["accent"], s["language"], s["density"]), ("violet", "en", "compact"))
        self.assertEqual(s["notifications"]["leads"], [15, 5])
        self.assertEqual(s["weekly_goal"]["mode"], "custom")
        self.assertIn("shortcuts", s)
        self.assertIn("profiles", s)
        self.assertIn("summer", s)
        self.assertEqual(data["data"]["calendar"]["recurring"]["12-25"], {"label": "Navidad"})
        self.assertEqual(data["counts"]["days"], 1)

    def test_round_trip_restores_exactly(self):
        self.populate()
        _, text = self.export()
        snapshot = self.files()
        # Cambios posteriores que la restauración debe deshacer.
        self.client.delete(f"/api/days/{THU}")
        self.client.put("/api/settings", json={"accent": "amber", "language": "es"})
        self.client.delete("/api/calendar/recurring/12-25")
        res = self.restore(text)
        self.assertEqual(res.status_code, 200, res.get_json())
        for name in ("records.json", "settings.json", "calendar.json"):
            self.assertEqual(json.loads(self.files()[name]), json.loads(snapshot[name]), name)
        # Copia automática de lo que había justo antes.
        folder = self.data / "backups"
        pre = [p for p in folder.iterdir() if p.name.startswith("pre-restauracion")]
        self.assertEqual(len(pre), 1)
        self.assertEqual(json.loads((pre[0] / "settings.json").read_text())["accent"], "amber")

    def test_preview_summarises_and_warns(self):
        self.populate()
        _, text = self.export()
        p = self.client.post("/api/backup/preview", json={"text": text}).get_json()
        self.assertTrue(p["overwrites"])
        self.assertEqual(p["counts"]["clocked_days"], 1)
        self.assertEqual(p["counts"]["recurring"], 1)
        self.assertEqual(p["meta"]["schema_version"], 1)

    def test_preview_never_writes(self):
        self.populate()
        _, text = self.export()
        before = self.files()
        self.client.post("/api/backup/preview", json={"text": text})
        self.assertEqual(self.files(), before)

    def test_requires_explicit_confirmation(self):
        _, text = self.export()
        p = self.client.post("/api/backup/preview", json={"text": text}).get_json()
        res = self.client.post("/api/backup/restore", json={"text": text, "fingerprint": p["fingerprint"],
                                                            "state": p["state"]})
        self.assertEqual(res.status_code, 400)

    def test_data_changed_since_preview_is_rejected(self):
        _, text = self.export()
        p = self.client.post("/api/backup/preview", json={"text": text}).get_json()
        self.act("start", "08:00")             # fichaje desde otra ventana tras la vista previa
        res = self.client.post("/api/backup/restore", json={"text": text, "fingerprint": p["fingerprint"],
                                                            "state": p["state"], "confirm": True})
        self.assertEqual(res.status_code, 409)
        self.assertIn("clock_in", self.files()["records.json"].decode())

    def test_invalid_files_are_rejected_without_writing(self):
        self.populate()
        _, good = self.export()
        before = self.files()
        data = json.loads(good)
        cases = {
            "vacío": "",
            "no JSON": "{esto no es json",
            "otro formato": json.dumps({"format": "otra-app", "schema_version": 1, "data": {}}),
            "lista": "[1, 2, 3]",
            "versión futura": json.dumps({**data, "schema_version": 99}),
            "clave inesperada": json.dumps({**data, "extra": 1}),
            "checksum": json.dumps({**data, "data": {**data["data"], "settings": {**data["data"]["settings"],
                                                                                "accent": "blue"}}}),
        }
        bad_record = json.loads(good)
        bad_record["data"]["records"]["days"][THU.isoformat()]["clock_in"] = "ayer por la tarde"
        bad_record["checksum"] = backup.checksum(bad_record["data"])
        cases["registro corrupto"] = json.dumps(bad_record)
        bad_settings = json.loads(good)
        bad_settings["data"]["settings"]["accent"] = "fucsia"
        bad_settings["checksum"] = backup.checksum(bad_settings["data"])
        cases["ajuste inválido"] = json.dumps(bad_settings)
        unknown = json.loads(good)
        unknown["data"]["records"]["days"][THU.isoformat()]["hack"] = True
        unknown.pop("checksum")
        cases["campo desconocido"] = json.dumps(unknown)
        for label, text in cases.items():
            with self.subTest(label):
                res = self.client.post("/api/backup/preview", json={"text": text})
                self.assertEqual(res.status_code, 400, label)
                self.assertTrue(res.get_json()["error"])
        self.assertEqual(self.files(), before)

    def test_too_big_is_rejected(self):
        with mock.patch.object(backup, "MAX_BYTES", 1000):
            _, text = self.export()
            res = self.client.post("/api/backup/preview", json={"text": text + " " * 2000})
            self.assertEqual(res.status_code, 400)

    def test_old_backup_without_calendar_and_v2_settings(self):
        """Compatibilidad: una copia con ajustes antiguos (v2) y sin calendario se migra al restaurar."""
        old_settings = {k: v for k, v in core.default_settings().items()
                        if k not in ("accent", "density", "motion", "cards", "weekly_goal", "day_types",
                                     "notifications")}
        old_settings["version"] = 2
        old_settings["theme"] = "dark"
        data = {"records": {"version": 1, "days": {THU.isoformat(): record(THU, "08:00", "17:30",
                                                                             [("14:00", "15:00")])}},
                "settings": old_settings}
        text = json.dumps({"format": "jornada-backup", "schema_version": 1, "app_version": "2.0",
                           "created_at": "2026-10-01T10:00:00+02:00", "data": data})
        res = self.restore(text)
        self.assertEqual(res.status_code, 200, res.get_json())
        s = json.loads(self.files()["settings.json"])
        self.assertEqual(s["version"], core.SETTINGS_VERSION)
        self.assertEqual(s["theme"], "dark")
        self.assertEqual(s["accent"], "teal")
        self.assertEqual(json.loads(self.files()["calendar.json"])["days"], {})

    def test_failure_mid_write_keeps_previous_state(self):
        self.populate()
        _, text = self.export()
        self.client.put("/api/settings", json={"accent": "coral"})
        self.client.delete("/api/calendar/recurring/12-25")
        before = self.files()
        real_replace = os.replace
        calls = {"n": 0}

        def flaky(src, dst):
            if str(src).endswith(".tmp"):
                calls["n"] += 1
                if calls["n"] == 2:              # falla al sustituir el segundo archivo
                    raise OSError("disco lleno (simulado)")
            return real_replace(src, dst)

        with mock.patch("storage.os.replace", side_effect=flaky), self.assertLogs("app", "ERROR"):
            res = self.restore(text)
        self.assertEqual(res.status_code, 500)         # el error llega al usuario; los datos no cambian
        self.assertEqual(calls["n"], 2)
        after = self.files()
        for name in ("records.json", "settings.json", "calendar.json"):
            self.assertEqual(json.loads(after[name]), json.loads(before[name]), name)
        self.assertEqual(list(self.data.glob(".*.tmp")), [])


class SaveMany(unittest.TestCase):
    def test_all_or_nothing(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            a = storage.JsonStore(Path(tmp) / "a.json", dict)
            b = storage.JsonStore(Path(tmp) / "b.json", dict)
            a.save({"v": 1})
            b.save({"v": 1})
            storage.save_many([(a, {"v": 2}), (b, {"v": 2})])
            self.assertEqual((a.load(), b.load()), ({"v": 2}, {"v": 2}))
            with mock.patch("storage.json.dump", side_effect=[None, ValueError("roto")]):
                with self.assertRaises(ValueError):
                    storage.save_many([(a, {"v": 3}), (b, {"v": 3})])
            self.assertEqual((a.load(), b.load()), ({"v": 2}, {"v": 2}))


class SettingsMigrationBackup(unittest.TestCase):
    def test_old_settings_are_copied_before_migration(self):
        import tempfile
        from pathlib import Path

        from app import create_app
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            old = {"version": 2, "theme": "light", "language": "en",
                   "shortcuts": {"start_day": "Ctrl+Alt+KeyJ"}}
            (data / "settings.json").write_text(json.dumps(old))
            create_app(data)
            folders = list((data / "backups").glob("pre-migracion-ajustes-v2-*"))
            self.assertEqual(len(folders), 1)
            self.assertEqual(json.loads((folders[0] / "settings.json").read_text()), old)
            new = json.loads((data / "settings.json").read_text())
            self.assertEqual((new["theme"], new["language"]), ("light", "en"))
            self.assertEqual(new["shortcuts"]["start_day"], "Ctrl+Alt+KeyJ")
            self.assertEqual(new["version"], core.SETTINGS_VERSION)
            create_app(data)                     # ya migrado: no hay segunda copia
            self.assertEqual(len(list((data / "backups").glob("pre-migracion-*"))), 1)


if __name__ == "__main__":
    unittest.main()
