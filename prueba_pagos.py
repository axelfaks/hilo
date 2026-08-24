"""Los cobros, por HTTP: que la fecha no mienta y que la cuota avise sin cortar.

Lo que se prueba acá es plata, así que los errores se pagan dos veces: una
cuando le cobrás de más a alguien y otra cuando te olvidás de cobrarle.

  1. Un usuario común no puede tocar los cobros.
  2. Poner precio deja la cuenta en "sin cobrar" — el que hay que ir a buscar.
  3. Un cobro corre `pagado_hasta` un mes, y queda en el libro.
  4. Pagar adelantado SUMA sobre lo que quedaba, no lo pisa.
  5. Una cuenta vencida se ve vencida… y sigue entrando: vencer no es cortar.
  6. Cobrarle a una suspendida la reactiva.
  7. El MRR no cuenta las suspendidas.
  8. Pasarse de la cuota avisa en la app del cliente y NO le corta nada.
  9. "Un mes" es el mismo día del mes que viene, también en enero.

    python prueba_pagos.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

os.environ["HILO_DB"] = os.path.join(tempfile.mkdtemp(), "pagos.db")
os.environ["HILO_SECRETO"] = "clave-de-prueba"
os.environ["HILO_OFFLINE"] = "1"
os.environ.pop("MAIL_USUARIO", None)
os.environ.pop("WA_TOKEN", None)

from fastapi.testclient import TestClient                             # noqa: E402
from sqlmodel import select                                           # noqa: E402

from app import cobros, inquilino                                     # noqa: E402
from app.db import sesion                                             # noqa: E402
from app.main import app                                              # noqa: E402
from app.models import Business, Usuario                              # noqa: E402

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    print(("  OK    " if ok else "  FALLA ") + nombre + (("  -> " + str(detalle)) if detalle else ""))
    if not ok:
        fallos += 1


def hacer_root(email):
    with sesion() as s, inquilino.sin_filtro():
        u = s.exec(select(Usuario).where(Usuario.email == email)).first()
        u.es_root = True
        s.add(u)
        s.commit()


def cuenta_de(datos, negocio_id):
    return {c["id"]: c for c in datos["cuentas"]}[negocio_id]


def sin_prueba(negocio_id):
    """Le deja la prueba gratis en el pasado.

    Toda cuenta nueva estrena 7 días de prueba (eso se prueba en
    `prueba_corte.py`), y esta prueba es sobre los cobros: mientras la prueba
    corre, la plata todavía no manda nada.
    """
    with sesion() as s, inquilino.sin_filtro():
        b = s.get(Business, negocio_id)
        b.prueba_hasta = datetime.now() - timedelta(days=30)
        s.add(b)
        s.commit()


# ------------------------------------------------- 9. la cuenta de los meses
print("\n9 · «Un mes» es el mismo día del mes que viene")
check("31 de enero + 1 mes cae en el último día de febrero",
      cobros.sumar_meses(datetime(2026, 1, 31), 1).date() == datetime(2026, 2, 28).date(),
      cobros.sumar_meses(datetime(2026, 1, 31), 1).date())
check("y en año bisiesto, el 29",
      cobros.sumar_meses(datetime(2028, 1, 31), 1).date() == datetime(2028, 2, 29).date(),
      cobros.sumar_meses(datetime(2028, 1, 31), 1).date())
check("15 de diciembre + 1 mes es el 15 de enero del año que viene",
      cobros.sumar_meses(datetime(2026, 12, 15), 1).date() == datetime(2027, 1, 15).date())
check("12 meses es un año exacto",
      cobros.sumar_meses(datetime(2026, 8, 23), 12).date() == datetime(2027, 8, 23).date())


with TestClient(app) as c:
    print("\nDos cuentas y un root")
    A = c.post("/api/auth/registro", json={"email": "axel@hilo.test",
                                           "password": "medialuna99", "nombre": "Axel"}).json()
    B = c.post("/api/auth/registro", json={"email": "sofia@panaderia.test",
                                           "password": "facturas2026", "nombre": "Sofía"}).json()
    ha = {"Authorization": "Bearer " + A["token"]}
    hb = {"Authorization": "Bearer " + B["token"]}
    NEG_A, NEG_B = A["usuario"]["negocio_id"], B["usuario"]["negocio_id"]
    sin_prueba(NEG_A)
    sin_prueba(NEG_B)
    c.post("/api/negocio", headers=hb, json={"nombre": "Panadería La Espiga"})
    hacer_root("axel@hilo.test")

    # ------------------------------------------------------ 1. la puerta
    print("\n1 · Los cobros son solo nuestros")
    r = c.post(f"/api/root/cuenta/{NEG_B}/cobro", headers=hb, json={"monto": 1})
    check("un usuario común no registra cobros", r.status_code == 403, r.status_code)
    r = c.get("/api/root/cobros", headers=hb)
    check("ni ve el libro", r.status_code == 403, r.status_code)

    # ------------------------------------------------- 2. precio y sin cobrar
    print("\n2 · Ponerle precio a una cuenta")
    r = c.post(f"/api/root/cuenta/{NEG_B}", headers=ha, json={"plan": "basico"})
    check("elegir plan propone el precio del catálogo",
          r.json()["precio_mensual"] == 25000, r.json().get("precio_mensual"))
    r = c.post(f"/api/root/cuenta/{NEG_B}", headers=ha, json={"precio_mensual": 30000})
    check("y se puede negociar otro", r.json()["precio_mensual"] == 30000,
          r.json().get("precio_mensual"))
    d = c.get("/api/root/resumen", headers=ha).json()
    check("con la prueba terminada y sin pagar, queda cortada",
          cuenta_de(d, NEG_B)["pago"]["estado"] == "cortada", cuenta_de(d, NEG_B)["pago"])
    check("y su dueña no entra", c.get("/api/cola", headers=hb).status_code == 402)
    check("y todavía no suma al MRR", d["plata"]["mrr"] == 0, d["plata"])
    check("pero sí a lo que hay que ir a cobrar", d["plata"]["vencido"] == 30000, d["plata"])

    # -------------------------------------------------------- 3. un cobro
    print("\n3 · Entra el primer pago")
    r = c.post(f"/api/root/cuenta/{NEG_B}/cobro", headers=ha,
               json={"monto": 30000, "medio": "transferencia", "meses": 1,
                     "nota": "transferencia del 23"})
    check("se registra", r.status_code == 200, r.text[:160])
    pago = r.json()["pago"]
    esperado = cobros.sumar_meses(datetime.now(), 1).date().isoformat()
    check("corre la fecha un mes", pago["pagado_hasta"][:10] == esperado,
          (pago["pagado_hasta"][:10], esperado))
    check("y queda al día", pago["estado"] == "al_dia", pago["estado"])

    libro = c.get("/api/root/cobros", headers=ha).json()
    check("aparece en el libro", libro["cobros"] and libro["cobros"][0]["monto"] == 30000,
          libro["cobros"][:1])
    check("con quién lo marcó", libro["cobros"][0]["quien"] == "axel@hilo.test",
          libro["cobros"][0]["quien"])
    check("con el nombre de la cuenta", libro["cobros"][0]["negocio"] == "Panadería La Espiga",
          libro["cobros"][0]["negocio"])
    check("suma a lo cobrado del mes", libro["plata"]["cobrado_mes"] == 30000, libro["plata"])
    check("y ahora sí al MRR", libro["plata"]["mrr"] == 30000, libro["plata"])
    check("ya no está en la lista de los que deben", libro["plata"]["vencido"] == 0,
          libro["plata"])

    # ------------------------------------------------- 4. pagar adelantado
    print("\n4 · Paga dos meses más, por adelantado")
    r = c.post(f"/api/root/cuenta/{NEG_B}/cobro", headers=ha,
               json={"monto": 60000, "medio": "mercadopago", "meses": 2})
    esperado = cobros.sumar_meses(datetime.now(), 3).date().isoformat()
    check("suma sobre lo que le quedaba, no lo pisa",
          r.json()["pago"]["pagado_hasta"][:10] == esperado,
          (r.json()["pago"]["pagado_hasta"][:10], esperado))
    libro = c.get("/api/root/cobros", headers=ha).json()
    check("el libro tiene los dos movimientos", len(libro["cobros"]) == 2, len(libro["cobros"]))
    check("y lo cobrado del mes son los dos", libro["plata"]["cobrado_mes"] == 90000,
          libro["plata"])

    # ------------------------------------------ 5. vencer no es cortar
    print("\n5 · Una cuenta vencida sigue entrando")
    with sesion() as s, inquilino.sin_filtro():
        b = s.get(Business, NEG_B)
        b.pagado_hasta = datetime.now() - timedelta(days=3)
        b.prueba_hasta = datetime.now() - timedelta(days=30)
        s.add(b)
        s.commit()
    d = c.get("/api/root/resumen", headers=ha).json()
    check("se ve en gracia", cuenta_de(d, NEG_B)["pago"]["estado"] == "en_gracia",
          cuenta_de(d, NEG_B)["pago"])
    check("aparece en «hay que escribirles»",
          any(x["id"] == NEG_B for x in d["vencen"]), d["vencen"])
    check("pero su dueña sigue entrando", c.get("/api/cola", headers=hb).status_code == 200)
    check("y no cuenta como MRR", d["plata"]["mrr"] == 0, d["plata"])

    # ------------------------------- 6 y 7. suspender, cobrar, reactivar
    print("\n6 · Cobrarle a una suspendida la reactiva")
    c.post(f"/api/root/cuenta/{NEG_B}", headers=ha, json={"estado": "suspendida"})
    check("suspendida no entra", c.get("/api/cola", headers=hb).status_code == 403)
    d = c.get("/api/root/resumen", headers=ha).json()
    check("una suspendida no suma al MRR aunque esté paga", d["plata"]["mrr"] == 0, d["plata"])
    r = c.post(f"/api/root/cuenta/{NEG_B}/cobro", headers=ha,
               json={"monto": 30000, "medio": "efectivo", "meses": 1})
    check("cobrarle la vuelve a activar", r.json()["estado"] == "activa", r.json()["estado"])
    check("y vuelve a entrar", c.get("/api/cola", headers=hb).status_code == 200)

    # ------------------------------------------------ 8. la cuota avisa
    print("\n8 · Pasarse de la cuota avisa, no corta")
    n = c.get("/api/negocio", headers=hb).json()
    check("el cliente ve su plan", n["plan"]["nombre"] == "Básico", n["plan"]["nombre"])
    check("y todavía no se pasó de nada", n["plan"]["pasado"] == [], n["plan"]["pasado"])

    with sesion() as s, inquilino.sin_filtro():
        b = s.get(Business, NEG_B)
        b.plan = "prueba"          # 25 clientes de tope
        s.add(b)
        s.commit()
    with inquilino.usar(NEG_B), sesion() as s:
        from app.models import Alias
        for i in range(26):
            s.add(Alias(nombre=f"Cliente {i}"))
        s.commit()

    n = c.get("/api/negocio", headers=hb).json()
    check("cuando se pasa, el aviso aparece en su app", len(n["plan"]["pasado"]) == 1,
          n["plan"]["pasado"])
    check("y el aviso dice el número y el tope",
          "26" in n["plan"]["pasado"][0] and "25" in n["plan"]["pasado"][0],
          n["plan"]["pasado"][0])
    check("pero la app le sigue andando", c.get("/api/cola", headers=hb).status_code == 200)
    d = c.get("/api/root/resumen", headers=ha).json()
    check("y nosotros lo vemos en el back-office",
          cuenta_de(d, NEG_B)["cuota"]["pasado"], cuenta_de(d, NEG_B)["cuota"])
    check("con el contador de cuántas se pasaron",
          d["totales"]["pasadas_de_cuota"] == 1, d["totales"]["pasadas_de_cuota"])

    # ------------------------------------------------------ validaciones
    print("\nLo que no se acepta")
    r = c.post(f"/api/root/cuenta/{NEG_B}/cobro", headers=ha,
               json={"monto": 1000, "medio": "criptomonedas"})
    check("un medio inventado", r.status_code == 400, r.status_code)
    r = c.post(f"/api/root/cuenta/{NEG_B}/cobro", headers=ha, json={"monto": 1000, "meses": 0})
    check("cero meses", r.status_code == 400, r.status_code)
    r = c.post(f"/api/root/cuenta/{NEG_B}/cobro", headers=ha, json={"monto": -5000})
    check("un monto negativo", r.status_code == 400, r.status_code)
    r = c.post("/api/root/cuenta/9999/cobro", headers=ha, json={"monto": 1000})
    check("una cuenta que no existe", r.status_code == 404, r.status_code)

    # la cuenta A nunca tuvo precio: no tiene que aparecer como deudora
    d = c.get("/api/root/resumen", headers=ha).json()
    check("una cuenta sin precio no figura como deuda",
          cuenta_de(d, NEG_A)["pago"]["precio"] == 0,
          cuenta_de(d, NEG_A)["pago"])

print("\n" + ("Todo bien." if not fallos else f"{fallos} prueba(s) fallaron."))
sys.exit(1 if fallos else 0)
