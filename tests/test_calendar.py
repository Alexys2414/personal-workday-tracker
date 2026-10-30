"""Festivos, vacaciones y ausencias: reglas de cálculo, rangos, importación y fichajes históricos."""
import json
import unittest
from datetime import date

import core
import daymarks
from tests.helpers import SETTINGS, THU, AppCase, record

NOW = core.combine(THU, "12:00")


def cal(days=None, recurring=None):
    return core.normalize_calendar({"days": days or {}, "recurring": recurring or {}})


class Rules(unittest.TestCase):
    def test_recurring_holiday_every_year(self):
        c = cal(recurring={"12-25": {"label": "Navidad"}})
        for year in (2025, 2026, 2031):
            m = core.day_mark(date(year, 12, 25), c)
            self.assertEqual((m["type"], m["label"], m["recurring"]), ("holiday", "Navidad", True))
        self.assertIsNone(core.day_mark(date(2026, 12, 24), c))

    def test_specific_day_overrides_recurring(self):
        c = cal(days={"2026-12-25": {"type": "vacation"}}, recurring={"12-25": {}})
        self.assertEqual(core.day_mark(date(2026, 12, 25), c)["type"], "vacation")
        self.assertEqual(core.day_mark(date(2027, 12, 25), c)["type"], "holiday")

    def test_free_day_has_no_target_and_no_deficit(self):
        c = cal(days={"2026-10-20": {"type": "holiday"}})
        day = core.compute_day(date(2026, 10, 20), None, SETTINGS, NOW, c)
        self.assertEqual((day["target_s"], day["balance_s"], day["counted"]), (0, 0, False))
        self.assertEqual(day["day_type"], "holiday")
        self.assertEqual(day["color"], "gray")

    def test_configurable_permit_keeps_target(self):
        s = core.normalize_settings({"day_types": {"permit": "target"}})
        c = cal(days={"2026-10-20": {"type": "permit"}, "2026-11-03": {"type": "permit"}})
        past = core.compute_day(date(2026, 10, 20), None, s, NOW, c)
        self.assertEqual((past["target_s"], past["balance_s"], past["counted"]), (510 * 60, -510 * 60, True))
        self.assertEqual(past["color"], "red")
        future = core.compute_day(date(2026, 11, 3), None, s, NOW, c)
        self.assertEqual((future["balance_s"], future["counted"]), (0, False))
        # Con «sin objetivo» (por defecto) el mismo permiso no genera déficit.
        self.assertEqual(core.compute_day(date(2026, 10, 20), None, SETTINGS, NOW, c)["balance_s"], 0)

    def test_summary_counts_configured_absence(self):
        s = core.normalize_settings({"day_types": {"sick": "target"}})
        c = cal(days={"2026-10-26": {"type": "sick"}})
        dates = core.week_dates(THU)
        computed = [core.compute_day(d, None, s, NOW, c) for d in dates]
        summary = core.summarize(computed, NOW)
        self.assertEqual(summary["balance_s"], -510 * 60)

    def test_holiday_inside_summer_intensive(self):
        s = core.normalize_settings({"summer": {"periods": [{"start": "2026-07-01", "end": "2026-08-31"}]}})
        c = cal(days={"2026-08-14": {"type": "holiday"}})
        hol = core.compute_day(date(2026, 8, 14), None, s, NOW, c)
        self.assertEqual(hol["target_s"], 0)
        self.assertEqual(core.compute_day(date(2026, 8, 13), None, s, NOW, c)["target_s"], 420 * 60)

    def test_holiday_on_non_working_day(self):
        c = cal(days={"2026-10-31": {"type": "holiday"}})          # sábado
        day = core.compute_day(date(2026, 10, 31), None, SETTINGS, NOW, c)
        self.assertEqual((day["status"], day["target_s"]), ("nonworking", 0))

    def test_working_on_a_holiday_is_all_extra(self):
        c = cal(days={THU.isoformat(): {"type": "holiday"}})
        rec = core.apply_action("start", THU, None, SETTINGS, core.combine(THU, "09:00"), c)
        self.assertEqual((rec["target_minutes"], rec["day_type"]), (0, "holiday"))
        rec = core.apply_action("stop", THU, rec, SETTINGS, core.combine(THU, "11:00"), c)
        day = core.compute_day(THU, rec, SETTINGS, NOW, c)
        self.assertEqual(day["balance_s"], 2 * 3600)

    def test_open_record_on_holiday_survives_settings_change(self):
        c = cal(days={THU.isoformat(): {"type": "holiday"}})
        rec = core.apply_action("start", THU, None, SETTINGS, core.combine(THU, "09:00"), c)
        s = core.normalize_settings({"profiles": {"normal": {"target_minutes": 480}}})
        core.refresh_open_record(rec, THU, s, c)
        self.assertEqual(rec["target_minutes"], 0)

    def test_historic_records_unchanged_by_marks(self):
        rec = record(date(2026, 10, 20), "08:00", "17:00", [("14:00", "15:00")])
        c = cal(days={"2026-10-20": {"type": "holiday"}})
        plain = core.compute_day(date(2026, 10, 20), rec, SETTINGS, NOW)
        marked = core.compute_day(date(2026, 10, 20), rec, SETTINGS, NOW, c)
        self.assertEqual(plain["balance_s"], marked["balance_s"])
        self.assertEqual(plain["target_s"], marked["target_s"])
        self.assertEqual(marked["day_type"], "holiday")              # se muestra, no recalcula

    def test_validation(self):
        bad = [{"days": {"2026-13-01": {"type": "holiday"}}}, {"days": {"2026-10-01": {"type": "party"}}},
               {"recurring": {"02-30": {}}}, {"days": {"2026-10-01": {"type": "holiday", "label": "x" * 200}}},
               {"version": 9}, []]
        for raw in bad:
            with self.subTest(raw), self.assertRaises(core.ValidationError):
                core.normalize_calendar(raw)
        self.assertIn("02-29", core.normalize_calendar({"recurring": {"02-29": {}}})["recurring"])


class Ranges(unittest.TestCase):
    def test_vacation_range_skips_weekends_and_holidays(self):
        c = cal(days={"2026-08-14": {"type": "holiday"}}, recurring={"08-15": {}})
        plan = daymarks.range_plan(date(2026, 8, 10), date(2026, 8, 23), {"type": "vacation"}, SETTINGS, c, {})
        self.assertEqual(plan["count"], 9)                           # 10 laborables − 1 festivo
        self.assertEqual(plan["skipped_holiday"], ["2026-08-14"])
        self.assertEqual(plan["skipped_nonworking"], 4)
        self.assertNotIn("2026-08-15", plan["dates"])

    def test_range_reports_conflicts(self):
        days = {"2026-08-11": record(date(2026, 8, 11), "08:00", "17:00", [("14:00", "15:00")])}
        plan = daymarks.range_plan(date(2026, 8, 10), date(2026, 8, 12), {"type": "vacation"}, SETTINGS, cal(), days)
        self.assertEqual(plan["conflicts"], ["2026-08-11"])

    def test_range_limits(self):
        with self.assertRaises(core.ValidationError):
            daymarks.range_plan(date(2026, 8, 10), date(2026, 8, 1), {"type": "vacation"}, SETTINGS, cal(), {})
        with self.assertRaises(core.ValidationError):
            daymarks.range_plan(date(2026, 1, 1), date(2028, 1, 1), {"type": "vacation"}, SETTINGS, cal(), {})


class Import(unittest.TestCase):
    def test_csv(self):
        text = "fecha;nombre;recurrente\n2026-12-08;Inmaculada;\n25/12/2026;Navidad;sí\n12-31;Nochevieja;\nmal;X;\n"
        r = daymarks.parse_import(text, "festivos.csv")
        keys = [(i["key"], i["recurring"]) for i in r["items"]]
        self.assertEqual(keys, [("2026-12-08", False), ("12-25", True), ("12-31", True)])
        self.assertEqual(len(r["errors"]), 1)

    def test_csv_without_header_and_commas(self):
        r = daymarks.parse_import("2026-01-06,Reyes\n2026-05-01,Trabajo\n", "f.csv")
        self.assertEqual([i["label"] for i in r["items"]], ["Reyes", "Trabajo"])

    def test_json(self):
        text = json.dumps({"holidays": [{"date": "2026-10-12", "label": "Fiesta"}, {"date": "--01-01", "recurring": True},
                                        {"date": "2026-08-03", "type": "vacation"}, {"date": "2026-02-30"}]})
        r = daymarks.parse_import(text, "f.json")
        self.assertEqual([i["key"] for i in r["items"]], ["2026-10-12", "01-01", "2026-08-03"])
        self.assertEqual(r["items"][2]["type"], "vacation")
        self.assertEqual(len(r["errors"]), 1)
        merged, n = daymarks.merge_import(cal(), r["items"])
        self.assertEqual(n, 3)
        self.assertIn("01-01", merged["recurring"])
        self.assertEqual(merged["days"]["2026-08-03"]["type"], "vacation")

    def test_bad_files(self):
        for text in ("", "{nope", json.dumps({"x": 1})):
            with self.subTest(text), self.assertRaises(core.ValidationError):
                daymarks.parse_import(text, "f.json")


class CalendarApi(AppCase, unittest.TestCase):
    def test_holiday_crud(self):
        self.assertEqual(self.client.put("/api/calendar/days/2026-12-08", json={"type": "holiday", "label": "Inmaculada"}).status_code, 200)
        self.assertEqual(self.client.put("/api/calendar/recurring/12-25", json={"label": "Navidad"}).status_code, 200)
        self.assertEqual(self.client.put("/api/calendar/days/2026-12-08", json={"type": "holiday", "label": "Editado"}).status_code, 200)
        c = self.client.get("/api/calendar").get_json()["calendar"]
        self.assertEqual(c["days"]["2026-12-08"]["label"], "Editado")
        self.assertEqual(self.client.delete("/api/calendar/days/2026-12-08").status_code, 200)
        self.assertEqual(self.client.delete("/api/calendar/recurring/12-25").status_code, 200)
        self.assertEqual(self.client.delete("/api/calendar/recurring/12-25").status_code, 404)
        self.assertEqual(self.client.put("/api/calendar/days/2026-12-08", json={"type": "fiesta"}).status_code, 400)

    def test_marking_a_registered_day_asks_first(self):
        self.act("start", "08:00")
        self.act("stop", "11:00")
        records = self.files()["records.json"]
        res = self.client.put(f"/api/calendar/days/{THU}", json={"type": "holiday"})
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.get_json()["conflicts"][0]["date"], THU.isoformat())
        self.assertEqual(self.files()["records.json"], records)
        # «Solo marcar»: la jornada no cambia.
        self.assertEqual(self.client.put(f"/api/calendar/days/{THU}", json={"type": "holiday", "apply": False}).status_code, 200)
        self.assertEqual(self.files()["records.json"], records)
        day = self.client.get(f"/api/days/{THU}").get_json()
        self.assertEqual((day["day_type"], day["target_s"]), ("holiday", 510 * 60))
        # «Aplicar reglas»: los tiempos se conservan, el objetivo pasa a 0 y hay copia previa.
        self.assertEqual(self.client.put(f"/api/calendar/days/{THU}", json={"type": "holiday", "apply": True}).status_code, 200)
        day = self.client.get(f"/api/days/{THU}").get_json()
        self.assertEqual((day["target_s"], day["worked_s"], day["local"]["clock_in"]), (0, 3 * 3600, "08:00:00"))
        self.assertTrue(list((self.data / "backups").glob("pre-tipo-de-dia-*")))

    def test_range_api_and_preview_count(self):
        body = {"from": "2026-11-02", "to": "2026-11-08", "type": "vacation"}
        p = self.client.post("/api/calendar/range/preview", json=body).get_json()
        self.assertEqual(p["count"], 5)
        self.assertEqual(self.client.post("/api/calendar/range", json={**body, "count": 4}).status_code, 409)
        self.assertEqual(self.client.post("/api/calendar/range", json={**body, "count": 5}).status_code, 200)
        w = self.client.get("/api/weekly/2026-11-04").get_json()
        self.assertEqual(w["goal_s"], 0)

    def test_import_api(self):
        p = self.client.post("/api/calendar/import/preview", json={"text": "2026-12-08;Inmaculada\nmal;x", "filename": "a.csv"}).get_json()
        self.assertEqual(len(p["items"]), 1)
        self.assertTrue(p["errors"][0]["message"])
        res = self.client.post("/api/calendar/import", json={"text": "2026-12-08;Inmaculada", "filename": "a.csv"})
        self.assertEqual(res.get_json()["imported"], 1)
        up = self.client.get("/api/state").get_json()["upcoming"]
        self.assertEqual(up[0]["label"], "Inmaculada")


class Upcoming(unittest.TestCase):
    def test_groups_consecutive_days(self):
        c = cal(days={"2026-11-06": {"type": "vacation"}, "2026-11-09": {"type": "vacation"},
                      "2026-11-10": {"type": "vacation"}}, recurring={"12-25": {"label": "Navidad"}})
        up = __import__("insights").upcoming_marks(c, SETTINGS, THU)
        self.assertEqual((up[0]["from"], up[0]["to"], up[0]["days"]), ("2026-11-06", "2026-11-10", 3))
        self.assertEqual(up[1]["label"], "Navidad")


if __name__ == "__main__":
    unittest.main()
