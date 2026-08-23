"""El recorrido de alguien que llega por primera vez, con la base ya sembrada.

    empezar_de_cero.py  ->  landing  ->  onboarding  ->  crear cuenta  ->  la cola

Es el guion de la demo. Con multi-inquilino hay un riesgo nuevo y silencioso: que
el onboarding cree un negocio NUEVO, la cuenta entre a ese, y los 11 clientes
sembrados queden en otro. Todo devolvería 200 y la cola aparecería vacía.

    python prueba_recorrido.py
"""
import os
import sys
import tempfile

os.environ["HILO_DB"] = os.path.join(tempfile.mkdtemp(), "recorrido.db")
os.environ["HILO_SECRETO"] = "clave-de-prueba"
os.environ["HILO_OFFLINE"] = "1"

from fastapi.testclient import TestClient                            # noqa: E402
from sqlmodel import select                                          # noqa: E402

from app import inquilino                                            # noqa: E402
from app.db import sesion                                            # noqa: E402
from app.models import Business, Usuario                             # noqa: E402
from seed import sembrar                                             # noqa: E402

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    print(("  OK    " if ok else "  FALLA ") + nombre + (("  -> " + str(detalle)) if detalle else ""))
    if not ok:
        fallos += 1


print("\n1. Se siembra la demo")
sembrar()
# sembrar() deja el inquilino fijado a propósito (los 11 clientes tienen que
# nacer con dueño). Acá se limpia para simular un server recién arrancado: si
# quedara puesto, el onboarding creería que ya hay un negocio elegido.
inquilino.fijar(None)

print("\n2. empezar_de_cero: se borran las cuentas y se reabre el onboarding")
with inquilino.sin_filtro(), sesion() as s:
    for u in s.exec(select(Usuario)):
        s.delete(u)
    b = s.exec(select(Business).order_by(Business.id)).first()
    b.onboarding_hecho = False
    s.add(b)
    s.commit()
    SEMBRADO = b.id
print(f"   negocio sembrado: {SEMBRADO}")

from app.main import app                                             # noqa: E402

with TestClient(app) as c:
    print("\n3. El onboarding, sin cuenta")
    r = c.post("/api/onboarding/guardar", json={
        "nombre": "Panadería La Espiga", "descripcion": "vendo pan",
        "rubro": "panaderias", "vendedor": "Axel",
        "estados": ["Nuevo", "En conversación", "Cerrado"],
        "reglas": {"tono": "cercano"}, "canales": [], "autonomia_default": 3})
    check("guarda la configuración", r.status_code == 200, r.text[:150])
    negocio_id = r.json().get("negocio_id")
    check("devuelve el negocio_id", negocio_id is not None, negocio_id)
    check("y ADOPTA el negocio sembrado en vez de crear uno nuevo",
          negocio_id == SEMBRADO, f"devolvió {negocio_id}, sembrado {SEMBRADO}")

    print("\n4. Se crea la cuenta pasando ese negocio_id")
    r = c.post("/api/auth/registro", json={"email": "axel@hilo.test",
                                           "password": "medialuna99",
                                           "nombre": "Axel", "negocio_id": negocio_id})
    check("se crea la cuenta", r.status_code == 200, r.text[:150])
    u = r.json()["usuario"]
    check("la cuenta entra al negocio sembrado", u["negocio_id"] == SEMBRADO,
          u["negocio_id"])
    h = {"Authorization": "Bearer " + r.json()["token"]}

    print("\n5. La cola tiene que traer los 11 clientes")
    cola = c.get("/api/cola", headers=h).json()
    check("11 clientes", len(cola.get("clientes", [])) == 11, len(cola.get("clientes", [])))
    check("el mensaje sin identificar sigue ahí",
          len(cola.get("sin_identificar", [])) >= 1, len(cola.get("sin_identificar", [])))
    check("el negocio quedó con el nombre del onboarding",
          c.get("/api/negocio", headers=h).json().get("nombre") == "Panadería La Espiga")

    print("\n6. Una SEGUNDA cuenta no se mete en la del primero")
    r = c.post("/api/onboarding/guardar", json={
        "nombre": "Estudio Ruiz", "descripcion": "contabilidad", "rubro": "contadores",
        "vendedor": "Ruiz", "estados": ["Nuevo", "Cerrado"], "reglas": {},
        "canales": [], "autonomia_default": 3})
    otro = r.json().get("negocio_id")
    check("el segundo visitante estrena su propio negocio", otro != SEMBRADO,
          f"{otro} vs {SEMBRADO}")
    r = c.post("/api/auth/registro", json={"email": "ruiz@hilo.test",
                                           "password": "balance2026", "negocio_id": otro})
    h2 = {"Authorization": "Bearer " + r.json()["token"]}
    cola2 = c.get("/api/cola", headers=h2).json()
    check("y arranca con la cola vacía, no con los 11 de la panadería",
          len(cola2.get("clientes", [])) == 0, len(cola2.get("clientes", [])))
    check("el primero sigue viendo sus 11",
          len(c.get("/api/cola", headers=h).json().get("clientes", [])) == 11)

    print("\n7. Y no se puede robar un negocio ajeno mandando su id")
    r = c.post("/api/auth/registro", json={"email": "colado@hilo.test",
                                           "password": "colado12345",
                                           "negocio_id": SEMBRADO})
    check("registrarse con el negocio_id de otro NO te mete adentro",
          r.status_code == 200 and r.json()["usuario"]["negocio_id"] != SEMBRADO,
          r.json().get("usuario", {}).get("negocio_id") if r.status_code == 200 else r.status_code)
    h3 = {"Authorization": "Bearer " + r.json()["token"]}
    check("y su cola está vacía",
          len(c.get("/api/cola", headers=h3).json().get("clientes", [])) == 0)

print()
if fallos:
    print(f"{fallos} prueba(s) fallaron.")
    sys.exit(1)
print("El recorrido de alguien nuevo sigue andando, y nadie entra a la cuenta de otro.")
