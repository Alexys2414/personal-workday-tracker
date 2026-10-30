"""Perfiles de horario, períodos de verano y prioridades."""
import unittest
from datetime import date

import core

SUMMER = core.normalize_settings({"summer": {"periods": [{"start": "2027-07-01", "end": "2027-08-31"}]}})
MON_JUL = date(2027, 7, 5)
FRI_JUL = date(2027, 7, 9)
SAT_JUL = date(2027, 7, 10)
MON_SEP = date(2027, 9, 6)
FRI_SEP = date(2027, 9, 10)


def at(day, value):
    return core.combine(day, value)


def worked_day(day, settings, clock_in, clock_out, breaks=(), **payload):
    payload = {"clock_in": clock_in, "clock_out": clock_out,
               "breaks": [{"start": s, "end": e} for s, e in breaks], **payload}
    return core.build_record(day, payload, None, settings, at(day, "23:00"))


class Resolution(unittest.TestCase):
    def test_defaults(self):
        s = core.default_settings()
        self.assertEqual(core.resolve_profile(date(2026, 10, 29), s), ("normal", "weekly"))
        self.assertEqual(core.resolve_profile(date(2026, 10, 30), s), ("friday", "weekly"))
        self.assertEqual(s["profiles"]["summer"]["target_minutes"], 420)

    def test_period_applies_inclusive(self):
        for d in (date(2027, 7, 1), MON_JUL, FRI_JUL, date(2027, 8, 31)):
            self.assertEqual(core.resolve_profile(d, SUMMER), ("summer", "period"), d)

    def test_outside_period_back_to_weekly_and_friday(self):
        self.assertEqual(core.resolve_profile(date(2027, 6, 30), SUMMER), ("normal", "weekly"))
        self.assertEqual(core.resolve_profile(MON_SEP, SUMMER), ("normal", "weekly"))
        self.assertEqual(core.resolve_profile(FRI_SEP, SUMMER), ("friday", "weekly"))

    def test_period_ignores_non_workdays(self):
        snap = core.snapshot_for(SAT_JUL, SUMMER)
        self.assertEqual(snap["profile_source"], "weekly")
        self.assertEqual(snap["target_minutes"], 0)

    def test_period_only_selected_weekdays(self):
        s = core.normalize_settings({"summer": {"weekdays": [0, 1, 2, 3]}}, SUMMER)
        self.assertEqual(core.resolve_profile(FRI_JUL, s), ("friday", "weekly"))
        self.assertEqual(core.resolve_profile(MON_JUL, s), ("summer", "period"))

    def test_priority_manual_over_period_over_weekly(self):
        self.assertEqual(core.resolve_profile(MON_JUL, SUMMER, "normal"), ("normal", "manual"))
        self.assertEqual(core.resolve_profile(MON_SEP, SUMMER, "summer"), ("summer", "manual"))
        self.assertEqual(core.resolve_profile(MON_JUL, SUMMER), ("summer", "period"))

    def test_manual_profile_on_non_workday_has_target(self):
        snap = core.snapshot_for(SAT_JUL, SUMMER, "summer")
        self.assertEqual(snap["target_minutes"], 420)

    def test_weekday_profile_configurable(self):
        s = core.normalize_settings({"weekdays": {"0": {"profile": "summer"}}})
        self.assertEqual(core.resolve_profile(date(2026, 10, 26), s), ("summer", "weekly"))


class Targets(unittest.TestCase):
    def test_seven_hours_in_summer_is_no_deficit(self):
        rec = worked_day(MON_JUL, SUMMER, "08:00", "15:00")
        c = core.compute_day(MON_JUL, rec, SUMMER, at(MON_JUL, "23:00"))
        self.assertEqual((c["profile"], c["target_s"], c["balance_s"], c["color"]), ("summer", 7 * 3600, 0, "green"))

    def test_unregistered_days_use_period_target(self):
        c = core.compute_day(MON_JUL, None, SUMMER, at(date(2027, 7, 1), "08:00"))
        self.assertEqual(c["target_s"], 7 * 3600)
        self.assertEqual(c["profile"], "summer")

    def test_summary_mixes_profiles(self):
        # Semana del 28/06/2027: lunes y martes normal, jueves 1/07 y viernes 2/07 de verano.
        now = at(date(2027, 7, 3), "12:00")
        days = {
            date(2027, 6, 28): worked_day(date(2027, 6, 28), SUMMER, "08:00", "17:30", [("14:00", "15:00")]),
            date(2027, 6, 29): worked_day(date(2027, 6, 29), SUMMER, "08:00", "17:30", [("14:00", "15:00")]),
            date(2027, 7, 1): worked_day(date(2027, 7, 1), SUMMER, "08:00", "15:00"),
            date(2027, 7, 2): worked_day(date(2027, 7, 2), SUMMER, "08:00", "15:10"),
        }
        computed = [core.compute_day(d, days.get(d), SUMMER, now) for d in core.week_dates(date(2027, 6, 28))]
        s = core.summarize(computed, now)
        self.assertEqual(s["target_s"], (2 * 510 + 2 * 420) * 60)
        self.assertEqual(s["balance_s"], 10 * 60)

    def test_manual_profile_in_editor(self):
        rec = worked_day(MON_SEP, SUMMER, "08:00", "15:00", profile="summer")
        c = core.compute_day(MON_SEP, rec, SUMMER, at(MON_SEP, "23:00"))
        self.assertEqual((c["profile"], c["profile_source"], c["target_s"]), ("summer", "manual", 420 * 60))
        self.assertFalse(c["custom_targets"])
        # Volver a automático recupera el perfil semanal.
        rec = core.build_record(MON_SEP, {"profile": ""}, rec, SUMMER, at(MON_SEP, "23:00"))
        self.assertEqual((rec["profile"], rec["target_minutes"]), ("normal", 510))

    def test_custom_targets_on_top_of_profile(self):
        rec = worked_day(MON_JUL, SUMMER, "08:00", "14:00", target_minutes=360)
        self.assertTrue(rec["custom_targets"])
        self.assertEqual(rec["profile"], "summer")


class History(unittest.TestCase):
    def test_closed_days_keep_profile_and_targets(self):
        rec = worked_day(MON_JUL, SUMMER, "08:00", "15:00")
        later = core.normalize_settings({"profiles": {"summer": {"target_minutes": 390, "min_break_minutes": 15}},
                                         "summer": {"periods": []}}, SUMMER)
        self.assertFalse(core.refresh_open_record(rec, MON_JUL, later))
        c = core.compute_day(MON_JUL, rec, later, at(MON_JUL, "23:00"))
        self.assertEqual((c["profile"], c["target_s"], c["min_break_s"]), ("summer", 420 * 60, 0))
        # Editar la hora de salida no cambia el perfil ni el objetivo de aquel día.
        rec = core.build_record(MON_JUL, {"clock_out": "15:30"}, rec, later, at(MON_JUL, "23:00"))
        self.assertEqual((rec["profile"], rec["target_minutes"]), ("summer", 420))

    def test_open_day_follows_new_period(self):
        today = MON_JUL
        rec = core.apply_action("start", today, None, core.default_settings(), at(today, "08:00"))
        self.assertEqual(rec["profile"], "normal")
        self.assertTrue(core.refresh_open_record(rec, today, SUMMER))
        self.assertEqual((rec["profile"], rec["profile_source"], rec["target_minutes"]), ("summer", "period", 420))

    def test_legacy_records_without_profile_still_work(self):
        rec = {"clock_in": "2026-10-29T08:00:00+01:00", "clock_out": "2026-10-29T17:30:00+01:00",
               "breaks": [{"start": "2026-10-29T14:00:00+01:00", "end": "2026-10-29T15:00:00+01:00"}],
               "target_minutes": 510, "min_break_minutes": 60, "optional_break_minutes": 30,
               "mode": "office", "notes": ""}
        c = core.compute_day(date(2026, 10, 29), rec, SUMMER, at(date(2026, 10, 30), "12:00"))
        self.assertEqual((c["balance_s"], c["profile"]), (0, None))


class Settings(unittest.TestCase):
    def test_migration_from_v1(self):
        v1 = {"version": 1, "theme": "dark", "time_format": "24h", "duration_format": "hms",
              "weekdays": {str(i): {"workday": i < 5, "start": "08:00", "end": "15:00" if i == 4 else "18:00",
                                    "target_minutes": 420 if i == 4 else 500, "min_break_minutes": 60 if i < 4 else 0,
                                    "optional_break_minutes": 30 if i < 4 else 0,
                                    "mode": "remote" if i == 2 else "office"} for i in range(7)}}
        s = core.normalize_settings(v1)
        self.assertEqual(s["version"], core.SETTINGS_VERSION)
        self.assertEqual(s["profiles"]["normal"]["target_minutes"], 500)
        self.assertEqual(s["profiles"]["friday"]["target_minutes"], 420)
        self.assertEqual(s["weekdays"]["4"]["profile"], "friday")
        self.assertEqual(s["weekdays"]["2"]["mode"], "remote")
        self.assertFalse(s["weekdays"]["6"]["workday"])
        self.assertEqual(s["theme"], "dark")
        self.assertNotIn("target_minutes", s["weekdays"]["0"])

    def test_invalid_periods(self):
        with self.assertRaises(core.ValidationError):
            core.normalize_settings({"summer": {"periods": [{"start": "2027-08-31", "end": "2027-07-01"}]}})
        with self.assertRaises(core.ValidationError):
            core.normalize_settings({"summer": {"periods": [{"start": "1 julio", "end": "2027-07-01"}]}})
        with self.assertRaises(core.ValidationError):
            core.normalize_settings({"summer": {"weekdays": [7]}})
        with self.assertRaises(core.ValidationError):
            core.normalize_settings({"weekdays": {"0": {"profile": "noche"}}})


if __name__ == "__main__":
    unittest.main()
