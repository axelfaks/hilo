"""Te da acceso al back-office (#/root). Se corre una vez por persona.

    python hacerme_root.py faksaxel@gmail.com

Ser root no es un rol más de la app: es ver TODAS las cuentas y poder entrar a
cualquiera. Por eso no se regala desde ninguna pantalla —ni siquiera desde el
back-office— y hay que venir hasta acá, con la base a mano, a escribirlo.

Sin argumentos, lista quién es root hoy.
"""
import sys

from sqlmodel import select

from app import inquilino
from app.config import cargar as cargar_env

cargar_env()
from app.db import crear_tablas, sesion                                 # noqa: E402
from app.models import Business, Usuario                                # noqa: E402

crear_tablas()

with sesion() as s, inquilino.sin_filtro():
    negocios = {b.id: b.nombre for b in s.exec(select(Business))}

    if len(sys.argv) < 2:
        print("Root hoy:")
        hay = False
        for u in s.exec(select(Usuario).where(Usuario.es_root == True)):   # noqa: E712
            print(f"  - {u.email}  (entra a {negocios.get(u.business_id, '?')})")
            hay = True
        if not hay:
            print("  (nadie)")
        print("\nPara sumar a alguien:  python hacerme_root.py su@mail.com")
        sys.exit(0)

    email = sys.argv[1].strip().lower()
    u = s.exec(select(Usuario).where(Usuario.email == email)).first()
    if not u:
        print(f"No hay ninguna cuenta con el mail {email}. Los que hay:")
        for otro in s.exec(select(Usuario)):
            print(f"  - {otro.email}")
        sys.exit(1)

    u.es_root = True
    s.add(u)
    s.commit()
    print(f"Listo: {u.email} ya es root.")
    print("Entrá a la app y vas a ver el botón «Back-office» arriba a la derecha,")
    print("o andá derecho a  #/root")
