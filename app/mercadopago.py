"""Mercado Pago Suscripciones: la tarjeta del cliente, cobrada sola todos los meses.

Por qué Suscripciones (`preapproval`) y no un pago suelto: el cliente pone la
tarjeta **una vez**, en el checkout de Mercado Pago, y MP le cobra todos los
meses solo. Nosotros no vemos ni guardamos un dígito de la tarjeta —eso es de
ellos y es exactamente donde queremos que esté— y nos enteramos de cada cobro por
webhook.

Los cuatro pasos, en orden:

  1. `crear_suscripcion()` arma el `preapproval` y devuelve un **init_point**.
  2. El cliente entra ahí, pone la tarjeta y vuelve.
  3. Mercado Pago nos pega en `/api/pagos/webhook` cada vez que pasa algo.
  4. Nosotros le preguntamos a MP por ese id —**nunca le creemos al webhook**, que
     es un POST abierto en internet— y recién ahí corremos la fecha.

**El modo simulado.** Sin `MP_ACCESS_TOKEN`, todo esto anda igual contra un
Mercado Pago de mentira: el init_point apunta a una pantalla nuestra con una
tarjeta falsa. Sirve para la demo y para las pruebas, y el día que haya
credenciales de verdad no cambia una línea de la lógica — cambia el `.env`.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

API = "https://api.mercadopago.com"

_estado = {"ultimo_error": "", "llamadas": 0, "webhooks": 0}


def token() -> str:
    return (os.environ.get("MP_ACCESS_TOKEN") or "").strip()


def configurado() -> bool:
    return bool(token())


def simulado() -> bool:
    """Sin credenciales, o con MP_SIMULADO=1 a la fuerza (para las pruebas)."""
    return os.environ.get("MP_SIMULADO") == "1" or not configurado()


def es_de_prueba() -> bool:
    """Las credenciales de prueba de MP empiezan con TEST-. Conviene decirlo en
    pantalla: nadie quiere descubrir en producción que estaba cobrando en juguete."""
    return token().startswith("TEST-")


def como_esta() -> dict:
    return {"configurado": configurado(), "simulado": simulado(),
            "de_prueba": es_de_prueba(), **_estado}


def _pedir(metodo: str, ruta: str, cuerpo: dict | None = None) -> tuple[bool, object]:
    """La ÚNICA puerta a la API de Mercado Pago.

    Igual que en `whatsapp.py`: un solo lugar que habla con afuera, para que el
    manejo de errores esté junto y para que las pruebas puedan reemplazar esta
    función y ejercitar el flujo entero sin tocar la red.
    """
    url = f"{API}/{ruta.lstrip('/')}"
    datos = json.dumps(cuerpo, ensure_ascii=False).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method=metodo, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token()}",
    })
    _estado["llamadas"] += 1
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="replace")[:400]
        try:
            j = json.loads(detalle)
            detalle = j.get("message") or j.get("error") or detalle
        except Exception:                                       # noqa: BLE001
            pass
        _estado["ultimo_error"] = f"HTTP {e.code}: {detalle}"
        return False, _estado["ultimo_error"]
    except Exception as e:                                      # noqa: BLE001
        _estado["ultimo_error"] = f"No pude hablar con Mercado Pago: {e}"
        return False, _estado["ultimo_error"]


# ------------------------------------------------------------- suscribirse

def crear_suscripcion(negocio_id: int, nombre_plan: str, precio: int, email: str,
                      volver_a: str) -> tuple[bool, dict]:
    """Arma la suscripción y devuelve a dónde mandar al cliente a poner la tarjeta.

    `external_reference` lleva el id del negocio: es lo que nos deja saber de quién
    era el pago cuando MP nos avisa, sin depender de que el mail coincida.
    """
    if simulado():
        # El id lleva el negocio adentro a propósito: en modo simulado no hay
        # nadie del otro lado que se acuerde de nada.
        sid = f"SIM-{negocio_id}-{int(datetime.now().timestamp())}"
        # Un hash suelto, sin dominio ni puerto. El checkout simulado es una
        # pantalla de ESTA app, y quién sabe en qué dirección está abierta la app
        # es el navegador, no el server: en desarrollo el front vive en :5173 y
        # el backend en :8000, así que armar la URL acá mandaba al usuario a otro
        # origen — misma app, pero sin su sesión, o sea a la portada.
        return True, {"id": sid, "init_point": f"#/tarjeta?s={sid}", "simulado": True}

    salio, r = _pedir("POST", "preapproval", {
        "reason": f"Hilo — plan {nombre_plan}",
        "external_reference": f"negocio-{negocio_id}",
        "payer_email": email,
        "back_url": f"{volver_a}#/plan",
        "status": "pending",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": float(precio),
            "currency_id": "ARS",
        },
    })
    if not salio or not isinstance(r, dict) or not r.get("init_point"):
        return False, {"error": str(r)}
    return True, {"id": r["id"], "init_point": r["init_point"], "simulado": False}


def ver_suscripcion(sid: str) -> tuple[bool, dict]:
    """El estado real, preguntado a MP. Lo que dice esto le gana a lo que diga el
    webhook: el webhook es un aviso, no una fuente de verdad."""
    if sid.startswith("SIM-"):
        return True, {"id": sid, "status": "authorized", "simulado": True}
    salio, r = _pedir("GET", f"preapproval/{sid}")
    return (salio and isinstance(r, dict)), (r if isinstance(r, dict) else {"error": str(r)})


def cancelar(sid: str) -> tuple[bool, str]:
    if sid.startswith("SIM-"):
        return True, "cancelada"
    salio, r = _pedir("PUT", f"preapproval/{sid}", {"status": "cancelled"})
    return salio, ("cancelada" if salio else str(r))


def ver_pago(pago_id: str) -> tuple[bool, dict]:
    """Un cobro concreto de una suscripción (`authorized_payment`)."""
    salio, r = _pedir("GET", f"authorized_payments/{pago_id}")
    return (salio and isinstance(r, dict)), (r if isinstance(r, dict) else {})


# --------------------------------------------------------------- traducción

# Lo que dice MP -> lo que decimos nosotros. La app entiende cuatro palabras.
ESTADOS = {
    "pending": "pendiente",      # la creamos, todavía no puso la tarjeta
    "authorized": "activa",      # tarjeta puesta y cobrando
    "paused": "pausada",
    "cancelled": "cancelada",
}


def traducir(status: str) -> str:
    return ESTADOS.get(status, status or "")


def tarjeta_de(sub: dict) -> str:
    """Los cuatro números que le sirven al cliente para reconocer cuál puso.

    Es todo lo que guardamos de una tarjeta, y ya es más de lo estrictamente
    necesario: existe solo para que el que tiene tres tarjetas sepa cuál cargó.
    """
    metodo = (sub.get("payment_method_id") or "").replace("_", " ").strip()
    ultimos = str(sub.get("last_four_digits")
                  or (sub.get("card") or {}).get("last_four_digits") or "")
    if not (metodo or ultimos):
        return ""
    return f"{metodo or 'tarjeta'} ····{ultimos}".strip()
