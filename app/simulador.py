"""El cliente, interpretado por la IA.

Sirve para dos cosas y las dos importan:
  1. Probar el agente sin esperar a que un humano escriba. Le tirás un turno y ves
     si tu prompt, tus barandas y tu nivel de autonomía hacen lo que creías.
  2. Mostrarlo. Ver a los dos conversando solos y cerrar una venta es la clase de
     cosa que se entiende sin que nadie la explique.

Los mensajes que salen de acá quedan marcados como simulados y se pueden borrar
de un botón, así la base vuelve limpia antes de la demo de verdad.
"""
import json

from sqlmodel import Session, select

from . import ai
from .logic import CANALES, CANALES_SALIENTES, transcribir_hilo
from .models import Alias, Briefing, Identity, Message
from .pipeline import (
    canal_para_responder, construir_briefing, ingesta, mensajes_de, negocio,
    nivel_autonomia,
)


def _canales_del_cliente(s: Session, alias_id: int) -> list:
    canales = [i.canal for i in s.exec(select(Identity).where(Identity.alias_id == alias_id))
               if i.canal in CANALES_SALIENTES]
    return canales or ["mail"]


def _de_reserva(alias: Alias, msgs: list) -> dict:
    """Sin IA el botón tiene que seguir haciendo algo: usamos las respuestas
    sembradas de este cliente, en orden."""
    opciones = json.loads(alias.respuestas_demo_json or "[]")
    if not opciones:
        return {"texto": "Seguimos esperando novedades de su lado.", "temperatura": "igual"}
    usados = sum(1 for m in msgs if m.simulado and m.direccion == "entrante")
    return {"texto": opciones[usados % len(opciones)], "temperatura": "igual",
            "por_que": "Respuesta de reserva: la IA no está conectada."}


def hablar_como_cliente(s: Session, alias: Alias, canal_pedido: str | None = None) -> dict:
    """Genera y mete el próximo mensaje del cliente."""
    b = negocio(s)
    msgs = mensajes_de(s, alias.id)
    canales = _canales_del_cliente(s, alias.id)

    r = ai.responder_como_cliente(
        alias_nombre=alias.nombre, contacto=alias.contacto, persona=alias.persona,
        negocio=f"{b.nombre}. {b.descripcion}", hilo=transcribir_hilo(msgs),
        canales=[CANALES[c] for c in canales],
    )
    if not r.get("texto"):
        r = {**_de_reserva(alias, msgs), **{k: v for k, v in r.items() if v}}

    # el canal que eligió el modelo viene con la etiqueta linda; lo traducimos
    canal = canal_pedido if canal_pedido in canales else None
    if not canal:
        etiqueta = (r.get("canal") or "").strip().lower()
        canal = next((c for c in canales if CANALES[c].lower() == etiqueta), None)
    if not canal:
        ultimo = next((m.canal for m in reversed(msgs)
                       if m.direccion == "entrante" and m.canal in canales), None)
        canal = ultimo or canales[0]

    ident = s.exec(select(Identity).where(
        Identity.alias_id == alias.id, Identity.canal == canal)).first()
    remitente = ident.valor if ident else f"{alias.token}@demo"

    resultado = ingesta(s, canal, remitente, r["texto"], simulado=True)
    return {
        "texto": r["texto"],
        "canal": canal,
        "canal_label": CANALES[canal],
        "temperatura": r.get("temperatura", "igual"),
        "por_que": r.get("por_que", ""),
        "listo_para_cerrar": bool(r.get("listo_para_cerrar")),
        "se_va": bool(r.get("se_va")),
        "agente": resultado.get("agente", {}),
    }


def _mandar_borrador(s: Session, alias: Alias, agente: dict) -> dict | None:
    """En modo conversación el agente contesta aunque su nivel pida permiso:
    estamos probando, no vendiendo. Las barandas se siguen respetando."""
    borrador = (agente or {}).get("borrador")
    if not borrador or borrador.get("escalar") or agente.get("accion") == "enviado":
        return None
    s.add(Message(alias_id=alias.id, canal=borrador["canal"], direccion="saliente",
                  autor="ia", texto=borrador["texto"], asunto=borrador.get("asunto", ""),
                  aprobado_por="simulación", simulado=True))
    s.commit()
    construir_briefing(s, alias)
    return borrador


def conversar(s: Session, alias_id: int, turnos: int = 1, auto: bool = False) -> dict:
    """Una ronda = el cliente escribe y, si auto está prendido, el agente contesta."""
    rondas = []
    for _ in range(max(1, min(turnos, 6))):
        alias = s.get(Alias, alias_id)
        cliente = hablar_como_cliente(s, alias)
        ronda = {"cliente": cliente, "agente": cliente.get("agente", {}), "respuesta": None}
        if auto:
            alias = s.get(Alias, alias_id)
            ronda["respuesta"] = _mandar_borrador(s, alias, ronda["agente"])
        rondas.append(ronda)
        if cliente["se_va"] or cliente["listo_para_cerrar"]:
            break
    return {"rondas": rondas}


def limpiar(s: Session, alias_id: int) -> int:
    """Borra todo lo simulado y deja la ficha como estaba."""
    borrados = 0
    for m in s.exec(select(Message).where(Message.alias_id == alias_id,
                                          Message.simulado == True)):  # noqa: E712
        s.delete(m)
        borrados += 1
    s.commit()
    alias = s.get(Alias, alias_id)
    if alias:
        construir_briefing(s, alias)
    return borrados
