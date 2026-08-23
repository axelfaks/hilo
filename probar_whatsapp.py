"""Prueba el canal de WhatsApp sin levantar la app.

    python probar_whatsapp.py --offline           # parseo y firma, sin red
    python probar_whatsapp.py 5491122334455       # manda un texto libre
    python probar_whatsapp.py 5491122334455 --plantilla   # manda hello_world
    python probar_whatsapp.py --normalizar        # arregla los números guardados

El hermano de `probar_correo.py`. La idea es la misma: si algo no anda, saber si
es la configuración, la red o el hilo del cliente, sin tener que adivinar.
"""
import json
import sys

from app.config import cargar as cargar_env
cargar_env()
from app import whatsapp as wa                                        # noqa: E402


# --------------------------------------------------------------- sin red

EJEMPLO = {
    "object": "whatsapp_business_account",
    "entry": [{
        "id": "WABA_ID",
        "changes": [{
            "field": "messages",
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {"display_phone_number": "5491100000000",
                             "phone_number_id": "PHONE_ID"},
                "contacts": [{"profile": {"name": "Sofía Ramírez"},
                              "wa_id": "5491122334455"}],
                "messages": [{
                    "from": "5491122334455",
                    "id": "wamid.HBgNNTQ5MTEyMjMzNDQ1NRUCABIYFjNBMDA=",
                    "timestamp": "1756000000",
                    "type": "text",
                    "text": {"body": "Hola! Me pasás precio de 20 medialunas?"},
                }],
            },
        }],
    }],
}

ACUSE = {
    "object": "whatsapp_business_account",
    "entry": [{"changes": [{"field": "messages", "value": {
        "statuses": [{"id": "wamid.X", "status": "delivered"}]}}]}],
}


def offline() -> int:
    fallos = 0

    def check(nombre, ok, detalle=""):
        nonlocal fallos
        print(("  OK   " if ok else "  FALLA") + "  " + nombre + ("  " + detalle if detalle else ""))
        if not ok:
            fallos += 1

    print("\nParseo del webhook")
    msgs = wa.procesar(EJEMPLO)
    check("entra un mensaje", len(msgs) == 1, f"(entraron {len(msgs)})")
    if msgs:
        m = msgs[0]
        check("el remitente son dígitos pelados", m["remitente"] == "5491122334455", m["remitente"])
        check("trae el texto", m["texto"].startswith("Hola!"), m["texto"][:40])
        check("trae el nombre del perfil", m["nombre"] == "Sofía Ramírez", m["nombre"])
        check("trae el wamid para idempotencia", m["wamid"].startswith("wamid."))

    print("\nLo que NO tiene que entrar al hilo")
    check("un acuse de entrega se ignora", wa.procesar(ACUSE) == [])
    check("un payload vacío no explota", wa.procesar({}) == [])
    check("un payload roto no explota", wa.procesar({"entry": [{}]}) == [])

    print("\nNormalización de números")
    for crudo, esperado in [("+54 9 11 2233-4455", "5491122334455"),
                            ("54 9 11 2233 4455", "5491122334455"),
                            ("", ""),
                            ("no es un numero", "")]:
        check(f"«{crudo}»", wa.normalizar(crudo) == esperado, wa.normalizar(crudo))

    print("\nFirma del webhook (X-Hub-Signature-256)")
    import hashlib
    import hmac
    import os
    os.environ["WA_APP_SECRET"] = "secreto-de-prueba"
    cuerpo = json.dumps(EJEMPLO).encode()
    buena = "sha256=" + hmac.new(b"secreto-de-prueba", cuerpo, hashlib.sha256).hexdigest()
    check("acepta la firma correcta", wa.firma_valida(cuerpo, buena))
    check("rechaza una firma inventada", not wa.firma_valida(cuerpo, "sha256=" + "0" * 64))
    check("rechaza si no viene firma", not wa.firma_valida(cuerpo, ""))
    check("rechaza si el cuerpo cambió", not wa.firma_valida(cuerpo + b" ", buena))
    os.environ.pop("WA_APP_SECRET")
    check("sin secreto configurado, deja pasar", wa.firma_valida(cuerpo, ""))

    print("\nVerificación del webhook")
    os.environ["WA_VERIFY_TOKEN"] = "abracadabra"
    check("devuelve el challenge con el token correcto",
          wa.verificar("subscribe", "abracadabra", "12345") == "12345")
    check("rechaza el token equivocado", wa.verificar("subscribe", "otro", "12345") is None)
    check("rechaza otro modo", wa.verificar("unsubscribe", "abracadabra", "12345") is None)
    os.environ.pop("WA_VERIFY_TOKEN")

    print("\nVentana de 24 h")
    from datetime import datetime, timedelta
    check("sin mensajes previos, cerrada", not wa.ventana_abierta(None))
    check("hace una hora, abierta", wa.ventana_abierta(datetime.now() - timedelta(hours=1)))
    check("hace 25 horas, cerrada", not wa.ventana_abierta(datetime.now() - timedelta(hours=25)))

    print()
    if fallos:
        print(f"{fallos} prueba(s) fallaron.")
    else:
        print("Todo bien. El parseo, la firma y la ventana andan.")
    return 1 if fallos else 0


# --------------------------------------------------------------- con red

def enviar(numero: str, plantilla: bool = False) -> int:
    print("\nConfiguración")
    e = wa.estado()
    for k in ("configurado", "numero", "phone_id", "waba_id", "version",
              "webhook_verificable", "firma_verificable"):
        print(f"  {k:22} {e[k]}")
    if not e["configurado"]:
        print("\nFaltan WA_TOKEN y WA_PHONE_ID en el .env. No puedo mandar nada.")
        return 1
    if not e["firma_verificable"]:
        print("\n  Aviso: sin WA_APP_SECRET el webhook acepta mensajes de cualquiera.")

    if plantilla:
        print(f"\nMandando la plantilla hello_world a {numero}...")
        salio, error = wa.enviar_plantilla(numero)
    else:
        print(f"\nMandando texto libre a {numero}...")
        salio, error = wa.enviar(numero, "Probando Hilo. Si te llegó esto, el canal está andando.")

    if not salio:
        print(f"  No salió: {error}")
        return 1

    e = wa.estado()
    print("  Meta ACEPTO el pedido.")
    print(f"    id del mensaje   {e['ultimo_wamid'] or '(no lo devolvio)'}")
    print(f"    entrega a        {e['ultimo_wa_id'] or '(no lo devolvio)'}")
    pedido = wa.normalizar(numero)
    if e["ultimo_wa_id"] and e["ultimo_wa_id"] != pedido:
        print()
        print(f"  OJO: mandaste a {pedido} y WhatsApp lo resolvio como {e['ultimo_wa_id']}.")
        print("       Ese segundo es el numero de verdad: usalo en la ficha del cliente.")

    print()
    print("  Aceptado NO es entregado. Si no te llega nada:")
    if not plantilla:
        print("   1. Probá con plantilla:  python probar_whatsapp.py " + numero + " --plantilla")
        print("      El texto libre SOLO sale si esa persona te escribió en las ultimas 24 h.")
    else:
        print("   1. Si la plantilla tampoco llega, el numero esta mal o no tiene WhatsApp.")
    print("   2. En celulares argentinos probá agregando el 9: 549" + pedido[2:])
    print("   3. Revisá que ese numero este en la lista de destinatarios de Meta.")
    return 0


# --------------------------------------------------------------- la base

def normalizar_guardados() -> int:
    """Deja las identidades de WhatsApp en dígitos pelados.

    Si una quedó guardada como «+54 9 11 1234-5678», el mensaje entrante no la
    encuentra —Meta manda 5491112345678— y el cliente cae en la cola de sin
    identificar cada vez que escribe. Esto es idempotente: correlo las veces que
    quieras.
    """
    from sqlmodel import select

    from app.db import sesion
    from app.models import Identity

    cambiadas = 0
    with sesion() as s:
        for i in s.exec(select(Identity).where(Identity.canal == "whatsapp")):
            limpio = wa.normalizar(i.valor)
            if limpio and limpio != i.valor:
                print(f"  {i.valor}  ->  {limpio}")
                i.valor = limpio
                s.add(i)
                cambiadas += 1
        s.commit()
    print(f"\n{cambiadas} identidad(es) normalizada(s).")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--offline"
    if arg == "--offline":
        sys.exit(offline())
    if arg == "--normalizar":
        sys.exit(normalizar_guardados())
    sys.exit(enviar(arg, "--plantilla" in sys.argv))
