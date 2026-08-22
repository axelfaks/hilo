"""Lo que se calcula, se calcula. La IA solo escribe lo que hay que interpretar.

La pelota, el silencio y el ritmo salen de los datos, no del modelo: son números
exactos y nunca se alucinan. Esa separacion es lo que hace confiable al briefing.
"""
from datetime import datetime, timedelta
from statistics import median

CANALES = {
    "mail": "Mail",
    "whatsapp": "WhatsApp",
    "instagram": "Instagram",
    "telegram": "Telegram",
    "linkedin": "LinkedIn",
    "llamada": "Llamada",
    "presencial": "Visita",
}

# Los canales por los que se puede escribir. La llamada y la visita se registran,
# no se envian. Y solo el mail tiene asunto.
CANALES_SALIENTES = ["mail", "whatsapp", "instagram", "telegram", "linkedin"]
CANALES_CON_ASUNTO = ["mail"]

NIVELES_AUTONOMIA = [
    ("Silencio", "No hace nada. Ni siquiera resume."),
    ("Observa", "Solo mantiene el resumen al día."),
    ("Sugiere", "Deja el borrador escrito, sin avisarte."),
    ("Pide permiso", "Redacta y te avisa. Vos apretas enviar."),
    ("Responde con barandas", "Envía sola si no toca precio ni temas sensibles."),
    ("Autónoma", "Envía sola siempre, dentro del reglamento del negocio."),
]


def horas(desde: datetime, hasta: datetime | None = None) -> float:
    hasta = hasta or datetime.now()
    return max(0.0, (hasta - desde).total_seconds() / 3600)


def texto_hace(h: float) -> str:
    if h < 1:
        return "hace minutos"
    if h < 24:
        return f"hace {int(h)} h"
    d = int(h // 24)
    return "hace 1 día" if d == 1 else f"hace {d} días"


CERRADOS_POR_DEFECTO = ["Cerrado ganado", "Cerrado", "Ganado", "Perdido", "Descartado"]


def es_cerrado(estado: str, cerrados: list | None = None) -> bool:
    """Un cliente ganado o perdido no le debe respuesta a nadie."""
    lista = cerrados if cerrados else CERRADOS_POR_DEFECTO
    return any(estado.strip().lower() == c.strip().lower() for c in lista)


def pelota(mensajes: list) -> dict:
    """De quien es la pelota, medido en el reloj y no a ojo."""
    if not mensajes:
        return {"de": "nadie", "horas": 0, "texto": "Sin actividad"}
    ultimo = mensajes[-1]
    h = horas(ultimo.creado)
    if ultimo.direccion == "entrante":
        return {
            "de": "nosotros",
            "horas": round(h),
            "texto": f"Le debés respuesta {texto_hace(h)}",
        }
    return {
        "de": "cliente",
        "horas": round(h),
        "texto": f"Esperás respuesta {texto_hace(h)}",
    }


def ritmo(mensajes: list) -> dict:
    """Cuanto suele tardar en contestar este cliente, comparado con ahora."""
    respuestas = []
    for anterior, actual in zip(mensajes, mensajes[1:]):
        if anterior.direccion == "saliente" and actual.direccion == "entrante":
            respuestas.append(horas(anterior.creado, actual.creado))
    promedio = round(median(respuestas)) if respuestas else None
    silencio = round(horas(mensajes[-1].creado)) if mensajes else 0
    fuera = bool(promedio and silencio > promedio * 3)
    return {"promedio_horas": promedio, "silencio_horas": silencio, "fuera_de_ritmo": fuera}


def temperatura(mensajes: list, r: dict) -> dict:
    """Un numero de 0 a 100. Sirve para ordenar la cola por urgencia real."""
    if not mensajes:
        return {"valor": 0, "nivel": "sin datos", "motivo": "Todavía no hablaron"}
    silencio = r["silencio_horas"]
    prom = r["promedio_horas"]
    if prom:
        exceso = silencio / max(prom, 1)
        valor = min(100, int(exceso * 25))
        motivo = f"Suele contestar en {prom} h y van {silencio} h"
    else:
        valor = min(100, int(silencio / 24 * 20))
        motivo = f"{silencio} h desde el último movimiento"
    nivel = "activo"
    if valor >= 75:
        nivel = "frio"
    elif valor >= 45:
        nivel = "enfriandose"
    elif valor >= 20:
        nivel = "tibio"
    return {"valor": valor, "nivel": nivel, "motivo": motivo}


PESO_IMPORTANCIA = {"alta": 1.35, "media": 1.0, "baja": 0.7}


def urgencia(p: dict, t: dict, vencidos: int, cerrado: bool = False,
             importancia: str = "media") -> int:
    """El orden de la cola. Deberle a alguien pesa mas que cualquier otra cosa,
    y la importancia que le puso el vendedor estira o achica todo lo demas."""
    if cerrado:
        return -1
    puntos = 0
    if p["de"] == "nosotros":
        puntos += 500 + min(p["horas"], 240)
    puntos += vencidos * 300
    puntos += t["valor"]
    return int(puntos * PESO_IMPORTANCIA.get(importancia, 1.0))


def dias_de_contacto(alias) -> int:
    return max(1, int(horas(alias.primer_contacto) // 24))


def transcribir_hilo(mensajes: list, limite: int = 22) -> str:
    """El hilo en texto plano, que es lo que va al modelo."""
    lineas = []
    for m in mensajes[-limite:]:
        quien = {"cliente": "CLIENTE", "humano": "VENDEDOR", "ia": "AGENTE IA"}[m.autor]
        canal = CANALES.get(m.canal, m.canal)
        fecha = m.creado.strftime("%d/%m %H:%M")
        # el id va adelante para poder devolver un resumen por mensaje
        falta = "" if m.resumen else " SIN-RESUMEN"
        lineas.append(f"[#{m.id} | {fecha} | {canal} | {quien}{falta}] {m.texto}")
    return "\n".join(lineas)


def por_canal(mensajes: list) -> list:
    """Un corte del hilo por canal: cuantos, cuando fue el ultimo y de quien es
    la pelota EN ESE CANAL. Todo calculado, nada inferido."""
    orden, grupos = [], {}
    for m in mensajes:
        if m.canal not in grupos:
            grupos[m.canal] = []
            orden.append(m.canal)
        grupos[m.canal].append(m)

    salida = []
    for canal in orden:
        ms = grupos[canal]
        ultimo = ms[-1]
        salida.append({
            "canal": canal,
            "label": CANALES.get(canal, canal),
            "cantidad": len(ms),
            "ultimo": ultimo.creado.isoformat(),
            "ultimo_hace": texto_hace(horas(ultimo.creado)),
            # una llamada registrada no le debe respuesta a nadie: se anota, no se contesta
            "pelota": pelota(ms) if canal in CANALES_SALIENTES else None,
            "puede_responder": canal in CANALES_SALIENTES,
        })
    salida.sort(key=lambda x: x["ultimo"], reverse=True)
    return salida


def demoras(mensajes: list) -> tuple:
    """(lo que tardamos nosotros, lo que tardan ellos) en horas, por cada vuelta."""
    nuestras, suyas = [], []
    for anterior, actual in zip(mensajes, mensajes[1:]):
        if anterior.direccion == actual.direccion:
            continue
        h = horas(anterior.creado, actual.creado)
        (nuestras if actual.direccion == "saliente" else suyas).append(h)
    return nuestras, suyas
