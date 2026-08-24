import json
import os
import secrets
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import select

from . import (ai, auth, cobros, correo, inquilino, mercadopago as mp,
               pipeline as pl, planes, root, secreto, simulador as sim,
               telegram as tg, uso, vinculos, whatsapp)
from .config import cargar as cargar_env

cargar_env()
from .db import crear_tablas, en_la_nube, sesion
from .logic import (CANALES, CANALES_CON_ASUNTO, CANALES_SALIENTES,
                    NIVELES_AUTONOMIA, es_cerrado, urgencia)
from .models import (Alias, Briefing, Business, Commitment, Credencial,
                     Identity, Message, Usuario)

app = FastAPI(title="Hilo")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def _arranque():
    crear_tablas()
    # Decir "falta X en el .env" cuando corre en la nube manda a la persona a
    # mirar un archivo que ahi no existe. En la nube las variables viven en el
    # panel. Un aviso que apunta al lugar equivocado cuesta mas que no avisar.
    DONDE = "en las variables del panel" if en_la_nube() else "en el .env"
    # En un hosting la base arranca vacía. Con HILO_SEMBRAR=1 se carga la demo
    # una sola vez; si ya hay clientes, no toca nada.
    #
    # OJO con el orden: sembrar() hace DROP TABLE, y en Postgres eso necesita un
    # lock exclusivo. Si la sesión que pregunta "¿está vacía?" sigue abierta, su
    # transacción retiene el lock compartido y el DROP espera para siempre: el
    # arranque se cuelga y el hosting nunca ve el puerto abierto. Por eso la
    # consulta se cierra ANTES de sembrar.
    if os.environ.get("HILO_SEMBRAR") == "1":
        try:
            with sesion() as s:
                vacia = s.exec(select(Alias)).first() is None
            if vacia:
                from seed import sembrar
                # El `with` no es decorativo: sembrar() deja fijado el inquilino
                # que acaba de crear, y sin esto ese valor quedaría pegado al
                # contexto del server. ¿Consecuencia? El onboarding —que va sin
                # sesión y decide por `inquilino.actual()`— creería que ya hay un
                # negocio elegido y le pisaría la configuración al del arranque.
                # Al salir del `with`, el ContextVar vuelve a como estaba.
                with inquilino.usar(None):
                    sembrar()
                print("[hilo] base vacía: cargué los datos de demo")
        except Exception as e:
            # que no se caiga el arranque: sin datos la app igual levanta
            print(f"[hilo] no pude sembrar ({e})")

    # El correo es el primer canal real de Hilo. Si hay casilla configurada,
    # queda un hilo mirando la bandeja: cada mail que llega entra por la misma
    # puerta que todo lo demás, pl.ingesta(). Sin configurar, esto no hace nada
    # y el mail sigue siendo simulado como hasta ahora.
    if correo.vigilar(_entro_un_mail):
        print(f"[hilo] mirando la casilla {correo.estado()['casilla']}")

    # WhatsApp no tiene vigía: entra por webhook, no hay a quién mirar. Pero
    # conviene decirlo en el arranque igual, porque si no la única forma de saber
    # si tomó el .env es mandar un mensaje y ver que no pasa nada.
    wa = whatsapp.estado()
    if wa["configurado"]:
        print(f"[hilo] whatsapp listo desde {wa['numero'] or wa['phone_id']}"
              f" (Graph {wa['version']})")
        # El token temporal de Meta dura 24 h y cuando vence NO avisa: los mensajes
        # dejan de salir y uno se entera en la demo. Preguntar cuesta una llamada
        # por arranque; el silencio cuesta una demo. En un hilo aparte para que un
        # Meta lento no demore el arranque del server.
        def _mirar_el_token():
            vivo, detalle = whatsapp.probar_token()
            print(f"[hilo] whatsapp: el token ANDA ({detalle})" if vivo else
                  f"[hilo] OJO: el token de WhatsApp no sirve -> {detalle}\n"
                  f"[hilo]      generá uno permanente en Meta Business ->"
                  f" Usuarios del sistema, y ponelo en WA_TOKEN")
        threading.Thread(target=_mirar_el_token, daemon=True).start()
        if not wa["firma_verificable"]:
            print("[hilo] OJO: sin WA_APP_SECRET el webhook le cree a cualquiera")
        if not wa["webhook_verificable"]:
            print("[hilo] OJO: sin WA_VERIFY_TOKEN no vas a poder registrar el webhook")
    else:
        print(f"[hilo] whatsapp dormido: faltan WA_TOKEN o WA_PHONE_ID {DONDE}")

    # Telegram: hay que DECIRLE a dónde mandar los mensajes. Sin esto, con el
    # token puesto y todo, no llega nada y no hay ningún error que lo explique.
    # Se hace en cada arranque a propósito: es idempotente y así la URL siempre
    # apunta a donde está corriendo la app ahora.
    if tg.configurado():
        publica = (os.environ.get("HILO_URL") or "").strip()
        if publica:
            def _enganchar_telegram():
                salio, detalle = tg.registrar_webhook(publica)
                print(f"[hilo] telegram: webhook en {detalle}" if salio else
                      f"[hilo] OJO: no pude registrar el webhook de Telegram -> {detalle}")
            threading.Thread(target=_enganchar_telegram, daemon=True).start()
        else:
            print(f"[hilo] telegram: falta HILO_URL {DONDE}, así que no registro "
                  "el webhook. En local levantá el túnel y poné esa URL ahí.")
    else:
        print(f"[hilo] telegram dormido: falta TG_TOKEN {DONDE}")


def _negocio_de(canal: str, externo_id: str = ""):
    """A qué negocio le corresponde un mensaje que llega de afuera.

    Un webhook no trae sesión: nadie nos dice de quién es. Lo dice el número (o la
    casilla) por el que entró, que está en la tabla `credencial`.

    Mientras las credenciales sigan en el `.env` —o sea, mientras haya un solo
    negocio— cae al primero. Es exactamente el comportamiento de antes, así que
    nada se rompe al actualizar; el día que un cliente conecte su WhatsApp por
    Embedded Signup, su credencial existe y esto lo encuentra solo.
    """
    with sesion() as s, inquilino.sin_filtro():
        if externo_id:
            c = s.exec(select(Credencial).where(
                Credencial.canal == canal,
                Credencial.externo_id == externo_id,
                Credencial.activo == True)).first()          # noqa: E712
            if c and c.business_id:
                return c.business_id
        b = s.exec(select(Business).order_by(Business.id)).first()
        return b.id if b else None


def _entro_un_mail(mail: dict):
    """Un mail de verdad, tratado igual que cualquier otro mensaje.

    Ojo: esto lo llama el hilo que vigila la casilla, que no es un request. Sin
    ponerle el inquilino a mano, la ingesta correría sin filtro y el mensaje
    quedaría sin dueño — invisible para todos.
    """
    negocio_id = _negocio_de("mail", (correo.estado().get("casilla") or ""))
    with inquilino.usar(negocio_id), sesion() as s:
        r = pl.ingesta(s, "mail", mail["remitente"], mail["texto"],
                       html=mail.get("html", ""), asunto=mail.get("asunto", ""))
    quien = mail["remitente"]
    print(f"[hilo] mail de {quien}: "
          + ("entró al hilo" if r.get("identificado") else "sin identificar"))


def _entro_un_whatsapp(m: dict):
    """Un WhatsApp de verdad, tratado igual que cualquier otro mensaje.

    El webhook va abierto y no trae sesión: el negocio lo dice el número nuestro
    por el que entró (`phone_id`), no el que escribe.
    """
    negocio_id = _negocio_de("whatsapp", m.get("phone_id", ""))
    with inquilino.usar(negocio_id), sesion() as s:
        r = pl.ingesta(s, "whatsapp", m["remitente"], m["texto"],
                       externo_id=m.get("wamid", ""),
                       remitente_nombre=m.get("nombre", ""))
    if r.get("duplicado"):
        return                                  # Meta reintentó, ya lo teníamos
    quien = m.get("nombre") or m["remitente"]
    print(f"[hilo] whatsapp de {quien}: "
          + ("entró al hilo" if r.get("identificado") else "sin identificar"))


# --------------------------------------------------------------------- login
# La API queda protegida SOLO cuando existe al menos un usuario. Mientras no haya
# ninguno la app funciona abierta y te pide crear la primera cuenta: nadie se
# queda afuera de su propia app por un problema de configuración.

# El onboarding va abierto porque es lo PRIMERO que hace alguien que llega:
# contás qué vendés, ves tu Hilo armado y recién después ponés una contraseña.
# Las rutas que NO piden cuenta. Van una por una, no por prefijo.
#
# Antes acá decía "/api/auth/" a secas, y eso abría TODO lo que colgara de ahí —
# incluidos `GET /api/auth/usuarios`, que listaba los mails de todas las cuentas
# sin pedir nada, y `POST /api/auth/usuarios`, que dejaba a cualquiera crearse un
# usuario con el rol que quisiera y entrar. El docstring de ese endpoint decía
# "pasa por la puerta, así que ya está logueado"; no era cierto.
#
# Regla para adelante: abrir rutas exactas, nunca un prefijo. Un prefijo abre
# también lo que alguien agregue mañana debajo.
ABIERTAS = (
    "/api/auth/estado",        # ¿hace falta crear la primera cuenta?
    "/api/auth/registro",      # darse de alta
    "/api/auth/login",
    "/api/auth/yo",            # valida el token por su cuenta
    "/api/cliente/",           # la vista pública: el token ES la credencial
    "/api/onboarding/",        # lo primero que hace alguien que llega
    "/api/whatsapp/webhook",   # Meta le pega sin credenciales; lo protege la firma
    "/api/pagos/webhook",      # Mercado Pago tampoco trae sesión; ver el endpoint
    "/api/telegram/webhook",   # Telegram tampoco; lo protege el secret token
)

# Las únicas rutas que sigue viendo una cuenta CORTADA por falta de pago. Son las
# justas para poder pagar y para que la app dibuje su marco: si al que le cortaron
# no le queda ni la pantalla donde poner la tarjeta, no hay forma de que vuelva.
SIN_PAGAR = (
    "/api/plan",
    "/api/plan/suscribir",
    "/api/plan/cancelar",
    "/api/negocio",
)


def _puede_sin_pagar(ruta: str) -> bool:
    """Rutas exactas, salvo lo que cuelga de `/api/pagos/`.

    La regla de la casa es no abrir por prefijo, y sigue valiendo para `ABIERTAS`,
    que saltea la sesión entera. Acá el prefijo es otra cosa: esto corre DESPUÉS
    de identificar al usuario y solo decide si le cobramos o no la entrada. Todo
    lo que cuelgue de `/api/pagos/` es, por definición, para poder pagar.
    """
    # `/api/root` tampoco paga peaje: el back-office no es parte del producto que
    # el cliente compra, así que a un usuario común le tiene que contestar «esto
    # no es para vos» (403) y no «pagá» (402), que sería una respuesta rarísima.
    # Quién entra ahí lo decide `es_root`, en `root.py`.
    return (ruta in SIN_PAGAR or ruta.startswith("/api/pagos/")
            or ruta.startswith("/api/root"))


# El header con el que una cuenta root mira la app como si fuera un cliente.
# No da permiso —lo da `es_root`— sino que dice a cuál. Para cualquier otro
# usuario se ignora, y por eso mandarlo a mano no sirve de nada.
VER_COMO = "x-hilo-negocio"


@app.middleware("http")
async def puerta(request: Request, call_next):
    ruta = request.url.path
    if not ruta.startswith("/api/") or ruta.startswith(ABIERTAS) or request.method == "OPTIONS":
        return await call_next(request)
    request.state.uid = None
    request.state.es_root = False
    with sesion() as s:
        if not auth.auth_encendida(s):
            # Instalación sin dueño: la app entera está abierta a propósito
            # (`AvisoSinCuenta` lo grita en pantalla). Si TODO está abierto, el
            # back-office también: esconderlo acá sería teatro, no seguridad.
            request.state.es_root = True
            return await call_next(request)
        cabecera = request.headers.get("authorization", "")
        token = cabecera[7:] if cabecera.lower().startswith("bearer ") else ""
        uid = auth.leer_token(token) if token else None
        usuario = s.get(Usuario, uid) if uid else None
        if not usuario or not usuario.activo:
            return JSONResponse({"detail": "Necesitás entrar con tu cuenta"}, status_code=401)
        request.state.uid = usuario.id
        request.state.es_root = bool(usuario.es_root)
        negocio_id = usuario.business_id

        # "Ver como": el back-office pide una cuenta ajena y la ve entera, con las
        # pantallas de verdad y sin pedirle una captura a nadie. Solo root.
        pedida = request.headers.get(VER_COMO, "").strip()
        if pedida and usuario.es_root:
            try:
                negocio_id = int(pedida)
            except ValueError:
                pass

        # Última visita. Se escribe como mucho una vez cada diez minutos: una
        # escritura por request es, en SQLite y con el vigía del correo al lado,
        # la receta exacta del "database is locked".
        ahora = datetime.now()
        if not usuario.ultimo_acceso or (ahora - usuario.ultimo_acceso).total_seconds() > 600:
            usuario.ultimo_acceso = ahora
            s.add(usuario)
            s.commit()

        if negocio_id is None:
            # Una cuenta sin negocio no puede ver NADA. Es el caso de un usuario
            # que quedó de una versión anterior: mejor un error claro que dejarlo
            # entrar a una app donde el filtro no aplica y ve todo. La excepción
            # es el back-office, que justamente no mira ningún negocio en
            # particular.
            if not (usuario.es_root and ruta.startswith("/api/root")):
                return JSONResponse(
                    {"detail": "Tu cuenta no está asociada a ningún negocio. Escribinos."},
                    status_code=409)
        else:
            b = s.get(Business, negocio_id)
            # Cuenta suspendida: no se corta el servicio por cuota (eso se avisa),
            # se corta cuando NOSOTROS la suspendimos. Los datos quedan intactos.
            if b and b.estado == "suspendida" and not usuario.es_root:
                return JSONResponse(
                    {"detail": "Tu cuenta está suspendida. Escribinos y la reactivamos."},
                    status_code=403)
            # Y el corte por falta de pago, que NO lo decide nadie: se deduce de
            # la fecha (`cobros.estado`). Un cron que no corrió no puede regalar
            # meses, y nadie tiene que acordarse de apagar una cuenta.
            #
            # 402 y no 403: el front lo distingue y manda a poner la tarjeta en
            # vez de mostrar "no tenés permiso", que sería mentira.
            if (b and not usuario.es_root and not _puede_sin_pagar(ruta)
                    and not cobros.puede_entrar(b)):
                e = cobros.estado(b)
                return JSONResponse(
                    {"detail": ("Se terminó tu prueba de Hilo. Poné una tarjeta y seguís."
                                if e.get("por_que") == "se acabó la prueba" else
                                "No pudimos cobrarte. Actualizá la tarjeta y vuelve todo."),
                     "cortada": True, "estado": e},
                    status_code=402)

    # ACÁ se decide qué ve este request. De este `with` para adentro, todas las
    # consultas de los modelos del inquilino salen filtradas solas: no hay que
    # acordarse en cada endpoint, que es exactamente la clase de olvido que
    # termina mostrándole los clientes de uno a otro.
    with inquilino.usar(negocio_id):
        return await call_next(request)


# El back-office vive en `app/root.py` y se monta acá. Va DESPUÉS del middleware
# a propósito: sus endpoints necesitan que la puerta ya haya resuelto quién es
# quién (`request.state.es_root`).
app.include_router(root.router)


@app.get("/api/auth/estado")
def auth_estado():
    with sesion() as s:
        return {"hay_usuarios": auth.hay_usuarios(s), "protegida": auth.auth_encendida(s)}


class RegistroIn(BaseModel):
    email: str
    password: str
    nombre: str = ""
    negocio_id: int | None = None     # el que devolvió el onboarding, si vino de ahí


@app.post("/api/auth/registro")
def auth_registro(body: RegistroIn):
    """Crea una cuenta. Cualquiera puede darse de alta."""
    if "@" not in body.email or "." not in body.email.split("@")[-1]:
        raise HTTPException(400, "Ese mail no parece un mail")
    problema = auth.problema_con_la_contrasena(body.password)
    if problema:
        raise HTTPException(400, problema)
    with sesion() as s:
        if auth.buscar_por_email(s, body.email):
            raise HTTPException(400, "Ya hay una cuenta con ese mail. Entrá con ella.")

        # Cada cuenta nueva estrena su propio negocio. Si viene del onboarding
        # (`negocio_id`) se adopta el que quedó armado, pero SOLO si todavía no
        # tiene dueño: si no, cualquiera que mandara el id de otro se metería
        # adentro de su cuenta.
        b = s.get(Business, body.negocio_id) if body.negocio_id else None
        if b and s.exec(select(Usuario).where(Usuario.business_id == b.id)).first():
            b = None
        if not b:
            b = Business(nombre=(body.nombre.strip() or body.email.split("@")[0]))
            s.add(b)
        # La prueba arranca acá y no en el onboarding: la cuenta es el momento en
        # que alguien decide entrar, y es la fecha que después le vamos a decir.
        # Vale también para el negocio que viene del onboarding, que hasta ahora
        # no tenía dueño ni reloj corriendo.
        cobros.empezar_la_prueba(b)
        s.add(b)
        s.commit()
        s.refresh(b)

        u = auth.crear_usuario(s, body.email, body.password, body.nombre, business_id=b.id)
        return {"token": auth.emitir_token(u.id), "usuario": auth.publico(u)}


class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def auth_login(body: LoginIn):
    with sesion() as s:
        u = auth.buscar_por_email(s, body.email)
        # el mismo mensaje para mail inexistente y contraseña mala: no regalamos pistas
        if not u or not u.activo or not auth.verificar(body.password, u.hash):
            raise HTTPException(401, "Mail o contraseña incorrectos")
        u.ultimo_acceso = datetime.now()
        s.add(u)
        s.commit()
        return {"token": auth.emitir_token(u.id), "usuario": auth.publico(u)}


@app.get("/api/auth/yo")
def auth_yo(request: Request):
    cabecera = request.headers.get("authorization", "")
    token = cabecera[7:] if cabecera.lower().startswith("bearer ") else ""
    uid = auth.leer_token(token) if token else None
    with sesion() as s:
        u = s.get(Usuario, uid) if uid else None
        if not u or not u.activo:
            raise HTTPException(401, "Sesión vencida o inexistente")
        return auth.publico(u)


class InvitarIn(BaseModel):
    email: str
    password: str
    nombre: str = ""
    rol: str = "vendedor"


@app.post("/api/auth/usuarios")
def auth_invitar(body: InvitarIn):
    """Sumar a alguien más al equipo. Pasa por la puerta, así que ya está logueado."""
    problema = auth.problema_con_la_contrasena(body.password)
    if problema:
        raise HTTPException(400, problema)
    with sesion() as s:
        if auth.buscar_por_email(s, body.email):
            raise HTTPException(400, "Ya hay una cuenta con ese mail")
        u = auth.crear_usuario(s, body.email, body.password, body.nombre, body.rol,
                               business_id=inquilino.actual())
        return auth.publico(u)


@app.get("/api/auth/usuarios")
def auth_listar():
    """El equipo de ESTE negocio. `Usuario` no se filtra solo (el login lo busca
    por mail antes de saber el negocio), así que acá el filtro va a mano."""
    with sesion() as s:
        q = select(Usuario)
        if inquilino.actual() is not None:
            q = q.where(Usuario.business_id == inquilino.actual())
        return [auth.publico(u) for u in s.exec(q)]


# ------------------------------------------------------------------ serializar

def _brief(s, alias_id: int) -> dict:
    fila = s.exec(select(Briefing).where(Briefing.alias_id == alias_id)).first()
    return json.loads(fila.data_json) if fila else {}


def _compromisos(s, alias_id: int) -> list:
    out = []
    for c in s.exec(select(Commitment).where(Commitment.alias_id == alias_id).order_by(Commitment.vence)):
        vencido = bool(c.vence and c.vence < datetime.now() and not c.cumplido)
        tarde = int((datetime.now() - c.vence).total_seconds() // 86400) if vencido else 0
        out.append({"id": c.id, "de_quien": c.de_quien, "texto": c.texto,
                    "vence": c.vence.isoformat() if c.vence else None,
                    "cumplido": c.cumplido, "vencido": vencido, "dias_tarde": tarde})
    return out


def _mensaje(m: Message) -> dict:
    return {"id": m.id, "canal": m.canal, "canal_label": CANALES.get(m.canal, m.canal),
            "direccion": m.direccion, "autor": m.autor, "texto": m.texto,
            "asunto": m.asunto, "html": m.html, "cc": m.cc, "cco": m.cco,
            "adjuntos": json.loads(m.adjuntos_json or "[]"), "simulado": m.simulado,
            "resumen": m.resumen,
            "aprobado_por": m.aprobado_por, "creado": m.creado.isoformat()}


# ------------------------------------------------------------------- endpoints

@app.get("/api/negocio")
def get_negocio():
    with sesion() as s:
        b = pl.negocio(s)
        return {"nombre": b.nombre, "descripcion": b.descripcion,
                "estados": pl.etapas(b), "reglas": pl.reglas(b),
                "rubro": b.rubro, "vendedor": b.vendedor,
                "canales": json.loads(b.canales_json or "[]"),
                "autonomia_default": b.autonomia_default,
                "onboarding_hecho": b.onboarding_hecho,
                "ia": ai.como_esta(),
                "niveles": [{"n": i, "nombre": n, "detalle": d}
                            for i, (n, d) in enumerate(NIVELES_AUTONOMIA)],
                "ia_activa": not ai.offline(),
                # Su plan y cuánto lleva usado. Va acá porque `/api/negocio` ya
                # lo pide toda la app: un endpoint nuevo sería otra llamada por
                # pantalla para mostrar una línea.
                #
                # Y avisa, no corta. Pasarse del límite no le apaga nada a nadie:
                # es la señal de que está listo para el plan que sigue.
                "plan": {"clave": b.plan or "prueba",
                         "nombre": planes.plan(b.plan)["nombre"],
                         **cobros.cuota(s, b)},
                # El estado de la plata viaja acá para que la barra pueda avisar
                # («te quedan 2 días de prueba») sin una llamada más por pantalla.
                "pago": cobros.estado(b)}


class NegocioIn(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    rubro: str | None = None
    vendedor: str | None = None
    canales: list[dict] | None = None
    estados: list[str] | None = None
    reglas: dict | None = None
    autonomia_default: int | None = None


@app.post("/api/negocio")
def set_negocio(body: NegocioIn):
    with sesion() as s:
        b = pl.negocio(s)
        if body.nombre is not None:
            b.nombre = body.nombre
        if body.descripcion is not None:
            b.descripcion = body.descripcion
        if body.rubro is not None:
            b.rubro = body.rubro
        if body.vendedor is not None:
            b.vendedor = body.vendedor
        if body.canales is not None:
            b.canales_json = json.dumps(body.canales, ensure_ascii=False)
        if body.estados is not None:
            b.estados_json = json.dumps(body.estados, ensure_ascii=False)
        if body.reglas is not None:
            b.reglas_json = json.dumps(body.reglas, ensure_ascii=False)
        if body.autonomia_default is not None:
            b.autonomia_default = body.autonomia_default
        s.add(b)
        s.commit()
    return get_negocio()


class DescripcionIn(BaseModel):
    descripcion: str


@app.post("/api/negocio/sugerir-estados")
def sugerir_estados(body: DescripcionIn):
    r = ai.sugerir_estados(body.descripcion)
    if not r.get("estados"):
        r = {"estados": ["Nuevo", "Calificado", "Reunion hecha", "Propuesta enviada",
                         "Negociacion", "Cerrado ganado", "Perdido"],
             "por_que": "Flujo generico: la IA no estaba disponible, editalo a mano."}
    return r


# --------------------------------------------------------------- onboarding
# El onboarding es lo que convierte a Hilo en "la app de ESTE negocio". Son cuatro
# pasos, y el unico que cuesta trabajo es el primero: contar que vendes. Del resto
# se encarga la IA y el dueño solo corrige.

class ProponerIn(BaseModel):
    descripcion: str


CONFIG_GENERICA = {
    "rubro": "",
    "estados": ["Nuevo", "Calificado", "Reunión hecha", "Propuesta enviada",
                "Negociación", "Cerrado ganado", "Perdido"],
    "estados_cerrados": ["Cerrado ganado", "Perdido"],
    "reglas": {
        "tono": "Cercano y directo, de vos. Sin fórmulas de cortesía largas.",
        "horario": [9, 19], "insistir_cada_dias": 3, "max_insistencias": 3,
        "descuento_max": 0, "temas_escalan": ["contrato", "legal", "reclamo"],
    },
    "canales": ["mail", "whatsapp"],
    "por_que": "Configuración genérica: la IA no estaba disponible. Editá lo que no te cierre.",
}


@app.post("/api/onboarding/proponer")
def onboarding_proponer(body: ProponerIn):
    """De dos oraciones sobre el negocio a toda la configuración propuesta."""
    r = ai.configurar_negocio(body.descripcion)
    if not r.get("estados"):
        return {**CONFIG_GENERICA, "sin_ia": True}
    r.setdefault("estados_cerrados", r["estados"][-2:])
    base = dict(CONFIG_GENERICA["reglas"])
    base.update(r.get("reglas") or {})
    r["reglas"] = base
    r.setdefault("canales", ["mail", "whatsapp"])
    return r


class OnboardingIn(BaseModel):
    nombre: str
    descripcion: str = ""
    rubro: str = ""
    vendedor: str = ""
    estados: list[str]
    reglas: dict = {}
    canales: list[dict] = []
    autonomia_default: int = 3


@app.post("/api/onboarding/guardar")
def onboarding_guardar(body: OnboardingIn):
    if not body.nombre.strip():
        raise HTTPException(400, "El negocio necesita un nombre")
    if len(body.estados) < 2:
        raise HTTPException(400, "Hacen falta al menos dos etapas")
    with sesion() as s:
        if inquilino.actual() is None:
            # Sin sesión: alguien que llega por primera vez.
            #
            # Antes esto hacía pl.negocio(s), que traía el ÚNICO negocio que había
            # y le pisaba la configuración. Con varias cuentas eso sería
            # reconfigurarle el negocio a un cliente que está laburando.
            #
            # Se adopta un negocio SIN dueño y con el onboarding sin terminar —el
            # de una instalación recién sembrada, o el de `empezar_de_cero.py`— y
            # si no hay ninguno así, se crea uno nuevo. Las dos condiciones
            # importan: sin la de "sin dueño" te metés en la cuenta de alguien, y
            # sin la de "sin terminar" el segundo visitante le pisa la
            # configuración al primero que todavía no se registró.
            b = None
            for candidato in s.exec(select(Business).where(
                    Business.onboarding_hecho == False).order_by(Business.id)):   # noqa: E712
                if not s.exec(select(Usuario).where(
                        Usuario.business_id == candidato.id)).first():
                    b = candidato
                    break
            if b is None:
                b = Business()
                s.add(b)
                s.commit()
                s.refresh(b)
        else:
            b = pl.negocio(s)
        b.nombre = body.nombre.strip()
        b.descripcion = body.descripcion
        b.rubro = body.rubro
        b.vendedor = body.vendedor
        b.estados_json = json.dumps(body.estados, ensure_ascii=False)
        b.reglas_json = json.dumps(body.reglas, ensure_ascii=False)
        b.canales_json = json.dumps(body.canales, ensure_ascii=False)
        b.autonomia_default = body.autonomia_default
        b.onboarding_hecho = True
        s.add(b)
        s.commit()
        negocio_id = b.id
    # El front tiene que guardarse este id y mandarlo en /api/auth/registro:
    # es lo que ata la configuración recién hecha con la cuenta que se va a crear.
    with inquilino.usar(negocio_id):
        return {**get_negocio(), "negocio_id": negocio_id}


@app.post("/api/onboarding/reabrir")
def onboarding_reabrir():
    """Para volver a pasar por las preguntas sin perder los clientes."""
    with sesion() as s:
        b = pl.negocio(s)
        b.onboarding_hecho = False
        s.add(b)
        s.commit()
    return {"ok": True}


# ------------------------------------------------------------------- correo


@app.get("/api/correo/estado")
def correo_estado():
    """Para mirar desde Configuración si el mail está andando de verdad."""
    return correo.estado()


@app.post("/api/correo/revisar")
def correo_revisar():
    """Mira la bandeja ahora mismo, sin esperar al próximo turno del vigía.

    En una demo en vivo no se puede quedar esperando diez segundos mirando la
    pantalla: con esto el mail entra cuando uno lo pide.
    """
    if not correo.configurado():
        raise HTTPException(400, "El correo no está configurado")
    entraron = 0
    for mail in correo.revisar():
        _entro_un_mail(mail)
        entraron += 1
    return {"entraron": entraron, "estado": correo.estado()}


# ----------------------------------------------------------------- whatsapp


@app.get("/api/whatsapp/webhook")
async def whatsapp_verificar(request: Request):
    """El apretón de manos que hace Meta al registrar el webhook.

    Devuelve el challenge EN TEXTO PLANO. Si sale envuelto en JSON —que es lo que
    hace FastAPI si devolvés un string a secas— Meta lo rechaza y el webhook nunca
    queda registrado. Es el error clásico y cuesta una tarde encontrarlo.
    """
    p = request.query_params
    challenge = whatsapp.verificar(
        p.get("hub.mode", ""), p.get("hub.verify_token", ""), p.get("hub.challenge", ""))
    if challenge is None:
        raise HTTPException(403, "Token de verificación incorrecto")
    return PlainTextResponse(challenge)


@app.post("/api/whatsapp/webhook")
async def whatsapp_entrante(request: Request):
    """Cada mensaje que llega. Entra por pl.ingesta(), como todo lo demás."""
    crudo = await request.body()
    if not whatsapp.firma_valida(crudo, request.headers.get("x-hub-signature-256", "")):
        whatsapp._estado["firmas_rechazadas"] += 1
        raise HTTPException(403, "Firma inválida")
    try:
        payload = json.loads(crudo.decode("utf-8") or "{}")
    except ValueError:
        payload = {}

    entraron = 0
    for m in whatsapp.procesar(payload):
        try:
            _entro_un_whatsapp(m)
            entraron += 1
        except Exception as e:                           # noqa: BLE001
            # A propósito no se propaga. Si esto devuelve un 500, Meta reintenta,
            # y si insiste sin éxito TE DA DE BAJA EL WEBHOOK: dejás de recibir
            # mensajes de verdad y te enterás tarde. El error queda registrado y
            # se ve en Configuración, que es donde hay que mirarlo.
            whatsapp._estado["ultimo_error"] = f"No pude ingerir un mensaje: {e}"
            print(f"[hilo] whatsapp: no pude ingerir un mensaje: {e}")
            # …y también en el back-office, con nombre de cuenta. Un error que
            # solo vive en la consola de Render es un error que nadie ve.
            uso.anotar_falla("whatsapp", f"No pude ingerir un mensaje: {e}",
                             _negocio_de("whatsapp", m.get("phone_id", "")))
    return {"ok": True, "entraron": entraron}


@app.get("/api/whatsapp/estado")
def whatsapp_estado():
    """Para mirar desde Configuración si WhatsApp está andando de verdad.

    Si este negocio conectó su propio número por Embedded Signup, manda ese. Si no,
    lo que haya en el `.env`, que es la instalación de un solo negocio.
    """
    e = whatsapp.estado()
    with sesion() as s:
        cred = s.exec(select(Credencial).where(
            Credencial.canal == "whatsapp",
            Credencial.activo == True)).first()                    # noqa: E712
    e["propio"] = bool(cred)
    if cred:
        e.update({"configurado": True, "numero": cred.etiqueta,
                  "phone_id": cred.externo_id,
                  "conectado_el": cred.creado.isoformat(),
                  "ultimo_error": cred.ultimo_error or e.get("ultimo_error", "")})
    return e


class ConectarWA(BaseModel):
    code: str
    waba_id: str
    phone_number_id: str


@app.post("/api/whatsapp/conectar")
def whatsapp_conectar(body: ConectarWA):
    """El final del Embedded Signup: el cliente apretó el botón y volvió con esto.

    Pasa por la puerta, así que el negocio sale de la sesión y la credencial queda
    guardada para ESE inquilino y para ninguno más. El código dura 30 segundos, así
    que esto se llama enseguida y el código no se guarda en ningún lado.
    """
    if inquilino.actual() is None:
        raise HTTPException(409, "Tu cuenta no está asociada a ningún negocio")
    if not (body.code and body.waba_id and body.phone_number_id):
        raise HTTPException(400, "Faltan datos del alta de WhatsApp")

    salio, r = whatsapp.conectar_cliente(body.code, body.waba_id, body.phone_number_id)
    if not salio:
        raise HTTPException(400, str(r))

    with sesion() as s:
        # Reconectar pisa la credencial anterior en vez de dejar dos: si quedan dos
        # activas, cuál gana depende del orden de la base, que es exactamente el
        # tipo de cosa que después nadie entiende.
        cred = s.exec(select(Credencial).where(Credencial.canal == "whatsapp")).first()
        if not cred:
            cred = Credencial(canal="whatsapp")
        cred.externo_id = r["phone_id"]
        cred.etiqueta = r["numero"] or r["phone_id"]
        cred.datos_json = secreto.cifrar(json.dumps(
            {"token": r["token"], "waba_id": r["waba_id"], "pin": r["pin"]},
            ensure_ascii=False))
        cred.activo = True
        cred.ultimo_error = r.get("aviso_registro", "")
        cred.ultimo_ok = datetime.now()
        s.add(cred)
        s.commit()

    return {"conectado": True, "numero": r["numero"],
            "nombre_visible": r["nombre_visible"], "calidad": r["calidad"],
            "aviso": r.get("aviso_registro", "")}


@app.post("/api/whatsapp/desconectar")
def whatsapp_desconectar():
    """Suelta el número de este negocio. No borra el hilo ni los mensajes."""
    with sesion() as s:
        cred = s.exec(select(Credencial).where(Credencial.canal == "whatsapp")).first()
        if not cred:
            raise HTTPException(404, "Este negocio no tiene WhatsApp conectado")
        s.delete(cred)
        s.commit()
    return {"conectado": False}


class ProbarWA(BaseModel):
    numero: str
    texto: str = "Probando Hilo. Si te llegó esto, el canal está andando."


@app.post("/api/whatsapp/probar")
def whatsapp_probar(body: ProbarWA):
    """Manda un mensaje suelto, sin pasar por ninguna ficha.

    Sirve para saber si el problema es la configuración o el hilo del cliente.
    Ojo: si la app está en modo desarrollo, el número tiene que estar en la lista
    de destinatarios permitidos de Meta.
    """
    if not whatsapp.configurado():
        raise HTTPException(400, "WhatsApp no está configurado")
    salio, error = whatsapp.enviar(body.numero, body.texto)
    if not salio:
        raise HTTPException(400, error or "No pude enviarlo")
    return {"enviado": True, "estado": whatsapp.estado()}


# ------------------------------------------------------------------- el plan
# Dónde se le pide la tarjeta al cliente. Tres endpoints y un webhook: mirar el
# plan, suscribirse, cancelar, y enterarse de cada cobro.


def _url_publica(request: Request) -> str:
    """A dónde vuelve el cliente después de pagar en Mercado Pago.

    Tres fuentes, en orden de cuánto saben:

      1. `HILO_URL` del `.env` — en la nube el server no sabe por qué dominio lo
         llamaron, así que se lo decimos.
      2. El `Origin` del pedido: es la dirección donde el usuario tiene la app
         abierta de verdad. En desarrollo eso es `:5173` (Vite) y NO `:8000`,
         que es donde corre este proceso.
      3. La request, como último recurso.

    El orden importa: mandarlo al puerto del backend es mandarlo a otro origen,
    donde su sesión no existe y la app lo recibe como si no hubiera entrado nunca.
    """
    fijada = (os.environ.get("HILO_URL") or "").strip()
    if fijada:
        return fijada.rstrip("/") + "/"
    origen = (request.headers.get("origin") or "").strip()
    if origen.startswith("http"):
        return origen.rstrip("/") + "/"
    return str(request.base_url)


def _mi_negocio(s) -> Business:
    b = s.get(Business, inquilino.actual()) if inquilino.actual() else None
    if not b:
        raise HTTPException(409, "Tu cuenta no está asociada a ningún negocio")
    return b


@app.get("/api/plan")
def mi_plan(request: Request):
    """Todo lo que el cliente necesita saber sobre su plan y su plata.

    Esta ruta sigue viva aunque la cuenta esté cortada: si al que le cortaste no
    le queda ni la pantalla donde poner la tarjeta, no hay forma de que vuelva.
    """
    with sesion() as s:
        b = _mi_negocio(s)
        return {
            "pago": cobros.estado(b),
            "cuota": cobros.cuota(s, b),
            "planes": planes.catalogo(),
            "cobros": cobros.historial(s, b.id, 12),
            "mercadopago": {"simulado": mp.simulado(), "de_prueba": mp.es_de_prueba()},
            "dias_de_prueba": cobros.DIAS_DE_PRUEBA,
        }


class SuscribirIn(BaseModel):
    plan: str = "basico"


@app.post("/api/plan/suscribir")
def suscribirse(body: SuscribirIn, request: Request):
    """Devuelve a dónde mandar al cliente a poner la tarjeta.

    La tarjeta la toma Mercado Pago, en su checkout. Nosotros no la vemos, no la
    guardamos y no la queremos: guardar tarjetas es un problema de cumplimiento
    que no le toca a una app de dos personas.
    """
    if body.plan not in planes.PLANES or body.plan == "prueba":
        raise HTTPException(400, "Elegí un plan de verdad")
    precio = planes.precio_sugerido(body.plan)
    with sesion() as s:
        b = _mi_negocio(s)
        if b.precio_mensual:
            precio = b.precio_mensual          # el precio negociado le gana al del catálogo
        u = s.exec(select(Usuario).where(Usuario.business_id == b.id)).first()
        salio, r = mp.crear_suscripcion(b.id, planes.plan(body.plan)["nombre"], precio,
                                        u.email if u else "sin-mail@hilo.app",
                                        _url_publica(request))
        if not salio:
            uso.anotar_falla("pagos", f"No pude crear la suscripción: {r.get('error')}")
            raise HTTPException(400, f"Mercado Pago no aceptó la suscripción: {r.get('error')}")
        b.plan = body.plan
        b.precio_mensual = precio
        b.suscripcion_id = r["id"]
        b.suscripcion_estado = "pendiente"
        s.add(b)
        s.commit()
        return {"ir_a": r["init_point"], "simulado": r.get("simulado", False)}


@app.post("/api/plan/cancelar")
def cancelar_suscripcion():
    """Da de baja el débito automático. NO le corta el acceso: paga lo que pagó.

    Que cancelar sea fácil es lo que hace que poner la tarjeta no dé miedo.
    """
    with sesion() as s:
        b = _mi_negocio(s)
        if not b.suscripcion_id:
            raise HTTPException(400, "No hay ninguna suscripción activa")
        salio, detalle = mp.cancelar(b.suscripcion_id)
        b.suscripcion_estado = "cancelada"
        b.suscripcion_id = ""
        b.tarjeta = ""
        s.add(b)
        s.commit()
        return {"cancelada": True, "detalle": detalle, "pago": cobros.estado(b)}


# ------------------------------------------------------------------- cobros
# Lo que pasa cuando Mercado Pago cobra (o no puede).


def _aplicar_pago(negocio_id: int, monto: int, pago_id: str, quien: str = "mercadopago"):
    """Un cobro que entró de verdad: corre la fecha y reactiva si hacía falta.

    Es el mismo camino que usa el back-office cuando marcamos una transferencia a
    mano. Que la tarjeta y la transferencia terminen en la misma función es lo que
    hace que el libro sea uno solo.
    """
    with sesion() as s, inquilino.sin_filtro():
        b = s.get(Business, negocio_id)
        if not b:
            return False
        if cobros.ya_registrado(s, pago_id):
            return True                     # MP reintenta: el mismo cobro no suma dos veces
        cobros.registrar(s, b, monto, "mercadopago", 1, nota="débito automático",
                         quien=quien, externo_id=pago_id)
        if b.estado == "suspendida":
            b.estado = "activa"
        b.suscripcion_estado = "activa"
        s.add(b)
        s.commit()
        return True


@app.post("/api/pagos/webhook")
async def pagos_webhook(request: Request):
    """Mercado Pago avisa que pasó algo. Nunca le creemos al aviso.

    Este endpoint está abierto —MP no manda credenciales— así que lo único que se
    toma del cuerpo es un **id**. Después le preguntamos a MP por ese id con
    nuestro token, y actuamos según lo que conteste ÉL. Si alguien nos inventa un
    webhook, lo peor que consigue es que le preguntemos a Mercado Pago por un id
    que no existe.

    Devuelve 200 siempre, incluso si algo falla: un 500 hace que MP reintente y,
    si insiste, deje de avisarnos. El error queda anotado.
    """
    mp._estado["webhooks"] += 1
    try:
        cuerpo = json.loads((await request.body()).decode() or "{}")
    except ValueError:
        cuerpo = {}
    tipo = cuerpo.get("type") or cuerpo.get("topic") or ""
    ident = str((cuerpo.get("data") or {}).get("id") or cuerpo.get("id") or "")
    if not ident:
        return {"ok": True, "ignorado": "sin id"}

    try:
        if tipo in ("subscription_preapproval", "preapproval"):
            salio, sub = mp.ver_suscripcion(ident)
            if not salio:
                return {"ok": True, "ignorado": "no pude leer la suscripción"}
            negocio_id = int(str(sub.get("external_reference", "")).replace("negocio-", "") or 0)
            with sesion() as s, inquilino.sin_filtro():
                b = s.get(Business, negocio_id) if negocio_id else None
                if b:
                    b.suscripcion_id = sub.get("id", b.suscripcion_id)
                    b.suscripcion_estado = mp.traducir(sub.get("status", ""))
                    b.tarjeta = mp.tarjeta_de(sub) or b.tarjeta
                    s.add(b)
                    s.commit()
            return {"ok": True, "suscripcion": ident}

        if tipo in ("subscription_authorized_payment", "authorized_payment"):
            salio, pago = mp.ver_pago(ident)
            if not salio:
                return {"ok": True, "ignorado": "no pude leer el pago"}
            estado_pago = pago.get("status", "")
            sid = str(pago.get("preapproval_id", ""))
            with sesion() as s, inquilino.sin_filtro():
                b = s.exec(select(Business).where(Business.suscripcion_id == sid)).first()
            if not b:
                return {"ok": True, "ignorado": "no encontré la cuenta"}
            if estado_pago == "approved":
                _aplicar_pago(b.id, int(float(pago.get("transaction_amount") or 0)), ident)
            else:
                # Un cobro rechazado no corta nada por sí solo: la cuenta se va a
                # cortar sola cuando se le acabe la gracia, que es lo mismo que le
                # pasaría si nunca hubiéramos recibido este aviso.
                uso.anotar_falla("pagos", f"Cobro rechazado ({estado_pago})", b.id)
            return {"ok": True, "pago": ident, "estado": estado_pago}
    except Exception as e:                                       # noqa: BLE001
        uso.anotar_falla("pagos", f"Webhook de Mercado Pago: {e}")
        print(f"[hilo] webhook de Mercado Pago: {e}")
    return {"ok": True}


@app.post("/api/pagos/simulado/{sid}")
def pago_simulado(sid: str):
    """El "pago" de la pantalla de tarjeta falsa. SOLO en modo simulado.

    Existe para poder mostrar el circuito entero —poner la tarjeta, que se cobre,
    que la cuenta vuelva— sin credenciales de Mercado Pago. Si algún día hay
    credenciales de verdad, `mp.simulado()` es False y esto devuelve 404: un
    endpoint que regala meses no puede quedar vivo en producción por olvido.
    """
    if not mp.simulado():
        raise HTTPException(404, "No existe")
    if not sid.startswith("SIM-"):
        raise HTTPException(400, "Esa no es una suscripción simulada")
    negocio_id = int(sid.split("-")[1])
    with sesion() as s, inquilino.sin_filtro():
        b = s.get(Business, negocio_id)
        if not b:
            raise HTTPException(404, "No existe esa cuenta")
        b.suscripcion_id = sid
        b.tarjeta = "Visa ····4242"
        s.add(b)
        s.commit()
        monto = b.precio_mensual or planes.precio_sugerido(b.plan)
    _aplicar_pago(negocio_id, monto, f"{sid}-1", quien="tarjeta simulada")
    with sesion() as s, inquilino.sin_filtro():
        return {"ok": True, "pago": cobros.estado(s.get(Business, negocio_id))}


# ----------------------------------------------------------------- telegram
# Un solo bot de Hilo para todos los clientes. Lo que cambia por cuenta no es el
# token —ese es nuestro— sino a quién pertenece cada conversación, y eso lo
# resuelve el código de vinculación (`app/vinculos.py`).


def _negocio_de_telegram(conexion_id: str, chat_id: str) -> int | None:
    """De qué cuenta de Hilo es este mensaje. Tres caminos, en orden de certeza.

    Un webhook no trae sesión: nadie nos dice de quién es. Con un bot por cliente
    lo diría el token, pero acá el bot es uno solo — así que hay que deducirlo.
    """
    with sesion() as s, inquilino.sin_filtro():
        # 1. Modo Business: la conexión es del vendedor y no hay ambigüedad.
        if conexion_id:
            c = s.exec(select(Credencial).where(
                Credencial.canal == "telegram",
                Credencial.referencia == conexion_id)).first()
            if c:
                return c.business_id
        # 2. Ya es cliente de alguien: su chat quedó guardado como identidad.
        ident = s.exec(select(Identity).where(
            Identity.canal == "telegram", Identity.valor == str(chat_id))).first()
        if ident:
            return ident.business_id
        # 3. Escribió antes pero todavía no lo convirtieron en cliente. Es el caso
        #    más común de todos y el más fácil de olvidar: alguien manda tres
        #    mensajes seguidos, el vendedor todavía no lo cargó, y del segundo en
        #    adelante no habría forma de saber de quién eran. El rastro está en
        #    los mensajes que ya entraron.
        m = s.exec(select(Message)
                   .where(Message.canal == "telegram",
                          Message.remitente == str(chat_id))
                   .order_by(Message.creado.desc())).first()
        if m and m.business_id:
            return m.business_id
        # 4. Es el dueño escribiéndole a su propio bot.
        c = s.exec(select(Credencial).where(
            Credencial.canal == "telegram",
            Credencial.externo_id == str(chat_id))).first()
        return c.business_id if c else None


def _telegram_vincular(ev: dict):
    """Alguien apretó un link del bot. Puede ser el dueño o un cliente suyo."""
    codigo = (ev.get("codigo") or "").strip()

    # --- un cliente del vendedor, que llegó por el link público ---
    if codigo.startswith("neg_"):
        with sesion() as s, inquilino.sin_filtro():
            b = s.exec(select(Business).where(
                Business.codigo_publico == codigo[4:])).first()
        if not b:
            tg.enviar(ev["chat_id"], "Ese link no corresponde a ninguna cuenta.")
            return
        with inquilino.usar(b.id), sesion() as s:
            pl.ingesta(s, "telegram", ev["chat_id"],
                       "Hola, te escribo por Telegram.",
                       remitente_nombre=ev.get("usuario", ""))
        tg.enviar(ev["chat_id"], "¡Listo! Escribime lo que necesites y te contestamos.")
        return

    # --- el dueño conectando su cuenta ---
    with sesion() as s:
        v = vinculos.buscar(s, codigo)
        if not v:
            tg.enviar(ev["chat_id"],
                      "Ese código no sirve o ya venció. Pedí uno nuevo desde Hilo, "
                      "en Canales.")
            return
        negocio_id = v.business_id
        vinculos.usar(s, v, {"usuario_id": ev.get("usuario_id"),
                             "arroba": ev.get("arroba"), "chat_id": ev.get("chat_id")})

    with inquilino.usar(negocio_id), sesion() as s:
        cred = s.exec(select(Credencial).where(Credencial.canal == "telegram")).first()
        if not cred:
            cred = Credencial(canal="telegram")
        cred.externo_id = str(ev.get("usuario_id") or ev.get("chat_id"))
        cred.etiqueta = ("@" + ev["arroba"]) if ev.get("arroba") else ev.get("usuario", "")
        cred.datos_json = secreto.cifrar(json.dumps(
            {"chat_id": ev.get("chat_id"), "usuario_id": ev.get("usuario_id"),
             "arroba": ev.get("arroba"), "modo": "bot"}, ensure_ascii=False))
        cred.activo = True
        cred.ultimo_error = ""
        cred.ultimo_ok = datetime.now()
        s.add(cred)
        b = s.get(Business, negocio_id)
        if b and not b.codigo_publico:
            b.codigo_publico = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
            s.add(b)
        s.commit()
        publico = b.codigo_publico if b else ""

    usuario = tg.quien_soy()
    tg.enviar(ev["chat_id"],
              f"Listo{(', ' + ev['usuario']) if ev.get('usuario') else ''}: "
              "tu Telegram quedó conectado a Hilo.\n\n"
              "Ahora tenés dos formas de usarlo:\n\n"
              f"1) Pasale este link a tus clientes y lo que te escriban entra a Hilo:\n"
              f"https://t.me/{usuario}?start=neg_{publico}\n\n"
              "2) Si tenés Telegram Premium, andá a Configuración → Telegram Business "
              f"→ Chatbots y poné @{usuario}. Ahí Hilo ve tus chats de siempre y "
              "contesta como vos.")


def _telegram_conexion(ev: dict):
    """El cliente conectó (o desconectó) el bot en su Telegram Business."""
    with sesion() as s, inquilino.sin_filtro():
        cred = s.exec(select(Credencial).where(
            Credencial.canal == "telegram",
            Credencial.externo_id == str(ev.get("usuario_id")))).first()
        if not cred:
            # Conectó el bot en Telegram sin haber pasado por Hilo. No sabemos de
            # qué cuenta es, así que se lo decimos en vez de tragárnoslo.
            tg.enviar(ev["chat_id"],
                      "Te conectaste al bot de Hilo, pero todavía no sé de qué cuenta "
                      "sos. Entrá a Hilo → Canales → Telegram y usá el link de ahí.")
            return
        datos = json.loads(secreto.descifrar(cred.datos_json) or "{}")
        datos.update({"conexion_id": ev["conexion_id"], "modo": "business",
                      "puede_responder": ev["puede_responder"]})
        cred.referencia = ev["conexion_id"] if ev["activa"] else ""
        cred.datos_json = secreto.cifrar(json.dumps(datos, ensure_ascii=False))
        cred.activo = bool(ev["activa"])
        cred.ultimo_ok = datetime.now()
        cred.ultimo_error = ("" if ev["puede_responder"] else
                             "Conectado, pero sin permiso para responder: activalo en "
                             "Telegram → Configuración → Telegram Business → Chatbots.")
        s.add(cred)
        s.commit()
    if ev["activa"]:
        tg.enviar(ev["chat_id"],
                  "Perfecto: ahora Hilo ve tus conversaciones y puede contestar como vos."
                  if ev["puede_responder"] else
                  "Quedé conectado, pero sin permiso para responder. Activá «puede "
                  "responder» en Telegram Business → Chatbots y ya está.")


def _entro_un_telegram(ev: dict):
    """Un mensaje de Telegram, tratado igual que cualquier otro."""
    negocio_id = _negocio_de_telegram(ev.get("conexion_id", ""), ev["remitente"])
    if not negocio_id:
        return False
    with inquilino.usar(negocio_id), sesion() as s:
        cred = s.exec(select(Credencial).where(Credencial.canal == "telegram")).first()
        # En Business, el vendedor puede contestar a mano desde su celular. Ese
        # mensaje entra por el mismo webhook y NO es del cliente: guardarlo como
        # entrante daría vuelta la pelota y Hilo le diría que le debe respuesta a
        # alguien al que ya le contestó.
        if cred and ev.get("de_quien_escribe") == cred.externo_id:
            ident = s.exec(select(Identity).where(
                Identity.canal == "telegram", Identity.valor == ev["remitente"])).first()
            if ident:
                s.add(Message(alias_id=ident.alias_id, canal="telegram",
                              direccion="saliente", autor="humano", texto=ev["texto"],
                              externo_id=ev["externo_id"]))
                s.commit()
            return True
        pl.ingesta(s, "telegram", ev["remitente"], ev["texto"],
                   externo_id=ev["externo_id"], remitente_nombre=ev.get("nombre", ""))
    return True


@app.post("/api/telegram/webhook")
async def telegram_entrante(request: Request):
    """Todo lo que manda Telegram. Va abierto: lo protege el secret token.

    Devuelve 200 siempre. Un 500 hace que Telegram reintente y, si insiste, deje
    de mandar: el error queda anotado, pero el webhook contesta que sí.
    """
    if not tg.firma_valida(request.headers.get("x-telegram-bot-api-secret-token", "")):
        tg._estado["rechazados"] += 1
        raise HTTPException(403, "Secret token incorrecto")
    try:
        payload = json.loads((await request.body()).decode() or "{}")
    except ValueError:
        payload = {}

    for ev in tg.procesar(payload):
        try:
            if ev["tipo"] == "vincular":
                _telegram_vincular(ev)
            elif ev["tipo"] == "conexion":
                _telegram_conexion(ev)
            elif ev["tipo"] == "mensaje":
                _entro_un_telegram(ev)
        except Exception as e:                                   # noqa: BLE001
            tg._estado["ultimo_error"] = str(e)[:300]
            uso.anotar_falla("telegram", f"No pude procesar un update: {e}")
            print(f"[hilo] telegram: {e}")
    return {"ok": True}


# ------------------------------------------------------------------ canales
# La pantalla donde el cliente enchufa sus cuentas. Es donde se cae la gente, así
# que la API está armada para que la pantalla no tenga que pensar: cada canal
# viene con su estado, su etiqueta y qué hacer a continuación, ya masticado.

# Los canales que existen, en el orden en que conviene mostrarlos.
CANALES_DEL_CLIENTE = [
    ("telegram",  "Telegram",  "Tus chats de Telegram, adentro de Hilo."),
    ("whatsapp",  "WhatsApp",  "Tu número de WhatsApp Business, con la API oficial."),
    ("mail",      "Mail",      "Tu casilla: lo que entra y lo que sale."),
    ("instagram", "Instagram", "Los mensajes directos de tu cuenta."),
    ("linkedin",  "LinkedIn",  "Tus conversaciones de LinkedIn."),
]

# Por qué un canal todavía no se puede conectar. Decirlo es mejor que mostrar un
# botón que no hace nada: el que lo aprieta y no pasa nada cree que se rompió.
POR_QUE_NO = {
    "instagram": "Falta que Meta apruebe nuestra app. Avisamos cuando esté.",
    "linkedin": "LinkedIn no tiene API de mensajes. Estamos armando una extensión "
                "del navegador para que funcione sin arriesgar tu cuenta.",
    "whatsapp": "Todavía no se conecta solo: escribinos y te lo dejamos andando en "
                "el día. Estamos terminando el alta con Meta para que sea un botón.",
    "mail": "Todavía no se conecta solo: escribinos y te lo dejamos andando. Va a "
            "ser una regla de reenvío en tu casilla, sin darnos ninguna contraseña.",
}


def _ultimos_del_canal(s, canal: str) -> dict:
    """Cuándo entró y cuándo salió el último mensaje. Es la prueba de vida."""
    def ultimo(direccion):
        m = s.exec(select(Message)
                   .where(Message.canal == canal, Message.direccion == direccion,
                          Message.simulado == False)                    # noqa: E712
                   .order_by(Message.creado.desc())).first()
        return m.creado.isoformat() if m else ""
    return {"ultimo_entrante": ultimo("entrante"), "ultimo_saliente": ultimo("saliente")}


@app.get("/api/canales")
def canales_del_cliente():
    """El estado de todos los canales de esta cuenta, en una sola llamada."""
    salida = []
    with sesion() as s:
        creds = {c.canal: c for c in s.exec(select(Credencial))}
        for clave, nombre, para_que in CANALES_DEL_CLIENTE:
            cred = creds.get(clave)
            item = {"canal": clave, "nombre": nombre, "para_que": para_que,
                    "estado": "desconectado", "etiqueta": "", "detalle": "",
                    "error": "", "modo": "", "conectado_el": "",
                    "puede_conectarse": clave not in POR_QUE_NO,
                    "por_que_no": POR_QUE_NO.get(clave, ""),
                    **_ultimos_del_canal(s, clave)}

            if cred and cred.activo:
                item.update({"estado": "andando", "etiqueta": cred.etiqueta,
                             "conectado_el": cred.creado.isoformat(),
                             "error": cred.ultimo_error or ""})
                if cred.ultimo_error:
                    item["estado"] = "error"
                if clave == "telegram":
                    datos = json.loads(secreto.descifrar(cred.datos_json) or "{}")
                    item["modo"] = datos.get("modo", "bot")
                    item["detalle"] = ("Conectado a tu cuenta: Hilo contesta como vos."
                                       if item["modo"] == "business" else
                                       "Andando en modo bot: tus clientes le escriben "
                                       "al bot de Hilo.")

            # Los dos canales que todavía pueden venir del .env de la instalación
            if clave == "mail" and item["estado"] == "desconectado" and correo.configurado():
                item.update({"estado": "andando", "etiqueta": correo.estado().get("casilla", ""),
                             "detalle": "Configurado por nosotros, en el servidor."})
            if clave == "whatsapp" and item["estado"] == "desconectado" and whatsapp.configurado():
                w = whatsapp.estado()
                item.update({"estado": "andando", "etiqueta": w.get("numero") or w.get("phone_id", ""),
                             "detalle": "Configurado por nosotros, en el servidor."})

            if clave == "telegram":
                v = vinculos.vivo(s, "telegram")
                item["vinculo"] = vinculos.como_esta(v)
                if item["estado"] == "desconectado" and item["vinculo"]["esperando"]:
                    item["estado"] = "conectando"
                if item["vinculo"]["esperando"]:
                    item["vinculo"]["link"] = tg.link_de_vinculacion(item["vinculo"]["codigo"])
                item["puede_conectarse"] = tg.configurado()
                if not tg.configurado():
                    item["por_que_no"] = ("Falta el token del bot de Hilo en el "
                                          "servidor (TG_TOKEN).")
                b = pl.negocio(s)
                item["link_publico"] = (
                    f"https://t.me/{tg.quien_soy()}?start=neg_{b.codigo_publico}"
                    if (b.codigo_publico and tg.quien_soy()) else "")
            # Un canal que YA está andando no necesita que le expliquen por qué
            # no se puede conectar. El cartel es para el que todavía no lo tiene.
            if item["estado"] in ("andando", "error"):
                item["por_que_no"] = ""
                item["puede_conectarse"] = True
            salida.append(item)
    return {"canales": salida, "bot": tg.quien_soy()}


@app.post("/api/canales/telegram/vincular")
def canal_telegram_vincular(request: Request):
    """Un código nuevo para enganchar Telegram. Dura media hora y se usa una vez."""
    if not tg.configurado():
        raise HTTPException(400, "El bot de Hilo todavía no está configurado en el servidor")
    with sesion() as s:
        u = s.get(Usuario, getattr(request.state, "uid", None) or 0)
        v = vinculos.crear(s, "telegram", quien=u.email if u else "")
        estado = vinculos.como_esta(v)
    estado["link"] = tg.link_de_vinculacion(v.codigo)
    estado["bot"] = tg.quien_soy()
    return estado


@app.post("/api/canales/{canal}/desconectar")
def canal_desconectar(canal: str):
    """Suelta el canal. No borra ni un mensaje: el hilo con cada cliente queda."""
    with sesion() as s:
        cred = s.exec(select(Credencial).where(Credencial.canal == canal)).first()
        if not cred:
            raise HTTPException(404, "Ese canal no está conectado")
        s.delete(cred)
        s.commit()
    return {"desconectado": True, "canal": canal}


@app.get("/api/diagnostico-ia")
def diagnostico_ia():
    """Para saber por que la IA no contesta, sin tener que mirar la consola."""
    return ai.diagnostico()


@app.get("/api/cola")
def cola():
    with sesion() as s:
        b = pl.negocio(s)
        filas = []
        for a in s.exec(select(Alias)):
            br = _brief(s, a.id)
            msgs = pl.mensajes_de(s, a.id)
            comps = _compromisos(s, a.id)
            vencidos = sum(1 for c in comps if c["vencido"])
            cerrado = es_cerrado(a.estado, pl.reglas(b).get("estados_cerrados"))
            entrantes = [m for m in msgs if m.direccion == "entrante" and m.autor == "cliente"]
            no_leido = bool(entrantes and (not a.visto_at or entrantes[-1].creado > a.visto_at))
            primera_etapa = pl.etapas(b)[0] if pl.etapas(b) else ""
            p = br.get("pelota") or {"de": "nadie", "horas": 0, "texto": ""}
            t = br.get("temperatura") or {"valor": 0, "nivel": "sin datos"}
            if cerrado:
                p = {"de": "nadie", "horas": p.get("horas", 0), "texto": a.estado}
                t = {"valor": 0, "nivel": "cerrado", "motivo": a.estado}
            filas.append({
                "id": a.id, "nombre": a.nombre, "contacto": a.contacto, "estado": a.estado,
                "estado_sugerido": a.estado_sugerido, "importancia": a.importancia,
                "token": a.token, "autonomia": pl.nivel_autonomia(a, b),
                "ultimo": msgs[-1].texto[:90] if msgs else "",
                "ultimo_canal": msgs[-1].canal if msgs else "",
                "horas": p.get("horas", 0), "pelota": p, "temperatura": t,
                "compromisos_vencidos": vencidos,
                "canales": br.get("canales") or sorted({m.canal for m in msgs}),
                "cerrado": cerrado, "no_leido": no_leido,
                "contacto_nuevo": (not cerrado) and a.estado == primera_etapa,
                "urgencia": urgencia(p, t, vencidos, cerrado, a.importancia),
            })
        filas.sort(key=lambda f: -f["urgencia"])

        sin_id = []
        for m in s.exec(select(Message).where(Message.alias_id == None)):  # noqa: E711
            sug = s.get(Alias, m.sugerencia_alias_id) if m.sugerencia_alias_id else None
            sin_id.append({"mensaje_id": m.id, "remitente": m.remitente,
                           "remitente_nombre": m.remitente_nombre, "canal": m.canal,
                           "texto": m.texto, "creado": m.creado.isoformat(),
                           "html": m.html,
                           "sugerencia": ({"alias_id": sug.id, "nombre": sug.nombre,
                                           "confianza": m.sugerencia_score,
                                           "motivo": m.sugerencia_motivo} if sug else None)})

        return {
            # Un cliente cae en UN solo grupo, y siempre el mismo acá y en el
            # panorama. Quién debe la respuesta manda: si se la debemos nosotros
            # es nuestra deuda por más frío que esté. "Enfriándose" es para el que
            # está esperando al cliente y el cliente no aparece.
            "contadores": {
                "te_esperan": sum(1 for f in filas if not f["cerrado"]
                                  and f["pelota"]["de"] == "nosotros"),
                "enfriandose": sum(1 for f in filas if not f["cerrado"]
                                   and f["pelota"]["de"] != "nosotros"
                                   and f["temperatura"]["nivel"] in ("enfriandose", "frio")),
                "sin_identificar": len(sin_id),
                "etapas_por_aprobar": sum(1 for f in filas if f["estado_sugerido"]),
                "sin_leer": sum(1 for f in filas if f["no_leido"]),
                "contactos_nuevos": sum(1 for f in filas if f["contacto_nuevo"]),
            },
            "clientes": filas,
            "sin_identificar": sin_id,
        }


@app.get("/api/panorama")
def panorama():
    """La foto de arriba: dónde está parada la cartera, no cliente por cliente."""
    from statistics import median

    from .logic import demoras
    with sesion() as s:
        b = pl.negocio(s)
        etps = pl.etapas(b)
        cerrados_cfg = pl.reglas(b).get("estados_cerrados")
        por_etapa = {e: 0 for e in etps}
        cuenta = {"te_toca": 0, "esperando": 0, "enfriandose": 0, "cerrados": 0}
        activos = 0
        riesgo_7d = 0
        nuestras, suyas = [], []
        importancia = {"alta": 0, "media": 0, "baja": 0}

        for a in s.exec(select(Alias)):
            msgs = pl.mensajes_de(s, a.id)
            n, x = demoras(msgs)
            nuestras += n
            suyas += x
            if a.estado in por_etapa:
                por_etapa[a.estado] += 1
            if es_cerrado(a.estado, cerrados_cfg):
                cuenta["cerrados"] += 1
                continue
            activos += 1
            importancia[a.importancia] = importancia.get(a.importancia, 0) + 1
            br = _brief(s, a.id)
            p = br.get("pelota") or {}
            t = br.get("temperatura") or {}
            if p.get("de") == "nosotros":
                cuenta["te_toca"] += 1
            elif t.get("nivel") in ("enfriandose", "frio"):
                cuenta["enfriandose"] += 1
                if (br.get("ritmo") or {}).get("silencio_horas", 0) > 168:
                    riesgo_7d += 1
            else:
                cuenta["esperando"] += 1

        sin_id = len(list(s.exec(select(Message).where(Message.alias_id == None))))  # noqa: E711
        return {
            "activos": activos,
            "riesgo_7d": riesgo_7d,
            "sin_identificar": sin_id,
            "por_etapa": [{"etapa": e, "n": por_etapa[e]} for e in etps],
            "pelota": [
                {"clave": "te_toca", "label": "Hay que responderle", "n": cuenta["te_toca"]},
                {"clave": "esperando", "label": "Esperando respuesta", "n": cuenta["esperando"]},
                {"clave": "enfriandose", "label": "Enfriándose", "n": cuenta["enfriandose"]},
                {"clave": "cerrados", "label": "Cerrados (ganado / perdido)", "n": cuenta["cerrados"]},
            ],
            "importancia": importancia,
            "ritmo": {
                "vos_horas": round(median(nuestras)) if nuestras else None,
                "clientes_horas": round(median(suyas)) if suyas else None,
            },
        }


@app.get("/api/alias/{alias_id}")
def ficha(alias_id: int):
    with sesion() as s:
        a = s.get(Alias, alias_id)
        if not a:
            raise HTTPException(404, "No existe ese cliente")
        b = pl.negocio(s)
        a.visto_at = datetime.now()   # abrir la ficha es haberla leído
        s.add(a)
        s.commit()
        return {
            "id": a.id, "nombre": a.nombre, "contacto": a.contacto, "rubro": a.rubro,
            "estado": a.estado, "token": a.token,
            "estado_sugerido": a.estado_sugerido,
            "estado_sugerido_motivo": a.estado_sugerido_motivo,
            "importancia": a.importancia,
            "responder_por": pl.canal_para_responder(pl.mensajes_de(s, a.id)),
            "primer_contacto": a.primer_contacto.isoformat(),
            "autonomia": pl.nivel_autonomia(a, b),
            "autonomia_propia": a.autonomia is not None,
            "estados": pl.etapas(b), "reglas": pl.reglas(b),
            "identidades": [{"canal": i.canal, "canal_label": CANALES.get(i.canal, i.canal),
                             "valor": i.valor}
                            for i in s.exec(select(Identity).where(Identity.alias_id == a.id))],
            "canales_salientes": [
                {"canal": c, "label": CANALES[c], "asunto": c in CANALES_CON_ASUNTO,
                 "destino": next((i.valor for i in s.exec(
                     select(Identity).where(Identity.alias_id == a.id, Identity.canal == c))), "")}
                for c in CANALES_SALIENTES],
            "mensajes": [_mensaje(m) for m in pl.mensajes_de(s, a.id)],
            "briefing": _brief(s, a.id),
            "compromisos": _compromisos(s, a.id),
            "persona": a.persona,
            "simulados": len([m for m in pl.mensajes_de(s, a.id) if m.simulado]),
            "ia": ai.como_esta(),
        }


class IngestIn(BaseModel):
    canal: str
    remitente: str
    texto: str
    adjuntos: list[str] = []


@app.post("/api/ingest")
def ingest(body: IngestIn):
    """La unica puerta de entrada. Hoy la usa la vista del cliente; manana, un mail real."""
    with sesion() as s:
        return pl.ingesta(s, body.canal, body.remitente, body.texto, body.adjuntos)


class RespuestaIn(BaseModel):
    texto: str
    canal: str = "mail"
    asunto: str = ""
    cc: str = ""
    cco: str = ""
    autor: str = "ia"          # "ia" si sale del borrador, "humano" si lo escribiste vos
    aprobado_por: str = "Axel"


@app.post("/api/alias/{alias_id}/responder")
def responder(alias_id: int, body: RespuestaIn):
    with sesion() as s:
        a = s.get(Alias, alias_id)
        if not a:
            raise HTTPException(404, "No existe ese cliente")
        if body.canal not in CANALES_SALIENTES:
            raise HTTPException(400, f"Por {body.canal} no se envía, se registra")

        # Por mail sale de verdad. Si el envío falla no guardamos nada: el hilo
        # no debe mostrar como enviado algo que se quedó en el camino, y así el
        # vendedor puede corregir y reintentar sin mensajes fantasma.
        asunto = body.asunto if body.canal in CANALES_CON_ASUNTO else ""
        salio, error = pl.despachar(s, a, body.canal, asunto, body.texto,
                                    cc=body.cc, cco=body.cco)
        if error:
            # Decía "el mail" siempre, también cuando fallaba WhatsApp. Un error
            # que nombra mal el canal manda a buscar el problema al lugar
            # equivocado. Y queda anotado: un envío que falla es exactamente lo
            # que el back-office tiene que mostrar en "últimas fallas".
            uso.anotar_falla(body.canal, f"No salió a {a.nombre}: {error}")
            raise HTTPException(400, f"No se pudo enviar por {body.canal}: {error}")

        s.add(Message(alias_id=alias_id, canal=body.canal, direccion="saliente",
                      autor=body.autor, texto=body.texto,
                      asunto=asunto,
                      cc=body.cc if body.canal in CANALES_CON_ASUNTO else "",
                      cco=body.cco if body.canal in CANALES_CON_ASUNTO else "",
                      aprobado_por=body.aprobado_por))
        s.commit()
        pl.construir_briefing(s, a)
    return ficha(alias_id)


class NotaIn(BaseModel):
    texto: str
    canal: str = "llamada"
    adjuntos: list[str] = []


@app.post("/api/alias/{alias_id}/nota")
def nota(alias_id: int, body: NotaIn):
    """La conversacion no digital: una llamada, una visita, un cafe."""
    with sesion() as s:
        a = s.get(Alias, alias_id)
        if not a:
            raise HTTPException(404, "No existe ese cliente")
        s.add(Message(alias_id=alias_id, canal=body.canal, direccion="entrante",
                      autor="humano", texto=body.texto,
                      adjuntos_json=json.dumps(body.adjuntos, ensure_ascii=False)))
        s.commit()
        pl.construir_briefing(s, a)
    return ficha(alias_id)


class EstadoIn(BaseModel):
    estado: str | None = None     # fijar esta etapa a mano
    aceptar: bool = False         # tomar la que propone la IA
    descartar: bool = False       # dejar la actual y borrar la propuesta


@app.post("/api/alias/{alias_id}/estado")
def cambiar_estado(alias_id: int, body: EstadoIn):
    """La etapa la decide el vendedor. La IA solo propone."""
    with sesion() as s:
        a = s.get(Alias, alias_id)
        if not a:
            raise HTTPException(404, "No existe ese cliente")
        etapas = pl.etapas(pl.negocio(s))

        if body.aceptar and a.estado_sugerido:
            a.estado = a.estado_sugerido
        elif body.estado:
            if body.estado not in etapas:
                raise HTTPException(400, f"«{body.estado}» no es una etapa de este negocio")
            a.estado = body.estado
        elif not body.descartar:
            raise HTTPException(400, "Decime qué hacer: estado, aceptar o descartar")

        a.estado_sugerido = ""
        a.estado_sugerido_motivo = ""
        s.add(a)
        s.commit()
    return ficha(alias_id)


class ImportanciaIn(BaseModel):
    importancia: str          # baja | media | alta


@app.post("/api/alias/{alias_id}/importancia")
def cambiar_importancia(alias_id: int, body: ImportanciaIn):
    """Cuánto pesa este cliente en la cola. Lo decide el vendedor, no la IA."""
    if body.importancia not in ("baja", "media", "alta"):
        raise HTTPException(400, "La importancia es baja, media o alta")
    with sesion() as s:
        a = s.get(Alias, alias_id)
        if not a:
            raise HTTPException(404, "No existe ese cliente")
        a.importancia = body.importancia
        s.add(a)
        s.commit()
    return ficha(alias_id)


class BorradorIn(BaseModel):
    tono: str = ""            # corto | calido | firme, o vacío para el tono normal
    canal: str | None = None


@app.post("/api/alias/{alias_id}/borrador")
def rehacer_borrador(alias_id: int, body: BorradorIn):
    """Vuelve a redactar la respuesta, opcionalmente pidiéndole otro tono."""
    with sesion() as s:
        a = s.get(Alias, alias_id)
        if not a:
            raise HTTPException(404, "No existe ese cliente")
        canal = body.canal or pl.canal_para_responder(pl.mensajes_de(s, a.id))
        r = pl.actuar(s, a, canal, tono=body.tono)
        fila = s.exec(select(Briefing).where(Briefing.alias_id == a.id)).first()
        if fila and r.get("borrador"):
            data = json.loads(fila.data_json)
            data["borrador"] = r["borrador"]
            data["accion_agente"] = r["accion"]
            data["tono_pedido"] = body.tono
            fila.data_json = json.dumps(data, ensure_ascii=False)
            s.add(fila)
            s.commit()
    return ficha(alias_id)


class AutonomiaIn(BaseModel):
    nivel: int | None


@app.post("/api/alias/{alias_id}/autonomia")
def autonomia(alias_id: int, body: AutonomiaIn):
    with sesion() as s:
        a = s.get(Alias, alias_id)
        if not a:
            raise HTTPException(404, "No existe ese cliente")
        a.autonomia = body.nivel
        s.add(a)
        s.commit()
    return ficha(alias_id)


@app.post("/api/alias/{alias_id}/refrescar")
def refrescar(alias_id: int):
    with sesion() as s:
        a = s.get(Alias, alias_id)
        if not a:
            raise HTTPException(404, "No existe ese cliente")
        pl.construir_briefing(s, a)
    return ficha(alias_id)


@app.post("/api/no-identificados/{mensaje_id}/fusionar")
def fusionar(mensaje_id: int, alias_id: int):
    """Adopta un mensaje huerfano y aprende la identidad para la proxima."""
    with sesion() as s:
        m = s.get(Message, mensaje_id)
        a = s.get(Alias, alias_id)
        if not m or not a:
            raise HTTPException(404, "No existe")
        m.alias_id = alias_id
        s.add(m)
        if m.remitente and not s.exec(select(Identity).where(Identity.valor == m.remitente)).first():
            s.add(Identity(alias_id=alias_id, canal=m.canal, valor=m.remitente))
        s.commit()
        pl.construir_briefing(s, a)
    return {"ok": True, "alias_id": alias_id}


class NuevoDesdeMensajeIn(BaseModel):
    nombre: str = ""
    importancia: str = "media"


@app.post("/api/no-identificados/{mensaje_id}/nuevo")
def nuevo_desde_mensaje(mensaje_id: int, body: NuevoDesdeMensajeIn):
    """Convierte un mensaje huérfano en un cliente nuevo.

    Es la otra mitad de fusionar: si el mensaje no es de nadie que ya tengamos,
    es de alguien que todavía no cargamos. Hasta ahora la app solo sabía hacer
    la primera mitad y el botón «Crear un alias nuevo» no llevaba a ningún lado.
    """
    import re as _re
    import secrets

    with sesion() as s:
        m = s.get(Message, mensaje_id)
        if not m:
            raise HTTPException(404, "No existe ese mensaje")
        if m.alias_id:
            raise HTTPException(400, "Ese mensaje ya pertenece a un cliente")

        # Si no escribieron un nombre, se arma con la parte de antes del arroba:
        # juan.rodriguez@… -> "Juan Rodriguez". Es un punto de partida editable.
        nombre = body.nombre.strip()
        if not nombre:
            # El nombre del perfil del canal le gana a deducirlo de la dirección.
            # En WhatsApp es lo único que hay: de un número no sale ningún nombre,
            # y sin esto el cliente nuevo se llamaría «5491168961470».
            nombre = (m.remitente_nombre or "").strip()
        if not nombre:
            local = (m.remitente or "").split("@")[0]
            partes = [p for p in _re.split(r"[._\-]+", local) if p]
            nombre = " ".join(p.capitalize() for p in partes) or "Cliente nuevo"

        b = pl.negocio(s)
        etps = pl.etapas(b)
        # El token va SIN filtro de inquilino a propósito. Es la credencial de una
        # URL pública (/#/c/<token>) y /api/cliente/<token> lo busca en toda la
        # base: si dos negocios llegaran a estrenar el mismo, el cliente de uno
        # abriría la conversación del otro. Tiene que ser único en toda la app,
        # no dentro de cada negocio.
        base = _re.sub(r"[^a-z0-9]+", "", nombre.lower())[:12] or "cliente"
        token = base
        with inquilino.sin_filtro():
            while s.exec(select(Alias).where(Alias.token == token)).first():
                token = f"{base}{secrets.token_hex(2)}"

        a = Alias(nombre=nombre, contacto=m.remitente or "", rubro=b.rubro or "",
                  importancia=body.importancia,
                  estado=etps[0] if etps else "Nuevo", token=token)
        s.add(a)
        s.commit()
        s.refresh(a)

        if m.remitente and not s.exec(
                select(Identity).where(Identity.valor == m.remitente)).first():
            s.add(Identity(alias_id=a.id, canal=m.canal, valor=m.remitente))

        m.alias_id = a.id
        m.sugerencia_alias_id = None
        m.sugerencia_score = 0
        m.sugerencia_motivo = ""
        s.add(m)
        s.commit()

        pl.construir_briefing(s, a)
        pl.actuar(s, a, m.canal)
        return {"ok": True, "alias_id": a.id, "nombre": a.nombre, "token": a.token}


@app.delete("/api/mensajes/{mensaje_id}")
def borrar_mensaje(mensaje_id: int):
    """Tira un mensaje a la basura.

    Sirve para lo que no es una conversación: la promoción que se coló, la
    prueba que uno mismo se mandó, el mail de bienvenida de Google. Si el
    mensaje pertenecía a un cliente, se recalcula su briefing para que el
    resumen no siga hablando de algo que ya no está.
    """
    with sesion() as s:
        m = s.get(Message, mensaje_id)
        if not m:
            raise HTTPException(404, "No existe ese mensaje")
        alias_id = m.alias_id
        s.delete(m)
        s.commit()
        if alias_id:
            a = s.get(Alias, alias_id)
            if a:
                pl.construir_briefing(s, a)
    return {"ok": True}


# ----------------------------------------------- el cliente interpretado por la IA

class SimularIn(BaseModel):
    turnos: int = 1
    auto: bool = False        # True = el agente también contesta, y conversan solos


@app.post("/api/alias/{alias_id}/simular")
def simular(alias_id: int, body: SimularIn):
    """Pone a la IA en el papel de ESTE cliente y le hace escribir su próximo
    mensaje. Entra por la misma puerta que cualquier otro mensaje."""
    with sesion() as s:
        if not s.get(Alias, alias_id):
            raise HTTPException(404, "No existe ese cliente")
        r = sim.conversar(s, alias_id, turnos=body.turnos, auto=body.auto)
    return {**r, "ficha": ficha(alias_id)}


@app.post("/api/alias/{alias_id}/limpiar-simulados")
def limpiar_simulados(alias_id: int):
    with sesion() as s:
        if not s.get(Alias, alias_id):
            raise HTTPException(404, "No existe ese cliente")
        borrados = sim.limpiar(s, alias_id)
    return {"borrados": borrados, "ficha": ficha(alias_id)}


# --------------------------------------------------- la vista del cliente (demo)
# Estas rutas van abiertas: el token ES la credencial. Por eso el alias se busca
# SIN filtro —no hay sesión que diga de qué negocio es— y apenas se sabe, se pone
# el inquilino para que todo lo que venga después quede encerrado ahí.


def _por_token(s, token: str) -> Alias:
    with inquilino.sin_filtro():
        a = s.exec(select(Alias).where(Alias.token == token)).first()
    if not a:
        raise HTTPException(404, "No existe esa conversación")
    return a


@app.get("/api/cliente/{token}")
def cliente(token: str):
    """Lo que ve el cliente en su celular. Sin resumenes, sin IA visible."""
    with sesion() as s:
        a = _por_token(s, token)
      # a partir de acá, solo el negocio dueño de esa conversación
        with inquilino.usar(a.business_id):
            b = pl.negocio(s)
            ids = {i.canal: i.valor
                   for i in s.exec(select(Identity).where(Identity.alias_id == a.id))}
            msgs = [m for m in pl.mensajes_de(s, a.id)
                    if m.canal not in ("llamada", "presencial")]
            return {"vendedor": b.nombre, "cliente": a.contacto or a.nombre,
                    "identidades": ids,
                    "mensajes": [{"mio": m.direccion == "entrante", "texto": m.texto,
                                  "canal": m.canal,
                                  "creado": m.creado.isoformat()} for m in msgs]}


@app.post("/api/cliente/{token}/simular")
def cliente_simula(token: str):
    """El mismo trigger, pero desde la pantalla del celular."""
    with sesion() as s:
        a = _por_token(s, token)
        with inquilino.usar(a.business_id):
            return sim.hablar_como_cliente(s, a)


class ClienteEnviaIn(BaseModel):
    texto: str
    canal: str = "mail"


@app.post("/api/cliente/{token}/enviar")
def cliente_envia(token: str, body: ClienteEnviaIn):
    with sesion() as s:
        a = _por_token(s, token)
        with inquilino.usar(a.business_id):
            ident = s.exec(select(Identity).where(
                Identity.alias_id == a.id, Identity.canal == body.canal)).first()
            remitente = ident.valor if ident else f"{token}@demo"
            return pl.ingesta(s, body.canal, remitente, body.texto)


@app.post("/api/reset")
def reset():
    """Vuelve a la posición de demo. Sirve entre ensayo y ensayo, sin reiniciar nada.

    OJO: `sembrar()` hace DROP TABLE. Con un solo negocio eso es "resetear la
    demo"; con varios sería borrarle los clientes a TODOS. Por eso, en cuanto hay
    más de una cuenta, esto se niega. No es una precaución teórica: este endpoint
    quedó abierto a propósito para el hackatón.
    """
    with sesion() as s, inquilino.sin_filtro():
        cuantos = len(list(s.exec(select(Business))))
    if cuantos > 1:
        raise HTTPException(
            409, f"Hay {cuantos} negocios en esta base. Resetear los borraría a todos.")
    from seed import sembrar
    with inquilino.usar(None):
        sembrar()
    return {"ok": True}


# ------------------------------------------------------ el front, si esta compilado
# Con `npm run build` en web/, todo queda servido desde este mismo puerto: un solo
# proceso, una sola URL, y el celular del publico entra por la misma direccion.
_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="web")
