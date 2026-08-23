import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import select

from . import ai, auth, correo, inquilino, pipeline as pl, simulador as sim, whatsapp
from .config import cargar as cargar_env

cargar_env()
from .db import crear_tablas, sesion
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
        if not wa["firma_verificable"]:
            print("[hilo] OJO: sin WA_APP_SECRET el webhook le cree a cualquiera")
        if not wa["webhook_verificable"]:
            print("[hilo] OJO: sin WA_VERIFY_TOKEN no vas a poder registrar el webhook")
    else:
        print("[hilo] whatsapp dormido: faltan WA_TOKEN o WA_PHONE_ID en el .env")


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
)


@app.middleware("http")
async def puerta(request: Request, call_next):
    ruta = request.url.path
    if not ruta.startswith("/api/") or ruta.startswith(ABIERTAS) or request.method == "OPTIONS":
        return await call_next(request)
    with sesion() as s:
        if not auth.auth_encendida(s):
            return await call_next(request)
        cabecera = request.headers.get("authorization", "")
        token = cabecera[7:] if cabecera.lower().startswith("bearer ") else ""
        uid = auth.leer_token(token) if token else None
        usuario = s.get(Usuario, uid) if uid else None
        if not usuario or not usuario.activo:
            return JSONResponse({"detail": "Necesitás entrar con tu cuenta"}, status_code=401)
        negocio_id = usuario.business_id

    if negocio_id is None:
        # Una cuenta sin negocio no puede ver NADA. Es el caso de un usuario que
        # quedó de una versión anterior: mejor un error claro que dejarlo entrar
        # a una app donde el filtro no aplica y ve todo.
        return JSONResponse(
            {"detail": "Tu cuenta no está asociada a ningún negocio. Escribinos."},
            status_code=409)

    # ACÁ se decide qué ve este request. De este `with` para adentro, todas las
    # consultas de los modelos del inquilino salen filtradas solas: no hay que
    # acordarse en cada endpoint, que es exactamente la clase de olvido que
    # termina mostrándole los clientes de uno a otro.
    with inquilino.usar(negocio_id):
        return await call_next(request)


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
                "ia_activa": not ai.offline()}


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
    return {"ok": True, "entraron": entraron}


@app.get("/api/whatsapp/estado")
def whatsapp_estado():
    """Para mirar desde Configuración si WhatsApp está andando de verdad."""
    return whatsapp.estado()


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
            raise HTTPException(400, f"No se pudo enviar el mail: {error}")

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
