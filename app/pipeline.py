"""Lo que pasa cuando entra un mensaje. Es el corazon de la demo."""
import json
from datetime import datetime

from sqlmodel import Session, select

from . import ai, correo, inquilino, whatsapp
from .logic import (
    CANALES, CANALES_SALIENTES, dias_de_contacto, pelota, por_canal, ritmo,
    temperatura, transcribir_hilo,
)
from .models import Alias, Briefing, Business, Commitment, Identity, Message


# ------------------------------------------------------------------ utilidades


def direccion_de(s: Session, alias_id: int, canal: str = "mail") -> str:
    """La dirección del cliente en ese canal, si la tenemos."""
    fila = s.exec(
        select(Identity).where(Identity.alias_id == alias_id, Identity.canal == canal)
    ).first()
    return (fila.valor if fila else "").strip()


def despachar(s: Session, alias: Alias, canal: str, asunto: str, texto: str,
              cc: str = "", cco: str = "") -> tuple[bool, str]:
    """Saca el mensaje por el canal de verdad, si ese canal existe de verdad.

    Hoy son dos: el mail y WhatsApp. Los demás siguen simulados y devuelven
    (False, "") sin ruido: no es un error que Instagram no salga, es que todavía
    no está enchufado. Devuelve (salió de verdad, error).
    """
    if canal == "mail" and correo.configurado():
        destino = direccion_de(s, alias.id, "mail")
        if not destino:
            return False, f"{alias.nombre} no tiene una dirección de mail cargada"
        return correo.enviar(destino, asunto, texto, cc=cc, cco=cco)

    if canal == "whatsapp" and whatsapp.configurado():
        destino = direccion_de(s, alias.id, "whatsapp")
        if not destino:
            return False, f"{alias.nombre} no tiene un número de WhatsApp cargado"
        # La ventana de 24 h se chequea ANTES de gastar el request. No es una
        # optimización: adentro de la ventana responder es GRATIS, afuera hace
        # falta una plantilla aprobada y se cobra. Que el vendedor lo sepa antes
        # de apretar enviar vale más que el error críptico de Meta después.
        ultimo = s.exec(
            select(Message)
            .where(Message.alias_id == alias.id,
                   Message.canal == "whatsapp",
                   Message.direccion == "entrante")
            .order_by(Message.creado.desc())
        ).first()
        if not whatsapp.ventana_abierta(ultimo.creado if ultimo else None):
            return False, (
                f"Pasaron más de {whatsapp.VENTANA_HORAS} h desde el último mensaje "
                f"de {alias.nombre}. Para reabrir la conversación hace falta una "
                f"plantilla aprobada por Meta."
            )
        return whatsapp.enviar(destino, texto)

    return False, ""



def negocio(s: Session) -> Business:
    """El negocio del inquilino actual.

    `Business` no está en la lista de modelos que se filtran solos —se busca por
    su propio id— así que acá el inquilino se lee a mano. Es el único lugar.
    """
    negocio_id = inquilino.actual()
    if negocio_id is not None:
        b = s.get(Business, negocio_id)
        if b:
            return b
    # Sin inquilino puesto: el primero. Es lo que pasa en los scripts (seed,
    # empezar_de_cero) y en una instalación de un solo negocio.
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


# Dominios donde compartir el dominio no significa NADA: que dos personas usen
# Gmail no las hace la misma empresa. Sin esta lista, el primer mail que llega de
# un particular "se parece" al primer cliente que también tenga un Gmail, y el
# sistema afirma con cara seria algo que es falso.
DOMINIOS_PUBLICOS = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.com.ar", "hotmail.es",
    "outlook.com", "outlook.com.ar", "outlook.es", "live.com", "live.com.ar",
    "yahoo.com", "yahoo.com.ar", "yahoo.es", "icloud.com", "me.com", "mac.com",
    "aol.com", "proton.me", "protonmail.com", "gmx.com", "zoho.com", "mail.com",
    "yandex.com", "fibertel.com.ar", "speedy.com.ar", "arnet.com.ar",
    "ciudad.com.ar", "hotmail.com.mx", "terra.com.ar",
}

# Debajo de esto no se sugiere nada: una corazonada floja mostrada como dato es
# peor que un "no sé". El vendedor termina fusionando mal y ensuciando un hilo.
CONFIANZA_MINIMA = 55


def _dominio(direccion: str) -> str:
    d = (direccion or "").strip().lower()
    return d.split("@")[-1] if "@" in d else ""


def _partes_del_nombre(texto: str) -> set:
    """Palabras de cuatro letras o más, sin acentos, para comparar nombres.

    Sin sacar los acentos, "rodriguez" escrito en una dirección de mail nunca
    coincide con "Rodríguez" escrito en la ficha, que es justo el caso que esto
    tiene que detectar.
    """
    import re as _re
    import unicodedata as _ud
    plano = _ud.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return {p for p in _re.split(r"[^a-z]+", plano.lower()) if len(p) >= 4}


def sugerir_alias(s: Session, remitente: str, texto: str) -> tuple:
    """Para los mensajes que llegan sin alias: a quien se parecen.

    La regla de la casa: si no hay un motivo de verdad, se devuelve None. Un
    sistema que inventa parecidos hace que el vendedor deje de creerle, y
    entonces no sirve para nada ni siquiera cuando acierta.
    """
    candidatos = []
    for a in s.exec(select(Alias)):
        ids = [i.valor for i in s.exec(select(Identity).where(Identity.alias_id == a.id))]
        candidatos.append({"id": a.id, "nombre": a.nombre, "contacto": a.contacto, "identidades": ids})
    if not candidatos:
        return None, 0, ""
    r = ai.identificar(remitente, texto, candidatos)
    if r.get("alias_id"):
        confianza = int(r.get("confianza", 0))
        if confianza >= CONFIANZA_MINIMA:
            return r["alias_id"], confianza, r.get("motivo", "")
        return None, 0, ""
    if r:
        # La IA contestó, leyó el hilo entero y dijo que no se parece a ninguno.
        # Una heurística de dominio no sabe más que ella: respetar el "no sé".
        return None, 0, ""

    # De acá para abajo: no hubo IA. Solo evidencia dura, nada de corazonadas.
    dominio = _dominio(remitente)
    if dominio and dominio not in DOMINIOS_PUBLICOS:
        for c in candidatos:
            # comparación exacta de dominio: "mail.com" no es "gmail.com"
            if any(_dominio(i) == dominio for i in c["identidades"] if "@" in i):
                return c["id"], 70, f"Le escriben desde el mismo dominio: @{dominio}"

    # El nombre en la dirección: juan.rodriguez@… contra el contacto del cliente.
    # Hacen falta DOS palabras en común, no una: "juan@" coincidiendo con "Juan
    # Rodríguez" no es evidencia de nada, hay un Juan en cada cartera de clientes.
    local = _partes_del_nombre(remitente.split("@")[0] if "@" in remitente else "")
    if len(local) >= 2:
        for c in candidatos:
            propias = _partes_del_nombre(c["nombre"] + " " + c.get("contacto", ""))
            comunes = local & propias
            if len(comunes) >= 2:
                return (c["id"], 65,
                        "El nombre de la dirección coincide con " + c["nombre"] +
                        ": " + ", ".join(sorted(comunes)))

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
        # Si el canal es real, el mensaje sale de verdad ANTES de quedar en el
        # hilo: que el hilo diga "enviado" para algo que nunca salió es peor que
        # no enviarlo. Si falla, queda registrado igual y el error va al estado
        # del correo — el vendedor lo ve en Configuración.
        salio, error = despachar(s, alias, canal_respuesta, borrador["asunto"], borrador["texto"])
        s.add(Message(
            alias_id=alias.id, canal=canal_respuesta, direccion="saliente", autor="ia",
            texto=borrador["texto"], asunto=borrador["asunto"], simulado=simulado,
        ))
        s.commit()
        return {"accion": "enviado", "nivel": nivel, "borrador": borrador,
                "por_mail": salio, "error_envio": error}

    accion = "borrador_para_aprobar" if nivel == 3 else "borrador"
    if freno:
        accion = "escalado"
    return {"accion": accion, "nivel": nivel, "borrador": borrador}


# ------------------------------------------------------------------- ingesta

def ingesta(s: Session, canal: str, remitente: str, texto: str, adjuntos: list | None = None,
            simulado: bool = False, html: str = "", asunto: str = "",
            externo_id: str = "", remitente_nombre: str = "") -> dict:
    """La UNICA puerta por la que entra un mensaje. Un mail real, manana, entra por aca."""
    # Idempotencia. Todos los webhooks reintentan cuando dudan de la respuesta, y
    # Meta reintenta bastante: sin esto, el mismo mensaje aparece tres veces en el
    # hilo, la IA lo resume tres veces y el vendedor deja de creerle a la ficha.
    if externo_id:
        repetido = s.exec(select(Message).where(Message.externo_id == externo_id)).first()
        if repetido:
            return {"duplicado": True, "mensaje_id": repetido.id,
                    "alias_id": repetido.alias_id,
                    "identificado": repetido.alias_id is not None}

    alias_id = resolver(s, canal, remitente)
    msg = Message(
        alias_id=alias_id, canal=canal, direccion="entrante", autor="cliente",
        texto=texto, remitente=remitente, simulado=simulado, html=html, asunto=asunto,
        externo_id=externo_id, remitente_nombre=(remitente_nombre or "").strip()[:120],
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
