"""El único lugar donde Hilo habla con un servidor de correo de verdad.

Hasta acá todos los canales eran simulados. Este módulo es la excepción: un mail
que sale de acá llega a una bandeja real, y un mail que entra a la casilla
aparece en el hilo por la misma puerta que usa la vista del cliente —
`pl.ingesta()`. No hay un camino especial para el correo: hay un canal más que
resulta ser real.

Todo con librería estándar (smtplib, imaplib, email), igual que auth.py: a esta
altura del proyecto, una dependencia nueva es un riesgo, no una comodidad.

Configuración, en el .env de la raíz:

    MAIL_USUARIO=lacasilla@gmail.com
    MAIL_CLAVE=abcd efgh ijkl mnop     <- contraseña de APLICACIÓN, no la de la cuenta
    MAIL_NOMBRE=Hilo                   <- opcional: el nombre que ve el que recibe
    MAIL_SMTP=smtp.gmail.com:587       <- opcional
    MAIL_IMAP=imap.gmail.com:993       <- opcional
    MAIL_INTERVALO=10                  <- opcional: cada cuántos segundos mira la bandeja

Sin MAIL_USUARIO y MAIL_CLAVE el módulo queda dormido y la app anda igual que
antes, con el mail simulado. Nada revienta por no configurarlo.
"""
import base64
import email
import imaplib
import os
import re
import smtplib
import threading
import time
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr, parsedate_to_datetime, parseaddr

# ------------------------------------------------------------------ estado vivo
# Lo que muestra /api/correo/estado. Sirve para saber, en medio de la demo, si el
# correo está andando sin tener que mirar los logs del server.
_estado = {
    "ultima_revision": None,
    "ultimo_error": "",
    "recibidos": 0,
    "enviados": 0,
    "vigilando": False,
    "descartados": 0,
}

# Cuánto para atrás mira Hilo la primera vez. Una casilla recién creada tiene
# sin leer los mails de bienvenida de Google, y no son conversaciones con
# clientes: si entraran al sistema, la cola arrancaría llena de basura. Los
# viejos se marcan leídos y se tiran; los de los últimos minutos entran, para
# que un mail de prueba mandado justo antes de levantar el server no se pierda.
MINUTOS_DE_GRACIA = 15


def _cfg() -> dict:
    def limpio(k, d=""):
        return (os.environ.get(k) or d).strip().strip('"').strip("'")

    smtp = limpio("MAIL_SMTP", "smtp.gmail.com:587")
    imap = limpio("MAIL_IMAP", "imap.gmail.com:993")
    return {
        "usuario": limpio("MAIL_USUARIO"),
        # Google muestra la contraseña de aplicación con espacios: no son parte de la clave
        "clave": limpio("MAIL_CLAVE").replace(" ", ""),
        "nombre": limpio("MAIL_NOMBRE", "Hilo"),
        "smtp_host": smtp.rsplit(":", 1)[0],
        "smtp_puerto": int(smtp.rsplit(":", 1)[1]) if ":" in smtp else 587,
        "imap_host": imap.rsplit(":", 1)[0],
        "imap_puerto": int(imap.rsplit(":", 1)[1]) if ":" in imap else 993,
        "intervalo": max(5, int(limpio("MAIL_INTERVALO", "10") or 10)),
    }


def configurado() -> bool:
    c = _cfg()
    return bool(c["usuario"] and c["clave"])


def estado() -> dict:
    c = _cfg()
    return {
        **_estado,
        "configurado": configurado(),
        "casilla": c["usuario"],
        "nombre": c["nombre"],
        "smtp": f"{c['smtp_host']}:{c['smtp_puerto']}",
        "imap": f"{c['imap_host']}:{c['imap_puerto']}",
        "intervalo": c["intervalo"],
    }


# ------------------------------------------------------------------------ salida

def enviar(destino: str, asunto: str, texto: str,
           cc: str = "", cco: str = "") -> tuple[bool, str]:
    """Manda un mail de verdad. Devuelve (salió, error).

    cc y cco son listas separadas por coma. La diferencia entre las dos no la
    hace una cabecera especial: el CCO simplemente NO se escribe en el mail, se
    agrega a la lista de destinatarios del sobre. Por eso los que reciben ven a
    los de CC y no a los de CCO.
    """
    if not configurado():
        return False, "El correo no está configurado (faltan MAIL_USUARIO y MAIL_CLAVE)"
    destino = (destino or "").strip()
    if "@" not in destino:
        return False, f"«{destino}» no es una dirección de mail"

    def lista(v):
        return [x.strip() for x in (v or "").replace(";", ",").split(",") if "@" in x]

    copias, ocultas = lista(cc), lista(cco)

    c = _cfg()
    m = EmailMessage()
    m["From"] = formataddr((c["nombre"], c["usuario"]))
    m["To"] = destino
    if copias:
        m["Cc"] = ", ".join(copias)
    m["Subject"] = asunto or "(sin asunto)"
    m.set_content(texto)

    try:
        with smtplib.SMTP(c["smtp_host"], c["smtp_puerto"], timeout=20) as s:
            s.starttls()
            s.login(c["usuario"], c["clave"])
            # el CCO va acá y en ningún lado más: en el sobre, no en el mensaje
            s.send_message(m, to_addrs=[destino] + copias + ocultas)
        _estado["enviados"] += 1
        _estado["ultimo_error"] = ""
        return True, ""
    except smtplib.SMTPAuthenticationError:
        err = ("Google rechazó la clave. Tiene que ser una contraseña de APLICACIÓN "
               "(16 caracteres), con la verificación en 2 pasos activada.")
    except Exception as e:                      # noqa: BLE001 — cualquier fallo se reporta igual
        err = f"{type(e).__name__}: {e}"
    _estado["ultimo_error"] = err
    return False, err


# ------------------------------------------------------------------------ entrada

# Dónde empieza la cita del mail anterior. Si no se corta acá, cada respuesta
# arrastra toda la conversación y el hilo de Hilo se vuelve ilegible.
# OJO: la línea de atribución de Gmail SE PARTE EN DOS RENGLONES cuando es larga:
#
#     El sáb, 22 ago 2026 a la(s) 5:12 p.m., Hilo (hilo.ventas.demo@gmail.com)
#     escribió:
#
# Por eso estos patrones se aplican sobre el texto entero y no renglón por
# renglón: buscarlos en una sola línea es exactamente el bug que dejaba entrar
# «Me llegó perrito El sáb, 22 ago 2026 a la(s) 5:12 p.m., … escribió:» al hilo.
CORTES = [
    re.compile(r"^[ \t]*El\b[\s\S]{0,300}?escribi[óo]:[ \t]*$", re.M),
    re.compile(r"^[ \t]*On\b[\s\S]{0,300}?wrote:[ \t]*$", re.M),
    re.compile(r"^[ \t]*-{2,}\s*Mensaje original\s*-{2,}", re.M | re.I),
    re.compile(r"^[ \t]*-{2,}\s*Original Message\s*-{2,}", re.M | re.I),
    re.compile(r"^[ \t]*_{5,}[ \t]*$", re.M),
    re.compile(r"^[ \t]*De:[ \t]+.+<.+@.+>[ \t]*$", re.M),
    re.compile(r"^[ \t]*From:[ \t]+.+<.+@.+>[ \t]*$", re.M),
    re.compile(r"^[ \t]*Enviado desde mi \w+", re.M),
    re.compile(r"^[ \t]*Sent from my \w+", re.M),
    # El separador de firma de toda la vida: dos guiones solos en un renglón.
    # Sin esto entra el bloque entero — logo, cargo, teléfono, "Schedule a call".
    re.compile(r"^--[ \t]*$", re.M),
]

# Cuánto pesa como máximo una imagen incrustada y el cuerpo HTML entero. Un
# logo de firma pesa unos pocos KB; el tope está para que un mail con fotos
# grandes no infle la base ni haga lenta la pantalla.
MAX_IMAGEN = 400_000
MAX_HTML = 800_000


def _texto_limpio(cuerpo: str) -> str:
    """Deja solo lo que la persona escribió esta vez."""
    texto = cuerpo.replace("\r\n", "\n")

    # 1. cortar en la primera marca de cita, mirando el texto completo
    corte = len(texto)
    for patron in CORTES:
        m = patron.search(texto)
        if m and m.start() < corte:
            corte = m.start()
    texto = texto[:corte]

    # 2. lo que quede empezando con ">" también es cita
    lineas = [l for l in texto.split("\n") if not l.lstrip().startswith(">")]

    # 3. Gmail escribe las imágenes del cuerpo así en la versión de texto plano
    texto = re.sub(r"\[image:[^\]]*\]", "", "\n".join(lineas))

    # 4. colapsar los renglones vacíos de más que deja el cliente de correo
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def _cuerpo(msg) -> str:
    """El texto del mail, prefiriendo text/plain y sin adjuntos."""
    if msg.is_multipart():
        for parte in msg.walk():
            if parte.get_content_type() == "text/plain" and "attachment" not in str(
                    parte.get("Content-Disposition", "")):
                try:
                    return parte.get_payload(decode=True).decode(
                        parte.get_content_charset() or "utf-8", errors="replace")
                except Exception:                    # noqa: BLE001
                    continue
        for parte in msg.walk():                     # si solo vino HTML, lo desnudamos
            if parte.get_content_type() == "text/html":
                try:
                    html = parte.get_payload(decode=True).decode(
                        parte.get_content_charset() or "utf-8", errors="replace")
                    return re.sub(r"<[^>]+>", " ", html)
                except Exception:                    # noqa: BLE001
                    continue
        return ""
    try:
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", errors="replace")
    except Exception:                                # noqa: BLE001
        return str(msg.get_payload())


def _html_con_imagenes(msg) -> str:
    """El cuerpo HTML del mail, con las imágenes incrustadas listas para mostrar.

    Las fotos que van dentro de un mail no viajan como URL sino como adjuntos
    referenciados por `cid:`. Si no se reemplazan por su contenido, el navegador
    muestra el cuadradito roto. Acá se convierten a data: URI, y así el cuerpo
    queda autocontenido: se puede guardar en la base y mostrar sin pedir nada.
    """
    html = ""
    incrustadas = {}

    for parte in msg.walk() if msg.is_multipart() else [msg]:
        tipo = parte.get_content_type()
        disp = str(parte.get("Content-Disposition", ""))

        if tipo == "text/html" and not html and "attachment" not in disp:
            try:
                html = parte.get_payload(decode=True).decode(
                    parte.get_content_charset() or "utf-8", errors="replace")
            except Exception:                    # noqa: BLE001
                pass

        cid = (parte.get("Content-ID") or "").strip().strip("<>")
        if cid and tipo.startswith("image/"):
            try:
                datos = parte.get_payload(decode=True)
                if datos and len(datos) <= MAX_IMAGEN:
                    incrustadas[cid] = (f"data:{tipo};base64,"
                                        + base64.b64encode(datos).decode())
            except Exception:                    # noqa: BLE001
                pass

    for cid, uri in incrustadas.items():
        html = html.replace(f"cid:{cid}", uri).replace(f"cid:%3C{cid}%3E", uri)

    # un cuerpo gigante no aporta nada y hace lenta la pantalla: se cae al texto
    return html if len(html) <= MAX_HTML else ""


def _titulo(bruto) -> str:
    if not bruto:
        return ""
    try:
        return str(make_header(decode_header(bruto))).strip()
    except Exception:                                # noqa: BLE001
        return str(bruto).strip()


def revisar(desde: datetime | None = None) -> list[dict]:
    """Trae los mails sin leer y los marca como leídos.

    `desde` descarta lo anterior a ese momento: se marca leído pero no se
    devuelve. Es lo que se usa en el primer barrido.
    """
    if not configurado():
        return []
    c = _cfg()
    nuevos = []
    try:
        con = imaplib.IMAP4_SSL(c["imap_host"], c["imap_puerto"], timeout=25)
        try:
            con.login(c["usuario"], c["clave"])
            con.select("INBOX")
            ok, datos = con.search(None, "UNSEEN")
            if ok != "OK":
                return []
            for num in datos[0].split():
                ok, cru = con.fetch(num, "(RFC822)")
                if ok != "OK" or not cru or not cru[0]:
                    continue
                msg = email.message_from_bytes(cru[0][1])
                if desde is not None:
                    try:
                        cuando = parsedate_to_datetime(msg.get("Date", ""))
                        if cuando and cuando.timestamp() < desde.timestamp():
                            _estado["descartados"] += 1
                            continue          # ya quedó marcado como leído por el fetch
                    except Exception:         # noqa: BLE001 — sin fecha legible, que pase
                        pass
                nombre, direccion = parseaddr(msg.get("From", ""))
                direccion = (direccion or "").lower().strip()
                # nunca comernos nuestros propios envíos: sería un bucle
                if not direccion or direccion == c["usuario"].lower():
                    continue
                texto = _texto_limpio(_cuerpo(msg))
                html = _html_con_imagenes(msg)
                if not texto and not html:
                    continue
                nuevos.append({
                    "remitente": direccion,
                    "nombre": _titulo(nombre),
                    "asunto": _titulo(msg.get("Subject", "")),
                    "texto": texto or "(el mail vino solo con formato)",
                    "html": html,
                })
            con.close()
        finally:
            try:
                con.logout()
            except Exception:                        # noqa: BLE001
                pass
        _estado["ultimo_error"] = ""
    except imaplib.IMAP4.error as e:
        _estado["ultimo_error"] = (
            f"IMAP rechazó la conexión ({e}). Revisá que la contraseña sea de "
            "aplicación y que IMAP esté habilitado en la casilla.")
    except Exception as e:                           # noqa: BLE001
        _estado["ultimo_error"] = f"{type(e).__name__}: {e}"

    _estado["ultima_revision"] = datetime.now().isoformat(timespec="seconds")
    _estado["recibidos"] += len(nuevos)
    return nuevos


# ------------------------------------------------------------------- vigilancia

def _bucle(entra):
    """Mira la bandeja cada tantos segundos y entrega lo que encuentra."""
    intervalo = _cfg()["intervalo"]

    # Primer barrido: limpia lo viejo sin meterlo al sistema. Ver MINUTOS_DE_GRACIA.
    corte = datetime.now() - timedelta(minutes=MINUTOS_DE_GRACIA)
    try:
        for mail in revisar(desde=corte):
            try:
                entra(mail)
            except Exception as e:                   # noqa: BLE001
                _estado["ultimo_error"] = f"al ingresar el mail: {e}"
        if _estado["descartados"]:
            print(f"[hilo] {_estado['descartados']} mails viejos marcados como leídos "
                  "y descartados (no eran conversaciones con clientes)")
    except Exception as e:                           # noqa: BLE001
        _estado["ultimo_error"] = f"en el primer barrido: {e}"

    while True:
        try:
            for mail in revisar():
                try:
                    entra(mail)
                except Exception as e:               # noqa: BLE001
                    _estado["ultimo_error"] = f"al ingresar el mail: {e}"
        except Exception as e:                       # noqa: BLE001
            _estado["ultimo_error"] = f"en la vigilancia: {e}"
        time.sleep(intervalo)


def vigilar(entra) -> bool:
    """Arranca el hilo que mira la casilla. `entra` recibe un dict por cada mail."""
    if not configurado() or _estado["vigilando"]:
        return False
    threading.Thread(target=_bucle, args=(entra,), daemon=True, name="correo").start()
    _estado["vigilando"] = True
    return True
