"""Lo que cuesta y lo que se rompe, anotado por cuenta.

Dos funciones y nada más:

  - `anotar_ia()`   suma una llamada al modelo, con sus tokens, a la fila del día
                    de ese negocio. Es nuestro único costo variable directo: sin
                    esto no sabemos cuál de los clientes nos hace perder plata.
  - `anotar_falla()` deja el error escrito con nombre de cuenta, para que el
                    back-office pueda mostrar las últimas 50 y "no me llegan los
                    mensajes" deje de contestarse pidiendo capturas.

Tres reglas de las que no se sale:

1. **Nunca revienta.** Todo está envuelto en `try`. Medir es importante; que la
   app se caiga porque no pudo medir, no. Si esto falla, falla en silencio y el
   mensaje del cliente igual entra.
2. **El negocio sale del contexto**, no del que llama. `inquilino.actual()` ya
   sabe de quién es el request (y también de quién es el hilo del vigía del
   correo). Así ningún llamador tiene que acordarse de pasarlo.
3. **Una fila por día, no una por llamada.** La tabla no crece con el uso.
"""
import threading
from datetime import datetime, timedelta

from sqlmodel import select

from . import inquilino
from .db import sesion
from .models import Falla, UsoIA

# Dos escritores compiten por la MISMA fila: el server y el hilo que vigila el
# correo. Sin el candado, dos llamadas simultáneas leen el mismo contador y una
# pisa a la otra — se pierden llamadas justo en el número que usamos para cobrar.
_candado = threading.Lock()


def hoy() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def anotar_ia(modelo: str = "", entrada: int = 0, salida: int = 0, fallo: bool = False):
    """Suma una llamada al modelo en la fila de hoy de este negocio."""
    try:
        negocio_id = inquilino.actual()
        with _candado, sesion() as s, inquilino.sin_filtro():
            fila = s.exec(select(UsoIA).where(UsoIA.business_id == negocio_id,
                                              UsoIA.dia == hoy())).first()
            if not fila:
                fila = UsoIA(business_id=negocio_id, dia=hoy())
            fila.llamadas += 1
            fila.fallos += 1 if fallo else 0
            fila.tokens_entrada += max(0, int(entrada or 0))
            fila.tokens_salida += max(0, int(salida or 0))
            if modelo:
                fila.modelo = modelo
            s.add(fila)
            s.commit()
    except Exception as e:                                          # noqa: BLE001
        print(f"[hilo] no pude anotar el uso de IA ({e})")


def anotar_falla(donde: str, detalle: str, negocio_id: int | None = None):
    """Deja el error escrito. `donde` es el canal o la parte: ia, whatsapp, correo…"""
    try:
        if negocio_id is None:
            negocio_id = inquilino.actual()
        with sesion() as s, inquilino.sin_filtro():
            s.add(Falla(business_id=negocio_id, donde=donde[:40],
                        detalle=str(detalle)[:600]))
            s.commit()
    except Exception as e:                                          # noqa: BLE001
        print(f"[hilo] no pude anotar la falla ({e})")


# ------------------------------------------------------------------ lecturas
# Las usa el back-office. Van acá y no en `root.py` para que la tabla se lea
# donde se escribe y las dos mitades no se desincronicen.


def del_mes(s, negocio_id: int | None = None) -> dict:
    """Llamadas y tokens de los últimos 30 días. Sin negocio, de TODAS las cuentas."""
    desde = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    q = select(UsoIA).where(UsoIA.dia >= desde)
    if negocio_id is not None:
        q = q.where(UsoIA.business_id == negocio_id)
    filas = list(s.exec(q))
    return {
        "llamadas": sum(f.llamadas for f in filas),
        "fallos": sum(f.fallos for f in filas),
        "tokens": sum(f.tokens_entrada + f.tokens_salida for f in filas),
        "modelo": next((f.modelo for f in sorted(filas, key=lambda x: x.dia, reverse=True)
                        if f.modelo), ""),
    }


def por_dia(s, negocio_id: int, dias: int = 14) -> list:
    """La serie diaria de una cuenta, sin huecos: los días sin uso van en cero."""
    filas = {f.dia: f for f in s.exec(select(UsoIA).where(UsoIA.business_id == negocio_id))}
    salida = []
    for i in range(dias - 1, -1, -1):
        dia = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        f = filas.get(dia)
        salida.append({"dia": dia,
                       "llamadas": f.llamadas if f else 0,
                       "fallos": f.fallos if f else 0,
                       "tokens": (f.tokens_entrada + f.tokens_salida) if f else 0})
    return salida


def ultimas_fallas(s, negocio_id: int, cuantas: int = 50) -> list:
    filas = s.exec(select(Falla).where(Falla.business_id == negocio_id)
                   .order_by(Falla.cuando.desc()).limit(cuantas))
    return [{"cuando": f.cuando.isoformat(), "donde": f.donde, "detalle": f.detalle}
            for f in filas]


def fallas_recientes(s, horas: int = 24) -> dict:
    """Cuántas fallas tuvo cada cuenta en las últimas N horas: {negocio_id: cantidad}."""
    desde = datetime.now() - timedelta(hours=horas)
    cuenta: dict = {}
    for f in s.exec(select(Falla).where(Falla.cuando >= desde)):
        cuenta[f.business_id] = cuenta.get(f.business_id, 0) + 1
    return cuenta
