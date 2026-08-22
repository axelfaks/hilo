# -*- coding: utf-8 -*-
"""Deja Hilo como recién instalado, para ensayar el recorrido completo.

    python empezar_de_cero.py          -> pregunta antes de borrar
    python empezar_de_cero.py --si     -> sin preguntar

`seed.py` a propósito NUNCA toca la tabla de usuarios: así uno resiembra los
clientes cien veces sin quedarse afuera de su propia app. Pero para mostrar el
recorrido de alguien que llega por primera vez —landing, crear cuenta,
onboarding— hay que borrar la cuenta también. Eso es lo que agrega este script,
y por eso está separado: borrar usuarios no puede ser un efecto secundario de
resembrar.
"""
import sys

from app.config import cargar as cargar_env

cargar_env()
from app.db import sesion                      # noqa: E402
from app.models import Business, Usuario       # noqa: E402
from sqlmodel import select                    # noqa: E402

if "--si" not in sys.argv:
    print()
    print("  Esto borra TODAS las cuentas y vuelve la base a la posición de demo.")
    print("  Vas a tener que crear tu usuario de nuevo desde la app.")
    print()
    if input("  ¿Seguimos? (escribí SI): ").strip().upper() != "SI":
        print("  No toqué nada.")
        raise SystemExit

from seed import sembrar                       # noqa: E402

sembrar()

with sesion() as s:
    cuentas = list(s.exec(select(Usuario)))
    for u in cuentas:
        s.delete(u)
    negocio = s.exec(select(Business)).first()
    if negocio:
        negocio.onboarding_hecho = False       # que vuelva a arrancar por el onboarding
        s.add(negocio)
    s.commit()

print()
print(f"  Listo. Borré {len(cuentas)} cuenta(s) y reabrí el onboarding.")
print()
print("  Ahora, entrando a la app vas a ver, en este orden:")
print("    1. la landing          (no hay sesión)")
print("    2. crear la cuenta     al tocar «Entrar a Hilo»")
print("    3. el onboarding       los 2 pasos de Mars")
print("    4. la cola             con los 11 clientes de la demo")
print()
