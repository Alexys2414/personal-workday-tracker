"""Arranque real del servidor: segunda instancia, puerto ocupado y cierre limpio."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
opener = build_opener(ProxyHandler({}))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(port, path):
    with opener.open(f"http://127.0.0.1:{port}{path}", timeout=2) as res:
        return json.load(res)


def post_json(port, path):
    req = Request(f"http://127.0.0.1:{port}{path}", data=b"{}", method="POST",
                  headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=2) as res:
        return json.load(res)


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {**os.environ, "WORKTIME_DATA_DIR": self.tmp.name, "BROWSER": "true"}
        self.procs = []

    def tearDown(self):
        for p in self.procs:          # solo los procesos lanzados por esta prueba
            if p.poll() is None:
                p.kill()
            p.wait()
            p.stdout.close()
        self.tmp.cleanup()

    def launch(self, port):
        p = subprocess.Popen([sys.executable, str(ROOT / "app.py"), "--port", str(port)],
                             cwd=ROOT, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.procs.append(p)
        return p

    def wait_ping(self, port, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            try:
                return get(port, "/api/ping")
            except OSError:
                time.sleep(0.1)
        self.fail(f"El servidor no respondió en el puerto {port}")

    def test_start_second_instance_and_clean_shutdown(self):
        port = free_port()
        first = self.launch(port)
        ping = self.wait_ping(port)
        self.assertEqual((ping["app"], ping["pid"]), ("jornada", first.pid))
        run_file = Path(self.tmp.name) / ".jornada-run.json"
        self.assertEqual(json.loads(run_file.read_text())["port"], port)

        # Segunda instancia: detecta la primera y termina sin abrir otro servidor.
        second = subprocess.run([sys.executable, str(ROOT / "app.py"), "--port", str(port)],
                                cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(second.returncode, 0)
        self.assertIn("ya estaba abierta", second.stdout)

        # Cierre desde la interfaz: el proceso termina, el puerto queda libre.
        self.assertTrue(post_json(port, "/api/shutdown")["ok"])
        self.assertEqual(first.wait(timeout=10), 0)
        self.assertIn("Jornada detenida", first.stdout.read())
        self.assertFalse(run_file.exists())
        with socket.socket() as s:
            s.bind(("127.0.0.1", port))      # no lanza: el puerto está libre

    def test_busy_port_is_skipped_without_touching_it(self):
        with socket.socket() as other:       # "otro programa" usando el puerto
            other.bind(("127.0.0.1", 0))
            other.listen()
            busy = other.getsockname()[1]
            proc = self.launch(busy)
            self.wait_ping(busy + 1)
            self.assertEqual(get(busy + 1, "/api/ping")["pid"], proc.pid)
            post_json(busy + 1, "/api/shutdown")
            self.assertEqual(proc.wait(timeout=10), 0)
            other.settimeout(0.1)            # el otro programa sigue intacto
            self.assertEqual(other.getsockname()[1], busy)

    def test_stale_run_file_is_ignored(self):
        port = free_port()
        (Path(self.tmp.name) / ".jornada-run.json").write_text(json.dumps({"pid": 1, "port": port}))
        proc = self.launch(port)
        self.assertEqual(self.wait_ping(port)["pid"], proc.pid)
        post_json(port, "/api/shutdown")
        self.assertEqual(proc.wait(timeout=10), 0)


if __name__ == "__main__":
    unittest.main()
