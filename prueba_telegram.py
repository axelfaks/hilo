"""Telegram de punta a punta, con un Telegram de mentira.

Lo que se prueba es la parte que no es obvia: **de qué cuenta de Hilo es cada
mensaje**. El bot es uno solo para todos los clientes, así que el token no lo
dice — lo dice el código de vinculación, y si eso falla, los mensajes de un
negocio caen en la cola de otro. Es el peor bug posible de un canal.

  1. Un código vincula la cuenta, y se quema al usarlo.
  2. Un código vencido o inventado no vincula nada.
  3. Un cliente que llega por el link público entra en la cuenta correcta.
  4. Los mensajes siguientes caen solos en la cuenta correcta.
  5. Otra cuenta NO ve nada de eso.
  6. El modo Business se engancha y las respuestas salen como el vendedor.
  7. Lo que el vendedor contesta a mano desde su celular entra como saliente.
  8. Telegram reintenta y el mensaje no se duplica.
  9. Un webhook sin el secret token correcto se rechaza.

    python prueba_telegram.py
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

os.environ["HILO_DB"] = os.path.join(tempfile.mkdtemp(), "telegram.db")
os.environ["HILO_SECRETO"] = "clave-de-prueba"
os.environ["HILO_OFFLINE"] = "1"
os.environ["TG_TOKEN"] = "123456:de-mentira"
os.environ["TG_SECRETO"] = "secreto-de-prueba"
os.environ.pop("MAIL_USUARIO", None)
os.environ.pop("WA_TOKEN", None)

from fastapi.testclient import TestClient                             # noqa: E402
from sqlmodel import select                                           # noqa: E402

from app import inquilino, telegram as tg, vinculos                   # noqa: E402
from app.db import sesion                                             # noqa: E402
from app.main import app                                              # noqa: E402
from app.models import Credencial, Message, Vinculo                   # noqa: E402

fallos = 0
ENVIADOS = []          # lo que el bot "mandó"


def check(nombre, ok, detalle=""):
    global fallos
    print(("  OK    " if ok else "  FALLA ") + nombre + (("  -> " + str(detalle)) if detalle else ""))
    if not ok:
        fallos += 1


def telegram_falso(metodo, cuerpo=None, timeout=20):
    """El mismo agujero por el que sale todo, tapado."""
    if metodo == "getMe":
        return True, {"username": "HiloVentasBot", "id": 42}
    if metodo == "sendMessage":
        ENVIADOS.append(cuerpo)
        return True, {"message_id": len(ENVIADOS)}
    if metodo == "setWebhook":
        return True, True
    return False, f"método no simulado: {metodo}"


tg._pedir = telegram_falso

CABECERA = {"X-Telegram-Bot-Api-Secret-Token": "secreto-de-prueba"}


def update(cuerpo, cliente):
    return cliente.post("/api/telegram/webhook", json=cuerpo, headers=CABECERA)


def mensaje_de(chat_id, texto, nombre="Lucas", conexion="", de=None, msg_id=1):
    m = {"message_id": msg_id, "text": texto,
         "from": {"id": de if de is not None else chat_id, "first_name": nombre},
         "chat": {"id": chat_id, "first_name": nombre}}
    if conexion:
        m["business_connection_id"] = conexion
        return {"business_message": m}
    return {"message": m}


with TestClient(app) as c:
    print("\nDos cuentas")
    A = c.post("/api/auth/registro", json={"email": "sofia@panaderia.test",
                                           "password": "facturas2026", "nombre": "Sofía"}).json()
    B = c.post("/api/auth/registro", json={"email": "ruiz@estudio.test",
                                           "password": "balance2026", "nombre": "Ruiz"}).json()
    ha = {"Authorization": "Bearer " + A["token"]}
    hb = {"Authorization": "Bearer " + B["token"]}
    NEG_A, NEG_B = A["usuario"]["negocio_id"], B["usuario"]["negocio_id"]
    c.post("/api/negocio", headers=ha, json={"nombre": "Panadería La Espiga"})

    # ---------------------------------------------------- 1. el código vincula
    print("\n1 · El código engancha la cuenta")
    r = c.get("/api/canales", headers=ha).json()
    telegram = {x["canal"]: x for x in r["canales"]}["telegram"]
    check("arranca desconectado", telegram["estado"] == "desconectado", telegram["estado"])
    check("y se puede conectar", telegram["puede_conectarse"] is True)

    r = c.post("/api/canales/telegram/vincular", headers=ha).json()
    codigo = r["codigo"]
    check("da un código corto", len(codigo) == 6, codigo)
    check("y el link del bot", r["link"] == f"https://t.me/HiloVentasBot?start={codigo}",
          r["link"])
    estado = {x["canal"]: x for x in c.get("/api/canales", headers=ha).json()["canales"]}
    check("la pantalla queda «conectando»", estado["telegram"]["estado"] == "conectando",
          estado["telegram"]["estado"])

    ENVIADOS.clear()
    update(mensaje_de(555001, f"/start {codigo}", nombre="Sofía"), c)
    estado = {x["canal"]: x for x in c.get("/api/canales", headers=ha).json()["canales"]}
    check("después del /start queda andando", estado["telegram"]["estado"] == "andando",
          estado["telegram"]["estado"])
    check("en modo bot", estado["telegram"]["modo"] == "bot", estado["telegram"]["modo"])
    check("y el bot le contestó a ella", ENVIADOS and str(ENVIADOS[0]["chat_id"]) == "555001",
          ENVIADOS[:1])
    check("con el link para sus clientes",
          ENVIADOS and "start=neg_" in ENVIADOS[0]["text"], ENVIADOS[0]["text"][:80])
    check("el link público aparece en la pantalla",
          "start=neg_" in estado["telegram"]["link_publico"], estado["telegram"]["link_publico"])
    publico = estado["telegram"]["link_publico"].split("start=")[1]

    print("\n2 · Un código no sirve dos veces, ni vencido, ni inventado")
    ENVIADOS.clear()
    update(mensaje_de(555777, f"/start {codigo}", nombre="Colado"), c)
    check("el mismo código otra vez no vincula",
          ENVIADOS and "no sirve" in ENVIADOS[0]["text"], ENVIADOS[0]["text"][:60])
    ENVIADOS.clear()
    update(mensaje_de(555777, "/start ZZZZZZ", nombre="Colado"), c)
    check("uno inventado tampoco", ENVIADOS and "no sirve" in ENVIADOS[0]["text"])
    r = c.post("/api/canales/telegram/vincular", headers=hb).json()
    with sesion() as s, inquilino.sin_filtro():
        v = s.exec(select(Vinculo).where(Vinculo.codigo == r["codigo"])).first()
        v.vence = datetime.now() - timedelta(minutes=1)
        s.add(v)
        s.commit()
    ENVIADOS.clear()
    update(mensaje_de(555888, f"/start {r['codigo']}", nombre="Ruiz"), c)
    check("uno vencido tampoco", ENVIADOS and "venció" in ENVIADOS[0]["text"])

    # -------------------------------------------- 3 y 4. los clientes del vendedor
    print("\n3 · Un cliente llega por el link público y entra en la cuenta correcta")
    ENVIADOS.clear()
    update(mensaje_de(777001, f"/start {publico}", nombre="Lucas"), c)
    cola = c.get("/api/cola", headers=ha).json()
    check("cae en la cola de Sofía", len(cola.get("sin_identificar", [])) == 1,
          len(cola.get("sin_identificar", [])))
    check("y el bot le dio la bienvenida",
          ENVIADOS and "Escribime" in ENVIADOS[-1]["text"], ENVIADOS[-1]["text"][:60])

    print("\n4 · Los mensajes siguientes caen solos donde va")
    update(mensaje_de(777001, "Necesito 200 medialunas para el viernes",
                      nombre="Lucas", msg_id=2), c)
    cola = c.get("/api/cola", headers=ha).json()
    sin = cola.get("sin_identificar", [])
    check("entra el mensaje de verdad", len(sin) == 2, len(sin))
    check("con el texto tal cual",
          any("medialunas" in x["texto"] for x in sin), [x["texto"][:30] for x in sin])
    check("y con el nombre del que escribe",
          any(x.get("remitente_nombre") == "Lucas" for x in sin),
          [x.get("remitente_nombre") for x in sin])

    print("\n5 · La otra cuenta no ve nada de eso")
    cola_b = c.get("/api/cola", headers=hb).json()
    check("Ruiz tiene la cola vacía", len(cola_b.get("sin_identificar", [])) == 0,
          len(cola_b.get("sin_identificar", [])))

    print("\n8 · Telegram reintenta y no se duplica")
    update(mensaje_de(777001, "Necesito 200 medialunas para el viernes",
                      nombre="Lucas", msg_id=2), c)
    sin = c.get("/api/cola", headers=ha).json().get("sin_identificar", [])
    check("sigue habiendo dos, no tres", len(sin) == 2, len(sin))

    # ------------------------------------------------------ 6. modo Business
    print("\n6 · Se conecta el modo Business")
    ENVIADOS.clear()
    update({"business_connection": {
        "id": "CONEXION-1", "user": {"id": 555001, "first_name": "Sofía"},
        "user_chat_id": 555001, "is_enabled": True,
        "rights": {"can_reply": True}}}, c)
    estado = {x["canal"]: x for x in c.get("/api/canales", headers=ha).json()["canales"]}
    check("pasa a modo business", estado["telegram"]["modo"] == "business",
          estado["telegram"]["modo"])
    check("y se lo confirma por Telegram",
          ENVIADOS and "contestar como vos" in ENVIADOS[-1]["text"], ENVIADOS[-1]["text"][:70])
    with sesion() as s, inquilino.sin_filtro():
        cred = s.exec(select(Credencial).where(Credencial.canal == "telegram",
                                               Credencial.business_id == NEG_A)).first()
        check("guarda la conexión para poder buscarla", cred.referencia == "CONEXION-1",
              cred.referencia)

    print("\n   un mensaje que entra por Business")
    update(mensaje_de(888001, "¿Hacen tortas por encargo?", nombre="Marina",
                      conexion="CONEXION-1", msg_id=10), c)
    sin = c.get("/api/cola", headers=ha).json().get("sin_identificar", [])
    check("entra a la cuenta de la conexión", len(sin) == 3, len(sin))
    check("la otra cuenta sigue sin ver nada",
          len(c.get("/api/cola", headers=hb).json().get("sin_identificar", [])) == 0)

    # ------------------------------- 7. lo que el vendedor contesta a mano
    print("\n7 · Lo que Sofía contesta a mano desde su celular")
    # el mensaje de Marina, el que entró por Business
    ID_MSG = next(x["mensaje_id"] for x in sin if "tortas" in x["texto"])
    nuevo = c.post(f"/api/no-identificados/{ID_MSG}/nuevo", headers=ha,
                   json={"nombre": "Marina"})
    check("primero la convertimos en cliente", nuevo.status_code == 200, nuevo.text[:120])
    antes = len(c.get("/api/cola", headers=ha).json().get("sin_identificar", []))
    update(mensaje_de(888001, "Sí, con dos días de aviso", nombre="Sofía",
                      conexion="CONEXION-1", de=555001, msg_id=11), c)
    with inquilino.usar(NEG_A), sesion() as s:
        m = s.exec(select(Message).where(Message.externo_id == "tg-888001-11")).first()
    check("queda guardado como saliente", m is not None and m.direccion == "saliente",
          m.direccion if m else None)
    check("y escrito por un humano, no por la IA", m and m.autor == "humano",
          m.autor if m else None)
    check("no volvió a entrar como si fuera del cliente",
          len(c.get("/api/cola", headers=ha).json().get("sin_identificar", [])) == antes)

    print("\n   y la respuesta desde Hilo sale como ella")
    ENVIADOS.clear()
    alias_id = nuevo.json()["alias_id"]          # la ficha de Marina
    r = c.post(f"/api/alias/{alias_id}/responder", headers=ha,
               json={"texto": "Te confirmo el jueves", "canal": "telegram", "autor": "humano"})
    check("el envío sale", r.status_code == 200, r.text[:140])
    check("con el business_connection_id puesto",
          ENVIADOS and ENVIADOS[-1].get("business_connection_id") == "CONEXION-1",
          ENVIADOS[-1] if ENVIADOS else None)

    # ------------------------------------------------------- 9. el secreto
    print("\n9 · Un webhook sin el secret token correcto")
    r = c.post("/api/telegram/webhook", json=mensaje_de(999, "hola"),
               headers={"X-Telegram-Bot-Api-Secret-Token": "cualquier-cosa"})
    check("se rechaza con 403", r.status_code == 403, r.status_code)
    r = c.post("/api/telegram/webhook", json=mensaje_de(999, "hola"))
    check("y sin el header tampoco entra", r.status_code == 403, r.status_code)

print("\n" + ("Todo bien." if not fallos else f"{fallos} prueba(s) fallaron."))
sys.exit(1 if fallos else 0)
