"""Traducciones de Jornada (servidor).

Los textos viven en static/i18n/<idioma>.json: una única fuente que usan el
servidor (plantilla inicial, errores, CSV e informe) y el navegador.
Para añadir un idioma basta con crear otro JSON con las mismas claves y
añadir su código a LANGUAGES.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LANGUAGES = ("es", "en")
DEFAULT = "es"
LOCALES = {"es": "es-ES", "en": "en-GB"}
_DIR = Path(__file__).resolve().parent / "static" / "i18n"


@lru_cache(maxsize=None)
def catalog(lang: str) -> dict:
    lang = lang if lang in LANGUAGES else DEFAULT
    with open(_DIR / f"{lang}.json", encoding="utf-8") as fh:
        return json.load(fh)


def tr(lang: str, key: str, **params) -> str:
    """Traduce `key`. Un parámetro que empieza por '@' es a su vez una clave."""
    text = catalog(lang).get(key) or catalog(DEFAULT).get(key) or key
    if not params:
        return text
    resolved = {k: tr(lang, v[1:], **{p: q for p, q in params.items() if p != k})
                if isinstance(v, str) and v.startswith("@") else v
                for k, v in params.items()}
    try:
        return text.format(**resolved)
    except (KeyError, IndexError, ValueError):
        return text


class Translatable(ValueError):
    """Error con código traducible: str() devuelve el texto en español."""

    def __init__(self, code: str, **params):
        self.code = code
        self.params = params
        super().__init__(tr(DEFAULT, code, **params))

    def message(self, lang: str) -> str:
        return tr(lang, self.code, **self.params)
