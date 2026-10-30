"""Estadísticas avanzadas: promedios, semanas incompletas, jornadas abiertas y balance acumulado."""
import unittest
from datetime import date

import core
import insights
from tests.helpers import SETTINGS, THU, AppCase, record

NOW = core.combine(THU, "12:00")


def sample():
    return {
        "2026-10-19": record(date(2026, 10, 19), "08:00", "17:30", [("14:00", "15:00")]),   # 8:30 exacta
        "2026-10-20": record(date(2026, 10, 20), "07:40", "17:40", [("14:00", "15:00")]),   # 9:00 (+0:30)
        "2026-10-21": record(date(2026, 10, 21), "08:20", "17:20", [("14:00", "15:00")]),   # 8:00 (−0:30)
        "2026-10-26": record(date(2026, 10, 26), "08:00", "18:00", [("14:00", "15:00")]),   # 9:00 (+0:30)
        THU.isoformat(): record(THU, "08:00", None, now=NOW),                                # abierta: 4 h
    }


class Averages(unittest.TestCase):
    def test_exact_averages_exclude_open_and_unregistered(self):
        s = insights.advanced_stats(sample(), SETTINGS, NOW, None, 2026, 10)
        a = s["averages"]
        self.assertEqual(a["days"], 4)
        self.assertEqual(a["open_days"], 1)
        # Entradas: 8:00, 7:40, 8:20, 8:00, 8:00 (la abierta sí tiene entrada) → 8:00.
        self.assertEqual(a["clock_in_s"], 8 * 3600)
        # Salidas solo de cerradas: 17:30, 17:40, 17:20, 18:00 → 17:37:30.
        self.assertEqual(a["clock_out_s"], 17 * 3600 + 37 * 60 + 30)
        self.assertEqual(a["worked_s"], (510 + 540 + 480 + 540) / 4 * 60)
        self.assertEqual(a["break_s"], 3600)
        self.assertEqual([d["date"] for d in a["most"]][:2], ["2026-10-20", "2026-10-26"])
        self.assertEqual(a["least"][0]["date"], "2026-10-21")

    def test_month_without_data(self):
        s = insights.advanced_stats(sample(), SETTINGS, NOW, None, 2026, 3)
        self.assertEqual(s["averages"]["days"], 0)
        self.assertIsNone(s["averages"]["worked_s"])
        self.assertEqual({c["category"] for c in s["heatmap"]} - {"none", "nonworking"}, set())
        empty = insights.advanced_stats({}, SETTINGS, NOW, None, 2026, 10)
        self.assertFalse(empty["has_data"])

    def test_heatmap_categories(self):
        days = sample()
        days["2026-10-22"] = record(date(2026, 10, 22), "08:00", None, now=NOW)          # sin cerrar
        cal = core.normalize_calendar({"days": {"2026-10-23": {"type": "vacation"}}})
        s = insights.advanced_stats(days, SETTINGS, NOW, cal, 2026, 10)
        cat = {c["date"]: c["category"] for c in s["heatmap"]}
        self.assertEqual(cat["2026-10-19"], "complete")
        self.assertEqual(cat["2026-10-21"], "incomplete")
        self.assertEqual(cat["2026-10-22"], "unclosed")
        self.assertEqual(cat["2026-10-23"], "absence")
        self.assertEqual(cat["2026-10-24"], "nonworking")
        self.assertEqual(cat["2026-10-27"], "none")
        self.assertEqual(cat[THU.isoformat()], "progress")
        self.assertEqual(cat["2026-10-30"], "future")


class Series(unittest.TestCase):
    def test_open_day_is_not_a_deficit(self):
        s = insights.advanced_stats(sample(), SETTINGS, NOW, None, 2026, 10, weeks=4)
        current = s["weekly"][-1]
        self.assertTrue(current["current"])
        self.assertEqual(current["balance_s"], 30 * 60)          # solo el lunes cerrado; el jueves abierto no resta
        self.assertGreater(current["pending_s"], 0)

    def test_incomplete_weeks_and_cumulative_balance(self):
        days = sample()
        s = insights.advanced_stats(days, SETTINGS, NOW, None, 2026, 10, weeks=4)
        weekly = s["weekly"]
        self.assertEqual([w["balance_s"] for w in weekly], [0, 0, 0, 1800])
        self.assertEqual([w["cumulative_s"] for w in weekly], [0, 0, 0, 1800])
        # La semana del 19 tiene tres días cerrados (+0:30 −0:30) y dos sin registro: balance 0, no déficit.
        total = core.summarize([core.compute_day(date.fromisoformat(k), v, SETTINGS, NOW) for k, v in days.items()], NOW)
        self.assertEqual(weekly[-1]["cumulative_s"], total["balance_s"])
        self.assertEqual(s["monthly"][-1]["cumulative_s"], total["balance_s"])
        self.assertEqual(len(s["monthly"]), 12)

    def test_cumulative_includes_history_before_window(self):
        days = sample()
        days["2026-01-12"] = record(date(2026, 1, 12), "08:00", "18:30", [("14:00", "15:00")])   # +1:00
        s = insights.advanced_stats(days, SETTINGS, NOW, None, 2026, 10, weeks=4)
        self.assertEqual(s["weekly"][0]["cumulative_s"], 3600)
        self.assertEqual(s["weekly"][-1]["cumulative_s"], 3600 + 1800)

    def test_weekly_goal_in_series(self):
        s = insights.advanced_stats(sample(), SETTINGS, NOW, None, 2026, 10, weeks=4)
        self.assertTrue(all(w["goal_s"] == 41 * 3600 for w in s["weekly"]))


class StatsApi(AppCase, unittest.TestCase):
    def test_endpoint(self):
        self.act("start", "08:00")
        res = self.client.get("/api/stats?month=2026-10&scope=all&weeks=8")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()["weekly"]), 8)
        self.assertEqual(self.client.get("/api/stats?month=2026-13").status_code, 400)


if __name__ == "__main__":
    unittest.main()
