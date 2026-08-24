"""El back-office: la pantalla con la que miramos TODAS las cuentas.

No es el panel del cliente ni la configuración de su negocio. Es el tercero, el
nuestro, y contesta cinco preguntas que hoy no tienen dónde mirarse:

  1. ¿Quiénes son nuestras cuentas y qué tan vivas están?
  2. ¿A quién se le cayó un canal? — es la causa número uno de soporte, y
     enterarse por el cliente enojado es enterarse tarde.
  3. ¿Cuánta IA gasta cada una? — nuestro único costo variable directo.
  4. ¿Puedo ver lo que ve el cliente sin pedirle una captura?
  5. ¿Qué se le rompió últimamente?

Todo lo de acá adentro corre con `inquilino.sin_filtro()`, que es exactamente lo
que el aislamiento prohíbe en el resto de la app. Por eso está en un archivo
aparte y detrás de `es_root`: saltear el filtro tiene que verse en el código y no
pasar por olvido.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import func, select

from . import ai, cobros, correo, inquilino, planes, uso, whatsapp
from .db import sesion
from .models import (Acceso, Alias, Business, Credencial, Falla, Message,
                     UsoIA, Usuario)

# Un canal sin novedades por más de esto está "quieto": puede ser normal (un
# cliente chico no recibe mensajes todos los días) pero es lo que hay que mirar
# cuando alguien dice "no me llega nada".
HORAS_QUIETO = 72


def exigir_root(request: Request):
    """La única puerta del back-office.

    `request.state.es_root` lo pone el middleware `puerta` de `main.py`, que ya
    resolvió el token. Acá no se vuelve a leer el header: si la puerta no dejó
    dicho que este usuario es root, no lo es.
    """
    if not getattr(request.state, "es_root", False):
        raise HTTPException(403, "El back-office es solo para las cuentas root")


router = APIRouter(prefix="/api/root", dependencies=[Depends(exigir_root)])


# --------------------------------------------------------------- ayudantes

def _iso(v) -> str:
    return v.isoformat() if isinstance(v, datetime) else ""


def _contar(s, modelo, extra=None) -> dict:
    """{business_id: cantidad} en UNA consulta, no una por cuenta."""
    q = select(modelo.business_id, func.count()).group_by(modelo.business_id)
    if extra is not None:
        q = q.where(extra)
    return {bid: n for bid, n in s.exec(q)}


def _actividad_por_canal(s) -> dict:
    """{(negocio, canal, dirección): última fecha}. Es de dónde sale la salud."""
    q = (select(Message.business_id, Message.canal, Message.direccion,
                func.max(Message.creado))
         .where(Message.simulado == False)                          # noqa: E712
         .group_by(Message.business_id, Message.canal, Message.direccion))
    return {(bid, canal, direccion): ultimo for bid, canal, direccion, ultimo in s.exec(q)}


def _salud(cred, ultimo_entrante, ultimo_saliente) -> str:
    """ok · error · quieto · sin-trafico. Una sola palabra, que es lo que se mira."""
    if cred is not None and not cred.activo:
        return "apagado"
    if cred is not None and cred.ultimo_error:
        return "error"
    ultimo = max([f for f in (ultimo_entrante, ultimo_saliente) if f], default=None)
    if not ultimo:
        return "sin-trafico"
    if datetime.now() - ultimo > timedelta(hours=HORAS_QUIETO):
        return "quieto"
    return "ok"


def _canales_de(negocio_id: int, creds: list, actividad: dict) -> list:
    """Los canales de una cuenta: los que conectó y los que igual tienen tráfico.

    Un canal puede tener mensajes sin credencial propia: es el mail o el WhatsApp
    del `.env`, o sea el nuestro. Se muestra igual, marcado como de la plataforma,
    porque el cliente lo está usando de verdad.
    """
    por_canal = {c.canal: c for c in creds}
    con_trafico = {canal for (bid, canal, _), _ in actividad.items() if bid == negocio_id}
    salida = []
    for canal in sorted(set(por_canal) | con_trafico):
        cred = por_canal.get(canal)
        entrante = actividad.get((negocio_id, canal, "entrante"))
        saliente = actividad.get((negocio_id, canal, "saliente"))
        salida.append({
            "canal": canal,
            "propio": cred is not None,          # False = anda por el .env nuestro
            "etiqueta": cred.etiqueta if cred else "",
            "activo": bool(cred.activo) if cred else None,
            "conectado_el": _iso(cred.creado) if cred else "",
            "ultimo_ok": _iso(cred.ultimo_ok) if cred else "",
            "ultimo_error": (cred.ultimo_error or "") if cred else "",
            "ultimo_entrante": _iso(entrante),
            "ultimo_saliente": _iso(saliente),
            "salud": _salud(cred, entrante, saliente),
        })
    return salida


# ----------------------------------------------------------------- resumen

@router.get("/resumen")
def resumen():
    """La pantalla entera en una sola llamada. Se pide cada 15 segundos."""
    hace_7 = datetime.now() - timedelta(days=7)
    with sesion() as s, inquilino.sin_filtro():
        negocios = list(s.exec(select(Business).order_by(Business.id)))
        clientes = _contar(s, Alias)
        mensajes = _contar(s, Message, Message.simulado == False)    # noqa: E712
        mensajes_7d = _contar(s, Message, (Message.simulado == False) &  # noqa: E712
                                          (Message.creado >= hace_7))
        # Las cuotas se miden por mes calendario. Estas dos consultas evitan
        # tres por cuenta: con 100 clientes eso es la diferencia entre una
        # pantalla que abre y una que hay que esperar.
        primero = cobros._primero_del_mes()
        mensajes_mes = _contar(s, Message, (Message.simulado == False) &   # noqa: E712
                                           (Message.creado >= primero))
        ia_mes = {bid: n for bid, n in s.exec(
            select(UsoIA.business_id, func.sum(UsoIA.llamadas))
            .where(UsoIA.dia >= primero.strftime("%Y-%m-%d"))
            .group_by(UsoIA.business_id))}
        actividad = _actividad_por_canal(s)
        fallas_24h = uso.fallas_recientes(s, 24)

        creds: dict = {}
        for c in s.exec(select(Credencial)):
            creds.setdefault(c.business_id, []).append(c)

        usuarios: dict = {}
        for u in s.exec(select(Usuario)):
            usuarios.setdefault(u.business_id, []).append(u)

        cuentas = []
        for b in negocios:
            gente = usuarios.get(b.id, [])
            canales = _canales_de(b.id, creds.get(b.id, []), actividad)
            accesos = [u.ultimo_acceso for u in gente if u.ultimo_acceso]
            consumo = {"clientes": clientes.get(b.id, 0),
                       "mensajes_mes": mensajes_mes.get(b.id, 0),
                       "ia_mes": int(ia_mes.get(b.id) or 0)}
            cuentas.append({
                "id": b.id,
                "nombre": b.nombre,
                "rubro": b.rubro,
                "plan": b.plan or "prueba",
                "estado": b.estado or "activa",
                "nota": b.nota or "",
                "creado": _iso(b.creado),
                "onboarding_hecho": bool(b.onboarding_hecho),
                "usuarios": [{"email": u.email, "rol": u.rol, "es_root": bool(u.es_root),
                              "ultimo_acceso": _iso(u.ultimo_acceso)} for u in gente],
                "ultimo_acceso": _iso(max(accesos)) if accesos else "",
                "clientes": clientes.get(b.id, 0),
                "mensajes": mensajes.get(b.id, 0),
                "mensajes_7d": mensajes_7d.get(b.id, 0),
                "canales": canales,
                "canales_caidos": sum(1 for c in canales if c["salud"] in ("error", "apagado")),
                "ia": uso.del_mes(s, b.id),
                "fallas_24h": fallas_24h.get(b.id, 0),
                # --- plata ---
                "pago": cobros.estado(b),
                "cuota": {"limites": planes.limites(b.plan), "uso": consumo,
                          "pasado": planes.pasados(consumo, b.plan)},
            })

        # Las cuentas sin dueño son un caso real y molesto: quedan del onboarding
        # que alguien empezó y no terminó. Se cuentan aparte para que no ensucien
        # el número de clientes de verdad.
        huerfanas = sum(1 for c in cuentas if not c["usuarios"])
        totales = {
            "cuentas": len(cuentas),
            "con_dueño": len(cuentas) - huerfanas,
            "huerfanas": huerfanas,
            "suspendidas": sum(1 for c in cuentas if c["estado"] == "suspendida"),
            "clientes": sum(c["clientes"] for c in cuentas),
            "mensajes": sum(c["mensajes"] for c in cuentas),
            "mensajes_7d": sum(c["mensajes_7d"] for c in cuentas),
            "canales_caidos": sum(c["canales_caidos"] for c in cuentas),
            "cuentas_con_canal_caido": sum(1 for c in cuentas if c["canales_caidos"]),
            "fallas_24h": sum(c["fallas_24h"] for c in cuentas),
            "ia": uso.del_mes(s),
            "pasadas_de_cuota": sum(1 for c in cuentas if c["cuota"]["pasado"]),
        }
        plata = cobros.resumen(s, negocios)
        vencen = cobros.vencen_en(s, negocios, 7)

    return {
        "totales": totales,
        "plata": plata,
        "vencen": vencen,
        "planes": planes.catalogo(),
        "medios": list(planes.MEDIOS),
        "cuentas": cuentas,
        # Lo que es de la instalación entera y no de ninguna cuenta: sirve para
        # saber si el problema es de uno o es nuestro.
        "plataforma": {
            "ia": ai.como_esta(),
            "whatsapp_env": whatsapp.configurado(),
            "correo_env": correo.configurado(),
            # Lo que sabemos del token, de la última vez que preguntamos. No se
            # pregunta acá: sería una llamada a Meta cada 15 segundos.
            "wa_token_ok": whatsapp._estado.get("token_ok"),
            "wa_token_detalle": whatsapp._estado.get("token_detalle", ""),
            "wa_token_probado": whatsapp._estado.get("token_probado", ""),
        },
        "ahora": datetime.now().isoformat(),
    }


# ------------------------------------------------------------------ detalle

@router.get("/cuenta/{negocio_id}")
def cuenta(negocio_id: int):
    """Todo lo de una cuenta: su gente, su consumo día por día y qué se le rompió."""
    with sesion() as s, inquilino.sin_filtro():
        b = s.get(Business, negocio_id)
        if not b:
            raise HTTPException(404, "No existe esa cuenta")
        creds = list(s.exec(select(Credencial).where(Credencial.business_id == negocio_id)))
        actividad = _actividad_por_canal(s)
        ultimos = s.exec(select(Message)
                         .where(Message.business_id == negocio_id)
                         .order_by(Message.creado.desc()).limit(8))
        return {
            "id": b.id,
            "nombre": b.nombre,
            "descripcion": b.descripcion,
            "canales": _canales_de(b.id, creds, actividad),
            "ia_por_dia": uso.por_dia(s, negocio_id, 14),
            "cobros": cobros.historial(s, negocio_id, 12),
            "fallas": uso.ultimas_fallas(s, negocio_id, 50),
            "ultimos_mensajes": [{
                "canal": m.canal, "direccion": m.direccion, "autor": m.autor,
                "cuando": _iso(m.creado),
                "texto": (m.texto or "")[:160],
            } for m in ultimos],
        }


class CuentaIn(BaseModel):
    plan: str | None = None
    estado: str | None = None
    nota: str | None = None
    precio_mensual: int | None = None
    prueba_dias: int | None = None      # mover la prueba: para regalar días o demostrar el corte


PLANES = ("prueba", "basico", "pro")
ESTADOS = ("activa", "suspendida")


@router.post("/cuenta/{negocio_id}")
def editar_cuenta(negocio_id: int, body: CuentaIn):
    """Plan, estado y nota interna. Es el cobro a mano de los primeros clientes.

    Suspender NO borra nada: bloquea la entrada de su gente con un mensaje claro
    y deja los datos intactos, que es lo único que uno quiere cuando alguien
    dejó de pagar y capaz vuelve.
    """
    if body.plan is not None and body.plan not in PLANES:
        raise HTTPException(400, f"Plan desconocido. Van: {', '.join(PLANES)}")
    if body.estado is not None and body.estado not in ESTADOS:
        raise HTTPException(400, f"Estado desconocido. Van: {', '.join(ESTADOS)}")
    with sesion() as s, inquilino.sin_filtro():
        b = s.get(Business, negocio_id)
        if not b:
            raise HTTPException(404, "No existe esa cuenta")
        if body.plan is not None:
            b.plan = body.plan
            # Cambiar de plan propone el precio del catálogo, pero solo si esta
            # cuenta todavía no tiene uno: el precio negociado con un cliente no
            # se pisa por tocar un select.
            if not b.precio_mensual and body.precio_mensual is None:
                b.precio_mensual = planes.precio_sugerido(body.plan)
        if body.precio_mensual is not None:
            b.precio_mensual = max(0, body.precio_mensual)
        if body.estado is not None:
            b.estado = body.estado
        if body.nota is not None:
            b.nota = body.nota[:2000]
        if body.prueba_dias is not None:
            # Sirve para dos cosas: regalarle una semana a alguien que la pidió, y
            # poner una cuenta a un día del corte para mostrar que el corte anda.
            b.prueba_hasta = datetime.now() + timedelta(days=body.prueba_dias)
        s.add(b)
        s.commit()
        return {"id": b.id, "plan": b.plan, "estado": b.estado, "nota": b.nota,
                "precio_mensual": b.precio_mensual, "pago": cobros.estado(b)}


# -------------------------------------------------------------------- plata

class CobroIn(BaseModel):
    monto: int
    medio: str = "transferencia"
    meses: int = 1
    nota: str = ""


@router.post("/cuenta/{negocio_id}/cobro")
def cobrar(negocio_id: int, body: CobroIn, request: Request):
    """Marca que entró plata y corre `pagado_hasta`.

    Esto es todo el billing que hay, y es a propósito: construir una pasarela
    antes de tener diez clientes pagando es construir la parte más aburrida del
    producto para nadie. Lo que sí importa desde el primer peso es que quede el
    registro de quién pagó cuánto y hasta cuándo.
    """
    if body.monto < 0:
        raise HTTPException(400, "El monto no puede ser negativo")
    if body.medio not in planes.MEDIOS:
        raise HTTPException(400, f"Medio desconocido. Van: {', '.join(planes.MEDIOS)}")
    if not 1 <= body.meses <= 24:
        raise HTTPException(400, "Los meses van de 1 a 24")
    with sesion() as s, inquilino.sin_filtro():
        b = s.get(Business, negocio_id)
        if not b:
            raise HTTPException(404, "No existe esa cuenta")
        u = s.get(Usuario, getattr(request.state, "uid", None) or 0)
        c = cobros.registrar(s, b, body.monto, body.medio, body.meses,
                             body.nota, u.email if u else "sin sesión")
        # Cobrarle a una cuenta suspendida es reactivarla: es lo que uno quiso
        # decir al marcar el pago, y si no se hace solo, se olvida.
        if b.estado == "suspendida":
            b.estado = "activa"
            s.add(b)
            s.commit()
        return {"cobro": {"id": c.id, "monto": c.monto, "medio": c.medio,
                          "meses": c.meses,
                          "periodo_hasta": _iso(c.periodo_hasta)},
                "pago": cobros.estado(b), "estado": b.estado}


@router.get("/cobros")
def libro():
    """El libro entero: los últimos 50 cobros y los totales del mes."""
    with sesion() as s, inquilino.sin_filtro():
        negocios = list(s.exec(select(Business)))
        nombres = {b.id: b.nombre for b in negocios}
        movimientos = cobros.historial(s, None, 50)
        for m in movimientos:
            m["negocio"] = nombres.get(m["negocio_id"], "—")
        return {"cobros": movimientos, "plata": cobros.resumen(s, negocios),
                "vencen": cobros.vencen_en(s, negocios, 7)}


# ----------------------------------------------------------------- ver como

@router.post("/ver-como/{negocio_id}")
def ver_como(negocio_id: int, request: Request):
    """Deja registrado que vamos a mirar la app como este cliente.

    El cambio de cuenta lo hace el header `X-Hilo-Negocio` en cada pedido (lo
    manda el front y lo aplica la puerta). Este endpoint no da permiso: lo
    ANOTA. Impersonar sin dejar rastro es la clase de poder que después no se
    puede explicar.
    """
    with sesion() as s, inquilino.sin_filtro():
        b = s.get(Business, negocio_id)
        if not b:
            raise HTTPException(404, "No existe esa cuenta")
        u = s.get(Usuario, getattr(request.state, "uid", None) or 0)
        s.add(Acceso(usuario_id=u.id if u else None,
                     usuario_email=u.email if u else "sin sesión (auth apagada)",
                     negocio_id=b.id, negocio_nombre=b.nombre))
        s.commit()
        return {"negocio_id": b.id, "nombre": b.nombre}


@router.post("/probar-whatsapp")
def probar_whatsapp():
    """Le pregunta a Meta, ahora mismo, si el token sigue vivo.

    Un clic antes de una demo. El token temporal dura 24 h y cuando vence no
    avisa: los mensajes dejan de salir y no hay nada en pantalla que lo diga.
    """
    vivo, detalle = whatsapp.probar_token()
    return {"ok": vivo, "detalle": detalle,
            "probado": whatsapp._estado.get("token_probado", "")}


@router.get("/accesos")
def accesos():
    """El log de quién miró qué cuenta y cuándo."""
    with sesion() as s, inquilino.sin_filtro():
        filas = s.exec(select(Acceso).order_by(Acceso.cuando.desc()).limit(50))
        return [{"cuando": _iso(a.cuando), "usuario": a.usuario_email,
                 "negocio_id": a.negocio_id, "negocio": a.negocio_nombre} for a in filas]


@router.get("/fallas")
def fallas():
    """Las últimas 50 fallas de TODAS las cuentas, para el arranque del día."""
    with sesion() as s, inquilino.sin_filtro():
        nombres = {b.id: b.nombre for b in s.exec(select(Business))}
        filas = s.exec(select(Falla).order_by(Falla.cuando.desc()).limit(50))
        return [{"cuando": _iso(f.cuando), "donde": f.donde, "detalle": f.detalle,
                 "negocio_id": f.business_id,
                 "negocio": nombres.get(f.business_id, "—")} for f in filas]
