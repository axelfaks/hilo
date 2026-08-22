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
engine = (create_engine(URL, pool_pre_ping=True) if URL
          else create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}))


def crear_tablas():
    SQLModel.metadata.create_all(engine)


def sesion() -> Session:
    return Session(engine)


def en_la_nube() -> bool:
    return bool(URL)
