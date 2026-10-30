"""Notas, exportación/importación CSV, atajos, idiomas y su integración en la API."""
import base64
import csv
import io
import json
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path

import core
import csvio
import i18n
from app import create_app

ROOT = Path(__file__).resolve().parent.parent
D = date(2026, 10, 27)
NOW = core.combine(date(2026, 10, 29), "12:00")
SETTINGS = core.default_settings()


def day_record(day, clock_in, clock_out, breaks=(), **payload):
    payload = {"clock_in": clock_in, "clock_out": clock_out,
               "breaks": [{"start": s, "end": e, "note": n} for s, e, n in breaks], **payload}
    return core.build_record(day, payload, None, SETTINGS, NOW)


def sample_days():
    return {
        "2026-10-26": day_record(date(2026, 10, 26), "08:00", "17:40", [("14:00", "15:00", "Cita médica")],
                                 notes="Reunión con el equipo"),
        "2026-10-27": day_record(D, "07:53:12", "17:20", [("10:30", "10:45", ""), ("14:00", "14:45", "=SUMA(A1)")]),
        "2026-10-28": day_record(date(2026, 10, 28), "08:00", "15:00", profile="summer", mode="remote"),
        "2026-10-30": core.build_record(date(2026, 10, 30), {"mode": "off", "notes": "Puente"}, None, SETTINGS, NOW),
    }


def b64(text, encoding="utf-8"):
    return base64.b64encode(text.encode(encoding)).decode()


class Notes(unittest.TestCase):
    def test_notes_never_change_calculations(self):
        rec = day_record(D, "08:00", "17:30", [("14:00", "15:00", "")])
        before = core.compute_day(D, rec, SETTINGS, NOW)
        rec = core.set_note(rec, "day", "Hoy he entrado antes")
        rec = core.set_note(rec, 0, "Gestión")
        after = core.compute_day(D, rec, SETTINGS, NOW)
        for key in ("worked_s", "break_s", "balance_s", "target_s", "status"):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(after["notes"], "Hoy he entrado antes")
        self.assertEqual(after["breaks"][0]["note"], "Gestión")
        self.assertTrue(after["has_notes"])

    def test_delete_note(self):
        rec = day_record(D, "08:00", "17:30", [("14:00", "15:00", "x")])
        rec = core.set_note(rec, 0, "")
        self.assertNotIn("note", rec["breaks"][0])

    def test_break_notes_survive_actions_and_edits(self):
        today = date(2026, 10, 29)
        rec = core.apply_action("start", today, None, SETTINGS, core.combine(today, "08:00"))
        rec = core.apply_action("break_start", today, rec, SETTINGS, core.combine(today, "11:00"))
        rec = core.set_note(rec, 0, "Café")
        rec = core.apply_action("stop", today, rec, SETTINGS, core.combine(today, "11:30"))
        self.assertEqual(rec["breaks"][0]["note"], "Café")
        rec = core.build_record(today, {"clock_out": "12:00"}, rec, SETTINGS, core.combine(today, "13:00"))
        self.assertEqual(rec["breaks"][0]["note"], "Café")

    def test_invalid_note_target_and_length(self):
        rec = day_record(D, "08:00", "17:30")
        with self.assertRaises(core.ValidationError):
            core.set_note(rec, 3, "x")
        with self.assertRaises(core.ValidationError):
            core.set_note(rec, "abc", "x")
        rec = day_record(D, "08:00", "17:30", [("14:00", "15:00", "")])
        with self.assertRaises(core.ValidationError):
            core.set_note(rec, 0, "x" * (core.MAX_BREAK_NOTE + 1))

    def test_legacy_records_without_notes(self):
        legacy = {"clock_in": "2026-10-27T08:00:00+01:00", "clock_out": "2026-10-27T17:30:00+01:00",
                  "breaks": [{"start": "2026-10-27T14:00:00+01:00", "end": "2026-10-27T15:00:00+01:00"}],
                  "target_minutes": 510, "min_break_minutes": 60, "optional_break_minutes": 30, "mode": "office"}
        c = core.compute_day(D, legacy, SETTINGS, NOW)
        self.assertFalse(c["has_notes"])
        self.assertEqual(c["breaks"][0]["note"], "")
        self.assertIn("2026-10-27", csvio.export_csv({"2026-10-27": legacy}, SETTINGS, "es", NOW))


class CsvExport(unittest.TestCase):
    def setUp(self):
        self.text = csvio.export_csv(sample_days(), SETTINGS, "es", NOW)
        self.rows = list(csv.reader(io.StringIO(self.text.lstrip("﻿")), delimiter=";"))

    def test_excel_friendly_format(self):
        self.assertTrue(self.text.startswith("﻿"))
        self.assertIn("\r\n", self.text)
        self.assertEqual(self.rows[0][:6], ["fecha", "dia", "modalidad", "perfil", "perfil_manual", "entrada"])
        self.assertIn("descanso_2_nota", self.rows[0])

    def test_values(self):
        row = dict(zip(self.rows[0], self.rows[2]))       # 27/10
        self.assertEqual(row["entrada"], "07:53:12")
        self.assertEqual(row["trabajo_efectivo"], "8:26:48")
        self.assertEqual(row["balance"], "-0:03:12")
        self.assertEqual(row["descanso_2_nota"], "'=SUMA(A1)")      # neutralizado para Excel
        first = dict(zip(self.rows[0], self.rows[1]))
        self.assertEqual(first["notas"], "Reunión con el equipo")
        self.assertEqual(first["descanso_1_nota"], "Cita médica")
        summer = dict(zip(self.rows[0], self.rows[3]))
        self.assertEqual((summer["perfil"], summer["perfil_manual"], summer["modalidad"]),
                         ("Intensivo de verano", "sí", "Teletrabajo"))

    def test_range_and_english(self):
        text = csvio.export_csv(sample_days(), SETTINGS, "en", NOW, date(2026, 10, 27), date(2026, 10, 28))
        rows = list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))
        self.assertEqual(rows[0][0], "date")
        self.assertEqual([r[0] for r in rows[1:]], ["2026-10-27", "2026-10-28"])


class CsvImport(unittest.TestCase):
    def test_round_trip_preserves_everything(self):
        days = sample_days()
        for lang in ("es", "en"):
            text = csvio.export_csv(days, SETTINGS, lang, NOW)
            result = csvio.parse_import(text, {}, SETTINGS, NOW, lang)
            self.assertEqual(result["counts"], {"new": 4, "dup": 0, "error": 0}, lang)
            for key, original in days.items():
                imported = result["records"][key]
                for field in ("clock_in", "clock_out", "breaks", "mode", "notes", "profile",
                              "target_minutes", "min_break_minutes", "optional_break_minutes"):
                    self.assertEqual(imported.get(field), original.get(field), f"{lang} {key} {field}")
                self.assertEqual(core.compute_day(date.fromisoformat(key), imported, SETTINGS, NOW)["worked_s"],
                                 core.compute_day(date.fromisoformat(key), original, SETTINGS, NOW)["worked_s"])
            self.assertEqual(result["records"]["2026-10-28"]["profile_source"], "manual")

    def test_duplicates_skip_or_overwrite(self):
        days = sample_days()
        text = csvio.export_csv(days, SETTINGS, "es", NOW)
        existing = {"2026-10-26": days["2026-10-26"], "2026-10-27": day_record(D, "09:00", "10:00")}
        result = csvio.parse_import(text, existing, SETTINGS, NOW, "es")
        self.assertEqual(result["counts"], {"new": 2, "dup": 2, "error": 0})
        merged, n = csvio.merge(existing, result["records"], set())
        self.assertEqual(n, 2)
        self.assertEqual(merged["2026-10-27"]["clock_out"], existing["2026-10-27"]["clock_out"])   # no se toca
        merged, n = csvio.merge(existing, result["records"], {"2026-10-27"})
        self.assertEqual(n, 3)
        self.assertEqual(merged["2026-10-27"]["clock_in"], days["2026-10-27"]["clock_in"])

    def test_row_validation(self):
        text = ("fecha;entrada;salida;descanso_1_inicio;descanso_1_fin;objetivo\n"
                "2026-13-01;08:00;17:00;;;8:30\n"         # fecha imposible
                "2026-10-20;08:00;07:00;;;8:30\n"         # salida antes de entrada
                "2026-10-21;08:00;17:00;16:00;18:00;8:30\n"  # descanso tras la salida
                "2026-10-22;08:00;17:00;;;ocho\n"          # duración no válida
                "2026-10-23;25:00;17:00;;;8:30\n"          # hora no válida
                "2026-10-26;08:00;17:00;;;8:30\n"
                "2026-10-26;08:00;17:00;;;8:30\n"          # duplicada en el archivo
                "2030-01-01;08:00;17:00;;;8:30\n")         # futuro
        result = csvio.parse_import(text, {}, SETTINGS, NOW, "es")
        statuses = [r["status"] for r in result["rows"]]
        self.assertEqual(statuses, ["error", "error", "error", "error", "error", "new", "error", "error"])
        self.assertTrue(all(r["errors"] for r in result["rows"] if r["status"] == "error"))
        self.assertIn("posterior", result["rows"][1]["errors"][0])

    def test_structure_errors(self):
        with self.assertRaises(core.ValidationError):
            csvio.parse_import("", {}, SETTINGS, NOW, "es")
        with self.assertRaises(core.ValidationError) as ctx:
            csvio.parse_import("hola;adios\n1;2\n", {}, SETTINGS, NOW, "es")
        self.assertEqual(ctx.exception.code, "imp.e.missing_cols")
        with self.assertRaises(core.ValidationError):
            csvio.decode_upload("no es base64!!", "es")

    def test_excel_resaved_file(self):
        """Excel en Windows: cp1252, separador «,» y fechas día/mes/año."""
        text = "fecha,modalidad,entrada,salida,descanso_1_inicio,descanso_1_fin,descanso_1_nota,notas\r\n" \
               "27/10/2026,Oficina,8:00,17:30,14:00,15:00,Cita médica,Reunión\r\n"
        decoded = csvio.decode_upload(b64(text, "cp1252"), "es")
        result = csvio.parse_import(decoded, {}, SETTINGS, NOW, "es")
        rec = result["records"]["2026-10-27"]
        self.assertEqual(rec["notes"], "Reunión")
        self.assertEqual(rec["breaks"][0]["note"], "Cita médica")
        self.assertEqual(core.compute_day(D, rec, SETTINGS, NOW)["worked_s"], 510 * 60)


class Preferences(unittest.TestCase):
    def test_defaults(self):
        s = core.default_settings()
        self.assertEqual(s["language"], "es")
        self.assertEqual(set(s["shortcuts"]), set(core.SHORTCUT_ACTIONS))
        self.assertTrue(all(core.valid_shortcut(c) for c in s["shortcuts"].values()))

    def test_shortcut_validation(self):
        ok = core.normalize_settings({"shortcuts": {"start_day": "Ctrl+Shift+KeyI", "open_calendar": None}})
        self.assertEqual(ok["shortcuts"]["start_day"], "Ctrl+Shift+KeyI")
        self.assertIsNone(ok["shortcuts"]["open_calendar"])
        for bad in ("Shift+Ctrl+KeyI", "Ctrl+Ctrl+KeyI", "Ctrl+", "Hyper+KeyA", "Ctrl+KeyÑ", 5):
            with self.assertRaises(core.ValidationError, msg=bad):
                core.normalize_settings({"shortcuts": {"start_day": bad}})
        with self.assertRaises(core.ValidationError) as ctx:
            core.normalize_settings({"shortcuts": {"start_day": "Alt+KeyC", "open_calendar": "Alt+KeyC"}})
        self.assertEqual(ctx.exception.code, "err.dup_shortcut")

    def test_language_validation(self):
        self.assertEqual(core.normalize_settings({"language": "en"})["language"], "en")
        with self.assertRaises(core.ValidationError):
            core.normalize_settings({"language": "fr"})


class Translations(unittest.TestCase):
    def test_same_keys_and_placeholders(self):
        es, en = i18n.catalog("es"), i18n.catalog("en")
        self.assertEqual(set(es), set(en), set(es) ^ set(en))
        params = lambda s: set(re.findall(r"\{(\w+)\}", s))  # noqa: E731
        for key in es:
            self.assertEqual(params(es[key]), params(en[key]), key)

    def test_every_key_used_in_code_exists(self):
        keys = set(i18n.catalog("es"))
        sources = [*ROOT.glob("static/js/*.js"), *ROOT.glob("templates/*.html"), *ROOT.glob("*.py")]
        pattern = re.compile(r"""(?:\bt|\btr|ValidationError|Conflict)\(\s*['"]([a-z_]+\.[\w.]+)['"]"""
                             r"""|data-i18n(?:-html|-title|-aria|-placeholder)?=["']([\w.]+)["']""")
        used = set()
        for path in sources:
            for a, b in pattern.findall(path.read_text(encoding="utf-8")):
                used.add(a or b)
        # Un prefijo que termina en «.» es una clave compuesta en ejecución (p. ej. 'weekday.short.' ~ i).
        missing = sorted(k for k in used if k not in keys and not k.endswith('.'))
        self.assertEqual(missing, [])
        self.assertGreater(len(used), 150)

    def test_errors_are_translated(self):
        with self.assertRaises(core.ValidationError) as ctx:
            core.build_record(D, {"clock_in": "09:00", "clock_out": "08:00"}, None, SETTINGS, NOW)
        self.assertIn("posterior", str(ctx.exception))
        self.assertEqual(ctx.exception.message("en"), "Clock-out must be after clock-in.")
        with self.assertRaises(core.ValidationError) as ctx:
            core.build_record(D, {"clock_in": "08:00", "breaks": [{"start": "xx"}]}, None, SETTINGS, NOW)
        self.assertEqual(ctx.exception.message("en"), "Break 1 start: “xx” isn't a valid time (HH:MM).")


class Report(unittest.TestCase):
    def test_totals_are_consistent(self):
        from app import report_context
        days = sample_days()
        days["2026-10-29"] = core.apply_action("start", date(2026, 10, 29), None, SETTINGS, core.combine(date(2026, 10, 29), "08:00"))
        ctx = report_context(days, SETTINGS, "es", NOW, date(2026, 10, 1), date(2026, 10, 31))
        to_min = lambda s: (-1 if s.startswith("−") else 1) * (int(s.strip("+−").split(":")[0]) * 60 + int(s.split(":")[1]))  # noqa: E731
        s = ctx["summary"]
        self.assertEqual(to_min(s["worked"]) - to_min(s["target"]), to_min(s["balance"]))
        self.assertTrue(s["has_open"])
        self.assertEqual(s["days"], 4)                       # 3 cerradas + 1 en curso
        self.assertEqual(ctx["period"], "Del 01/10/2026 al 31/10/2026")


class ApiFeatures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.client = create_app(self.data, lambda: NOW).test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def put_day(self, day, **body):
        r = self.client.put(f"/api/days/{day}", json=body)
        self.assertEqual(r.status_code, 200, r.get_json())

    def test_notes_endpoint(self):
        self.put_day("2026-10-27", clock_in="08:00", clock_out="17:30", breaks=[{"start": "14:00", "end": "15:00"}])
        r = self.client.post("/api/days/2026-10-27/note", json={"target": 0, "text": "Cita médica"})
        self.assertEqual(r.get_json()["breaks"][0]["note"], "Cita médica")
        r = self.client.post("/api/days/2026-10-27/note", json={"target": "day", "text": "Reunión"})
        self.assertEqual((r.get_json()["notes"], r.get_json()["worked_s"]), ("Reunión", 510 * 60))
        self.assertEqual(self.client.post("/api/days/2026-10-27/note", json={"target": 9, "text": "x"}).status_code, 400)

    def test_preferences_persist(self):
        r = self.client.put("/api/settings", json={"language": "en", "shortcuts": {"toggle_theme": "Ctrl+Alt+KeyY"}})
        self.assertEqual(r.status_code, 200)
        again = create_app(self.data, lambda: NOW).test_client().get("/api/settings").get_json()
        self.assertEqual((again["language"], again["shortcuts"]["toggle_theme"]), ("en", "Ctrl+Alt+KeyY"))
        page = create_app(self.data, lambda: NOW).test_client().get("/").get_data(as_text=True)
        self.assertIn('<html lang="en"', page)
        self.assertIn(">History</h2>", page)                     # la página llega ya traducida
        self.assertIn('"_lang": "en"', page)                      # diccionario incrustado
        self.assertNotIn(">Historial</h2>", page)
        defaults = self.client.get("/api/shortcuts/defaults").get_json()
        self.assertEqual(defaults, core.DEFAULT_SHORTCUTS)
        bad = self.client.put("/api/days/2026-10-27", json={"clock_in": "09:00", "clock_out": "08:00"})
        self.assertEqual(bad.get_json()["error"], "Clock-out must be after clock-in.")

    def test_export_report_import_flow(self):
        self.put_day("2026-10-26", clock_in="08:00", clock_out="17:40", breaks=[{"start": "14:00", "end": "15:00", "note": "Gestión"}])
        self.put_day("2026-10-27", clock_in="08:00", clock_out="17:20", notes="Hoy he entrado antes")
        r = self.client.get("/api/export.csv?from=2026-10-01&to=2026-10-31")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.content_type)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        exported = r.get_data(as_text=True)

        report = self.client.get("/report?from=2026-10-01&to=2026-10-31").get_data(as_text=True)
        self.assertIn("Informe de jornada", report)
        self.assertIn("Gestión", report)
        self.assertIn("@page", report)
        self.assertEqual(self.client.get("/report?from=2026-10-31&to=2026-10-01").status_code, 400)

        # Importar en otra instancia vacía: vista previa, confirmación y copia de seguridad.
        other = Path(self.tmp.name) / "otro"
        client = create_app(other, lambda: NOW).test_client()
        client.put("/api/days/2026-10-27", json={"clock_in": "09:00", "clock_out": "10:00"})
        prev = client.post("/api/import/preview", json={"file": b64(exported)}).get_json()
        self.assertEqual(prev["counts"], {"new": 1, "dup": 1, "error": 0})
        self.assertNotIn("records", prev)
        # Sin elegir sobrescritura: solo entra la nueva.
        r = client.post("/api/import/commit", json={"file": b64(exported), "overwrite": [], "fingerprint": prev["fingerprint"]})
        self.assertEqual(r.get_json()["imported"], 1)
        backup = other / r.get_json()["backup"].removeprefix("data/")
        self.assertTrue(backup.exists())
        days = json.loads((other / "records.json").read_text())["days"]
        self.assertEqual(days["2026-10-27"]["clock_in"], "2026-10-27T09:00:00+01:00")   # intacto
        self.assertEqual(days["2026-10-26"]["breaks"][0]["note"], "Gestión")
        # La huella ya no coincide: hay que volver a previsualizar.
        r = client.post("/api/import/commit", json={"file": b64(exported), "overwrite": ["2026-10-27"], "fingerprint": prev["fingerprint"]})
        self.assertEqual(r.status_code, 409)
        prev = client.post("/api/import/preview", json={"file": b64(exported)}).get_json()
        r = client.post("/api/import/commit", json={"file": b64(exported), "overwrite": ["2026-10-27"], "fingerprint": prev["fingerprint"]})
        self.assertEqual(r.get_json()["imported"], 1)
        days = json.loads((other / "records.json").read_text())["days"]
        self.assertEqual(days["2026-10-27"]["notes"], "Hoy he entrado antes")

    def test_import_with_errors_writes_nothing(self):
        before = (self.data / "records.json").read_text()
        prev = self.client.post("/api/import/preview", json={"file": b64("fecha;entrada;salida\n2026-10-27;09:00;08:00\n")}).get_json()
        self.assertEqual(prev["counts"]["error"], 1)
        r = self.client.post("/api/import/commit", json={"file": b64("fecha;entrada;salida\n2026-10-27;09:00;08:00\n"),
                                                         "overwrite": [], "fingerprint": prev["fingerprint"]})
        self.assertEqual(r.get_json(), {"imported": 0, "backup": None})
        self.assertEqual((self.data / "records.json").read_text(), before)
        self.assertFalse((self.data / "backups").exists())


if __name__ == "__main__":
    unittest.main()
