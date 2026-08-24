"""Multi-inquilino: que cada negocio vea SOLO lo suyo.

El bug más peligroso de una app con varias cuentas no es de los que rompen: es de
los que le muestran los clientes de uno a otro. Y aparece siempre igual — alguien
escribe una consulta nueva y se olvida del `where business_id`.

Por eso acá el filtro **no se escribe a mano en ninguna consulta**. Se cuelga de
SQLAlchemy y se aplica solo:

  - `do_orm_execute` le agrega el filtro a TODO `select` de los modelos de la
    lista, incluidos los `s.get()` y las cargas de relaciones.
  - `before_flush` le pone el `business_id` a todo objeto nuevo antes de guardarlo,
    así tampoco hay que acordarse al crear.

Consecuencia práctica: una consulta nueva ya nace filtrada. Para que se escape
hay que pedirlo a propósito con `sin_filtro()`, que es justo lo que se quiere —
que saltear el aislamiento sea una decisión visible y no un olvido.

Quién NO está en la lista, y por qué:
  - `Business`  — se busca por su propio id.
  - `Acceso`    — el log de "ver como" es NUESTRO, no de ningún inquilino.
  - `Usuario`   — el login tiene que encontrar a alguien por mail ANTES de saber
                  de qué negocio es. Igual lleva `business_id` para saber a dónde
                  pertenece, y el mail es único en toda la app.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event, orm

from .models import (Alias, Briefing, Cobro, Commitment, Credencial, Falla,
                     Identity, Message, UsoIA, Vinculo)

# Los modelos que pertenecen a UN negocio.
MODELOS = (Alias, Identity, Message, Briefing, Commitment, Credencial, UsoIA,
           Falla, Cobro, Vinculo)

# ContextVar y no una global: cada request y cada hilo (el vigía del correo es un
# hilo aparte) tiene el suyo. Con una variable global el vigía del mail y el
# request de un usuario se pisarían el negocio a mitad de camino.
_NEGOCIO: ContextVar = ContextVar("negocio_actual", default=None)


def actual():
    return _NEGOCIO.get()


@contextmanager
def usar(negocio_id):
    """Todo lo que pase adentro ve solo ese negocio."""
    ficha = _NEGOCIO.set(negocio_id)
    try:
        yield negocio_id
    finally:
        _NEGOCIO.reset(ficha)


@contextmanager
def sin_filtro():
    """Ve TODOS los negocios. Solo para el back-office nuestro y las migraciones.

    Que esto exista y haya que escribirlo es el punto: saltear el aislamiento se
    ve en el código, no pasa por olvido.
    """
    ficha = _NEGOCIO.set(None)
    try:
        yield
    finally:
        _NEGOCIO.reset(ficha)


@event.listens_for(orm.Session, "do_orm_execute")
def _filtrar_las_consultas(estado):
    if not estado.is_select or estado.is_column_load or estado.is_relationship_load:
        return
    negocio_id = _NEGOCIO.get()
    if negocio_id is None:
        return
    for modelo in MODELOS:
        # El criterio va como expresión y no como lambda a propósito: SQLAlchemy
        # cachea las lambdas junto con las variables que capturan, y con un valor
        # que cambia por request eso sirve el negocio equivocado.
        estado.statement = estado.statement.options(
            orm.with_loader_criteria(modelo, modelo.business_id == negocio_id,
                                     include_aliases=True)
        )


@event.listens_for(orm.Session, "before_flush")
def _sellar_lo_nuevo(sesion, contexto, instancias):
    negocio_id = _NEGOCIO.get()
    if negocio_id is None:
        return
    for obj in sesion.new:
        if isinstance(obj, MODELOS) and getattr(obj, "business_id", None) is None:
            obj.business_id = negocio_id


def fijar(negocio_id):
    """Deja puesto el inquilino para todo lo que venga, sin bloque `with`.

    Es para los scripts (`seed.py`, `empezar_de_cero.py`) y para los hilos de
    fondo, donde no hay un request que abra y cierre un bloque. En un endpoint no
    se usa: ahí va `usar()`, que lo devuelve como estaba al terminar.
    """
    _NEGOCIO.set(negocio_id)
