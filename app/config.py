"""Carga el .env si existe, para no tener que exportar variables a mano.

Poné UNA clave en un archivo `.env` en la raíz del proyecto:

    GEMINI_API_KEY=...        # https://aistudio.google.com/apikey
    ANTHROPIC_API_KEY=sk-...  # https://platform.claude.com/settings/keys

Lo parseamos a mano a propósito: PowerShell escribe archivos con BOM y con
comillas, y eso rompe silenciosamente el nombre de la primera variable. Acá se
limpia todo antes de que llegue a os.environ.
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def cargar() -> list:
    """Devuelve los nombres de las claves que encontró, sin sus valores."""
    archivo = RAIZ / ".env"
    if not archivo.exists():
        return []
    encontradas = []
    # utf-8-sig se come el BOM que deja PowerShell con Out-File -Encoding utf8
    for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip().lstrip("﻿")
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip().lstrip("﻿")
        valor = valor.strip().strip('"').strip("'").strip()
        if not clave or not valor:
            continue
        os.environ[clave] = valor
        encontradas.append(clave)
    return encontradas
