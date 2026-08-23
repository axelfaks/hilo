"""Prueba que un negocio NO puede ver lo de otro.

Es la prueba más importante de la app. Si esto falla, un cliente ve la cartera de
otro cliente, que es el peor bug posible acá — peor que caerse.

    python prueba_inquilino.py
"""
import os
import sys
import tempfile

os.environ["HILO_DB"] = os.path.join(tempfile.mkdtemp(), "prueba.db")
os.environ["HILO_SECRETO"] = "clave-de-prueba-para-el-test"

from sqlmodel import select                                          # noqa: E402

from app import inquilino, secreto                                   # noqa: E402
from app.db import crear_tablas, sesion                              # noqa: E402
from app.models import (Alias, Briefing, Business, Credencial,       # noqa: E402
                        Identity, Message, Usuario)

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    print(("  OK    " if ok else "  FALLA ") + nombre + (("  -> " + str(detalle)) if detalle else ""))
    if not ok:
        fallos += 1


crear_tablas()

# ---------------------------------------------------------------- dos negocios
with sesion() as s:
    a = Business(nombre="Panadería La Espiga", rubro="panaderias")
    b = Business(nombre="Estudio Contable Ruiz", rubro="contadores")
    s.add(a); s.add(b); s.commit(); s.refresh(a); s.refresh(b)
    A, B = a.id, b.id
print(f"\nNegocios creados: A={A} (panadería)  B={B} (estudio)")

# A propósito el MISMO mail en los dos negocios: es el caso que rompe todo si el
# filtro no está. Dos negocios distintos pueden tenerle vendido a la misma persona.
MISMO_MAIL = "sofia@gmail.com"

print("\nSe crean datos en cada negocio (sin escribir business_id a mano)")
with inquilino.usar(A), sesion() as s:
    c = Alias(nombre="Sofía Ramírez")
    s.add(c); s.commit(); s.refresh(c)
    s.add(Identity(alias_id=c.id, canal="mail", valor=MISMO_MAIL))
    s.add(Message(alias_id=c.id, canal="mail", direccion="entrante",
                  autor="cliente", texto="Quiero 20 medialunas"))
    s.add(Briefing(alias_id=c.id, data_json='{"quien_es": "cliente de la panaderia"}'))
    s.commit()
    ALIAS_A = c.id
    check("el alias de A quedó sellado con business_id=A", c.business_id == A, c.business_id)

with inquilino.usar(B), sesion() as s:
    c = Alias(nombre="Sofía Ramírez")
    s.add(c); s.commit(); s.refresh(c)
    s.add(Identity(alias_id=c.id, canal="mail", valor=MISMO_MAIL))
    s.add(Message(alias_id=c.id, canal="mail", direccion="entrante",
                  autor="cliente", texto="Necesito el balance"))
    s.commit()
    ALIAS_B = c.id
    check("el alias de B quedó sellado con business_id=B", c.business_id == B, c.business_id)

# ------------------------------------------------------------------ aislamiento
print("\nAislamiento en las consultas")
with inquilino.usar(A), sesion() as s:
    aliases = list(s.exec(select(Alias)))
    check("A ve exactamente 1 cliente", len(aliases) == 1, [x.nombre for x in aliases])
    check("y es el suyo", aliases and aliases[0].id == ALIAS_A)
    msgs = list(s.exec(select(Message)))
    check("A ve solo su mensaje", len(msgs) == 1 and "medialunas" in msgs[0].texto,
          [m.texto for m in msgs])
    check("A NO puede traer el alias de B con get()", s.get(Alias, ALIAS_B) is None)
    idents = list(s.exec(select(Identity).where(Identity.valor == MISMO_MAIL)))
    check("el mismo mail resuelve a UNA sola identidad", len(idents) == 1, len(idents))
    check("y apunta al cliente de A", idents and idents[0].alias_id == ALIAS_A)
    brs = list(s.exec(select(Briefing)))
    check("A ve solo su briefing", len(brs) == 1, len(brs))

with inquilino.usar(B), sesion() as s:
    aliases = list(s.exec(select(Alias)))
    check("B ve exactamente 1 cliente", len(aliases) == 1, [x.nombre for x in aliases])
    check("y es el suyo", aliases and aliases[0].id == ALIAS_B)
    check("B NO puede traer el alias de A con get()", s.get(Alias, ALIAS_A) is None)
    check("B no ve ningún briefing (el único es de A)",
          len(list(s.exec(select(Briefing)))) == 0)
    msgs = list(s.exec(select(Message)))
    check("B ve solo su mensaje", len(msgs) == 1 and "balance" in msgs[0].texto,
          [m.texto for m in msgs])

# ------------------------------------------------- el borrado tampoco se escapa
print("\nEscribir tampoco se escapa")
with inquilino.usar(B), sesion() as s:
    ajeno = s.get(Message, 1)                      # el mensaje 1 es de A
    check("B no puede alcanzar el mensaje de A para borrarlo", ajeno is None)

# ------------------------------------------------------------- el back-office
print("\nEl back-office (sin_filtro) sí ve todo")
with inquilino.sin_filtro(), sesion() as s:
    check("ve los 2 clientes", len(list(s.exec(select(Alias)))) == 2)
    check("ve los 2 mensajes", len(list(s.exec(select(Message)))) == 2)
    check("ve las 2 identidades", len(list(s.exec(select(Identity)))) == 2)

print("\nEl filtro se restablece al salir del bloque")
with inquilino.usar(A), sesion() as s:
    with inquilino.sin_filtro():
        pass
    check("después de sin_filtro(), A sigue viendo solo lo suyo",
          len(list(s.exec(select(Alias)))) == 1)
check("fuera de todo bloque no queda ningún negocio pegado", inquilino.actual() is None)

# ---------------------------------------------------------------- credenciales
print("\nCredenciales por negocio, cifradas")
import json                                                          # noqa: E402
TOKEN = "EAAG" + "x" * 180
with inquilino.usar(A), sesion() as s:
    s.add(Credencial(canal="whatsapp", externo_id="1172105905976179",
                     etiqueta="+54 9 11 2265 7773",
                     datos_json=secreto.cifrar(json.dumps({"token": TOKEN}))))
    s.commit()
with inquilino.usar(B), sesion() as s:
    check("B no ve la credencial de A", len(list(s.exec(select(Credencial)))) == 0)
with inquilino.usar(A), sesion() as s:
    cred = s.exec(select(Credencial).where(Credencial.canal == "whatsapp")).first()
    check("A ve la suya", cred is not None)
    check("el token vuelve entero",
          cred and json.loads(secreto.descifrar(cred.datos_json))["token"] == TOKEN)
    check("en la base NO está en texto plano", cred and TOKEN not in cred.datos_json)

# --------------------------------------------------------------- los usuarios
print("\nUsuarios: el login los tiene que encontrar antes de saber el negocio")
with sesion() as s:
    s.add(Usuario(email="axel@hilo.test", business_id=A, hash="x"))
    s.add(Usuario(email="ruiz@hilo.test", business_id=B, hash="x"))
    s.commit()
with inquilino.usar(A), sesion() as s:
    u = s.exec(select(Usuario).where(Usuario.email == "ruiz@hilo.test")).first()
    check("el login encuentra a un usuario de otro negocio (a propósito)", u is not None)
    check("y sabe a qué negocio mandarlo", u and u.business_id == B, u.business_id if u else None)

print()
if fallos:
    print(f"{fallos} prueba(s) fallaron.")
    sys.exit(1)
print("Aislamiento verificado: ningún negocio ve lo del otro.")
