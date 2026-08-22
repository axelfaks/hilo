"""Lo que pasa cuando entra un mensaje. Es el corazon de la demo."""
import json
from datetime import datetime

from sqlmodel import Session, select

from . import ai
from .logic import (
    CANALES, CANALES_SALIENTES, dias_de_contacto, pelota, por_canal, ritmo,
    temperatura, transcribir_hilo,
)
from .models import Alias, Briefing, Business, Commitment, Identity, Message


# ------------------------------------------------------------------ utilidades

def negocio(s: Session) -> Business:
    b = s.exec(select(Business)).first()
    if not b:
        b = Business()
        s.add(b)
        s.commit()
        s.refresh(b)
    return b


def etapas(b: Business) -> list:
    return json.loads(b.estados_json) or ["Nuevo", "En conversacion", "Cerrado"]


def reglas(b: Business) -> dict:
    return json.loads(b.reglas_json) or {}


def mensajes_de(s: Session, alias_id: int) -> list:
    return list(s.exec(
        select(Message).where(Message.alias_id == alias_id).order_by(Message.creado)
    ))


def nivel_autonomia(alias: Alias, b: Business) -> int:
    return alias.autonomia if alias.autonomia is not None else b.autonomia_default


# ------------------------------------------------------- resolucion de identidad

def resolver(s: Session, canal: str, valor: str) -> int | None:
    ident = s.exec(
        select(Identity).where(Identity.canal == canal, Identity.valor == valor)
    ).first()
    if ident:
        return ident.alias_id
    # el mismo valor por otro canal tambien sirve (un telefono en WhatsApp y en Telegram)
    ident = s.exec(select(Identity).where(Identity.valor == valor)).first()
    return ident.alias_id if ident else None


def sugerir_alias(s: Session, remitente: str, texto: str) -> tuple:
    """Para los mensajes que llegan sin alias: a quien se parecen."""
    candidatos = []
    for a in s.exec(select(Alias)):
        ids = [i.valor for i in s.exec(select(Identity).where(Identity.alias_id == a.id))]
        candidatos.append({"id": a.id, "nombre": a.nombre, "contacto": a.contacto, "identidades": ids})
    if not candidatos:
        return None, 0, ""
    r = ai.identificar(remitente, texto, candidatos)
    if r.get("alias_id"):
        return r["alias_id"], int(r.get("confianza", 0)), r.get("motivo", "")
    # sin IA: el dominio del mail alcanza para una sugerencia decente
    if "@" in remitente:
        dominio = remitente.split("@")[-1].lower()
        for c in candidatos:
            if any(dominio in i.lower() for i in c["identidades"] if "@" in i):
                return c["id"], 85, f"Mismo dominio de mail: {dominio}"
    return None, 0, ""


# --------------------------------------------------------------------- briefing

def _offline(alias: Alias, msgs: list, previo: dict, etps: list) -> dict:
    """Sin IA la ficha no queda vacia: se refresca lo calculable y se conserva
    lo cualitativo que ya habia."""
    d = dict(previo)
    entrantes = [m for m in msgs if m.direccion == "entrante"]
    if entrantes:
        ultimo = entrantes[-1].texto.strip().replace("\n", " ")
        bullet = f"Lo último que dijo: «{ultimo[:150]}»"
        anteriores = [x for x in d.get("lo_ultimo", []) if not x.startswith("Lo último que dijo:")]
        d["lo_ultimo"] = [bullet] + anteriores[:2]
    d.setdefault("quien_es", alias.notas or f"{alias.contacto or alias.nombre}, {alias.rubro}".strip(", "))
    d.setdefault("estado", alias.estado if alias.estado in etps else etps[0])
    d.setdefault("proximo_paso", "")
    d.setdefault("senal_de_urgencia", "")
    d["sin_ia"] = True
    return d


def construir_briefing(s: Session, alias: Alias) -> dict:
    b = negocio(s)
    etps = etapas(b)
    msgs = mensajes_de(s, alias.id)

    fila = s.exec(select(Briefing).where(Briefing.alias_id == alias.id)).first()
    previo = json.loads(fila.data_json) if fila else {}

    fresco = ai.briefing(transcribir_hilo(msgs), etps, alias.nombre)
    data = fresco if fresco else _offline(alias, msgs, previo, etps)

    # lo medible se calcula siempre aca, nunca lo escribe el modelo
    p = pelota(msgs)
    r = ritmo(msgs)
    data["pelota"] = p
    data["ritmo"] = r
    data["temperatura"] = temperatura(msgs, r)
    data["dias_contacto"] = dias_de_contacto(alias)
    data["canales"] = sorted({m.canal for m in msgs})

    # el corte por canal: los numeros salen de aca, el texto lo pone la IA.
    # Ojo: si venimos de un recalculo, "por_canal" ya es la lista de la vuelta
    # anterior y no el diccionario del modelo. Conservamos sus textos.
    crudo = data.get("por_canal")
    if isinstance(crudo, dict):
        textos = crudo
    elif isinstance(crudo, list):
        textos = {c.get("canal"): c.get("resumen", "")
                  for c in crudo if isinstance(c, dict) and c.get("canal")}
    else:
        textos = {}
    cortes = por_canal(msgs)
    for c in cortes:
        c["resumen"] = textos.get(c["canal"], "")
        if not c["resumen"]:
            ultimos = [m for m in msgs if m.canal == c["canal"]][-1:]
            if ultimos:
                c["resumen"] = f"Lo último por acá: «{ultimos[0].texto.strip()[:170]}»"
    data["por_canal"] = cortes
    data["generado"] = datetime.now().isoformat(timespec="seconds")
    # el borrador pertenece al mensaje que lo disparo: no sobrevive al recalculo
    data.pop("borrador", None)
    data.pop("accion_agente", None)

    if fresco:
        _guardar_resumenes(s, fresco.get("resumen_mensajes") or {})
        _guardar_compromisos(s, alias.id, fresco.get("compromisos", []))
        # La IA NO mueve la etapa: la propone. El vendedor decide.
        nuevo_estado = fresco.get("estado", "")
        if nuevo_estado in etps and nuevo_estado != alias.estado:
            alias.estado_sugerido = nuevo_estado
            alias.estado_sugerido_motivo = fresco.get("por_que_estado", "")
            s.add(alias)
        elif nuevo_estado == alias.estado and alias.estado_sugerido:
            alias.estado_sugerido = ""          # la sugerencia quedó vieja
            alias.estado_sugerido_motivo = ""
            s.add(alias)

    if fila:
        fila.data_json = json.dumps(data, ensure_ascii=False)
        fila.generado = datetime.now()
    else:
        fila = Briefing(alias_id=alias.id, data_json=json.dumps(data, ensure_ascii=False))
    s.add(fila)
    s.commit()
    return data


def _guardar_resumenes(s: Session, mapa: dict):
    """La linea de contexto que va arriba de cada mensaje en el hilo."""
    for clave, texto in mapa.items():
        try:
            mid = int(str(clave).lstrip("#"))
        except ValueError:
            continue
        m = s.get(Message, mid)
        if m and texto and not m.resumen:
            m.resumen = str(texto)[:200]
            s.add(m)
    s.commit()


def _guardar_compromisos(s: Session, alias_id: int, lista: list):
    for c in s.exec(select(Commitment).where(Commitment.alias_id == alias_id, Commitment.cumplido == False)):  # noqa: E712
        s.delete(c)
    for c in lista[:6]:
        vence = None
        if c.get("vence"):
            try:
                vence = datetime.fromisoformat(c["vence"])
            except ValueError:
                vence = None
        s.add(Commitment(
            alias_id=alias_id,
            de_quien=c.get("de_quien", "nosotros"),
            texto=c.get("texto", "")[:300],
            vence=vence,
        ))
    s.commit()


# ----------------------------------------------------------------- el agente

def _rompe_barandas(texto_cliente: str, rls: dict) -> str:
    for tema in rls.get("temas_escalan", []):
        if tema.lower() in texto_cliente.lower():
            return f"El cliente mencionó «{tema}», que está marcado para escalar a un humano"
    return ""


def _en_horario(rls: dict) -> bool:
    desde, hasta = rls.get("horario", [8, 20])
    return desde <= datetime.now().hour < hasta


def canal_para_responder(msgs: list) -> str:
    """Por donde conviene contestar: el ultimo canal por el que el cliente escribio,
    si es un canal por el que se puede escribir. Si no, mail."""
    for m in reversed(msgs):
        if m.direccion == "entrante" and m.canal in CANALES_SALIENTES:
            return m.canal
    return "mail"


def actuar(s: Session, alias: Alias, canal_respuesta: str, simulado: bool = False,
           tono: str = "") -> dict:
    """Que hace el agente al entrar un mensaje, segun su nivel para este cliente."""
    b = negocio(s)
    nivel = nivel_autonomia(alias, b)
    if nivel <= 1:
        return {"accion": "nada", "nivel": nivel}

    msgs = mensajes_de(s, alias.id)
    entrantes = [m for m in msgs if m.direccion == "entrante"]
    ultimo_texto = entrantes[-1].texto if entrantes else ""
    rls = reglas(b)

    r = ai.redactar(transcribir_hilo(msgs), rls, alias.nombre, canal_respuesta, tono)
    if not r:
        r = {
            "asunto": f"Sobre lo que veníamos hablando",
            "texto": "Hola, perdón la demora. Te contesto en un rato con el detalle.",
            "escalar": False,
            "motivo_escalada": "",
        }

    freno = r.get("motivo_escalada", "") if r.get("escalar") else _rompe_barandas(ultimo_texto, rls)
    if canal_respuesta not in CANALES_SALIENTES:
        canal_respuesta = canal_para_responder(msgs)
    borrador = {
        "asunto": r.get("asunto", "") if canal_respuesta == "mail" else "",
        "texto": r.get("texto", ""),
        "canal": canal_respuesta,
        "escalar": bool(freno),
        "motivo_escalada": freno,
    }

    envia_solo = nivel >= 4 and not freno and _en_horario(rls)
    if envia_solo:
        s.add(Message(
            alias_id=alias.id, canal=canal_respuesta, direccion="saliente", autor="ia",
            texto=borrador["texto"], asunto=borrador["asunto"], simulado=simulado,
        ))
        s.commit()
        return {"accion": "enviado", "nivel": nivel, "borrador": borrador}

    accion = "borrador_para_aprobar" if nivel == 3 else "borrador"
    if freno:
        accion = "escalado"
    return {"accion": accion, "nivel": nivel, "borrador": borrador}


# ------------------------------------------------------------------- ingesta

def ingesta(s: Session, canal: str, remitente: str, texto: str, adjuntos: list | None = None,
            simulado: bool = False) -> dict:
    """La UNICA puerta por la que entra un mensaje. Un mail real, manana, entra por aca."""
    alias_id = resolver(s, canal, remitente)
    msg = Message(
        alias_id=alias_id, canal=canal, direccion="entrante", autor="cliente",
        texto=texto, remitente=remitente, simulado=simulado,
        adjuntos_json=json.dumps(adjuntos or [], ensure_ascii=False),
    )

    if alias_id is None:
        sug, score, motivo = sugerir_alias(s, remitente, texto)
        msg.sugerencia_alias_id, msg.sugerencia_score, msg.sugerencia_motivo = sug, score, motivo
        s.add(msg)
        s.commit()
        s.refresh(msg)
        return {"identificado": False, "mensaje_id": msg.id,
                "sugerencia": {"alias_id": sug, "confianza": score, "motivo": motivo}}

    s.add(msg)
    s.commit()
    alias = s.get(Alias, alias_id)
    brief = construir_briefing(s, alias)
    resultado = actuar(s, alias, canal, simulado=simulado)
    if resultado["accion"] != "nada":
        brief["borrador"] = resultado.get("borrador")
        brief["accion_agente"] = resultado["accion"]
        fila = s.exec(select(Briefing).where(Briefing.alias_id == alias.id)).first()
        fila.data_json = json.dumps(brief, ensure_ascii=False)
        s.add(fila)
        s.commit()
    return {"identificado": True, "alias_id": alias_id, "briefing": brief, "agente": resultado}
