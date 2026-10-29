"""Persistencia en JSON con escritura atómica.

Cada guardado escribe en un archivo temporal del mismo directorio, hace
fsync y lo sustituye con os.replace(), que es atómico: si el proceso se
interrumpe a mitad, el archivo original sigue intacto. Antes de sustituirlo
se conserva la versión anterior como copia `.bak`.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)


class JsonStore:
    def __init__(self, path: Path, default_factory: Callable[[], dict]):
        self.path = Path(path)
        self.backup = self.path.with_suffix(self.path.suffix + ".bak")
        self.default_factory = default_factory
        self.lock = threading.RLock()

    def load(self) -> dict:
        with self.lock:
            if not self.path.exists():
                data = self.default_factory()
                self.save(data)
                return data
            try:
                return self._read(self.path)
            except (OSError, ValueError) as exc:
                return self._recover(exc)

    def save(self, data: dict) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.",
                                       suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
                    fh.write("\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                if self.path.exists():
                    shutil.copy2(self.path, self.backup)
                os.replace(tmp, self.path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
            self._fsync_dir()

    @staticmethod
    def _read(path: Path) -> dict:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("el contenido no es un objeto JSON")
        return data

    def _recover(self, exc: Exception) -> dict:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        corrupt = self.path.with_name(f"{self.path.stem}.corrupt-{stamp}{self.path.suffix}")
        os.replace(self.path, corrupt)
        log.error("%s ilegible (%s). Copia apartada en %s", self.path.name, exc, corrupt.name)
        try:
            data = self._read(self.backup)
            log.warning("Restaurado desde %s", self.backup.name)
        except (OSError, ValueError):
            data = self.default_factory()
        self.save(data)
        return data

    def _fsync_dir(self) -> None:
        if os.name != "posix":
            return
        try:
            fd = os.open(self.path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
