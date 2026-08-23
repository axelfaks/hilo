"""La prueba de aislamiento, pero por HTTP: dos cuentas contra la API de verdad.

`prueba_inquilino.py` prueba la capa de datos. Esta prueba lo que de verdad
importa: que el filtro llegue vivo desde el middleware hasta el endpoint. Es el
punto donde esto podría fallar en silencio — FastAPI corre el endpoint en otra
tarea, y un ContextVar mal puesto se pierde ahí sin dar ningún error.

    python prueba_api_inquilino.py
"""
import os
import sys
import tempfile

os.environ["HILO_DB"] = os.path.join(tempfile.mkdtemp(), "api.db")
os.environ["HILO_SECRETO"] = "clave-de-prueba"
os.environ["HILO_OFFLINE"] = "1"          # sin llamadas a la IA
os.environ.pop("MAIL_USUARIO", None)      # sin vigía de correo
os.environ.pop("WA_TOKEN", None)

from fastapi.testclient import TestClient                             # noqa: E402

from app.main import app                                              # noqa: E402

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    print(("  OK    " if ok else "  FALLA ") + nombre + (("  -> " + str(detalle)) if detalle else ""))
    if not ok:
        fallos += 1


with TestClient(app) as c:
    # ------------------------------------------------------------- dos cuentas
    print("\nAlta de dos cuentas independientes")
    ra = c.post("/api/auth/registro", json={"email": "axel@panaderia.test",
                                            "password": "medialuna99", "nombre": "Axel"})
    check("se registra la primera", ra.status_code == 200, ra.text[:160])
    A = ra.json()
    rb = c.post("/api/auth/registro", json={"email": "ruiz@estudio.test",
                                            "password": "balance2026", "nombre": "Ruiz"})
    check("se registra la segunda", rb.status_code == 200, rb.text[:160])
    B = rb.json()
    check("cada una estrena su propio negocio",
          A["usuario"]["negocio_id"] != B["usuario"]["negocio_id"],
          f'A={A["usuario"]["negocio_id"]} B={B["usuario"]["negocio_id"]}')

    ha = {"Authorization": "Bearer " + A["token"]}
    hb = {"Authorization": "Bearer " + B["token"]}

    # ------------------------------------------------------ cada uno lo suyo
    print("\nCada cuenta configura su negocio")
    c.post("/api/negocio", headers=ha, json={"nombre": "Panadería La Espiga"})
    c.post("/api/negocio", headers=hb, json={"nombre": "Estudio Ruiz"})
    na = c.get("/api/negocio", headers=ha).json()
    nb = c.get("/api/negocio", headers=hb).json()
    check("A ve su negocio", na.get("nombre") == "Panadería La Espiga", na.get("nombre"))
    check("B ve el suyo", nb.get("nombre") == "Estudio Ruiz", nb.get("nombre"))

    # ------------------------------------------------- el MISMO mail en las dos
    print("\nEntra un mensaje del MISMO remitente a las dos cuentas")
    MAIL = "sofia@gmail.com"
    c.post("/api/ingest", headers=ha,
           json={"canal": "mail", "remitente": MAIL, "texto": "Quiero 20 medialunas"})
    c.post("/api/ingest", headers=hb,
           json={"canal": "mail", "remitente": MAIL, "texto": "Necesito el balance"})

    cola_a = c.get("/api/cola", headers=ha).json()
    cola_b = c.get("/api/cola", headers=hb).json()
    sa = cola_a.get("sin_identificar", [])
    sb = cola_b.get("sin_identificar", [])
    check("A ve 1 mensaje sin identificar", len(sa) == 1, len(sa))
    check("B ve 1 mensaje sin identificar", len(sb) == 1, len(sb))
    check("A ve SOLO el suyo", sa and "medialunas" in sa[0]["texto"], sa[0]["texto"] if sa else None)
    check("B ve SOLO el suyo", sb and "balance" in sb[0]["texto"], sb[0]["texto"] if sb else None)

    # -------------------------------------------- convertirlos en clientes
    print("\nCada uno crea su cliente a partir de ese mensaje")
    ID_MSG_A = sa[0]["mensaje_id"]
    ID_MSG_B = sb[0]["mensaje_id"]
    ca = c.post(f"/api/no-identificados/{ID_MSG_A}/nuevo", headers=ha,
                json={"nombre": "Sofía de la panadería"})
    cb = c.post(f"/api/no-identificados/{ID_MSG_B}/nuevo", headers=hb,
                json={"nombre": "Sofía del estudio"})
    check("A crea su cliente", ca.status_code == 200, ca.text[:200])
    check("B crea su cliente", cb.status_code == 200, cb.text[:200])
    ID_A = ca.json().get("alias_id") or ca.json().get("id")
    ID_B = cb.json().get("alias_id") or cb.json().get("id")

    cola_a = c.get("/api/cola", headers=ha).json()
    cola_b = c.get("/api/cola", headers=hb).json()
    check("A ve 1 cliente en su cola", len(cola_a.get("clientes", [])) == 1,
          [x.get("nombre") for x in cola_a.get("clientes", [])])
    check("B ve 1 cliente en su cola", len(cola_b.get("clientes", [])) == 1,
          [x.get("nombre") for x in cola_b.get("clientes", [])])

    # --------------------------------------------------- LO QUE NO PUEDE PASAR
    print("\nLo que NO puede pasar (el bug que hay que evitar)")
    r = c.get(f"/api/alias/{ID_B}", headers=ha)
    check("A NO puede abrir la ficha del cliente de B", r.status_code == 404,
          f"status {r.status_code}")
    r = c.get(f"/api/alias/{ID_A}", headers=hb)
    check("B NO puede abrir la ficha del cliente de A", r.status_code == 404,
          f"status {r.status_code}")
    r = c.post(f"/api/alias/{ID_B}/nota", headers=ha, json={"texto": "no deberia poder"})
    check("A NO puede escribirle una nota al cliente de B", r.status_code == 404,
          f"status {r.status_code}")
    r = c.post(f"/api/alias/{ID_B}/importancia", headers=ha, json={"importancia": "alta"})
    check("A NO puede tocarle la importancia al cliente de B", r.status_code == 404,
          f"status {r.status_code}")
    r = c.delete(f"/api/mensajes/{ID_MSG_B}", headers=ha)
    check("A NO puede borrar un mensaje de B", r.status_code == 404, f"status {r.status_code}")

    print("\nEl equipo también está separado")
    ua = c.get("/api/auth/usuarios", headers=ha).json()
    ub = c.get("/api/auth/usuarios", headers=hb).json()
    check("A ve solo su usuario", len(ua) == 1 and ua[0]["email"] == "axel@panaderia.test",
          [x["email"] for x in ua])
    check("B ve solo el suyo", len(ub) == 1 and ub[0]["email"] == "ruiz@estudio.test",
          [x["email"] for x in ub])

    print("\nLa vista pública del cliente (el token ES la credencial)")
    tok_a = ca.json()["token"]
    tok_b = cb.json()["token"]
    check("los dos negocios estrenan tokens distintos", tok_a != tok_b, f"{tok_a} / {tok_b}")
    va = c.get(f"/api/cliente/{tok_a}")
    vb = c.get(f"/api/cliente/{tok_b}")
    check("el token de A abre la conversación de A",
          va.status_code == 200 and va.json()["vendedor"] == "Panadería La Espiga",
          va.json().get("vendedor") if va.status_code == 200 else va.status_code)
    check("el token de B abre la de B",
          vb.status_code == 200 and vb.json()["vendedor"] == "Estudio Ruiz",
          vb.json().get("vendedor") if vb.status_code == 200 else vb.status_code)
    check("un token inventado no abre nada", c.get("/api/cliente/nada").status_code == 404)

    print("\nLos endpoints de equipo ya no están abiertos")
    r = c.get("/api/auth/usuarios")
    check("GET /api/auth/usuarios sin token -> 401", r.status_code == 401,
          f"status {r.status_code}: {r.text[:90]}")
    r = c.post("/api/auth/usuarios",
               json={"email": "intruso@x.test", "password": "colado123", "rol": "dueño"})
    check("POST /api/auth/usuarios sin token -> 401", r.status_code == 401,
          f"status {r.status_code}: {r.text[:90]}")
    r = c.post("/api/auth/login", json={"email": "intruso@x.test", "password": "colado123"})
    check("y ese usuario nunca llegó a existir", r.status_code == 401, r.status_code)

    print("\nSin credenciales")
    r = c.get("/api/cola")
    check("sin token no se entra", r.status_code == 401, r.status_code)
    r = c.get("/api/alias/1", headers={"Authorization": "Bearer inventado"})
    check("con un token inventado tampoco", r.status_code == 401, r.status_code)

print()
if fallos:
    print(f"{fallos} prueba(s) fallaron.")
    sys.exit(1)
print("El aislamiento llega vivo del middleware al endpoint.")
