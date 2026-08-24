"""La prueba de 7 días, la tarjeta y el corte automático.

Esto es lo que separa "una app que usa gente" de "una app que cobra", así que se
prueba entero y por HTTP:

  1. Una cuenta nueva estrena 7 días de prueba y entra a todo.
  2. Cuando se le acaba, la API le devuelve 402 —no 403— y solo le deja las
     pantallas para pagar. El corte no lo dispara nadie: sale de la fecha.
  3. Pone la tarjeta (Mercado Pago simulado) y vuelve a entrar sola.
  4. El mismo aviso de pago repetido NO suma dos meses.
  5. Al que ya pagó, una tarjeta que rebota le da 3 días de gracia; al que nunca
     pagó, la prueba se le termina el día que se termina.
  6. Cancelar la suscripción no le corta el acceso que ya pagó.
  7. El webhook de Mercado Pago cobra de verdad… y nunca le cree al aviso: le
     pregunta a MP.
  8. Nosotros (root) no nos cortamos nunca.
  9. El endpoint de pago simulado NO existe si hay credenciales de verdad.

    python prueba_corte.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

os.environ["HILO_DB"] = os.path.join(tempfile.mkdtemp(), "corte.db")
os.environ["HILO_SECRETO"] = "clave-de-prueba"
os.environ["HILO_OFFLINE"] = "1"
os.environ.pop("MAIL_USUARIO", None)
os.environ.pop("WA_TOKEN", None)
os.environ.pop("MP_ACCESS_TOKEN", None)          # arrancamos en modo simulado

from fastapi.testclient import TestClient                             # noqa: E402
from sqlmodel import select                                           # noqa: E402

from app import cobros, inquilino, mercadopago as mp                  # noqa: E402
from app.db import sesion                                             # noqa: E402
from app.main import app                                              # noqa: E402
from app.models import Business, Usuario                              # noqa: E402

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    print(("  OK    " if ok else "  FALLA ") + nombre + (("  -> " + str(detalle)) if detalle else ""))
    if not ok:
        fallos += 1


def mover(negocio_id, **campos):
    """Mueve las fechas de una cuenta. Es viajar en el tiempo sin esperar 7 días."""
    with sesion() as s, inquilino.sin_filtro():
        b = s.get(Business, negocio_id)
        for k, v in campos.items():
            setattr(b, k, v)
        s.add(b)
        s.commit()


def ver(negocio_id):
    with sesion() as s, inquilino.sin_filtro():
        return cobros.estado(s.get(Business, negocio_id))


with TestClient(app) as c:
    print("\n1 · Una cuenta nueva estrena 7 días")
    A = c.post("/api/auth/registro", json={"email": "sofia@panaderia.test",
                                           "password": "facturas2026", "nombre": "Sofía"}).json()
    ha = {"Authorization": "Bearer " + A["token"]}
    NEG = A["usuario"]["negocio_id"]
    e = ver(NEG)
    check("arranca en prueba", e["estado"] == "prueba", e["estado"])
    check("con 7 días", e["dias"] == 7, e["dias"])
    check("y entra a todo", c.get("/api/cola", headers=ha).status_code == 200)
    plan = c.get("/api/plan", headers=ha).json()
    check("ve su plan y los precios", len(plan["planes"]) == 3, plan.get("planes"))
    check("y sabe que está en modo simulado", plan["mercadopago"]["simulado"] is True)

    print("\n2 · Se le acaba la prueba: 402, no 403")
    mover(NEG, prueba_hasta=datetime.now() - timedelta(days=1))
    r = c.get("/api/cola", headers=ha)
    check("la cola le devuelve 402", r.status_code == 402, r.status_code)
    check("el cuerpo dice que está cortada", r.json().get("cortada") is True, r.text[:120])
    check("y explica por qué", "prueba" in r.json()["detail"].lower(), r.json()["detail"])
    check("no le queda ni la ficha", c.get("/api/alias/1", headers=ha).status_code == 402)
    check("PERO la pantalla del plan vive", c.get("/api/plan", headers=ha).status_code == 200)
    check("y el marco de la app también", c.get("/api/negocio", headers=ha).status_code == 200)
    check("sin gracia: nunca pagó", ver(NEG)["dias_de_gracia"] == 0, ver(NEG)["dias_de_gracia"])

    print("\n3 · Pone la tarjeta")
    r = c.post("/api/plan/suscribir", headers=ha, json={"plan": "basico"})
    check("le devuelve a dónde ir", r.status_code == 200 and "#/tarjeta" in r.json()["ir_a"],
          r.text[:160])
    sid = r.json()["ir_a"].split("s=")[1]
    check("la suscripción queda pendiente", ver(NEG)["suscripcion"] == "pendiente",
          ver(NEG)["suscripcion"])
    r = c.post(f"/api/pagos/simulado/{sid}", headers=ha)
    check("el pago simulado entra", r.status_code == 200, r.text[:160])
    e = ver(NEG)
    check("queda al día", e["estado"] == "al_dia", e["estado"])
    check("por un mes", e["pagado_hasta"][:10] == cobros.sumar_meses(datetime.now(), 1).date().isoformat(),
          e["pagado_hasta"][:10])
    check("con la tarjeta a la vista", e["tarjeta"] == "Visa ····4242", e["tarjeta"])
    check("y vuelve a entrar sola", c.get("/api/cola", headers=ha).status_code == 200)

    print("\n4 · El mismo pago repetido no suma dos meses")
    antes = ver(NEG)["pagado_hasta"]
    c.post(f"/api/pagos/simulado/{sid}", headers=ha)
    check("la fecha no se movió", ver(NEG)["pagado_hasta"] == antes, ver(NEG)["pagado_hasta"])
    libro = c.get("/api/plan", headers=ha).json()["cobros"]
    check("y hay un solo cobro anotado", len(libro) == 1, len(libro))

    print("\n5 · La gracia es para el que ya pagó")
    # La prueba queda vieja: el acceso ahora lo manda lo pagado. (Las dos fechas
    # conviven a propósito — ver `cobros.acceso_hasta`: regalar días de prueba a
    # alguien que paga es una palanca que usamos desde el back-office.)
    mover(NEG, prueba_hasta=datetime.now() - timedelta(days=60),
          pagado_hasta=datetime.now() - timedelta(days=2))
    e = ver(NEG)
    check("venció hace 2 días pero sigue entrando", e["estado"] == "en_gracia", e["estado"])
    check("y le quedan días de gracia", e["corta_en"] == 1, e.get("corta_en"))
    check("la app le anda", c.get("/api/cola", headers=ha).status_code == 200)
    mover(NEG, pagado_hasta=datetime.now() - timedelta(days=5))
    check("cinco días después, cortada", ver(NEG)["estado"] == "cortada", ver(NEG)["estado"])
    check("y la API le dice 402", c.get("/api/cola", headers=ha).status_code == 402)
    detalle = c.get("/api/cola", headers=ha).json().get("detail", "")
    check("con el motivo del pago", "tarjeta" in detalle, detalle)

    print("\n6 · Cancelar no es perder lo pagado")
    mover(NEG, pagado_hasta=datetime.now() + timedelta(days=12))
    r = c.post("/api/plan/cancelar", headers=ha)
    check("se cancela", r.status_code == 200 and r.json()["cancelada"], r.text[:120])
    check("pero sigue entrando hasta que venza", c.get("/api/cola", headers=ha).status_code == 200)
    check("y ya no hay débito automático", ver(NEG)["pago_automatico"] is False)

    # ------------------------------------------------------- 7. el webhook real
    print("\n7 · El webhook de Mercado Pago, con un MP de mentira")
    os.environ["MP_ACCESS_TOKEN"] = "TEST-de-mentira"
    with sesion() as s, inquilino.sin_filtro():
        b = s.get(Business, NEG)
        b.suscripcion_id = "PREAPPROVAL-1"
        b.prueba_hasta = datetime.now() - timedelta(days=60)
        b.pagado_hasta = datetime.now() - timedelta(days=10)   # cortada
        s.add(b)
        s.commit()
    check("con la fecha vieja está cortada", ver(NEG)["estado"] == "cortada", ver(NEG)["estado"])
    check("y no entra", c.get("/api/cola", headers=ha).status_code == 402)

    PAGOS = {"PAGO-1": {"status": "approved", "preapproval_id": "PREAPPROVAL-1",
                        "transaction_amount": 25000},
             "PAGO-2": {"status": "rejected", "preapproval_id": "PREAPPROVAL-1",
                        "transaction_amount": 25000}}
    SUBS = {"PREAPPROVAL-1": {"id": "PREAPPROVAL-1", "status": "authorized",
                              "external_reference": f"negocio-{NEG}",
                              "payment_method_id": "master", "last_four_digits": "9999"}}

    def falso(metodo, ruta, cuerpo=None):
        """Un Mercado Pago de mentira: la misma puerta, otra respuesta."""
        if ruta.startswith("authorized_payments/"):
            return True, PAGOS.get(ruta.split("/")[1], {})
        if ruta.startswith("preapproval/"):
            return True, SUBS.get(ruta.split("/")[1], {})
        return False, "ruta no simulada"

    mp._pedir = falso

    r = c.post("/api/pagos/webhook", json={"type": "subscription_authorized_payment",
                                           "data": {"id": "PAGO-1"}})
    check("el webhook contesta 200", r.status_code == 200, r.status_code)
    e = ver(NEG)
    check("el cobro corrió la fecha", e["estado"] == "al_dia", e["estado"])
    check("y la cuenta volvió sola", c.get("/api/cola", headers=ha).status_code == 200)

    antes = ver(NEG)["pagado_hasta"]
    c.post("/api/pagos/webhook", json={"type": "subscription_authorized_payment",
                                       "data": {"id": "PAGO-1"}})
    check("el reintento de MP no suma otro mes", ver(NEG)["pagado_hasta"] == antes)

    antes = ver(NEG)["pagado_hasta"]
    c.post("/api/pagos/webhook", json={"type": "subscription_authorized_payment",
                                       "data": {"id": "PAGO-2"}})
    check("un cobro rechazado no extiende nada", ver(NEG)["pagado_hasta"] == antes)

    c.post("/api/pagos/webhook", json={"type": "subscription_preapproval",
                                       "data": {"id": "PREAPPROVAL-1"}})
    e = ver(NEG)
    check("el aviso de suscripción guarda la tarjeta", e["tarjeta"] == "master ····9999", e["tarjeta"])
    check("y la marca activa", e["suscripcion"] == "activa", e["suscripcion"])

    r = c.post("/api/pagos/webhook", json={"type": "subscription_authorized_payment",
                                           "data": {"id": "NO-EXISTE"}})
    check("un webhook inventado no rompe nada", r.status_code == 200, r.status_code)
    r = c.post("/api/pagos/webhook", json={"cualquier": "cosa"})
    check("y basura tampoco", r.status_code == 200, r.status_code)

    print("\n9 · Con credenciales de verdad, el pago simulado no existe")
    r = c.post(f"/api/pagos/simulado/{sid}", headers=ha)
    check("devuelve 404", r.status_code == 404, r.status_code)
    os.environ.pop("MP_ACCESS_TOKEN")

    # ------------------------------------------------------------ 8. nosotros
    print("\n8 · A nosotros no nos corta nunca")
    R = c.post("/api/auth/registro", json={"email": "axel@hilo.test",
                                           "password": "medialuna99"}).json()
    hr = {"Authorization": "Bearer " + R["token"]}
    with sesion() as s, inquilino.sin_filtro():
        u = s.exec(select(Usuario).where(Usuario.email == "axel@hilo.test")).first()
        u.es_root = True
        s.add(u)
        b = s.get(Business, R["usuario"]["negocio_id"])
        b.prueba_hasta = datetime.now() - timedelta(days=90)
        s.add(b)
        s.commit()
    check("con la prueba vencida hace tres meses, entra igual",
          c.get("/api/cola", headers=hr).status_code == 200)
    check("y al back-office también", c.get("/api/root/resumen", headers=hr).status_code == 200)

    print("\nLa cuenta vieja, la que existía antes de todo esto")
    with sesion() as s, inquilino.sin_filtro():
        vieja = Business(nombre="De antes")
        s.add(vieja)
        s.commit()
        s.refresh(vieja)
        e = cobros.estado(vieja)
    check("no queda cortada por actualizar", e["puede_entrar"] is True, e)
    check("y se ve como «sin precio»", e["estado"] == "sin_precio", e["estado"])

print("\n" + ("Todo bien." if not fallos else f"{fallos} prueba(s) fallaron."))
sys.exit(1 if fallos else 0)
