"""Telegram: un solo bot de Hilo para todos los clientes.

Hay dos modos y la diferencia decide el producto:

**Modo bot.** Los clientes del vendedor le escriben *al bot*. Se conecta en
treinta segundos y no cuesta nada, pero nadie cambia por dónde le escriben sus
clientes. Sirve para mostrar Hilo funcionando, no para reemplazar el canal.

**Modo Business.** El vendedor tiene Telegram Premium y desde
*Configuración → Telegram Business → Chatbots* conecta nuestro bot a **su cuenta
personal**. A partir de ahí Hilo ve sus conversaciones de verdad y contesta como
él: el que recibe no puede distinguir una respuesta del bot de una escrita a
mano. Este es el que sirve.

Lo bueno es que **son el mismo código**. Un mensaje de Business trae un
`business_connection_id` y sale con ese mismo id; todo lo demás es igual.

Y lo que hace que esto escale: **un solo bot para todos los clientes.** No hay un
token por cliente que guardar, cifrar y rotar. Lo que guardamos por cuenta es a
quién pertenece la conexión, que es un número, no un secreto.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

# El de siempre. `TG_API` existe para poder levantar la app contra un Telegram de
# mentira y caminar la pantalla de conectar canales sin tocar la red de verdad.
API = (os.environ.get("TG_API") or "https://api.telegram.org").rstrip("/")

_estado = {
    "recibidos": 0, "enviados": 0, "ultimo_error": "", "ultimo_recibido": "",
    "usuario": "", "webhook": "", "rechazados": 0,
}


# ------------------------------------------------------------------ config

def token() -> str:
    return (os.environ.get("TG_TOKEN") or "").strip()


def secreto_webhook() -> str:
    """La frase que Telegram nos devuelve en cada webhook para probar que es él.

    Si no está en el `.env`, se deriva del token: no es tan bueno como una frase
    propia, pero es infinitamente mejor que no verificar nada. Un webhook abierto
    en internet sin verificar es un endpoint donde cualquiera inventa mensajes.
    """
    propio = (os.environ.get("TG_SECRETO") or "").strip()
    if propio:
        return propio
    t = token()
    return ("hilo-" + t.split(":")[-1][:24]) if t else ""


def configurado() -> bool:
    return bool(token())


def estado() -> dict:
    return {**_estado, "configurado": configurado(),
            "usuario": _estado["usuario"] or "",
            "secreto_puesto": bool(secreto_webhook())}


# ---------------------------------------------------------------- la puerta

def _pedir(metodo: str, cuerpo: dict | None = None, timeout: int = 20) -> tuple[bool, object]:
    """La ÚNICA puerta a la API de Telegram.

    Igual que en `whatsapp.py` y `mercadopago.py`: un solo lugar que habla con
    afuera, para que el manejo de errores esté junto y para que las pruebas
    puedan reemplazar esta función y ejercitar el flujo entero sin red.
    """
    if not token():
        return False, "Falta TG_TOKEN en el .env"
    url = f"{API}/bot{token()}/{metodo}"
    datos = json.dumps(cuerpo, ensure_ascii=False).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method="POST" if datos else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read().decode() or "{}")
        if not j.get("ok"):
            _estado["ultimo_error"] = str(j.get("description", ""))[:300]
            return False, _estado["ultimo_error"]
        return True, j.get("result")
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="replace")[:300]
        try:
            detalle = json.loads(detalle).get("description", detalle)
        except Exception:                                        # noqa: BLE001
            pass
        _estado["ultimo_error"] = f"HTTP {e.code}: {detalle}"
        return False, _estado["ultimo_error"]
    except Exception as e:                                       # noqa: BLE001
        _estado["ultimo_error"] = f"No pude hablar con Telegram: {e}"
        return False, _estado["ultimo_error"]


def quien_soy(refrescar: bool = False) -> str:
    """El @usuario del bot. Hace falta para armar el link de vinculación."""
    if _estado["usuario"] and not refrescar:
        return _estado["usuario"]
    salio, r = _pedir("getMe")
    if salio and isinstance(r, dict):
        _estado["usuario"] = r.get("username", "")
    return _estado["usuario"]


def registrar_webhook(url_base: str) -> tuple[bool, str]:
    """Le dice a Telegram a dónde mandarnos los mensajes.

    `allowed_updates` incluye los de Business a propósito: **si no se piden, no
    llegan**, y es exactamente el error que hace pensar que el modo Business no
    funciona cuando en realidad nunca se pidió.
    """
    if not configurado():
        return False, "Falta TG_TOKEN"
    url = url_base.rstrip("/") + "/api/telegram/webhook"
    salio, r = _pedir("setWebhook", {
        "url": url,
        "secret_token": secreto_webhook(),
        "allowed_updates": ["message", "edited_message",
                            "business_connection", "business_message",
                            "edited_business_message", "deleted_business_messages"],
        "drop_pending_updates": False,
    })
    if salio:
        _estado["webhook"] = url
    return salio, (url if salio else str(r))


def link_de_vinculacion(codigo: str) -> str:
    """`t.me/HiloBot?start=A7K2M9` — el link que hace todo el trabajo.

    Telegram le manda al bot `/start A7K2M9` en cuanto el usuario aprieta
    «Iniciar». Ese código es lo único que nos dice de qué cuenta de Hilo se trata.
    """
    usuario = quien_soy()
    return f"https://t.me/{usuario}?start={codigo}" if usuario else ""


def firma_valida(cabecera: str) -> bool:
    esperado = secreto_webhook()
    if not esperado:
        return True                     # sin token configurado no hay nada que proteger
    return (cabecera or "") == esperado


# ------------------------------------------------------------------ recibir

def _nombre_de(quien: dict) -> str:
    partes = [quien.get("first_name", ""), quien.get("last_name", "")]
    nombre = " ".join(p for p in partes if p).strip()
    if not nombre:
        nombre = quien.get("username", "")
    return nombre[:120]


def _texto_de(m: dict) -> str:
    """Lo que se puede leer del mensaje. Un audio o una foto entran igual.

    Un mensaje sin texto no es un mensaje vacío: es alguien que mandó algo que
    todavía no sabemos leer. Que entre con una etiqueta clara vale más que
    ignorarlo, porque el vendedor igual tiene que contestarle.
    """
    if m.get("text"):
        return m["text"]
    if m.get("caption"):
        return m["caption"]
    for campo, etiqueta in (("photo", "[una foto]"), ("voice", "[un audio]"),
                            ("video", "[un video]"), ("document", "[un archivo]"),
                            ("sticker", "[un sticker]"), ("location", "[una ubicación]"),
                            ("contact", "[un contacto]")):
        if m.get(campo):
            return etiqueta
    return "[un mensaje que no pude leer]"


def procesar(payload: dict) -> list[dict]:
    """Traduce un update de Telegram a eventos que el resto de la app entiende.

    Devuelve una lista porque un update puede no traer nada que nos importe (y
    entonces la lista viene vacía, que es lo correcto: no es un error que
    Telegram nos avise de algo que no usamos).

    Tres tipos de evento:
      vincular  · alguien apretó el link con el código
      conexion  · un cliente conectó el bot a su Telegram Business
      mensaje   · un mensaje de verdad, para la cola
    """
    eventos: list[dict] = []

    # --- el cliente conectó (o desconectó) el bot a su cuenta Business ---
    con = payload.get("business_connection")
    if con:
        eventos.append({
            "tipo": "conexion",
            "conexion_id": con.get("id", ""),
            "usuario_id": str((con.get("user") or {}).get("id", "")),
            "usuario": _nombre_de(con.get("user") or {}),
            "chat_id": str(con.get("user_chat_id", "")),
            # `rights` es el formato nuevo; `can_reply` el viejo. Aceptamos los dos.
            "puede_responder": bool(
                (con.get("rights") or {}).get("can_reply")
                or con.get("can_reply")),
            "activa": bool(con.get("is_enabled", True)),
        })
        return eventos

    m = payload.get("message") or payload.get("business_message")
    if not m:
        return eventos

    quien = m.get("from") or {}
    chat = m.get("chat") or {}
    texto = _texto_de(m)
    conexion_id = m.get("business_connection_id", "")

    # --- /start CODIGO: la vinculación ---
    if isinstance(m.get("text"), str) and m["text"].startswith("/start"):
        partes = m["text"].split(maxsplit=1)
        eventos.append({
            "tipo": "vincular",
            "codigo": partes[1].strip() if len(partes) > 1 else "",
            "usuario_id": str(quien.get("id", "")),
            "usuario": _nombre_de(quien),
            "arroba": quien.get("username", ""),
            "chat_id": str(chat.get("id", "")),
        })
        return eventos

    if not chat.get("id"):
        return eventos

    _estado["recibidos"] += 1
    _estado["ultimo_recibido"] = datetime.now().isoformat()
    eventos.append({
        "tipo": "mensaje",
        # En un chat privado la contraparte es el chat. Sirve igual para el modo
        # bot (el lead escribiéndole al bot) y para Business (el lead
        # escribiéndole al vendedor): en los dos, `chat.id` es el otro.
        "remitente": str(chat.get("id")),
        "nombre": _nombre_de(quien) or _nombre_de(chat),
        "arroba": quien.get("username", "") or chat.get("username", ""),
        "texto": texto,
        "externo_id": f"tg-{chat.get('id')}-{m.get('message_id')}",
        "conexion_id": conexion_id,
        "de_quien_escribe": str(quien.get("id", "")),
        "es_business": bool(conexion_id),
    })
    return eventos


# ------------------------------------------------------------------ enviar

def enviar(chat_id: str, texto: str, conexion_id: str = "") -> tuple[bool, str]:
    """Manda un mensaje. Con `conexion_id`, sale como el vendedor.

    Esa es toda la diferencia entre los dos modos, y es un campo.
    """
    if not configurado():
        return False, "Telegram no está configurado"
    cuerpo = {"chat_id": chat_id, "text": texto}
    if conexion_id:
        cuerpo["business_connection_id"] = conexion_id
    salio, r = _pedir("sendMessage", cuerpo)
    if salio:
        _estado["enviados"] += 1
        return True, ""
    return False, str(r)
