"""El alta de un cliente por Embedded Signup, sin tocar la red.

Reemplaza la única puerta a la Graph API (`whatsapp._pedir`) por una falsa que
responde como Meta. Así se ejercita el flujo entero —código, token, suscripción,
registro, guardado— y además se verifica lo que más importa: que la credencial de
un cliente quede encerrada en SU negocio.

    python prueba_conectar_whatsapp.py
"""
import json
import os
import sys
import tempfile

os.environ["HILO_DB"] = os.path.join(tempfile.mkdtemp(), "conectar.db")
os.environ["HILO_SECRETO"] = "clave-de-prueba"
os.environ["HILO_OFFLINE"] = "1"
os.environ["WA_APP_ID"] = "1759253065274588"
os.environ["WA_APP_SECRET"] = "secreto-de-la-app"
os.environ.pop("WA_TOKEN", None)
os.environ.pop("WA_PHONE_ID", None)
os.environ.pop("MAIL_USUARIO", None)

from fastapi.testclient import TestClient                            # noqa: E402
from sqlmodel import select                                          # noqa: E402

from app import inquilino, secreto, whatsapp                         # noqa: E402
from app.db import sesion                                            # noqa: E402
from app.models import Credencial                                    # noqa: E402

fallos = 0
llamadas = []


def check(nombre, ok, detalle=""):
    global fallos
    print(("  OK    " if ok else "  FALLA ") + nombre + (("  -> " + str(detalle)) if detalle else ""))
    if not ok:
        fallos += 1


# ----------------------------------------------------------- el Meta de mentira
def meta_falso(metodo, ruta, token, cuerpo=None, params=None, version=""):
    llamadas.append((metodo, ruta, cuerpo, params))
    if ruta == "oauth/access_token":
        if (params or {}).get("code") == "codigo-vencido":
            return False, "Meta devolvió 100: el código expiró"
        return True, {"access_token": "TOKEN-DEL-CLIENTE-" + (params or {}).get("code", "")}
    if ruta.endswith("/subscribed_apps"):
        return True, {"success": True}
    if ruta.endswith("/register"):
        return True, {"success": True}
    if "/" not in ruta:                                   # GET del número
        return True, {"display_phone_number": "+54 9 11 6896 1470",
                      "verified_name": "Panadería La Espiga",
                      "quality_rating": "GREEN"}
    return True, {}


whatsapp._pedir = meta_falso
from app.main import app                                             # noqa: E402

with TestClient(app) as c:
    print("\nDos negocios")
    A = c.post("/api/auth/registro", json={"email": "axel@pan.test",
                                           "password": "medialuna99"}).json()
    B = c.post("/api/auth/registro", json={"email": "ruiz@est.test",
                                           "password": "balance2026"}).json()
    ha = {"Authorization": "Bearer " + A["token"]}
    hb = {"Authorization": "Bearer " + B["token"]}
    check("dos negocios distintos",
          A["usuario"]["negocio_id"] != B["usuario"]["negocio_id"])

    print("\nAntes de conectar")
    e = c.get("/api/whatsapp/estado", headers=ha).json()
    check("A no tiene WhatsApp propio", e["propio"] is False)
    check("y con el .env vacío, tampoco configurado", e["configurado"] is False)
    check("puede_conectar_clientes es True (hay app_id y secreto)",
          e["puede_conectar_clientes"] is True)

    print("\nA conecta su WhatsApp desde el popup")
    llamadas.clear()
    r = c.post("/api/whatsapp/conectar", headers=ha, json={
        "code": "codigo-del-popup", "waba_id": "WABA-DE-A", "phone_number_id": "PHONE-DE-A"})
    check("el alta responde 200", r.status_code == 200, r.text[:200])
    d = r.json()
    check("devuelve el número para mostrarlo", d.get("numero") == "+54 9 11 6896 1470", d)
    check("y el nombre visible", d.get("nombre_visible") == "Panadería La Espiga")

    print("\n  Lo que le pidió a Meta, en orden:")
    for m, ruta, _, _ in llamadas:
        print(f"    {m:5} {ruta}")
    rutas = [x[1] for x in llamadas]
    check("cambió el código por un token", rutas[0] == "oauth/access_token", rutas[:1])
    check("SUSCRIBIÓ la app a la cuenta del cliente",
          "WABA-DE-A/subscribed_apps" in rutas, rutas)
    check("registró el número", "PHONE-DE-A/register" in rutas, rutas)
    pin = [x[2] for x in llamadas if x[1].endswith("/register")][0]["pin"]
    check("con un PIN de 6 dígitos", len(pin) == 6 and pin.isdigit(), pin)

    print("\nLa credencial quedó guardada, cifrada y con dueño")
    with inquilino.sin_filtro(), sesion() as s:
        creds = list(s.exec(select(Credencial)))
        check("hay exactamente 1 credencial", len(creds) == 1, len(creds))
        cred = creds[0]
        check("es del negocio de A", cred.business_id == A["usuario"]["negocio_id"],
              cred.business_id)
        check("el token NO está en texto plano",
              "TOKEN-DEL-CLIENTE" not in cred.datos_json, cred.datos_json[:40])
        guardado = json.loads(secreto.descifrar(cred.datos_json))
        check("pero se descifra entero",
              guardado["token"] == "TOKEN-DEL-CLIENTE-codigo-del-popup", guardado.get("token"))
        check("guarda también el waba_id", guardado["waba_id"] == "WABA-DE-A")

    print("\nB no ve nada de eso")
    e = c.get("/api/whatsapp/estado", headers=hb).json()
    check("B sigue sin WhatsApp propio", e["propio"] is False, e["propio"])
    check("y sin número", not e.get("numero"), e.get("numero"))
    e = c.get("/api/whatsapp/estado", headers=ha).json()
    check("A sí lo tiene", e["propio"] is True and e["configurado"] is True)
    check("con su número", e["numero"] == "+54 9 11 6896 1470", e["numero"])

    print("\nCada uno manda con SU cuenta")
    from app.models import Alias, Identity                           # noqa: E402
    with inquilino.usar(A["usuario"]["negocio_id"]), sesion() as s:
        import app.pipeline as pl
        cuenta = pl.cuenta_whatsapp(s)
        check("A resuelve su token", cuenta and cuenta["token"].endswith("codigo-del-popup"),
              cuenta)
        check("y su phone_id", cuenta and cuenta["phone_id"] == "PHONE-DE-A", cuenta)
    with inquilino.usar(B["usuario"]["negocio_id"]), sesion() as s:
        check("B no resuelve ninguna", pl.cuenta_whatsapp(s) is None)

    print("\nReconectar pisa, no duplica")
    c.post("/api/whatsapp/conectar", headers=ha, json={
        "code": "otro-codigo", "waba_id": "WABA-DE-A", "phone_number_id": "PHONE-NUEVO"})
    with inquilino.sin_filtro(), sesion() as s:
        creds = list(s.exec(select(Credencial)))
        check("sigue habiendo 1 sola", len(creds) == 1, len(creds))
        check("con el número nuevo", creds[0].externo_id == "PHONE-NUEVO", creds[0].externo_id)

    print("\nCuando Meta dice que no")
    r = c.post("/api/whatsapp/conectar", headers=hb, json={
        "code": "codigo-vencido", "waba_id": "WABA-DE-B", "phone_number_id": "PHONE-DE-B"})
    check("responde 400 con el motivo", r.status_code == 400, r.status_code)
    check("y el motivo se entiende", "código" in r.text or "codigo" in r.text, r.text[:140])
    with inquilino.usar(B["usuario"]["negocio_id"]), sesion() as s:
        check("B NO quedó con una credencial a medias", pl.cuenta_whatsapp(s) is None)

    print("\nDesconectar")
    r = c.post("/api/whatsapp/desconectar", headers=ha)
    check("responde 200", r.status_code == 200, r.text[:120])
    check("y A vuelve a no tener número",
          c.get("/api/whatsapp/estado", headers=ha).json()["propio"] is False)

    print("\nSin sesión no se conecta nada")
    r = c.post("/api/whatsapp/conectar", json={"code": "x", "waba_id": "y",
                                               "phone_number_id": "z"})
    check("sin token, 401", r.status_code == 401, r.status_code)

print()
if fallos:
    print(f"{fallos} prueba(s) fallaron.")
    sys.exit(1)
print("Un cliente conecta su WhatsApp y su token queda encerrado en su negocio.")
