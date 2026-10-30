"""Tareas e imputación (2.2): cronómetro, integración con el fichaje, tramos, resúmenes y copias.

Solo datos ficticios (DEMO-…, carpetas temporales).
"""
import json
import unittest
from datetime import date, timedelta

import backup
import core
import tasks as tm
from app import create_app
from tests.helpers import THU, AppCase, FakeClock

H = 3600


class TasksApi(AppCase, unittest.TestCase):
    def new(self, key, estimate=None, **extra):
        res = self.client.post("/api/tasks", json={"key": key, "title": f"Tarea ficticia {key}",
                                                   "estimate_minutes": estimate, **extra})
        self.assertEqual(res.status_code, 200, res.get_json())
        return res.get_json()["task"]["id"]

    def start(self, task_id, at, **body):
        self.clock.set(at)
        return self.client.post(f"/api/tasks/{task_id}/start", json=body)

    def raw(self):
        return json.loads((self.data / "tasks.json").read_text())

    def day(self, d=THU):
        return self.client.get(f"/api/tasks/day/{d}").get_json()

    def worked_day(self, clock_in="08:00"):
        self.act("start", clock_in)

    # ---------------------------------------------------- cronómetro

    def test_start_and_stop(self):
        self.worked_day()
        a = self.new("DEMO-101", 8 * 60)
        self.assertEqual(self.start(a, "08:00").status_code, 200)
        self.clock.set("10:00")
        state = self.client.get("/api/tasks").get_json()
        self.assertEqual(state["active"]["key"], "DEMO-101")
        self.assertEqual(state["active"]["task_s"], 2 * H)              # calculado con marcas, no con un contador
        res = self.client.post("/api/tasks/pause", json={})
        self.assertIsNone(res.get_json()["active"])
        entries = list(self.raw()["entries"].values())
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual((e["date"], e["source"]), ("2026-10-29", "timer"))
        self.assertEqual(core.seconds(core.parse_ts(e["start"]), core.parse_ts(e["end"])), 2 * H)

    def test_switching_closes_previous_and_never_runs_two(self):
        """08:00–10:00 DEMO-123 · 10:00–14:00 DEMO-145 · (descanso) · 15:00–17:00 DEMO-170 = 8 h."""
        self.worked_day()
        a, b, c = self.new("DEMO-123", 480), self.new("DEMO-145", 240), self.new("DEMO-170", 720)
        self.start(a, "08:00")
        self.start(b, "10:00")
        self.act("break_start", "14:00")
        self.act("break_end", "15:00")
        self.start(c, "15:00")
        self.clock.set("17:00")
        self.client.post("/api/tasks/pause", json={})
        raw = self.raw()
        actives = [e for e in raw["entries"].values() if not e["end"]]
        self.assertEqual(actives, [])
        s = self.day()
        self.assertEqual(s["imputed_s"], 8 * H)
        self.assertEqual({t["key"]: t["seconds"] for t in s["tasks"]}, {"DEMO-123": 2 * H, "DEMO-145": 4 * H, "DEMO-170": 2 * H})
        self.assertEqual(s["worked_s"], 8 * H)
        self.assertEqual(s["unassigned_s"], 0)
        self.assertEqual(s["issues"], [])

    def test_start_same_task_twice_is_noop(self):
        self.worked_day()
        a = self.new("DEMO-1")
        self.start(a, "08:00")
        self.start(a, "09:00")
        self.assertEqual(len(self.raw()["entries"]), 1)

    def test_two_windows_expect_active(self):
        self.worked_day()
        a, b = self.new("DEMO-1"), self.new("DEMO-2")
        self.start(a, "08:00", expect_active=None)
        stale = self.start(b, "09:00", expect_active=None)          # la otra ventana aún no veía el cronómetro
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(len(self.raw()["entries"]), 1)

    # ----------------------------------------------- integración con el fichaje

    def test_break_pauses_and_offers_resume(self):
        self.worked_day()
        a = self.new("DEMO-1")
        self.start(a, "08:00")
        res = self.act("break_start", "12:00")
        self.assertEqual(res.get_json()["task_paused"], a)
        state = self.client.get("/api/tasks").get_json()
        self.assertIsNone(state["active"])
        self.assertEqual(state["resume_task_id"], a)
        self.act("break_end", "13:00")
        self.assertIsNone(self.client.get("/api/tasks").get_json()["active"])   # no se reanuda solo
        self.start(a, "13:05")
        self.clock.set("14:05")
        self.client.post("/api/tasks/pause", json={})
        s = self.day()
        self.assertEqual(s["imputed_s"], 5 * H)                     # el descanso (12–13) no se imputa
        self.assertIsNone(self.client.get("/api/tasks").get_json()["resume_task_id"])

    def test_starting_during_break_asks_and_can_end_break(self):
        self.worked_day()
        a = self.new("DEMO-1")
        self.act("break_start", "11:00")
        res = self.start(a, "11:30")
        self.assertEqual((res.status_code, res.get_json()["code"]), (409, "task.on_break"))
        self.assertEqual(self.raw()["entries"], {})
        res = self.start(a, "11:30", day="end_break")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["day_changed"])
        today = self.client.get("/api/today").get_json()["today"]
        self.assertEqual(today["status"], "working")

    def test_starting_without_workday_asks(self):
        a = self.new("DEMO-1")
        res = self.start(a, "08:00")
        self.assertEqual((res.status_code, res.get_json()["code"]), (409, "task.no_day"))
        res = self.start(a, "08:00", day="start")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.client.get("/api/today").get_json()["today"]["status"], "working")
        # «Solo la tarea» también es posible, sin tocar el fichaje.
        b = self.new("DEMO-2")
        self.act("stop", "09:00")
        records = (self.data / "records.json").read_bytes()
        self.assertEqual(self.start(b, "09:30", day="ignore").status_code, 200)
        self.assertEqual((self.data / "records.json").read_bytes(), records)

    def test_finishing_day_closes_entry(self):
        self.worked_day()
        a = self.new("DEMO-1")
        self.start(a, "08:00")
        res = self.act("stop", "16:30")
        self.assertEqual(res.get_json()["task_paused"], a)
        e = list(self.raw()["entries"].values())[0]
        self.assertEqual(core.local_clock(core.parse_ts(e["end"])), "16:30:00")
        self.assertIsNone(self.client.get("/api/tasks").get_json()["resume_task_id"])

    def test_clock_corrections_do_not_touch_entries_and_report_discrepancy(self):
        self.worked_day()
        a = self.new("DEMO-1")
        self.start(a, "08:00")
        self.act("stop", "12:00")
        before = self.raw()["entries"]
        # Se corrige el fichaje: entrada a las 09:00 y un descanso de 10 a 10:30.
        self.client.put(f"/api/days/{THU}", json={"clock_in": "09:00", "clock_out": "12:00",
                                                  "breaks": [{"start": "10:00", "end": "10:30"}]})
        self.assertEqual(self.raw()["entries"], before)
        s = self.day()
        types = sorted(i["type"] for i in s["issues"])
        self.assertEqual(types, ["outside_work", "over_imputed"])
        outside = next(i for i in s["issues"] if i["type"] == "outside_work")
        self.assertEqual(outside["seconds"], 1.5 * H)
        # Propuesta de ajuste: solo con confirmación y con la misma propuesta.
        plan = self.client.get(f"/api/tasks/day/{THU}/trim").get_json()["plan"]
        self.assertEqual(len(plan[0]["pieces"]), 2)
        self.assertEqual(self.client.post(f"/api/tasks/day/{THU}/trim", json={"entry_ids": [plan[0]["entry_id"]]}).status_code, 400)
        res = self.client.post(f"/api/tasks/day/{THU}/trim", json={"confirm": True, "entry_ids": [plan[0]["entry_id"]]})
        self.assertEqual(res.status_code, 200)
        s = self.day()
        self.assertEqual((s["imputed_s"], s["issues"]), (2.5 * H, []))

    def test_manual_time_without_clock(self):
        a = self.new("DEMO-1")
        res = self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-28", "minutes": 90})
        self.assertEqual(res.status_code, 200)
        e = res.get_json()["entry"]
        self.assertEqual((e["source"], e["seconds"], e["start"]), ("manual", 5400, None))
        s = self.day(date(2026, 10, 28))
        self.assertEqual(s["imputed_s"], 5400)
        self.assertEqual(s["issues"], [])                            # lo manual sin fichaje es legítimo

    # ---------------------------------------------------- tramos

    def test_multiple_sessions_and_several_days(self):
        a = self.new("DEMO-9", 12 * 60)
        for d, (s, e) in ((date(2026, 10, 26), ("08:00", "11:00")), (date(2026, 10, 27), ("09:00", "13:30")),
                          (date(2026, 10, 27), ("15:00", "16:00"))):
            self.assertEqual(self.client.post("/api/entries", json={"task_id": a, "date": d.isoformat(),
                                                                    "start": s, "end": e}).status_code, 200)
        t = next(x for x in self.client.get("/api/tasks").get_json()["tasks"] if x["id"] == a)
        self.assertEqual((t["sessions"], t["total_s"]), (3, 8.5 * H))
        self.assertEqual(t["remaining_s"], 3.5 * H)
        entries = self.client.get(f"/api/tasks/{a}/entries").get_json()["entries"]
        self.assertEqual([e["date"] for e in entries], ["2026-10-27", "2026-10-27", "2026-10-26"])

    def test_estimate_is_not_a_limit(self):
        a = self.new("DEMO-123", 8 * 60)
        self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-28", "start": "08:00", "end": "13:30"})
        t = next(x for x in self.client.get("/api/tasks").get_json()["tasks"] if x["id"] == a)
        self.assertEqual((t["remaining_s"], t["pct"]), (2.5 * H, 68.75))
        r = self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-29", "minutes": 240})
        self.assertEqual(r.status_code, 200)
        t = next(x for x in r.get_json()["tasks"] if x["id"] == a)
        self.assertEqual((t["remaining_s"], t["over_s"], t["pct"]), (0, 1.5 * H, 118.75))

    def test_overlaps_are_rejected(self):
        a, b = self.new("DEMO-1"), self.new("DEMO-2")
        self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-28", "start": "08:00", "end": "10:00"})
        res = self.client.post("/api/entries", json={"task_id": b, "date": "2026-10-28", "start": "09:30", "end": "11:00"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("solap", res.get_json()["error"])
        ok = self.client.post("/api/entries", json={"task_id": b, "date": "2026-10-28", "start": "10:00", "end": "11:00"})
        self.assertEqual(ok.status_code, 200)
        e = ok.get_json()["entry"]
        self.assertEqual(self.client.put(f"/api/entries/{e['id']}", json={"start": "09:00", "end": "11:00"}).status_code, 400)

    def test_edit_move_and_split_preserve_time(self):
        a, b = self.new("DEMO-1"), self.new("DEMO-2")
        e = self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-28", "start": "08:00",
                                                   "end": "12:00"}).get_json()["entry"]
        res = self.client.post(f"/api/entries/{e['id']}/split", json={"at": "10:30", "task_id": b})
        self.assertEqual(res.status_code, 200)
        first, second = res.get_json()["first"], res.get_json()["second"]
        dur = lambda x: core.seconds(core.parse_ts(x["start"]), core.parse_ts(x["end"]))  # noqa: E731
        self.assertEqual((dur(first), dur(second)), (2.5 * H, 1.5 * H))
        self.assertEqual(second["task_id"], b)
        # Mover la segunda parte de vuelta y cambiar su hora.
        self.assertEqual(self.client.put(f"/api/entries/{second['id']}", json={"task_id": a, "note": "revisado"}).status_code, 200)
        self.assertEqual(self.client.put(f"/api/entries/{second['id']}", json={"start": "10:30", "end": "11:45"}).status_code, 200)
        self.assertEqual(self.day(date(2026, 10, 28))["imputed_s"], 3.75 * H)
        # Dividir un tramo manual sin hora conserva la suma.
        m = self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-27", "minutes": 120}).get_json()["entry"]
        r = self.client.post(f"/api/entries/{m['id']}/split", json={"first_minutes": 45, "task_id": b}).get_json()
        self.assertEqual((r["first"]["seconds"], r["second"]["seconds"]), (45 * 60, 75 * 60))
        bad = self.client.post(f"/api/entries/{m['id']}/split", json={"first_minutes": 500})
        self.assertEqual(bad.status_code, 400)

    def test_deleting_requires_confirmation(self):
        a = self.new("DEMO-1")
        e = self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-28", "minutes": 30}).get_json()["entry"]
        self.assertEqual(self.client.delete(f"/api/entries/{e['id']}", json={}).status_code, 400)
        self.assertEqual(len(self.raw()["entries"]), 1)
        self.assertEqual(self.client.delete(f"/api/tasks/{a}", json={}).status_code, 409)
        self.assertEqual(len(self.raw()["tasks"]), 1)
        self.assertEqual(self.client.delete(f"/api/entries/{e['id']}", json={"confirm": True}).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/tasks/{a}", json={}).status_code, 200)   # sin tramos: directo

    def test_future_and_validation(self):
        a = self.new("DEMO-1")
        self.assertEqual(self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-30", "minutes": 30}).status_code, 400)
        self.assertEqual(self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-29", "start": "13:00", "end": "14:00"}).status_code, 400)
        self.assertEqual(self.client.post("/api/tasks", json={"key": "DEMO-1"}).status_code, 400)          # clave repetida
        self.assertEqual(self.client.post("/api/tasks", json={"key": "con espacios"}).status_code, 400)
        self.assertEqual(self.client.post("/api/tasks", json={}).status_code, 400)
        internal = self.client.post("/api/tasks", json={"title": "Formación interna"})
        self.assertEqual((internal.status_code, internal.get_json()["task"]["key"]), (200, ""))

    def test_complete_and_reopen(self):
        self.worked_day()
        a = self.new("DEMO-1")
        self.start(a, "08:00")
        self.clock.set("09:00")
        res = self.client.put(f"/api/tasks/{a}", json={"status": "done", "estimate_minutes": 120})
        t = res.get_json()["task"]
        self.assertEqual(t["status"], "done")
        self.assertTrue(t["completed_at"])
        self.assertIsNone(res.get_json()["active"])                     # completar detiene el cronómetro
        t = self.client.put(f"/api/tasks/{a}", json={"status": "paused"}).get_json()["task"]
        self.assertIsNone(t["completed_at"])

    # --------------------------------------------------- resúmenes

    def test_week_summary_separates_goals_and_future(self):
        self.client.put("/api/settings", json={"tasks": {"weekly_goal_minutes": 30 * 60}})
        a, b = self.new("DEMO-1"), self.new("DEMO-2", project="Proyecto ficticio")
        self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-26", "minutes": 300})
        self.client.post("/api/entries", json={"task_id": b, "date": "2026-10-27", "minutes": 240})
        w = self.client.get(f"/api/tasks/week/{THU}").get_json()
        self.assertEqual((w["goal_s"], w["imputed_s"]), (30 * H, 9 * H))
        self.assertEqual(w["remaining_s"], 21 * H)
        self.assertEqual(w["deficit_s"], 0)                    # la semana no ha terminado: pendiente, no déficit
        self.assertTrue(w["days"][4]["future"])
        self.assertEqual({p["project"]: p["seconds"] for p in w["projects"]}, {"": 5 * H, "Proyecto ficticio": 4 * H})
        self.assertEqual([t["key"] for t in w["tickets"]], ["DEMO-1", "DEMO-2"])
        settings = self.client.get("/api/settings").get_json()
        self.assertEqual(settings["weekly_goal"]["mode"], "auto")     # el objetivo laboral no cambia
        last = self.client.get("/api/tasks/week/2026-10-20").get_json()
        self.assertTrue(last["closed"])
        self.assertEqual(last["deficit_s"], 30 * H)

    def test_report_grouping_booking_and_csv(self):
        a, b = self.new("DEMO-123"), self.new("DEMO-145")
        for d, t, s, e in (("2026-10-28", a, "08:00", "10:00"), ("2026-10-28", b, "10:00", "14:00"),
                           ("2026-10-28", a, "15:00", "16:30"), ("2026-10-27", b, "09:00", "10:15")):
            self.client.post("/api/entries", json={"task_id": t, "date": d, "start": s, "end": e})
        rep = self.client.get("/api/tasks/report?from=2026-10-27&to=2026-10-28&group=day").get_json()
        rows = [(r["date"], r["key"], r["seconds"], r["hours"]) for r in rep["rows"]]
        self.assertEqual(rows, [("2026-10-27", "DEMO-145", 4500, 1.25), ("2026-10-28", "DEMO-123", 12600, 3.5),
                                ("2026-10-28", "DEMO-145", 14400, 4.0)])
        by_ticket = self.client.get("/api/tasks/report?group=ticket").get_json()
        self.assertEqual([(r["key"], r["hours"]) for r in by_ticket["rows"]], [("DEMO-145", 5.25), ("DEMO-123", 3.5)])
        ids = rep["rows"][1]["entry_ids"]
        self.assertEqual(self.client.post("/api/entries/booked", json={"ids": ids, "booked": True}).get_json()["updated"], 2)
        rep = self.client.get("/api/tasks/report?from=2026-10-28&to=2026-10-28").get_json()
        self.assertEqual([r["booked"] for r in rep["rows"]], ["all", "none"])
        self.assertEqual(rep["pending_s"], 14400)
        csv_text = self.client.get("/api/tasks/report.csv?from=2026-10-28&to=2026-10-28&format=decimal").get_data(as_text=True)
        self.assertTrue(csv_text.startswith("﻿Fecha;Ticket"))
        self.assertIn("28/10/2026;DEMO-123;Tarea ficticia DEMO-123;;3,50;Ya imputado", csv_text)
        hm = self.client.get("/api/tasks/report.csv?from=2026-10-28&to=2026-10-28").get_data(as_text=True)
        self.assertIn(";3 h 30 min;", hm)

    def test_running_entry_not_in_report(self):
        self.worked_day()
        a = self.new("DEMO-1")
        self.start(a, "08:00")
        self.clock.set("09:00")
        self.assertEqual(self.client.get("/api/tasks/report").get_json()["rows"], [])

    # ------------------------------------------------- persistencia y copias

    def test_persistence_after_restart(self):
        self.worked_day()
        a = self.new("DEMO-1", 60)
        self.start(a, "08:00")
        clock = FakeClock(THU, "09:30")
        again = create_app(self.data, clock).test_client()
        state = again.get("/api/tasks").get_json()
        self.assertEqual(state["active"]["task_id"], a)
        self.assertEqual(state["active"]["task_s"], 1.5 * H)        # sigue exacto tras «cerrar» la aplicación

    def test_backup_includes_tasks_and_restores(self):
        self.worked_day()
        a = self.new("DEMO-1", 60, project="Proyecto ficticio")
        self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-28", "minutes": 45, "note": "nota"})
        text = self.client.get("/api/backup").get_data(as_text=True)
        data = json.loads(text)
        self.assertEqual(data["schema_version"], 2)
        self.assertEqual(data["counts"]["tasks"], 1)
        self.assertEqual(len(data["data"]["tasks"]["entries"]), 1)
        snapshot = self.raw()
        self.client.delete(f"/api/tasks/{a}", json={"confirm": True})
        p = self.client.post("/api/backup/preview", json={"text": text}).get_json()
        res = self.client.post("/api/backup/restore", json={"text": text, "fingerprint": p["fingerprint"],
                                                            "state": p["state"], "confirm": True})
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertEqual(self.raw(), snapshot)

    def test_schema_1_backup_restores_with_empty_tasks(self):
        a = self.new("DEMO-1")
        self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-28", "minutes": 30})
        old = {"format": "jornada-backup", "schema_version": 1, "app_version": "2.1.0",
               "created_at": "2026-10-01T10:00:00+02:00",
               "data": {"records": {"version": 1, "days": {}}, "settings": core.default_settings()}}
        text = json.dumps(old)
        p = self.client.post("/api/backup/preview", json={"text": text}).get_json()
        self.assertTrue(p["overwrites"])
        res = self.client.post("/api/backup/restore", json={"text": text, "fingerprint": p["fingerprint"],
                                                            "state": p["state"], "confirm": True})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.raw()["tasks"], {})
        pre = next((self.data / "backups").glob("pre-restauracion-*"))
        self.assertTrue((pre / "tasks.json").exists())                # lo anterior queda guardado

    def test_corrupt_tasks_in_backup_rejected(self):
        a = self.new("DEMO-1")
        self.client.post("/api/entries", json={"task_id": a, "date": "2026-10-28", "minutes": 30})
        data = json.loads(self.client.get("/api/backup").get_data(as_text=True))
        e = next(iter(data["data"]["tasks"]["entries"].values()))
        e["task_id"] = "t_inexistente"
        data["checksum"] = backup.checksum(data["data"])
        res = self.client.post("/api/backup/preview", json={"text": json.dumps(data)})
        self.assertEqual(res.status_code, 400)

    def test_existing_data_without_tasks_file(self):
        """Datos de 2.1 (sin tasks.json): arrancan, se crea vacío y los fichajes no cambian."""
        self.worked_day()
        self.act("stop", "12:00")
        (self.data / "tasks.json").unlink()
        records = (self.data / "records.json").read_bytes()
        client = create_app(self.data, self.clock).test_client()
        self.assertEqual(client.get("/api/tasks").get_json()["tasks"], [])
        self.assertTrue((self.data / "tasks.json").exists())
        self.assertEqual((self.data / "records.json").read_bytes(), records)
        self.assertEqual(client.get("/api/state").status_code, 200)


class PureLogic(unittest.TestCase):
    NOW = core.combine(THU, "12:00")

    def test_decimal_hours(self):
        self.assertEqual(tm.decimal_hours(5400), 1.5)
        self.assertEqual(tm.decimal_hours(1200), 0.33)
        self.assertEqual(tm.decimal_hours(2700), 0.75)
        self.assertEqual(tm.decimal_hours(8 * H), 8.0)
        self.assertEqual(tm.hm_text(5400), "1 h 30 min")
        self.assertEqual(tm.hm_text(7200), "2 h")
        self.assertEqual(tm.hm_text(2700), "45 min")

    def test_normalize_rejects_bad_data(self):
        ok, task = tm.create_task(tm.default_data(), {"key": "demo-5", "title": "x"}, self.NOW)
        self.assertEqual(task["key"], "DEMO-5")
        bad_variants = []
        a = json.loads(json.dumps(ok))
        a["tasks"][task["id"]]["status"] = "rara"
        bad_variants.append(a)
        b = json.loads(json.dumps(ok))
        b["extra"] = 1
        bad_variants.append(b)
        c, _ = tm.add_manual(ok, {"task_id": task["id"], "date": "2026-10-28", "minutes": 30}, self.NOW)
        c = json.loads(json.dumps(c))
        next(iter(c["entries"].values()))["seconds"] = -5
        bad_variants.append(c)
        for raw in bad_variants:
            with self.assertRaises(core.ValidationError):
                tm.normalize(raw)
        self.assertEqual(tm.normalize(json.loads(json.dumps(ok)))["tasks"][task["id"]]["key"], "DEMO-5")

    def test_cross_midnight_entry(self):
        data, task = tm.create_task(tm.default_data(), {"key": "DEMO-7"}, self.NOW)
        data, e = tm.add_manual(data, {"task_id": task["id"], "date": "2026-10-27", "start": "22:00", "end": "01:00"}, self.NOW)
        self.assertEqual(tm.entry_seconds(e, self.NOW), 3 * H)

    def test_operations_never_mutate_input(self):
        data, task = tm.create_task(tm.default_data(), {"key": "DEMO-8"}, self.NOW)
        snapshot = json.dumps(data, sort_keys=True)
        tm.start(data, task["id"], self.NOW)
        tm.add_manual(data, {"task_id": task["id"], "date": "2026-10-28", "minutes": 30}, self.NOW)
        tm.pause(data, self.NOW + timedelta(hours=1))
        self.assertEqual(json.dumps(data, sort_keys=True), snapshot)


if __name__ == "__main__":
    unittest.main()
