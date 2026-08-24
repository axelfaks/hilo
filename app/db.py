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


def _literal(valor, dialecto: str = "") -> str | None:
    """El default de una columna, escrito para SQL. Solo escalares simples.

    El booleano se escribe distinto según el motor, y no es un detalle estético:
    Postgres es estricto con los tipos y `BOOLEAN DEFAULT 1` no es "un uno que se
    interpreta como verdadero", es un error de tipos que hace fallar el ALTER
    ENTERO. Como el ALTER va dentro de un try, el arranque no se cae: la columna
    simplemente no se agrega y la app queda pidiendo en cada SELECT una columna
    que no existe. Eso fue exactamente un login rompiéndose con 500 en Render
    mientras en SQLite andaba todo, porque SQLite sí acepta 1/0.
    """
    if isinstance(valor, bool):
        if dialecto == "sqlite":
            return "1" if valor else "0"
        return "TRUE" if valor else "FALSE"
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
            por_defecto = (_literal(col.default.arg, engine.dialect.name)
                           if col.default is not None and not col.default.is_callable else None)
            if por_defecto is not None:
                sql += f" DEFAULT {por_defecto}"
            try:
                with engine.begin() as con:
                    con.execute(text(sql))
                agregadas.append(f"{tabla.name}.{col.name}")
            except Exception as e:                    # noqa: BLE001
                # No se corta el arranque —una app que levanta se puede mirar—
                # pero esto NO es un aviso menor: sin la columna, toda consulta
                # a esa tabla revienta. Que se lea como lo que es.
                print(f"[hilo] OJO: NO pude agregar {tabla.name}.{col.name} -> {e}\n"
                      f"[hilo]      toda consulta a '{tabla.name}' va a fallar hasta que exista.")
    if agregadas:
        print("[hilo] columnas agregadas sin perder datos: " + ", ".join(agregadas))


# Las tablas que pasaron a pertenecer a un negocio. Antes de que existiera el
# multi-inquilino sus filas no tenían dueño; el ALTER las deja en NULL y una fila
# en NULL no la ve NADIE (el filtro pide business_id = X). O sea: sin este
# backfill, actualizar la app hace desaparecer todos los datos de la pantalla.
TABLAS_DEL_INQUILINO = ("alias", "identity", "message", "briefing",
                        "commitment", "credencial", "usuario")


def asignar_negocio_a_lo_viejo():
    """Le pone dueño a las filas que quedaron sin él al actualizar.

    Va en SQL crudo a propósito: el filtro por inquilino se cuelga del ORM, y una
    migración que corre por el ORM no vería justo las filas que tiene que
    arreglar. Es idempotente: la segunda vez no hay ningún NULL y no hace nada.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if not insp.has_table("business"):
        return
    with engine.begin() as con:
        primero = con.execute(text("SELECT id FROM business ORDER BY id LIMIT 1")).first()
        if not primero:
            return                                  # base vacía: no hay nada que migrar
        negocio_id = primero[0]
        tocadas = []
        for tabla in TABLAS_DEL_INQUILINO:
            if not insp.has_table(tabla):
                continue
            if "business_id" not in {c["name"] for c in insp.get_columns(tabla)}:
                continue
            r = con.execute(text(
                f'UPDATE "{tabla}" SET business_id = :n WHERE business_id IS NULL'),
                {"n": negocio_id})
            if r.rowcount:
                tocadas.append(f"{tabla}: {r.rowcount}")
    if tocadas:
        print(f"[hilo] filas viejas asignadas al negocio {negocio_id} -> " + ", ".join(tocadas))


def fechar_los_negocios_viejos():
    """Los negocios de antes del back-office no tienen fecha de alta.

    La columna se agrega vacía, y una lista de cuentas donde la mitad dice "—" en
    "alta" no sirve para nada. Se la ponemos con la del cliente más viejo, que es
    lo más parecido a la verdad que hay en la base; si no tiene ninguno, con la
    fecha de hoy. Idempotente: la segunda vez no queda ningún NULL.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if not insp.has_table("business"):
        return
    if "creado" not in {c["name"] for c in insp.get_columns("business")}:
        return
    with engine.begin() as con:
        if insp.has_table("alias"):
            con.execute(text("""
                UPDATE business SET creado = (
                    SELECT MIN(primer_contacto) FROM alias
                    WHERE alias.business_id = business.id)
                WHERE creado IS NULL"""))
        con.execute(text("UPDATE business SET creado = CURRENT_TIMESTAMP "
                         "WHERE creado IS NULL"))


def crear_tablas():
    SQLModel.metadata.create_all(engine)
    asegurar_columnas()
    asignar_negocio_a_lo_viejo()
    fechar_los_negocios_viejos()


def sesion() -> Session:
    return Session(engine)


def en_la_nube() -> bool:
    return bool(URL)
