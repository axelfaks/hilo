"""Que actualizar la app NO haga desaparecer los datos.

El escenario: una base que se llenó ANTES de que existiera el multi-inquilino.
Sus filas no tienen `business_id`. El ALTER las deja en NULL, y una fila en NULL
no la ve nadie, porque el filtro pide `business_id = X`.

O sea: sin el backfill, actualizar la app deja al usuario mirando una cola vacía
con todos sus clientes todavía en la base. Esto lo prueba.

    python prueba_migracion.py [ruta/a/una.db]
"""
import os
import shutil
import sys
import tempfile

ORIGEN = sys.argv[1] if len(sys.argv) > 1 else ""
CARPETA = tempfile.mkdtemp()
DB = os.path.join(CARPETA, "vieja.db")
os.environ["HILO_DB"] = DB
os.environ["HILO_SECRETO"] = "clave-de-prueba"
os.environ["HILO_OFFLINE"] = "1"

from sqlalchemy import text                                          # noqa: E402
from sqlmodel import select                                          # noqa: E402

from app import inquilino                                            # noqa: E402
from app.db import crear_tablas, engine, sesion                      # noqa: E402
from app.models import Alias, Business, Identity, Message            # noqa: E402

COLUMNAS = ("alias", "identity", "message", "briefing", "commitment", "usuario")

if ORIGEN:
    print(f"Base real: {ORIGEN}")
    for sufijo in ("", "-wal", "-shm"):
        if os.path.exists(ORIGEN + sufijo):
            shutil.copy(ORIGEN + sufijo, DB + sufijo)
else:
    print("Base sintética: se siembra y después se le sacan las columnas nuevas,")
    print("para que quede igual que una base anterior al multi-inquilino.")
    from seed import sembrar
    sembrar()

# Se simula la base vieja sacando business_id de las tablas (si está)
with engine.begin() as con:
    for t in COLUMNAS:
        try:
            con.execute(text(f'ALTER TABLE "{t}" DROP COLUMN business_id'))
        except Exception:                        # noqa: BLE001
            pass                                  # ya no la tenía: era vieja de verdad

with engine.connect() as con:
    antes = {}
    for t in ("alias", "message", "identity"):
        try:
            antes[t] = con.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
        except Exception:                        # noqa: BLE001
            antes[t] = 0
print(f"\nAntes de actualizar: {antes}")
if not antes.get("alias"):
    print("La base no tiene clientes: no hay nada que migrar. Fin.")
    sys.exit(0)

print("\nArranca la app (crear_tablas hace el ALTER y el backfill)")
crear_tablas()

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    print(("  OK    " if ok else "  FALLA ") + nombre + (("  -> " + str(detalle)) if detalle else ""))
    if not ok:
        fallos += 1


with inquilino.sin_filtro(), sesion() as s:
    negocio = s.exec(select(Business).order_by(Business.id)).first()
    check("sigue habiendo un negocio", negocio is not None)
    despues = {"alias": len(list(s.exec(select(Alias)))),
               "message": len(list(s.exec(select(Message)))),
               "identity": len(list(s.exec(select(Identity))))}
    check("no se perdió ninguna fila", despues == antes, f"{antes} -> {despues}")
    huerfanos = [a.id for a in s.exec(select(Alias)) if a.business_id is None]
    check("ningún cliente quedó sin dueño", not huerfanos, huerfanos[:5])

with inquilino.usar(negocio.id), sesion() as s:
    ve = len(list(s.exec(select(Alias))))
    check("y el negocio los sigue viendo TODOS", ve == antes["alias"],
          f"{ve} de {antes['alias']}")
    msgs = len(list(s.exec(select(Message))))
    check("y todos sus mensajes", msgs == antes["message"], f"{msgs} de {antes['message']}")

print("\nSegunda corrida (tiene que ser inofensiva)")
crear_tablas()
with inquilino.usar(negocio.id), sesion() as s:
    check("no duplicó ni perdió nada", len(list(s.exec(select(Alias)))) == antes["alias"])

print()
if fallos:
    print(f"{fallos} prueba(s) fallaron.")
    sys.exit(1)
print("Actualizar no pierde datos.")
