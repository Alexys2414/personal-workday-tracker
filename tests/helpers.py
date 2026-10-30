"""Utilidades comunes de las pruebas de Jornada 2.1 (siempre con datos ficticios en carpetas temporales)."""
import tempfile
from datetime import date
from pathlib import Path

import core
from app import create_app

THU = date(2026, 10, 29)      # jueves: horario normal 8:30, descanso mínimo 1 h + 30 min opcional
FRI = date(2026, 10, 30)      # viernes: intensivo 7:00 sin descanso
SETTINGS = core.default_settings()


class FakeClock:
    def __init__(self, day=THU, value="12:00"):
        self.set(value, day)

    def set(self, value, day=None):
        self.day = day or self.day
        self.now = core.combine(self.day, value)

    def __call__(self):
        return self.now


def record(day, clock_in, clock_out=None, breaks=(), settings=SETTINGS, now=None, **payload):
    now = now or core.combine(date(2030, 1, 1), "12:00")
    payload = {"clock_in": clock_in, "clock_out": clock_out,
               "breaks": [{"start": s, "end": e} for s, e in breaks], **payload}
    return core.build_record(day, payload, None, settings, now)


class AppCase:
    """Mezcla para pruebas con la API sobre una carpeta temporal."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.clock = FakeClock()
        self.client = create_app(self.data, self.clock).test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def act(self, action, at, expect=None):
        self.clock.set(at)
        return self.client.post("/api/clock", json={"action": action, "expect": expect})

    def files(self):
        return {p.name: p.read_bytes() for p in self.data.glob("*.json")}
