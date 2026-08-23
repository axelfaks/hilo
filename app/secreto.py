"""Cifrado de las credenciales que guardamos por cliente.

El token de WhatsApp de un cliente da acceso a mandar mensajes **en su nombre**.
Guardarlo en texto plano en la base significa que una copia de la base es una
copia de las llaves de todos. Esto lo evita.

Construcción, para que se entienda qué garantiza y qué no:

  - La clave maestra sale de `HILO_SECRETO` o del archivo `.hilo_secreto`, el
    mismo que ya firma los tokens de sesión.
  - De ahí se derivan DOS subclaves distintas, una para cifrar y otra para
    autenticar. Usar la misma para las dos cosas es un error clásico.
  - El texto se cifra con un keystream de HMAC-SHA256 en modo contador —una
    construcción estándar, no un invento— y después se firma el resultado
    (cifrar-y-después-autenticar). Si alguien toca un byte, `descifrar` lo
    rechaza en vez de devolver basura.

Lo que NO hace: si alguien se lleva la base **y** el `.hilo_secreto`, lee todo.
Esto protege contra una copia de la base sola, que es el escenario realista.
Cuando haya clientes de verdad, el reemplazo es Fernet de `cryptography`:
cambian estas dos funciones y nada más.
"""
import base64
import hashlib
import hmac
import os
import secrets
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VERSION = "v1"


def _maestra() -> bytes:
    del_entorno = os.environ.get("HILO_SECRETO", "").strip()
    if del_entorno:
        return del_entorno.encode()
    archivo = RAIZ / ".hilo_secreto"
    if archivo.exists():
        return archivo.read_text().strip().encode()
    nuevo = secrets.token_urlsafe(48)
    archivo.write_text(nuevo)
    try:
        archivo.chmod(0o600)
    except OSError:
        pass                                    # en Windows no aplica
    return nuevo.encode()


def _subclaves() -> tuple[bytes, bytes]:
    m = _maestra()
    return (hmac.new(m, b"hilo/cifrado", hashlib.sha256).digest(),
            hmac.new(m, b"hilo/autenticacion", hashlib.sha256).digest())


def _keystream(clave: bytes, nonce: bytes, largo: int) -> bytes:
    salida = bytearray()
    contador = 0
    while len(salida) < largo:
        salida += hmac.new(clave, nonce + contador.to_bytes(4, "big"), hashlib.sha256).digest()
        contador += 1
    return bytes(salida[:largo])


def cifrar(texto: str) -> str:
    if not texto:
        return ""
    k_cif, k_aut = _subclaves()
    nonce = secrets.token_bytes(16)
    claro = texto.encode("utf-8")
    cifrado = bytes(a ^ b for a, b in zip(claro, _keystream(k_cif, nonce, len(claro))))
    tag = hmac.new(k_aut, nonce + cifrado, hashlib.sha256).digest()[:16]
    return VERSION + "." + base64.urlsafe_b64encode(nonce + tag + cifrado).decode()


def descifrar(guardado: str) -> str:
    """Devuelve el texto, o "" si está vacío, corrupto o firmado con otra clave."""
    if not guardado:
        return ""
    try:
        version, cuerpo = guardado.split(".", 1)
        if version != VERSION:
            return ""
        crudo = base64.urlsafe_b64decode(cuerpo)
        nonce, tag, cifrado = crudo[:16], crudo[16:32], crudo[32:]
        k_cif, k_aut = _subclaves()
        esperado = hmac.new(k_aut, nonce + cifrado, hashlib.sha256).digest()[:16]
        # compare_digest y no ==: comparar con == filtra información por el tiempo
        if not hmac.compare_digest(tag, esperado):
            return ""
        return bytes(a ^ b for a, b in zip(cifrado, _keystream(k_cif, nonce, len(cifrado)))).decode("utf-8")
    except Exception:                            # noqa: BLE001
        return ""
