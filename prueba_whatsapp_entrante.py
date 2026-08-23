"""El camino completo de un WhatsApp que entra: webhook -> cola -> cliente.

Prueba lo que no prueban las otras: que el mensaje pase por el webhook de verdad,
caiga en el negocio correcto, se muestre en la cola con el nombre del perfil, y
que crear el cliente desde ahí lo llame «Sofía Ramírez» y no «5491122334455».

    python prueba_whatsapp_entrante.py
"""
import json
import os
import sys
import tempfile

os.environ["HILO_DB"] = os.path.join(tempfile.mkdtemp(), "wa.db")
os.environ["HILO_SECRETO"] = "clave-de-prueba"
os.environ["HILO_OFFLINE"] = "1"
os.environ["WA_TOKEN"] = "token-de-prueba"
os.environ["WA_PHONE_ID"] = "1176912338832728"
os.environ["WA_NUMERO"] = "15556631386"
os.environ.pop("WA_APP_SECRET", None)          # sin secreto, la firma deja pasar
os.environ.pop("MAIL_USUARIO", None)

from fastapi.testclient import TestClient                            # noqa: E402

from app.main import app                                             # noqa: E402

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    print(("  OK    " if ok else "  FALLA ") + nombre + (("  -> " + str(detalle)) if detalle else ""))
    if not ok:
        fallos += 1


def golpe(wamid, texto="Hola! Me pasás precio de 20 medialunas?"):
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages",
            "value": {"messaging_product": "whatsapp",
                      "metadata": {"display_phone_number": "15556631386",
                                   "phone_number_id": "1176912338832728"},
                      "contacts": [{"profile": {"name": "Sofía Ramírez"},
                                    "wa_id": "5491122334455"}],
                      "messages": [{"from": "5491122334455", "id": wamid,
                                    "timestamp": "1756000000", "type": "text",
                                    "text": {"body": texto}}]}}]}]}


with TestClient(app) as c:
    print("\nUna cuenta con su negocio")
    r = c.post("/api/auth/registro", json={"email": "axel@hilo.test",
                                           "password": "medialuna99", "nombre": "Axel"})
    h = {"Authorization": "Bearer " + r.json()["token"]}
    check("cuenta creada", r.status_code == 200, r.text[:120])

    print("\nMeta verifica el webhook")
    r = c.get("/api/whatsapp/webhook", params={"hub.mode": "subscribe",
                                               "hub.verify_token": "hilo-webhook-2026",
                                               "hub.challenge": "12345"})
    # el .env de prueba no tiene verify token, así que acá tiene que rechazar
    check("sin WA_VERIFY_TOKEN rechaza la verificación", r.status_code == 403, r.status_code)
    os.environ["WA_VERIFY_TOKEN"] = "hilo-webhook-2026"
    r = c.get("/api/whatsapp/webhook", params={"hub.mode": "subscribe",
                                               "hub.verify_token": "hilo-webhook-2026",
                                               "hub.challenge": "12345"})
    check("con el token correcto devuelve el challenge", r.status_code == 200 and r.text == "12345",
          f"{r.status_code} {r.text[:40]}")
    check("y lo devuelve EN TEXTO PLANO, sin comillas ni JSON", '"' not in r.text, repr(r.text))

    print("\nLlega un mensaje")
    r = c.post("/api/whatsapp/webhook", json=golpe("wamid.AAA"))
    check("el webhook contesta 200", r.status_code == 200, r.text[:120])
    check("entró 1 mensaje", r.json().get("entraron") == 1, r.json())

    cola = c.get("/api/cola", headers=h).json()
    sin_id = cola.get("sin_identificar", [])
    check("aparece en la cola sin identificar", len(sin_id) == 1, len(sin_id))
    check("por el canal whatsapp", sin_id and sin_id[0]["canal"] == "whatsapp")
    check("con el número como remitente", sin_id and sin_id[0]["remitente"] == "5491122334455",
          sin_id[0]["remitente"] if sin_id else None)
    check("y con el NOMBRE del perfil", sin_id and sin_id[0]["remitente_nombre"] == "Sofía Ramírez",
          sin_id[0].get("remitente_nombre") if sin_id else None)

    print("\nMeta reintenta el mismo mensaje (siempre lo hace)")
    r = c.post("/api/whatsapp/webhook", json=golpe("wamid.AAA"))
    check("el webhook vuelve a contestar 200", r.status_code == 200)
    cola = c.get("/api/cola", headers=h).json()
    check("NO se duplicó en el hilo", len(cola.get("sin_identificar", [])) == 1,
          len(cola.get("sin_identificar", [])))

    print("\nCrear el cliente desde ese mensaje, sin escribir el nombre")
    mid = sin_id[0]["mensaje_id"]
    r = c.post(f"/api/no-identificados/{mid}/nuevo", headers=h, json={"nombre": ""})
    check("se crea", r.status_code == 200, r.text[:150])
    creado = r.json().get("nombre", "")
    check("se llama «Sofía Ramírez», no el número", creado == "Sofía Ramírez", creado)

    alias_id = r.json()["alias_id"]
    ficha = c.get(f"/api/alias/{alias_id}", headers=h).json()
    check("el mensaje quedó en su hilo",
          any("medialunas" in m["texto"] for m in ficha.get("mensajes", [])),
          [m["texto"][:30] for m in ficha.get("mensajes", [])])

    print("\nUn mensaje nuevo del mismo número ya cae en su ficha")
    r = c.post("/api/whatsapp/webhook", json=golpe("wamid.BBB", "Y de facturas?"))
    ficha = c.get(f"/api/alias/{alias_id}", headers=h).json()
    check("ahora son 2 mensajes en el hilo", len(ficha.get("mensajes", [])) == 2,
          len(ficha.get("mensajes", [])))
    check("y no quedó nada sin identificar",
          len(c.get("/api/cola", headers=h).json().get("sin_identificar", [])) == 0)

    print("\nBasura que no tiene que entrar")
    acuse = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages",
             "value": {"statuses": [{"id": "wamid.X", "status": "delivered"}]}}]}]}
    r = c.post("/api/whatsapp/webhook", json=acuse)
    check("un acuse de entrega no entra", r.json().get("entraron") == 0, r.json())
    os.environ["WA_APP_SECRET"] = "un-secreto"
    r = c.post("/api/whatsapp/webhook", json=golpe("wamid.CCC"))
    check("con secreto configurado y firma ausente, 403", r.status_code == 403, r.status_code)
    os.environ.pop("WA_APP_SECRET")

print()
if fallos:
    print(f"{fallos} prueba(s) fallaron.")
    sys.exit(1)
print("Un WhatsApp entra, no se duplica, y el cliente nace con nombre de persona.")
