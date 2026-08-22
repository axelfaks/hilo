# -*- coding: utf-8 -*-
"""Arranca Hilo sin depender del PATH.

    python run.py            -> http://localhost:8000
    python run.py --reload   -> con recarga en caliente mientras programás

En Windows, `pip install` deja uvicorn.exe en una carpeta que PowerShell no mira,
así que `uvicorn ...` a secas falla. Esto lo evita.
"""
import socket
import sys


def mi_ip() -> str:
    """La IP de esta máquina en la red local: es la que hay que pasarle al celular."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "localhost"
    finally:
        s.close()


if __name__ == "__main__":
    import os

    import uvicorn

    from app.config import cargar
    cargar()

    from app import ai
    estado = ai.como_esta()

    ip = mi_ip()
    print()
    print("  Hilo levantado")
    puerto = int(os.environ.get("PORT", 8000))
    print(f"  En esta compu      http://localhost:{puerto}")
    print(f"  Desde el celular   http://{ip}:{puerto}/#/c/laespiga")
    if estado["activa"]:
        print(f"  IA                 conectada por {estado['proveedor']}")
    else:
        print("  IA                 apagada (poné GEMINI_API_KEY en el archivo .env)")
    print()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload="--reload" in sys.argv,
        log_level="warning",
    )
