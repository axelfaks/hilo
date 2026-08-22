import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import select

from . import ai, auth, pipeline as pl, simulador as sim
from .config import cargar as cargar_env

cargar_env()
from .db import crear_tablas, sesion
from .logic import (CANALES, CANALES_CON_ASUNTO, CANALES_SALIENTES,
                    NIVELES_AUTONOMIA, es_cerrado, urgencia)
from .models import Alias, Briefing, Commitment, Identity, Message, Usuario

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
                sembrar()
                print("[hilo] base vacía: cargué los datos de demo")
        except Exception as e:
            # que no se caiga el arranque: sin datos la app igual levanta
            print(f"[hilo] no pude sembrar ({e})")


# --------------------------------------------------------------------- login
# La API queda protegida SOLO cuando existe al menos un usuario. Mientras no haya
# ninguno la app funciona abierta y te pide crear la primera cuenta: nadie se
# queda afuera de su propia app por un problema de configuración.

ABIERTAS = ("/api/auth/", "/api/cliente/")   # login y la vista del cliente de la demo


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
    return await call_next(request)


@app.get("/api/auth/estado")
def auth_estado():
    with sesion() as s:
        return {"hay_usuarios": auth.hay_usuarios(s), "protegida": auth.auth_encendida(s)}


class RegistroIn(BaseModel):
    email: str
    password: str
    nombre: str = ""


@app.post("/api/auth/registro")
def auth_registro(body: RegistroIn):
    """Crea la primera cuenta. Después de eso, los usuarios los invita el dueño."""
    if "@" not in body.email or "." not in body.email.split("@")[-1]:
        raise HTTPException(400, "Ese mail no parece un mail")
    problema = auth.problema_con_la_contrasena(body.password)
    if problema:
        raise HTTPException(400, problema)
    with sesion() as s:
        if auth.hay_usuarios(s):
            raise HTTPException(403, "Ya hay una cuenta creada. Entrá con ella.")
        u = auth.crear_usuario(s, body.email, body.password, body.nombre)
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
        u = auth.crear_usuario(s, body.email, body.password, body.nombre, body.rol)
        return auth.publico(u)


@app.get("/api/auth/usuarios")
def auth_listar():
    with sesion() as s:
        return [auth.publico(u) for u in s.exec(select(Usuario))]


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
            "asunto": m.asunto,
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
    return get_negocio()


@app.post("/api/onboarding/reabrir")
def onboarding_reabrir():
    """Para volver a pasar por las preguntas sin perder los clientes."""
    with sesion() as s:
        b = pl.negocio(s)
        b.onboarding_hecho = False
        s.add(b)
        s.commit()
    return {"ok": True}


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
            sin_id.append({"mensaje_id": m.id, "remitente": m.remitente, "canal": m.canal,
                           "texto": m.texto[:160], "creado": m.creado.isoformat(),
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
        s.add(Message(alias_id=alias_id, canal=body.canal, direccion="saliente",
                      autor=body.autor, texto=body.texto,
                      asunto=body.asunto if body.canal in CANALES_CON_ASUNTO else "",
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

@app.get("/api/cliente/{token}")
def cliente(token: str):
    """Lo que ve el cliente en su celular. Sin resumenes, sin IA visible."""
    with sesion() as s:
        a = s.exec(select(Alias).where(Alias.token == token)).first()
        if not a:
            raise HTTPException(404, "No existe esa conversacion")
        b = pl.negocio(s)
        ids = {i.canal: i.valor for i in s.exec(select(Identity).where(Identity.alias_id == a.id))}
        msgs = [m for m in pl.mensajes_de(s, a.id) if m.canal not in ("llamada", "presencial")]
        return {"vendedor": b.nombre, "cliente": a.contacto or a.nombre,
                "identidades": ids,
                "mensajes": [{"mio": m.direccion == "entrante", "texto": m.texto,
                              "canal": m.canal, "creado": m.creado.isoformat()} for m in msgs]}


@app.post("/api/cliente/{token}/simular")
def cliente_simula(token: str):
    """El mismo trigger, pero desde la pantalla del celular."""
    with sesion() as s:
        a = s.exec(select(Alias).where(Alias.token == token)).first()
        if not a:
            raise HTTPException(404, "No existe esa conversación")
        return sim.hablar_como_cliente(s, a)


class ClienteEnviaIn(BaseModel):
    texto: str
    canal: str = "mail"


@app.post("/api/cliente/{token}/enviar")
def cliente_envia(token: str, body: ClienteEnviaIn):
    with sesion() as s:
        a = s.exec(select(Alias).where(Alias.token == token)).first()
        if not a:
            raise HTTPException(404, "No existe esa conversacion")
        ident = s.exec(select(Identity).where(
            Identity.alias_id == a.id, Identity.canal == body.canal)).first()
        remitente = ident.valor if ident else f"{token}@demo"
        return pl.ingesta(s, body.canal, remitente, body.texto)


@app.post("/api/reset")
def reset():
    """Vuelve a la posicion de demo. Sirve entre ensayo y ensayo, sin reiniciar nada."""
    from seed import sembrar
    sembrar()
    return {"ok": True}


# ------------------------------------------------------ el front, si esta compilado
# Con `npm run build` en web/, todo queda servido desde este mismo puerto: un solo
# proceso, una sola URL, y el celular del publico entra por la misma direccion.
_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="web")
