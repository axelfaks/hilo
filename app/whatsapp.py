"""WhatsApp Cloud API: el segundo canal real.

Igual que el correo, no hay un camino especial. Un mensaje de WhatsApp entra por
`pl.ingesta()`, la misma puerta que usa el mail y la vista del cliente. Hay un
canal más que resulta ser real, no un sistema paralelo.

Solo librería estándar, como `ai.py` y `correo.py`. Es una API REST con JSON: no
hace falta sumar una dependencia para eso.

**Los números se guardan en dígitos pelados.** El `wa_id` que manda Meta ya viene
así (`5491112345678`) y es la forma canónica. Si una identidad de WhatsApp quedó
guardada como «+54 9 11 1234-5678», el mensaje entrante NO la va a encontrar y va
a caer en la cola de sin identificar. `probar_whatsapp.py --normalizar` deja las
que ya existen en la forma correcta.
"""
import hashlib
import hmac
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

# Lo que muestra Configuración. Se llena solo, a medida que pasan cosas.
_estado = {
    "enviados": 0,
    "recibidos": 0,
    "ultimo_error": "",
    "ultimo_envio": "",
    "ultimo_recibido": "",
    "firmas_rechazadas": 0,
    # Lo que devolvió Meta en el último envío. `wa_id` es el número al que WhatsApp
    # dice que va a entregar de verdad: si no coincide con el que mandaste, ahí
    # está el problema (el caso clásico es el 9 de los celulares argentinos).
    "ultimo_wamid": "",
    "ultimo_wa_id": "",
    # Lo último que dijo Meta cuando le preguntamos si el token sirve. None =
    # todavía no preguntamos. Se llena en el arranque y con el botón del
    # back-office; NO en cada request, que sería una llamada a Meta por pantalla.
    "token_ok": None,
    "token_detalle": "",
    "token_probado": "",
}

# Meta deja responder libremente solo dentro de las 24 h desde el último mensaje
# del cliente. Fuera de esa ventana hay que mandar una PLANTILLA aprobada, y eso
# SE COBRA; adentro, es gratis. Por eso conviene chequearlo nosotros antes de
# gastar el request: el error de Meta llega tarde, es un código y no se entiende.
VENTANA_HORAS = 24

GRAPH = "https://graph.facebook.com"


def _cfg() -> dict:
    return {
        "app_id": os.environ.get("WA_APP_ID", "").strip(),
        "token": os.environ.get("WA_TOKEN", "").strip(),
        "phone_id": os.environ.get("WA_PHONE_ID", "").strip(),
        "waba_id": os.environ.get("WA_WABA_ID", "").strip(),
        "verify": os.environ.get("WA_VERIFY_TOKEN", "").strip(),
        "secreto": os.environ.get("WA_APP_SECRET", "").strip(),
        "version": os.environ.get("WA_VERSION", "").strip() or "v25.0",
        "numero": os.environ.get("WA_NUMERO", "").strip(),   # solo para mostrarlo
    }


def configurado() -> bool:
    c = _cfg()
    return bool(c["token"] and c["phone_id"])


def estado() -> dict:
    c = _cfg()
    return {
        **_estado,
        "configurado": configurado(),
        "numero": c["numero"],
        "phone_id": c["phone_id"],
        "waba_id": c["waba_id"],
        "version": c["version"],
        "webhook_verificable": bool(c["verify"]),
        "firma_verificable": bool(c["secreto"]),
        # Sin app_id + secreto no se puede cambiar el código del popup por el token
        # del cliente, o sea que el Embedded Signup no puede funcionar.
        "puede_conectar_clientes": bool(c["app_id"] and c["secreto"]),
    }


def cuenta_del_env() -> dict:
    """Las llaves del `.env`. Es el fallback de la instalación de un solo negocio.

    Cuando un cliente conecta su WhatsApp por Embedded Signup, sus llaves viven en
    la tabla `credencial` y llegan acá como parámetro `cuenta`.
    """
    c = _cfg()
    return {"token": c["token"], "phone_id": c["phone_id"], "version": c["version"]}


# ------------------------------------------------------------------- números

def normalizar(numero: str) -> str:
    """Solo dígitos: la forma en que Meta identifica a una persona.

    Ojo Argentina: un celular es +54 9 11 1234-5678 y Meta lo entrega como
    5491112345678, pero la gente lo escribe de seis maneras distintas. Guardamos
    siempre los dígitos pelados y no intentamos adivinar el 9: agregarlo o
    sacarlo por nuestra cuenta manda mensajes a números equivocados.
    """
    return "".join(c for c in (numero or "") if c.isdigit())


# --------------------------------------------------------------------- salida

# Los códigos de Meta son números y el mensaje viene en inglés. Traducirlos acá
# es la diferencia entre "error 131030" y saber exactamente qué hacer.
ERRORES = {
    131047: ("Pasaron más de 24 h desde el último mensaje del cliente. "
             "Para reabrir la conversación hace falta una plantilla aprobada."),
    131026: "Ese número no tiene WhatsApp, o no puede recibir mensajes.",
    131030: ("El número no está en la lista de destinatarios permitidos. "
             "La app está en modo desarrollo: agregalo en Meta → WhatsApp → "
             "Configuración de la API."),
    131051: "Tipo de mensaje no soportado.",
    130429: "Demasiados mensajes por segundo. Meta está limitando el ritmo.",
    100: "Parámetro inválido: revisá el WA_PHONE_ID.",
    190: "El token venció o fue revocado. Generá uno nuevo en Meta.",
    368: "El número está bloqueado temporalmente por Meta por calidad.",
}


def _leer_error(e: urllib.error.HTTPError) -> str:
    try:
        d = json.loads(e.read().decode())
        err = d.get("error", {})
        codigo = err.get("code")
        detalle = (err.get("error_data") or {}).get("details") or err.get("message") or ""
        amable = ERRORES.get(codigo)
        if amable:
            return amable
        return f"Meta devolvió {codigo}: {detalle}"[:300]
    except Exception:                                    # noqa: BLE001
        return f"HTTP {e.code} de Meta"


def ventana_abierta(ultimo_entrante: datetime | None) -> bool:
    """¿Se puede escribir libre, o hace falta plantilla?"""
    if ultimo_entrante is None:
        return False
    return datetime.now() - ultimo_entrante < timedelta(hours=VENTANA_HORAS)


def _pedir(metodo: str, ruta: str, token: str, cuerpo: dict | None = None,
           params: dict | None = None, version: str = "") -> tuple[bool, object]:
    """La ÚNICA puerta a la Graph API. Devuelve (salió, datos) o (False, mensaje).

    Todo pasa por acá para que el manejo de errores y la traducción de los códigos
    de Meta estén en un solo lugar — y para que las pruebas puedan reemplazar esta
    función y ejercitar el flujo entero sin tocar la red.
    """
    v = version or _cfg()["version"]
    url = f"{GRAPH}/{v}/{ruta.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8") if cuerpo is not None else None
    cabeceras = {"Content-Type": "application/json"}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=datos, method=metodo, headers=cabeceras)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            crudo = r.read().decode() or "{}"
        return True, json.loads(crudo)
    except urllib.error.HTTPError as e:
        return False, _leer_error(e)
    except Exception as e:                               # noqa: BLE001
        return False, f"No pude hablar con Meta: {e}"


def _postear(cuerpo: dict, cuenta: dict | None = None) -> tuple[bool, str]:
    """El POST a /messages. Lo comparten el texto libre y las plantillas.

    OJO con lo que significa el éxito acá: Meta responde 200 cuando ACEPTA el
    pedido, no cuando lo entrega. Un 200 con el número mal escrito igual da 200, y
    el mensaje no llega nunca. Por eso se guarda el `wa_id` que devuelve: ese es
    el número al que WhatsApp va a entregar de verdad.
    """
    cta = cuenta or cuenta_del_env()
    salio, r = _pedir("POST", f"{cta['phone_id']}/messages", cta["token"], cuerpo,
                      version=cta.get("version") or "")
    if not salio:
        _estado["ultimo_error"] = str(r)
        return False, str(r)
    _estado["enviados"] += 1
    _estado["ultimo_envio"] = datetime.now().isoformat(timespec="seconds")
    _estado["ultimo_error"] = ""
    _estado["ultimo_wamid"] = (r.get("messages") or [{}])[0].get("id", "")
    _estado["ultimo_wa_id"] = (r.get("contacts") or [{}])[0].get("wa_id", "")
    return True, ""


def enviar(destino: str, texto: str, cuenta: dict | None = None) -> tuple[bool, str]:
    """Manda un mensaje de texto libre. Devuelve (salió, error). Nunca explota.

    Solo funciona DENTRO de la ventana de 24 h. Fuera de ella hay que usar
    `enviar_plantilla()`.
    """
    if not (cuenta or configurado()):
        return False, "WhatsApp no está configurado"
    numero = normalizar(destino)
    if not numero:
        return False, f"«{destino}» no parece un número de WhatsApp"
    return _postear({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "text",
        # 4096 es el máximo de Meta. Cortar acá es mejor que un 400 sin explicar.
        "text": {"preview_url": True, "body": (texto or "").strip()[:4096]},
    }, cuenta)


def enviar_plantilla(destino: str, nombre: str = "hello_world",
                     idioma: str = "en_US", cuenta: dict | None = None) -> tuple[bool, str]:
    """Manda una plantilla aprobada.

    Es lo ÚNICO que se puede mandar cuando no hay una ventana de 24 h abierta —o
    sea, cuando el cliente todavía no te escribió nunca. `hello_world` viene
    aprobada de fábrica en toda cuenta nueva, así que sirve como prueba de vida:
    si la plantilla llega y el texto libre no, el problema es la ventana y no la
    configuración.
    """
    if not (cuenta or configurado()):
        return False, "WhatsApp no está configurado"
    numero = normalizar(destino)
    if not numero:
        return False, f"«{destino}» no parece un número de WhatsApp"
    return _postear({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "template",
        "template": {"name": nombre, "language": {"code": idioma}},
    }, cuenta)


# --------------------------------------------------------------------- entrada

def verificar(modo: str, token: str, challenge: str) -> str | None:
    """El apretón de manos que hace Meta al registrar el webhook.

    Meta pega un GET con un token que elegimos nosotros; si coincide, hay que
    devolver el `challenge` tal cual, en texto plano. Si no coincide, 403 — y el
    webhook nunca queda registrado.
    """
    c = _cfg()
    if modo == "subscribe" and c["verify"] and token == c["verify"]:
        return challenge
    return None


def firma_valida(crudo: bytes, cabecera: str) -> bool:
    """Verifica la X-Hub-Signature-256 que manda Meta.

    El webhook es un endpoint ABIERTO: sin esto, cualquiera que sepa la URL puede
    inventar mensajes de clientes. Con el app secret cargado, solo entra lo que
    firmó Meta.

    Si no hay `WA_APP_SECRET`, devuelve True y deja pasar: durante las primeras
    pruebas es un estorbo, pero `estado()` avisa que la firma no se está
    verificando para que no quede así en producción.
    """
    c = _cfg()
    if not c["secreto"]:
        return True
    if not cabecera or not cabecera.startswith("sha256="):
        return False
    esperado = hmac.new(c["secreto"].encode(), crudo, hashlib.sha256).hexdigest()
    # compare_digest y no ==: comparar strings secretos con == filtra información
    # por el tiempo que tarda en fallar.
    return hmac.compare_digest(esperado, cabecera.split("=", 1)[1])


def _texto_de(m: dict) -> str:
    """El texto de un mensaje, sea del tipo que sea.

    Un audio o una foto no traen texto, pero el hilo tiene que registrar que
    pasaron: si no, el vendedor ve un hueco y no entiende por qué la IA habla de
    algo que «nadie dijo».
    """
    tipo = m.get("type", "")
    if tipo == "text":
        return (m.get("text") or {}).get("body", "")
    if tipo == "button":
        return (m.get("button") or {}).get("text", "")
    if tipo == "interactive":
        i = m.get("interactive") or {}
        for clave in ("button_reply", "list_reply"):
            if i.get(clave):
                return i[clave].get("title", "")
        return ""
    if tipo in ("image", "video", "document", "audio", "sticker"):
        pie = (m.get(tipo) or {}).get("caption", "")
        etiqueta = {"image": "una imagen", "video": "un video",
                    "document": "un documento", "audio": "un audio",
                    "sticker": "un sticker"}[tipo]
        return f"[Mandó {etiqueta}]" + (f" {pie}" if pie else "")
    if tipo == "location":
        loc = m.get("location") or {}
        return f"[Mandó una ubicación] {loc.get('name', '')}".strip()
    if tipo == "contacts":
        return "[Mandó un contacto]"
    return f"[Mandó un mensaje de tipo {tipo}]"


def procesar(payload: dict) -> list[dict]:
    """Del cuerpo del webhook a una lista de mensajes limpios.

    Meta manda MUCHO más que mensajes por el mismo webhook: acuses de entrega,
    cambios de calidad del número, actualizaciones de plantillas. Todo eso se
    ignora acá y no llega nunca al hilo.
    """
    salida = []
    c = _cfg()
    propio = normalizar(c["numero"])
    for entrada in (payload or {}).get("entry", []):
        for cambio in entrada.get("changes", []):
            valor = cambio.get("value") or {}
            # De qué número nuestro es este mensaje. Con varios clientes, cada uno
            # tiene el suyo, y esto es lo que dice a qué negocio entregárselo.
            phone_id = (valor.get("metadata") or {}).get("phone_number_id", "")
            # nombres del perfil, para no crear clientes llamados "5491112345678"
            nombres = {}
            for contacto in valor.get("contacts", []):
                nombres[normalizar(contacto.get("wa_id", ""))] = \
                    (contacto.get("profile") or {}).get("name", "")
            for m in valor.get("messages", []):
                remitente = normalizar(m.get("from", ""))
                if not remitente:
                    continue
                # nunca ingerir un mensaje nuestro: sería un bucle
                if propio and remitente == propio:
                    continue
                salida.append({
                    "remitente": remitente,
                    "nombre": nombres.get(remitente, ""),
                    "texto": _texto_de(m),
                    "wamid": m.get("id", ""),
                    "tipo": m.get("type", ""),
                    "phone_id": phone_id,
                })
    if salida:
        _estado["recibidos"] += len(salida)
        _estado["ultimo_recibido"] = datetime.now().isoformat(timespec="seconds")
    return salida


# ------------------------------------------ conectar el WhatsApp de un cliente
#
# Esto es el Embedded Signup visto desde el backend. El cliente aprieta un botón
# en Hilo, se abre un popup de Facebook, y vuelve con tres cosas: un código que
# dura 30 segundos, el id de su cuenta de WhatsApp (waba_id) y el de su número
# (phone_id). Lo que sigue convierte eso en un canal andando, sin que el cliente
# vea un solo identificador.
#
# Nada de esto se configura a mano por cliente. Es el mismo código para el cliente
# 1 y para el 100.


def pin_nuevo() -> str:
    """Un PIN de verificación en dos pasos, distinto para cada cliente.

    Meta lo pide al registrar el número. Usar el mismo para todos sería darle a
    cualquiera que lo averigüe la llave de todos los números.
    """
    return f"{secrets.randbelow(1000000):06d}"


def intercambiar_codigo(codigo: str) -> tuple[bool, str]:
    """El código del popup, por el token del cliente.

    El código dura 30 segundos: esto se llama enseguida y no se guarda nunca.
    """
    c = _cfg()
    if not (c["app_id"] and c["secreto"]):
        return False, ("Faltan WA_APP_ID o WA_APP_SECRET en el .env: sin eso no se "
                       "puede conectar el WhatsApp de un cliente")
    salio, r = _pedir("GET", "oauth/access_token", "", params={
        "client_id": c["app_id"], "client_secret": c["secreto"], "code": codigo})
    if not salio:
        return False, str(r)
    token = (r or {}).get("access_token", "")
    if not token:
        return False, "Meta aceptó el código pero no devolvió ningún token"
    return True, token


def suscribir_waba(waba_id: str, token: str) -> tuple[bool, str]:
    """Engancha NUESTRA app a la cuenta de WhatsApp del cliente.

    Esta es la línea que hace que todo esto escale. A partir de acá los mensajes de
    ese cliente caen en el webhook que ya configuramos una sola vez, y no hay que
    tocar ninguna configuración por cliente nuevo. Sin esto el alta parece exitosa
    y después no llega nunca un mensaje.
    """
    salio, r = _pedir("POST", f"{waba_id}/subscribed_apps", token)
    if not salio:
        return False, str(r)
    if not (r or {}).get("success", True):
        return False, "Meta no confirmó la suscripción de la app a esa cuenta"
    return True, ""


def registrar_numero(phone_id: str, token: str, pin: str) -> tuple[bool, str]:
    """Activa el número en la Cloud API. Sin esto no se puede mandar ni recibir."""
    salio, r = _pedir("POST", f"{phone_id}/register", token,
                      {"messaging_product": "whatsapp", "pin": pin})
    if not salio:
        return False, str(r)
    return True, ""


def datos_del_numero(phone_id: str, token: str) -> dict:
    """El número tal como lo va a ver el cliente. Para mostrarlo, no para operar."""
    salio, r = _pedir("GET", phone_id, token, params={
        "fields": "display_phone_number,verified_name,quality_rating"})
    return r if (salio and isinstance(r, dict)) else {}


def probar_token(cuenta: dict | None = None) -> tuple[bool, str]:
    """¿El token sigue vivo? Una pregunta barata a Meta que evita una demo muerta.

    El token temporal de Meta dura 24 h y cuando vence NO avisa: los mensajes
    simplemente dejan de salir, con un error que solo se ve si alguien mira. Esto
    lo pregunta de frente, pidiendo los datos del número —el pedido más barato que
    hay— y devuelve el motivo traducido.

    Se llama en el arranque y desde el back-office. Nunca en un request normal:
    una llamada a Meta por pantalla es una pantalla lenta.
    """
    c = cuenta or cuenta_del_env()
    if not (c.get("phone_id") and c.get("token")):
        _estado["token_ok"] = None
        _estado["token_detalle"] = "Falta WA_TOKEN o WA_PHONE_ID en el .env"
        return False, _estado["token_detalle"]
    salio, r = _pedir("GET", c["phone_id"], c["token"],
                      params={"fields": "display_phone_number,verified_name"})
    _estado["token_probado"] = datetime.now().isoformat()
    if salio and isinstance(r, dict):
        _estado["token_ok"] = True
        _estado["token_detalle"] = (f"{r.get('verified_name', '')} "
                                    f"{r.get('display_phone_number', '')}").strip()
        return True, _estado["token_detalle"]
    _estado["token_ok"] = False
    _estado["token_detalle"] = str(r)
    return False, str(r)


def conectar_cliente(codigo: str, waba_id: str, phone_id: str) -> tuple[bool, object]:
    """El alta completa de un cliente, en orden. Devuelve (ok, datos) o (False, motivo).

    Los pasos van en este orden a propósito: si el token falla no tiene sentido
    seguir, y si la suscripción falla el número queda registrado pero mudo — mejor
    cortar y decirlo que dejar un canal a medio conectar que parece andar.

    El registro del número es el único paso que se perdona: un número que ya estaba
    registrado devuelve error y eso NO es un problema — es un cliente que se está
    reconectando.
    """
    salio, token = intercambiar_codigo(codigo)
    if not salio:
        return False, f"No pude obtener el acceso a la cuenta del cliente: {token}"

    salio, error = suscribir_waba(waba_id, token)
    if not salio:
        return False, f"No pude suscribir Hilo a su cuenta de WhatsApp: {error}"

    pin = pin_nuevo()
    registrado, error_registro = registrar_numero(phone_id, token, pin)

    datos = datos_del_numero(phone_id, token)
    return True, {
        "token": token,
        "waba_id": waba_id,
        "phone_id": phone_id,
        "pin": pin if registrado else "",
        "numero": datos.get("display_phone_number", ""),
        "nombre_visible": datos.get("verified_name", ""),
        "calidad": datos.get("quality_rating", ""),
        # Se devuelve el aviso en vez de fallar: casi siempre es "ya estaba
        # registrado", que es exactamente lo que pasa cuando alguien reconecta.
        "aviso_registro": "" if registrado else error_registro,
    }
