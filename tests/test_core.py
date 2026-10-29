"""Pruebas de cálculo de jornadas.  Ejecutar:  python -m unittest -v"""
import unittest
from datetime import date

import core

D = date(2026, 10, 29)          # jueves (CET, +01:00)
FRI = date(2026, 10, 30)
SETTINGS = core.default_settings()


def at(value, day=D):
    return core.combine(day, value)


def record(clock_in, breaks=(), clock_out=None, day=D, **extra):
    rec = core.new_record(day, SETTINGS)
    rec.update(extra)
    rec["clock_in"] = core.iso(at(clock_in, day))
    rec["clock_out"] = core.iso(at(clock_out, day)) if clock_out else None
    rec["breaks"] = [{"start": core.iso(at(s, day)), "end": core.iso(at(e, day)) if e else None}
                     for s, e in breaks]
    return rec


def local(iso_value):
    return core.local_clock(core.parse_ts(iso_value))


class ExampleFromSpec(unittest.TestCase):
    """Entrada 07:53, descanso 14:50–15:49, objetivo 8 h 30 min."""

    def setUp(self):
        self.rec = record("07:53", [("14:50", "15:49")])

    def test_on_return_from_break(self):
        c = core.compute_day(D, self.rec, SETTINGS, at("15:49"))
        self.assertEqual(c["status"], "working")
        self.assertEqual(c["worked_s"], (6 * 60 + 57) * 60)       # 6 h 57 min
        self.assertEqual(c["break_s"], 59 * 60)                     # 59 min
        self.assertEqual(c["remaining_s"], 93 * 60)                 # 1 h 33 min
        self.assertEqual(local(c["exit_min_at"]), "17:22:00")       # sin el minuto que falta
        self.assertEqual(c["pending_break_s"], 60)                  # falta 1 min de descanso
        self.assertEqual(local(c["exit_at"]), "17:23:00")           # cumpliendo el descanso

    def test_exit_is_stable_while_working(self):
        for t in ("15:50", "16:30:17", "17:00"):
            c = core.compute_day(D, self.rec, SETTINGS, at(t))
            self.assertEqual(local(c["exit_at"]), "17:23:00", t)

    def test_completion_and_extra(self):
        c = core.compute_day(D, self.rec, SETTINGS, at("17:30"))
        self.assertEqual(c["remaining_s"], 0)
        self.assertEqual(c["extra_s"], 8 * 60)
        self.assertEqual(local(c["completed_at"]), "17:22:00")
        self.assertEqual(c["color"], "green")


class Calculations(unittest.TestCase):
    def test_not_started_estimate_includes_mandatory_break(self):
        c = core.compute_day(D, None, SETTINGS, at("08:00"))
        self.assertEqual(c["status"], "not_started")
        self.assertEqual(local(c["exit_at"]), "17:30:00")           # 8:30 + 1:00
        self.assertEqual(local(c["exit_optional_at"]), "18:00:00")  # + 30 min opcionales

    def test_before_break_estimate(self):
        rec = record("08:00")
        c = core.compute_day(D, rec, SETTINGS, at("10:00"))
        self.assertEqual(c["remaining_s"], 6.5 * 3600)
        self.assertEqual(c["pending_break_s"], 3600)
        self.assertEqual(local(c["exit_at"]), "17:30:00")
        self.assertEqual(local(c["exit_min_at"]), "16:30:00")

    def test_counter_frozen_during_break(self):
        rec = record("08:00", [("13:00", None)])
        a = core.compute_day(D, rec, SETTINGS, at("13:10"))
        b = core.compute_day(D, rec, SETTINGS, at("13:40"))
        self.assertEqual(a["status"], "on_break")
        self.assertEqual(a["worked_s"], b["worked_s"])
        self.assertEqual(b["current_break_s"], 40 * 60)
        # Durante la pausa mínima la salida no se mueve; después, sí.
        self.assertEqual(local(a["exit_at"]), "17:30:00")
        self.assertEqual(local(b["exit_at"]), "17:30:00")
        c = core.compute_day(D, rec, SETTINGS, at("14:15"))
        self.assertEqual(local(c["exit_at"]), "17:45:00")

    def test_multiple_breaks(self):
        rec = record("08:00", [("10:30", "10:45"), ("14:00", "14:45"), ("16:00", "16:10")], "18:00")
        c = core.compute_day(D, rec, SETTINGS, at("20:00"))
        self.assertEqual(c["break_s"], 70 * 60)
        self.assertEqual(c["worked_s"], 10 * 3600 - 70 * 60)
        self.assertEqual(c["balance_s"], (8 * 60 + 50 - 510) * 60)  # +20 min
        self.assertEqual(c["status"], "finished")
        self.assertEqual(c["color"], "green")

    def test_completion_instant_skips_later_breaks(self):
        # Completa a las 17:30 y luego descansa 10 min: la hora de completado no cambia.
        rec = record("08:00", [("12:00", "13:00"), ("17:40", "17:50")], "18:00")
        c = core.compute_day(D, rec, SETTINGS, at("19:00"))
        self.assertEqual(local(c["completed_at"]), "17:30:00")

    def test_finished_with_deficit(self):
        rec = record("08:00", [("13:00", "14:00")], "16:00")
        c = core.compute_day(D, rec, SETTINGS, at("20:00"))
        self.assertEqual(c["balance_s"], -90 * 60)
        self.assertEqual(c["deficit_s"], 90 * 60)
        self.assertEqual(c["color"], "red")

    def test_short_break_flag(self):
        rec = record("08:00", [("13:00", "13:30")], "17:00")
        c = core.compute_day(D, rec, SETTINGS, at("20:00"))
        self.assertIn("break_short", c["flags"])

    def test_friday_target(self):
        rec = record("08:00", day=FRI)
        c = core.compute_day(FRI, rec, SETTINGS, at("09:00", FRI))
        self.assertEqual(c["target_s"], 7 * 3600)
        self.assertEqual(local(c["exit_at"]), "15:00:00")

    def test_dst_change_day(self):
        # 25/10/2026: a las 03:00 CEST se vuelve a las 02:00 CET (el día dura 25 h).
        day = date(2026, 10, 25)
        rec = record("01:00", clock_out="05:00", day=day)
        c = core.compute_day(day, rec, SETTINGS, core.combine(day, "12:00"))
        self.assertEqual(c["worked_s"], 5 * 3600)

    def test_past_unclosed_day(self):
        rec = record("08:00", [("13:00", "14:00")])
        c = core.compute_day(D, rec, SETTINGS, at("09:00", date(2026, 10, 30)))
        self.assertEqual(c["status"], "unclosed")
        self.assertEqual(c["worked_s"], 5 * 3600)
        self.assertFalse(c["counted"])

    def test_day_off(self):
        rec = core.new_record(D, SETTINGS)
        rec["mode"] = "off"
        c = core.compute_day(D, rec, SETTINGS, at("10:00"))
        self.assertEqual(c["status"], "off")
        self.assertEqual(c["target_s"], 0)


class Summaries(unittest.TestCase):
    def test_week_balance_ignores_future_and_pending(self):
        now = at("12:00")                                   # jueves en curso
        days = {
            date(2026, 10, 26): record("08:00", [("13:00", "14:00")], "17:40", day=date(2026, 10, 26)),  # +10 min
            date(2026, 10, 27): record("08:00", [("13:00", "14:00")], "17:20", day=date(2026, 10, 27)),  # −10 min
            # miércoles 28 sin registro: no cuenta como déficit
            D: record("08:00"),                             # en curso: pendiente, no déficit
        }
        computed = [core.compute_day(d, days.get(d), SETTINGS, now) for d in core.week_dates(D)]
        s = core.summarize(computed, now)
        self.assertEqual(s["balance_s"], 0)
        self.assertEqual(s["pending_s"], 4.5 * 3600)
        # Objetivo: lun + mar + jue (fichados) + vie (futuro) = 3 × 8:30 + 7:00
        self.assertEqual(s["target_s"], 3 * 510 * 60 + 420 * 60)
        self.assertEqual(s["worked_days"], 3)
        self.assertEqual(s["completed_days"], 1)


class Flexibility(unittest.TestCase):
    def test_cumulative_balance_example(self):
        # +25, −15, +40, −10  →  +40 min (sin tocar los objetivos de los días siguientes)
        monday = date(2026, 10, 19)
        outs = ["17:55", "17:15", "18:10", "17:20"]
        days = [monday + core.timedelta(days=i) for i in range(4)]
        computed = [core.compute_day(d, record("08:00", [("14:00", "15:00")], out, day=d), SETTINGS, at("20:00"))
                    for d, out in zip(days, outs)]
        self.assertEqual([c["balance_s"] / 60 for c in computed], [25, -15, 40, -10])
        self.assertEqual(core.summarize(computed, at("20:00"))["balance_s"], 40 * 60)
        self.assertTrue(all(c["target_s"] == 510 * 60 for c in computed))

    def test_can_finish_early_and_skip_break(self):
        rec = core.apply_action("start", D, None, SETTINGS, at("08:00"))
        rec = core.apply_action("stop", D, rec, SETTINGS, at("12:00"))   # sin descanso, 4 h
        c = core.compute_day(D, rec, SETTINGS, at("12:00"))
        self.assertEqual(c["status"], "finished")
        self.assertEqual(c["balance_s"], -(4 * 60 + 30) * 60)
        self.assertIn("break_short", c["flags"])                        # solo aviso

    def test_closed_day_can_be_edited(self):
        rec = record("08:00", [("13:00", "14:00")], "17:30")
        rec = core.build_record(D, {"clock_out": "19:00"}, rec, SETTINGS, at("20:00"))
        self.assertEqual(core.compute_day(D, rec, SETTINGS, at("20:00"))["balance_s"], 90 * 60)


class Validation(unittest.TestCase):
    now = at("20:00")

    def build(self, **payload):
        return core.build_record(D, payload, None, SETTINGS, self.now)

    def test_valid_manual_entry(self):
        rec = self.build(clock_in="08:00", clock_out="17:30",
                         breaks=[{"start": "14:00", "end": "15:00"}])
        c = core.compute_day(D, rec, SETTINGS, self.now)
        self.assertEqual(c["worked_s"], 510 * 60)

    def test_exit_before_entry(self):
        with self.assertRaises(core.ValidationError):
            self.build(clock_in="09:00", clock_out="08:00")

    def test_overlapping_breaks(self):
        with self.assertRaises(core.ValidationError):
            self.build(clock_in="08:00", clock_out="18:00",
                       breaks=[{"start": "13:00", "end": "14:00"}, {"start": "13:30", "end": "14:30"}])

    def test_break_outside_workday(self):
        with self.assertRaises(core.ValidationError):
            self.build(clock_in="08:00", clock_out="17:00", breaks=[{"start": "16:30", "end": "17:30"}])
        with self.assertRaises(core.ValidationError):
            self.build(clock_in="08:00", breaks=[{"start": "07:30", "end": "08:30"}])

    def test_open_break_on_closed_day(self):
        with self.assertRaises(core.ValidationError):
            self.build(clock_in="08:00", clock_out="17:00", breaks=[{"start": "13:00", "end": ""}])

    def test_future_time(self):
        with self.assertRaises(core.ValidationError):
            core.build_record(D, {"clock_in": "08:00", "clock_out": "21:00"}, None, SETTINGS, self.now)

    def test_bad_format(self):
        with self.assertRaises(core.ValidationError):
            self.build(clock_in="25:00")

    def test_editing_keeps_seconds_and_targets(self):
        rec = self.build(clock_in="07:53:12", target_minutes=480)
        self.assertTrue(rec["custom_targets"])
        self.assertEqual(local(rec["clock_in"]), "07:53:12")


class Actions(unittest.TestCase):
    def test_full_flow(self):
        rec = core.apply_action("start", D, None, SETTINGS, at("07:53"))
        rec = core.apply_action("break_start", D, rec, SETTINGS, at("14:50"))
        with self.assertRaises(core.Conflict):            # doble clic
            core.apply_action("break_start", D, rec, SETTINGS, at("14:50"))
        rec = core.apply_action("break_end", D, rec, SETTINGS, at("15:49"))
        c = core.compute_day(D, rec, SETTINGS, at("15:49"))
        self.assertEqual(local(c["exit_at"]), "17:23:00")
        # Sale a las 17:22 sin el minuto extra de pausa: 8:30 exactas, pero con aviso.
        rec = core.apply_action("stop", D, rec, SETTINGS, at("17:22"))
        c = core.compute_day(D, rec, SETTINGS, at("18:00"))
        self.assertEqual(c["status"], "finished")
        self.assertEqual(c["worked_s"], 510 * 60)
        self.assertEqual(c["balance_s"], 0)
        self.assertIn("break_short", c["flags"])
        with self.assertRaises(core.Conflict):
            core.apply_action("start", D, rec, SETTINGS, at("18:00"))

    def test_stop_during_break_closes_it(self):
        rec = core.apply_action("start", D, None, SETTINGS, at("08:00"))
        rec = core.apply_action("break_start", D, rec, SETTINGS, at("13:00"))
        rec = core.apply_action("stop", D, rec, SETTINGS, at("13:30"))
        self.assertEqual(local(rec["breaks"][0]["end"]), "13:30:00")

    def test_resume_converts_gap_into_break(self):
        rec = core.apply_action("start", D, None, SETTINGS, at("08:00"))
        rec = core.apply_action("stop", D, rec, SETTINGS, at("12:00"))
        rec = core.apply_action("resume", D, rec, SETTINGS, at("13:00"))
        c = core.compute_day(D, rec, SETTINGS, at("14:00"))
        self.assertEqual(c["status"], "working")
        self.assertEqual(c["worked_s"], 5 * 3600)
        self.assertEqual(c["break_s"], 3600)


class SettingsBehaviour(unittest.TestCase):
    def test_closed_days_keep_their_targets(self):
        rec = record("08:00", [("13:00", "14:00")], "17:30")
        new = core.normalize_settings({"profiles": {"normal": {"target_minutes": 480}}}, SETTINGS)
        self.assertFalse(core.refresh_open_record(rec, D, new))
        self.assertEqual(core.compute_day(D, rec, new, at("20:00"))["target_s"], 510 * 60)

    def test_open_day_adopts_new_targets(self):
        rec = record("08:00")
        new = core.normalize_settings({"profiles": {"normal": {"target_minutes": 480}}}, SETTINGS)
        self.assertTrue(core.refresh_open_record(rec, D, new))
        self.assertEqual(rec["target_minutes"], 480)

    def test_invalid_settings(self):
        with self.assertRaises(core.ValidationError):
            core.normalize_settings({"profiles": {"normal": {"start": "19:00", "end": "08:00"}}})
        with self.assertRaises(core.ValidationError):
            core.normalize_settings({"theme": "pink"})


if __name__ == "__main__":
    unittest.main()
