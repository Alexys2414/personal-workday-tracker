"""Simulador de salida, objetivo semanal y compensación simulada (solo lectura)."""
import json
import unittest
from datetime import date, timedelta

import core
import insights
from tests.helpers import FRI, SETTINGS, THU, AppCase, record

NOW = core.combine(THU, "15:49")


def hm(iso):
    return core.local_clock(core.parse_ts(iso))[:5]


class Simulator(unittest.TestCase):
    def setUp(self):
        self.rec = record(THU, "07:53", None, [("14:50", "15:49")], now=NOW)

    def test_baseline_matches_dashboard_exit(self):
        real = core.compute_day(THU, self.rec, SETTINGS, NOW)
        r = insights.simulate(THU, self.rec, SETTINGS, NOW)
        self.assertEqual(r["base"]["exit"], real["exit_at"])
        self.assertEqual(hm(r["base"]["exit"]), "17:23")
        self.assertEqual(r["base"]["balance_s"], 0)
        self.assertEqual(r["diff"], {"exit_s": 0, "worked_s": 0, "balance_s": 0, "break_s": 0})

    def test_baseline_matches_dashboard_during_break(self):
        rec = record(THU, "07:53", None, [("14:50", None)], now=NOW)
        real = core.compute_day(THU, rec, SETTINGS, NOW)
        r = insights.simulate(THU, rec, SETTINGS, NOW)
        self.assertEqual(r["base"]["exit"], real["exit_at"])

    def test_extra_break_moves_exit(self):
        r = insights.simulate(THU, self.rec, SETTINGS, NOW, {"extra_break_minutes": 20})
        # 59 min hechos + 20 = 79; el mínimo (60) ya estaba casi cumplido: la salida se retrasa 19 min.
        self.assertEqual(hm(r["sim"]["exit"]), "17:42")
        self.assertEqual(r["diff"]["exit_s"], 19 * 60)
        self.assertEqual(r["sim"]["worked_s"], 510 * 60)

    def test_pending_mandatory_break_is_added(self):
        rec = record(THU, "08:00", None, [("14:00", "14:30")], now=NOW)
        r = insights.simulate(THU, rec, SETTINGS, NOW)
        self.assertEqual(r["base"]["added_break_s"], 30 * 60)
        self.assertEqual(hm(r["base"]["exit"]), "17:30")

    def test_optional_break(self):
        r = insights.simulate(THU, self.rec, SETTINGS, NOW, {"use_optional": True})
        # mínimo 60 + opcional 30 = 90 min de descanso.
        self.assertEqual(r["sim"]["break_s"], 90 * 60)
        self.assertEqual(hm(r["sim"]["exit"]), "17:53")
        self.assertNotIn("break_long", r["sim"]["flags"])

    def test_desired_exit_overtime_and_early_exit(self):
        late = insights.simulate(THU, self.rec, SETTINGS, NOW, {"exit": "18:30"})
        self.assertEqual(late["sim"]["balance_s"], 67 * 60)
        early = insights.simulate(THU, self.rec, SETTINGS, NOW, {"exit": "17:00"})
        self.assertEqual(early["sim"]["balance_s"], -23 * 60)
        self.assertEqual(early["diff"]["exit_s"], -23 * 60)

    def test_tomorrow_with_other_start(self):
        r = insights.simulate(FRI, None, SETTINGS, NOW, {"clock_in": "07:45"})
        # Viernes intensivo: 7 h sin descanso obligatorio.
        self.assertEqual(r["defaults"]["target_minutes"], 420)
        self.assertEqual(hm(r["sim"]["exit"]), "14:45")
        self.assertEqual(hm(r["base"]["exit"]), "15:00")

    def test_summer_intensive_profile(self):
        s = core.normalize_settings({"summer": {"periods": [{"start": "2026-07-01", "end": "2026-08-31"}]}})
        day = date(2026, 7, 15)
        r = insights.simulate(day, None, s, core.combine(day, "07:00"), {"clock_in": "08:00"})
        self.assertEqual(r["defaults"]["target_minutes"], 420)
        self.assertEqual(hm(r["sim"]["exit"]), "15:00")

    def test_custom_target(self):
        r = insights.simulate(THU, self.rec, SETTINGS, NOW, {"target_minutes": 480})
        self.assertEqual(hm(r["sim"]["exit"]), "16:53")

    def test_finished_day_compares_against_real_exit(self):
        rec = record(THU, "08:00", "17:30", [("14:00", "15:00")])
        r = insights.simulate(THU, rec, SETTINGS, NOW, {"exit": "18:00"})
        self.assertEqual(hm(r["base"]["exit"]), "17:30")
        self.assertEqual(r["diff"]["balance_s"], 30 * 60)

    def test_invalid_values(self):
        for params in ({"exit": "07:00"}, {"exit": "25:00"}, {"extra_break_minutes": -5},
                       {"extra_break_minutes": 9999}, {"clock_in": "xx"}):
            with self.subTest(params), self.assertRaises(core.ValidationError):
                insights.simulate(THU, self.rec, SETTINGS, NOW, params)

    def test_simulate_does_not_mutate_record(self):
        before = json.dumps(self.rec, sort_keys=True)
        insights.simulate(THU, self.rec, SETTINGS, NOW, {"exit": "19:00", "extra_break_minutes": 60})
        self.assertEqual(json.dumps(self.rec, sort_keys=True), before)


class SimulatorApi(AppCase, unittest.TestCase):
    def test_api_never_writes(self):
        self.act("start", "07:53")
        self.act("break_start", "14:50")
        self.clock.set("15:20")
        before = self.files()
        mtimes = {p.name: p.stat().st_mtime_ns for p in self.data.glob("*.json")}
        for params in ({}, {"extra_break_minutes": 30}, {"exit": "18:30"}, {"use_optional": True}):
            res = self.client.post("/api/simulate", json={"params": params})
            self.assertEqual(res.status_code, 200)
        res = self.client.post("/api/simulate", json={"date": "2026-10-30", "params": {"clock_in": "07:45"}})
        self.assertEqual(res.status_code, 200)
        self.client.post("/api/compensation", json={"minutes": 45})
        self.assertEqual(self.files(), before)
        self.assertEqual({p.name: p.stat().st_mtime_ns for p in self.data.glob("*.json")}, mtimes)
        self.assertEqual(self.client.get("/api/today").get_json()["today"]["status"], "on_break")

    def test_api_validation(self):
        res = self.client.post("/api/simulate", json={"params": {"exit": "nope"}})
        self.assertEqual(res.status_code, 400)


class WeeklyGoal(unittest.TestCase):
    def test_derived_from_profiles(self):
        w = insights.weekly_goal(THU, {}, SETTINGS, NOW)
        self.assertEqual(w["goal_s"], 41 * 3600)        # 4 × 8:30 + 7:00
        self.assertEqual(w["mode"], "auto")

    def test_custom_goal(self):
        s = core.normalize_settings({"weekly_goal": {"mode": "custom", "custom_minutes": 40 * 60}})
        self.assertEqual(insights.weekly_goal(THU, {}, s, NOW)["goal_s"], 40 * 3600)

    def test_week_with_vacation(self):
        cal = core.normalize_calendar({"days": {"2026-10-26": {"type": "vacation"}, "2026-10-27": {"type": "vacation"}}})
        w = insights.weekly_goal(THU, {}, SETTINGS, NOW, cal)
        self.assertEqual(w["goal_s"], 41 * 3600 - 2 * 510 * 60)
        s = core.normalize_settings({"weekly_goal": {"mode": "custom", "custom_minutes": 40 * 60}})
        w = insights.weekly_goal(THU, {}, s, NOW, cal)
        self.assertEqual(w["excused_s"], 2 * 510 * 60)
        self.assertEqual(w["goal_s"], 40 * 3600 - 2 * 510 * 60)

    def test_balance_vs_progress(self):
        days = {
            "2026-10-26": record(date(2026, 10, 26), "08:00", "17:45", [("14:00", "15:00")]),   # +0:15
            "2026-10-27": record(date(2026, 10, 27), "08:00", "17:00", [("14:00", "15:00")]),   # −0:30
            THU.isoformat(): record(THU, "07:53", None, [("14:50", "15:49")], now=NOW),          # abierta
        }
        w = insights.weekly_goal(THU, days, SETTINGS, NOW, None)
        self.assertEqual(w["closed_balance_s"], -15 * 60)            # la abierta no cuenta como déficit
        self.assertEqual(w["closed_days"], 2)
        worked = (8 * 60 + 45 + 8 * 60) * 60 + core.compute_day(THU, days[THU.isoformat()], SETTINGS, NOW)["worked_s"]
        self.assertEqual(w["worked_s"], worked)
        self.assertEqual(w["remaining_s"], 41 * 3600 - worked)
        self.assertEqual(w["extra_s"], 0)
        self.assertAlmostEqual(w["progress"], worked / (41 * 3600), places=3)

    def test_compensation(self):
        days = {"2026-10-26": record(date(2026, 10, 26), "08:00", "18:15", [("14:00", "15:00")])}  # +0:45
        c = insights.compensation(None, None, days, SETTINGS, NOW, None)
        self.assertEqual(c["date"], "2026-10-30")                    # siguiente día laborable
        self.assertEqual(c["minutes"], 45)
        self.assertEqual(hm(c["base_exit"]), "15:00")
        self.assertEqual(hm(c["exit"]), "14:15")
        self.assertEqual(c["day_balance_s"], -45 * 60)
        self.assertEqual(c["week_closed_before_s"], 45 * 60)
        self.assertEqual(c["week_closed_after_s"], 0)
        nxt = insights.compensation(date(2026, 11, 2), 30, days, SETTINGS, NOW, None)
        self.assertFalse(nxt["same_week"])
        self.assertIsNone(nxt["week_closed_after_s"])

    def test_compensation_can_be_disabled(self):
        s = core.normalize_settings({"weekly_goal": {"compensation": False}})
        self.assertFalse(s["weekly_goal"]["compensation"])

    def test_next_workday_skips_holiday(self):
        cal = core.normalize_calendar({"days": {"2026-10-30": {"type": "holiday"}}})
        self.assertEqual(insights.next_workday(THU, {}, SETTINGS, NOW, cal), date(2026, 11, 2))


if __name__ == "__main__":
    unittest.main()
