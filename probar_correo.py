"""Prueba el canal de mail de punta a punta contra Gmail de verdad.

    python probar_correo.py                    -> manda a tu propia casilla
    python probar_correo.py otro@mail.com      -> manda ahí

Hace tres cosas y te dice cuál falla:
  1. SMTP  — se autentica y manda un mail real.
  2. IMAP  — se autentica y cuenta lo que hay sin leer.
  3. Lee   — trae los mails sin leer y muestra cómo los ve Hilo.

OJO con el paso 3: marca como leídos los mails que trae, igual que hace la app.
"""
import sys

from app.config import cargar as cargar_env

cargar_env()
from app import correo                                   # noqa: E402

e = correo.estado()
print("=" * 62)
print(f"  casilla : {e['casilla'] or '(sin configurar)'}")
print(f"  smtp    : {e['smtp']}")
print(f"  imap    : {e['imap']}")
print("=" * 62)

if not correo.configurado():
    print("\nFALTA configurar MAIL_USUARIO y MAIL_CLAVE en el .env")
    sys.exit(1)

destino = sys.argv[1] if len(sys.argv) > 1 else e["casilla"]

# ------------------------------------------------------------------ 1. SMTP
print(f"\n[1/3] Mandando un mail a {destino} …")
ok, error = correo.enviar(
    destino,
    "Hilo: probando el canal de mail",
    "Si estás leyendo esto, Hilo puede mandar mails de verdad.\n\n"
    "Respondé este mail y, si el server está corriendo, en unos segundos\n"
    "lo vas a ver aparecer en el hilo del cliente.\n",
)
print("      OK, salió." if ok else f"      FALLÓ: {error}")

# ------------------------------------------------------------------ 2. IMAP
print("\n[2/3] Entrando por IMAP a la bandeja …")
nuevos = correo.revisar()
if correo.estado()["ultimo_error"]:
    print(f"      FALLÓ: {correo.estado()['ultimo_error']}")
    sys.exit(1)
print(f"      OK. Mails sin leer que Hilo tomaría: {len(nuevos)}")

# -------------------------------------------------------------- 3. lectura
print("\n[3/3] Así los ve Hilo:")
if not nuevos:
    print("      (no había nada sin leer — mandale un mail a la casilla y repetí)")
for m in nuevos:
    print(f"      · de {m['remitente']} — «{m['asunto']}»")
    for linea in m["texto"].splitlines()[:4]:
        print(f"          {linea}")

print("\n" + "=" * 62)
print("  Listo. Si los tres pasos dieron OK, el mail está enchufado.")
print("=" * 62)
