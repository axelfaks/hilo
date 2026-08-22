"""Login. Sin dependencias nuevas: todo con la biblioteca estándar.

Cómo funciona:
  - La contraseña nunca se guarda. Se guarda scrypt(contraseña + sal aleatoria).
  - El token es un JSON firmado con HMAC-SHA256 y con vencimiento. No hay sesiones
    en memoria, así que reiniciar el server no desloguea a nadie.
  - La API queda protegida SOLO cuando existe al menos un usuario. Mientras no haya
    ninguno, la app funciona abierta y te pide crear la primera cuenta. Así nadie
    se queda afuera de su propia app.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from sqlmodel import Session, func, select

from .models import Usuario

DIAS_DE_SESION = 30
RAIZ = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------- secreto

def _secreto() -> bytes:
    """Se guarda en disco para que los tokens sobrevivan a un reinicio."""
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
        pass  # en Windows no aplica
    return nuevo.encode()


# --------------------------------------------------------------- contraseñas

def hashear(contrasena: str) -> str:
    sal = secrets.token_bytes(16)
    clave = hashlib.scrypt(contrasena.encode(), salt=sal, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${base64.b64encode(sal).decode()}${base64.b64encode(clave).decode()}"


def verificar(contrasena: str, guardado: str) -> bool:
    try:
        algo, sal_b64, clave_b64 = guardado.split("$")
        if algo != "scrypt":
            return False
        sal = base64.b64decode(sal_b64)
        esperada = base64.b64decode(clave_b64)
        calculada = hashlib.scrypt(contrasena.encode(), salt=sal, n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calculada, esperada)
    except Exception:
        return False


def problema_con_la_contrasena(c: str) -> str:
    """Devuelve el motivo, o cadena vacía si está bien. En español y accionable."""
    if len(c) < 8:
        return "La contraseña tiene que tener al menos 8 caracteres"
    if c.isdigit() or c.isalpha():
        return "Mezclá letras y números para que no sea tan fácil de adivinar"
    return ""


# -------------------------------------------------------------------- tokens

def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def _des64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def emitir_token(usuario_id: int) -> str:
    cuerpo = _b64(json.dumps({
        "uid": usuario_id,
        "exp": int(time.time()) + DIAS_DE_SESION * 86400,
    }).encode())
    firma = _b64(hmac.new(_secreto(), cuerpo.encode(), hashlib.sha256).digest())
    return f"{cuerpo}.{firma}"


def leer_token(token: str) -> int | None:
    """Devuelve el id del usuario, o None si el token es falso o venció."""
    try:
        cuerpo, firma = token.split(".")
        esperada = _b64(hmac.new(_secreto(), cuerpo.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(firma, esperada):
            return None
        datos = json.loads(_des64(cuerpo))
        if datos.get("exp", 0) < time.time():
            return None
        return int(datos["uid"])
    except Exception:
        return None


# ------------------------------------------------------------------ usuarios

def hay_usuarios(s: Session) -> bool:
    return (s.exec(select(func.count()).select_from(Usuario)).one() or 0) > 0


def auth_encendida(s: Session) -> bool:
    if os.environ.get("HILO_AUTH") == "0":
        return False
    return hay_usuarios(s)


def crear_usuario(s: Session, email: str, contrasena: str, nombre: str, rol: str = "dueño") -> Usuario:
    u = Usuario(email=email.strip().lower(), nombre=nombre.strip() or email.split("@")[0],
                hash=hashear(contrasena), rol=rol)
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


def buscar_por_email(s: Session, email: str) -> Usuario | None:
    return s.exec(select(Usuario).where(Usuario.email == email.strip().lower())).first()


def publico(u: Usuario) -> dict:
    return {"id": u.id, "email": u.email, "nombre": u.nombre, "rol": u.rol}
