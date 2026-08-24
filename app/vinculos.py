"""Cómo se engancha una cuenta de afuera con una cuenta de Hilo.

El problema es el mismo en todos los canales y no es técnico. El cliente abre
Telegram y le escribe a nuestro bot; nos llega un mensaje **de un desconocido**.
Nada adentro de ese mensaje dice a qué cuenta de Hilo pertenece. Lo mismo pasa
con un mail reenviado, con un webhook de Instagram y con la extensión del
navegador.

La solución es un **código corto de un solo uso** que el cliente lleva puesto:

    1. la pantalla pide un código          ->  A7K2M9
    2. viaja adentro del link              ->  t.me/HiloBot?start=A7K2M9
    3. vuelve con el primer mensaje        ->  "/start A7K2M9"
    4. ahí sabemos de quién es, y recién ahí se guarda algo

Tres decisiones que conviene no revertir:

- **Un solo uso.** Se quema al usarlo. Un código que sirve dos veces es un
  código que alguien puede reusar sobre la cuenta de otro.
- **Vence.** Media hora. Un código sin vencimiento es una llave permanente a la
  cuenta de alguien, tirada para siempre en un historial de chat.
- **No es un secreto largo, es un código para escribir a mano.** Seis caracteres
  sin letras que se confundan (nada de O/0, I/1). Con media hora de vida y un
  solo uso, seis caracteres alcanzan de sobra; treinta caracteres no se pueden
  dictar por teléfono, y dictarlo por teléfono es exactamente el caso de uso.
"""
import json
import secrets
from datetime import datetime, timedelta

from sqlmodel import select

from . import inquilino
from .models import Vinculo

# Sin las que se confunden leyendo o dictando: 0/O, 1/I/L, 5/S, 8/B.
ALFABETO = "ACDEFGHJKMNPQRTUVWXY2346789"
LARGO = 6
MINUTOS_DE_VIDA = 30


def _codigo_nuevo() -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(LARGO))


def crear(s, canal: str, quien: str = "") -> Vinculo:
    """Un código nuevo para este negocio y este canal.

    Si ya había uno vivo para el mismo canal, se reemplaza: dos códigos vivos a
    la vez son dos formas de que el cliente use el equivocado.
    """
    for viejo in s.exec(select(Vinculo).where(Vinculo.canal == canal,
                                              Vinculo.usado == None)):   # noqa: E711
        viejo.vence = datetime.now()
        s.add(viejo)

    v = Vinculo(canal=canal, codigo=_codigo_nuevo(), quien=quien,
                vence=datetime.now() + timedelta(minutes=MINUTOS_DE_VIDA))
    s.add(v)
    s.commit()
    s.refresh(v)
    return v


def buscar(s, codigo: str) -> Vinculo | None:
    """Encuentra un código VIVO, mire quien mire.

    Va sin filtro de inquilino a propósito: el que llega con el código es el
    webhook de Telegram, que no tiene sesión ni sabe de qué negocio es. Ese es
    justamente el trabajo del código — decirlo.
    """
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return None
    with inquilino.sin_filtro():
        v = s.exec(select(Vinculo).where(Vinculo.codigo == codigo)).first()
    if not v or v.usado:
        return None
    if v.vence and v.vence < datetime.now():
        return None
    return v


def usar(s, v: Vinculo, datos: dict | None = None) -> int:
    """Lo quema y devuelve el negocio al que pertenece."""
    v.usado = datetime.now()
    if datos:
        v.datos_json = json.dumps(datos, ensure_ascii=False)
    s.add(v)
    s.commit()
    return v.business_id


def vivo(s, canal: str) -> Vinculo | None:
    """El código que está esperando ahora mismo, si hay uno."""
    v = s.exec(select(Vinculo)
               .where(Vinculo.canal == canal, Vinculo.usado == None)      # noqa: E711
               .order_by(Vinculo.creado.desc())).first()
    if v and (not v.vence or v.vence > datetime.now()):
        return v
    return None


def como_esta(v: Vinculo | None) -> dict:
    """Lo que la pantalla necesita saber de un código en curso."""
    if not v:
        return {"esperando": False}
    faltan = int((v.vence - datetime.now()).total_seconds()) if v.vence else 0
    return {"esperando": True, "codigo": v.codigo,
            "vence_en_segundos": max(0, faltan),
            "minutos_de_vida": MINUTOS_DE_VIDA}
