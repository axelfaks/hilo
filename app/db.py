import os

from sqlmodel import SQLModel, Session, create_engine

# En la nube casi todos los hostings te dan DATABASE_URL apuntando a Postgres.
# Si no está, seguimos con el archivo SQLite de siempre.
URL = os.environ.get("DATABASE_URL", "").strip()
if URL.startswith("postgres://"):            # formato viejo de Heroku/Render
    URL = URL.replace("postgres://", "postgresql+psycopg://", 1)
elif URL.startswith("postgresql://"):
    URL = URL.replace("postgresql://", "postgresql+psycopg://", 1)

DB_PATH = os.environ.get("HILO_DB", "hilo.db")
engine = (create_engine(URL, pool_pre_ping=True, connect_args={"connect_timeout": 10})
          if URL else
          create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}))


# Con el correo enchufado hay DOS escritores: el hilo que vigila la casilla y el
# server atendiendo pedidos, mientras el frontend lee cada 2 segundos. En SQLite
# eso es la receta exacta del "database is locked". WAL deja que el que lee y el
# que escribe convivan, y el busy_timeout le da 15 s a quien llegue segundo en
# lugar de fallar al instante. En Postgres no hace falta: no se toca.
if not URL:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_al_conectar(dbapi_con, _):
        cur = dbapi_con.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=15000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


def _literal(valor) -> str | None:
    """El default de una columna, escrito para SQL. Solo escalares simples."""
    if isinstance(valor, bool):
        return "1" if valor else "0"
    if isinstance(valor, (int, float)):
        return str(valor)
    if isinstance(valor, str):
        return "'" + valor.replace("'", "''") + "'"
    return None


def asegurar_columnas():
    """Agrega al vuelo las columnas que el modelo tiene y la base todavía no.

    `create_all` crea tablas nuevas pero NUNCA modifica una que ya existe: si se
    agrega un campo al modelo, la base vieja se queda sin él y todo consulta
    revienta con "no such column". Resembrar lo arregla en local, pero en la nube
    no: ahí la base tiene datos de verdad y el seed solo corre si está vacía.

    Esto lo resuelve donde corresponde, sin tocar una sola fila. Las columnas se
    agregan como nullable a propósito: las filas que ya existen no tienen valor y
    exigirles uno haría fallar el ALTER.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    agregadas = []
    for tabla in SQLModel.metadata.sorted_tables:
        if not insp.has_table(tabla.name):
            continue
        existentes = {c["name"] for c in insp.get_columns(tabla.name)}
        for col in tabla.columns:
            if col.name in existentes:
                continue
            tipo = col.type.compile(engine.dialect)
            sql = f'ALTER TABLE "{tabla.name}" ADD COLUMN "{col.name}" {tipo}'
            por_defecto = _literal(col.default.arg) if col.default is not None and not col.default.is_callable else None
            if por_defecto is not None:
                sql += f" DEFAULT {por_defecto}"
            try:
                with engine.begin() as con:
                    con.execute(text(sql))
                agregadas.append(f"{tabla.name}.{col.name}")
            except Exception as e:                    # noqa: BLE001
                print(f"[hilo] no pude agregar {tabla.name}.{col.name}: {e}")
    if agregadas:
        print("[hilo] columnas agregadas sin perder datos: " + ", ".join(agregadas))


def crear_tablas():
    SQLModel.metadata.create_all(engine)
    asegurar_columnas()


def sesion() -> Session:
    return Session(engine)


def en_la_nube() -> bool:
    return bool(URL)
