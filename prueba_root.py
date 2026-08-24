"""El back-office, probado por HTTP: que vea todo el que tiene que ver, y nadie más.

Acá se prueba lo único que puede salir realmente caro de esta pantalla:

  1. Un usuario común NO entra al back-office (ni sabiendo la URL).
  2. Un root ve todas las cuentas, con los contadores de cada una.
  3. "Ver como" cambia de cuenta de verdad… y queda registrado.
  4. El header de "ver como" NO es un permiso: si lo manda un usuario común, no
     pasa nada. Es el ataque obvio contra esta función y tiene que ser aburrido.
  5. Suspender una cuenta le corta la entrada a su gente, no a nosotros.
  6. El consumo de IA y las fallas se le anotan a la cuenta que las causó.

    python prueba_root.py
"""
import os
import sys
import tempfile

os.environ["HILO_DB"] = os.path.join(tempfile.mkdtemp(), "root.db")
os.environ["HILO_SECRETO"] = "clave-de-prueba"
os.environ["HILO_OFFLINE"] = "1"          # sin llamadas a la IA
os.environ.pop("MAIL_USUARIO", None)      # sin vigía de correo
os.environ.pop("WA_TOKEN", None)

from fastapi.testclient import TestClient                             # noqa: E402
from sqlmodel import select                                           # noqa: E402

from app import inquilino, uso                                        # noqa: E402
from app.db import sesion                                             # noqa: E402
from app.main import app                                              # noqa: E402
from app.models import Usuario                                        # noqa: E402

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    print(("  OK    " if ok else "  FALLA ") + nombre + (("  -> " + str(detalle)) if detalle else ""))
    if not ok:
        fallos += 1


def hacer_root(email: str):
    """Lo que en la vida real se hace una vez a mano contra la base."""
    with sesion() as s, inquilino.sin_filtro():
        u = s.exec(select(Usuario).where(Usuario.email == email)).first()
        u.es_root = True
        s.add(u)
        s.commit()


with TestClient(app) as c:
    # --------------------------------------------------------- dos cuentas
    print("\nDos cuentas y dos dueños")
    A = c.post("/api/auth/registro", json={"email": "axel@hilo.test",
                                           "password": "medialuna99", "nombre": "Axel"}).json()
    B = c.post("/api/auth/registro", json={"email": "sofia@panaderia.test",
                                           "password": "facturas2026", "nombre": "Sofía"}).json()
    ha = {"Authorization": "Bearer " + A["token"]}
    hb = {"Authorization": "Bearer " + B["token"]}
    c.post("/api/negocio", headers=ha, json={"nombre": "Hilo"})
    c.post("/api/negocio", headers=hb, json={"nombre": "Panadería La Espiga"})
    NEG_A = A["usuario"]["negocio_id"]
    NEG_B = B["usuario"]["negocio_id"]

    # un cliente y un mensaje en cada una, para que haya números que mirar
    c.post("/api/ingest", headers=ha, json={"canal": "mail", "remitente": "lucas@x.test",
                                            "texto": "Quiero probar Hilo"})
    for i in range(3):
        c.post("/api/ingest", headers=hb, json={"canal": "whatsapp", "remitente": "+5491133",
                                                "texto": f"Hola, mensaje {i}"})

    # ---------------------------------------------------- 1. la puerta cierra
    print("\n1 · El back-office no es para los clientes")
    r = c.get("/api/root/resumen", headers=hb)
    check("un usuario común recibe 403", r.status_code == 403, r.status_code)
    r = c.get("/api/root/cuenta/%d" % NEG_A, headers=hb)
    check("tampoco entra a una cuenta por id", r.status_code == 403, r.status_code)
    r = c.get("/api/root/resumen")
    check("sin token tampoco", r.status_code in (401, 403), r.status_code)

    # -------------------------------------------------------- 2. el root ve
    print("\n2 · El root ve todas las cuentas")
    hacer_root("axel@hilo.test")
    r = c.get("/api/root/resumen", headers=ha)
    check("ahora sí entra", r.status_code == 200, r.text[:160])
    d = r.json()
    check("ve las dos cuentas", d["totales"]["cuentas"] == 2, d["totales"]["cuentas"])
    por_id = {x["id"]: x for x in d["cuentas"]}
    check("cuenta los clientes de cada una",
          por_id[NEG_A]["clientes"] == 0 and por_id[NEG_B]["clientes"] == 0,
          {k: v["clientes"] for k, v in por_id.items()})
    check("cuenta los mensajes de cada una",
          por_id[NEG_A]["mensajes"] == 1 and por_id[NEG_B]["mensajes"] == 3,
          {k: v["mensajes"] for k, v in por_id.items()})
    check("le pone fecha de alta a las cuentas nuevas", bool(por_id[NEG_B]["creado"]),
          por_id[NEG_B]["creado"])
    check("sabe cuándo entró cada dueño", bool(por_id[NEG_B]["ultimo_acceso"]),
          por_id[NEG_B]["ultimo_acceso"])
    canales_b = {x["canal"] for x in por_id[NEG_B]["canales"]}
    check("ve por qué canal habla cada cuenta", canales_b == {"whatsapp"}, canales_b)

    # -------------------------------------------------------- 3. ver como
    print("\n3 · Ver como, con log")
    r = c.post(f"/api/root/ver-como/{NEG_B}", headers=ha)
    check("deja mirar la cuenta del cliente", r.status_code == 200, r.text[:160])
    mirando = dict(ha, **{"X-Hilo-Negocio": str(NEG_B)})
    neg = c.get("/api/negocio", headers=mirando).json()
    check("con el header ve el negocio del cliente", neg.get("nombre") == "Panadería La Espiga",
          neg.get("nombre"))
    cola = c.get("/api/cola", headers=mirando).json()
    check("y su cola, no la nuestra", len(cola.get("sin_identificar", [])) == 3,
          len(cola.get("sin_identificar", [])))
    propio = c.get("/api/negocio", headers=ha).json()
    check("sin el header vuelve a lo nuestro", propio.get("nombre") == "Hilo", propio.get("nombre"))
    log = c.get("/api/root/accesos", headers=ha).json()
    check("quedó registrado quién miró qué",
          log and log[0]["usuario"] == "axel@hilo.test" and log[0]["negocio_id"] == NEG_B,
          log[:1])

    # ------------------------------- 4. el header NO es un permiso (el ataque)
    print("\n4 · El header no le sirve a un usuario común")
    colado = dict(hb, **{"X-Hilo-Negocio": str(NEG_A)})
    neg = c.get("/api/negocio", headers=colado).json()
    check("Sofía sigue viendo lo suyo", neg.get("nombre") == "Panadería La Espiga",
          neg.get("nombre"))
    cola = c.get("/api/cola", headers=colado).json()
    check("y su propia cola", len(cola.get("sin_identificar", [])) == 3,
          len(cola.get("sin_identificar", [])))

    # ----------------------------------------------------- 5. suspender
    print("\n5 · Suspender corta la entrada, no los datos")
    r = c.post(f"/api/root/cuenta/{NEG_B}", headers=ha, json={"estado": "suspendida",
                                                              "plan": "basico",
                                                              "nota": "no pagó agosto"})
    check("se suspende desde el back-office", r.status_code == 200, r.text[:160])
    r = c.get("/api/cola", headers=hb)
    check("su dueña ya no entra", r.status_code == 403, r.status_code)
    check("y el mensaje se lo explica", "suspendida" in r.text.lower(), r.text[:120])
    r = c.get("/api/root/resumen", headers=ha)
    check("nosotros seguimos entrando", r.status_code == 200, r.status_code)
    cuenta_b = {x["id"]: x for x in r.json()["cuentas"]}[NEG_B]
    check("los datos quedaron intactos", cuenta_b["mensajes"] == 3, cuenta_b["mensajes"])
    check("y se ve el plan y la nota",
          cuenta_b["plan"] == "basico" and cuenta_b["nota"] == "no pagó agosto",
          (cuenta_b["plan"], cuenta_b["nota"]))
    r = c.post(f"/api/root/cuenta/{NEG_B}", headers=ha, json={"estado": "activa"})
    check("y se reactiva", c.get("/api/cola", headers=hb).status_code == 200)
    r = c.post(f"/api/root/cuenta/{NEG_B}", headers=ha, json={"plan": "gratis-para-siempre"})
    check("un plan inventado se rechaza", r.status_code == 400, r.status_code)

    # ------------------------------------------------ 6. consumo y fallas
    print("\n6 · Consumo de IA y fallas, con nombre de cuenta")
    with inquilino.usar(NEG_B):
        uso.anotar_ia(modelo="gemini-2.5-flash", entrada=1200, salida=300)
        uso.anotar_ia(modelo="gemini-2.5-flash", entrada=800, salida=200, fallo=True)
        uso.anotar_falla("whatsapp", "el número quedó sin registrar")
    with inquilino.usar(NEG_A):
        uso.anotar_ia(modelo="gemini-2.5-flash", entrada=100, salida=50)

    d = c.get("/api/root/resumen", headers=ha).json()
    por_id = {x["id"]: x for x in d["cuentas"]}
    check("le carga las llamadas a quien las pidió",
          por_id[NEG_B]["ia"]["llamadas"] == 2 and por_id[NEG_A]["ia"]["llamadas"] == 1,
          {k: v["ia"]["llamadas"] for k, v in por_id.items()})
    check("suma los tokens", por_id[NEG_B]["ia"]["tokens"] == 2500,
          por_id[NEG_B]["ia"]["tokens"])
    check("cuenta las que fallaron", por_id[NEG_B]["ia"]["fallos"] == 1,
          por_id[NEG_B]["ia"]["fallos"])
    check("el total es la suma de las cuentas", d["totales"]["ia"]["llamadas"] == 3,
          d["totales"]["ia"]["llamadas"])
    check("avisa que esa cuenta tuvo una falla hoy", por_id[NEG_B]["fallas_24h"] == 1,
          por_id[NEG_B]["fallas_24h"])

    det = c.get(f"/api/root/cuenta/{NEG_B}", headers=ha).json()
    check("el detalle trae la falla escrita",
          det["fallas"] and det["fallas"][0]["donde"] == "whatsapp",
          det["fallas"][:1])
    check("y la serie por día de 14 días", len(det["ia_por_dia"]) == 14, len(det["ia_por_dia"]))
    check("con el consumo de hoy adentro", det["ia_por_dia"][-1]["llamadas"] == 2,
          det["ia_por_dia"][-1])
    check("los últimos mensajes de esa cuenta son suyos",
          all("mensaje" in m["texto"] for m in det["ultimos_mensajes"]),
          [m["texto"][:20] for m in det["ultimos_mensajes"]])

print("\n" + ("Todo bien." if not fallos else f"{fallos} prueba(s) fallaron."))
sys.exit(1 if fallos else 0)
