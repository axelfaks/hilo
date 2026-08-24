"""Los planes: qué cuesta cada uno y hasta dónde llega.

Dos ideas que conviene no perder:

**El precio vive en la cuenta, no en el plan.** El catálogo de acá abajo es solo
el valor por defecto que se propone al elegir un plan; después cada cuenta tiene
su `precio_mensual` y se puede tocar. Los primeros diez clientes de cualquier
producto pagan precios distintos —uno porque entró temprano, otro porque
regateó— y una tabla de precios rígida obliga a mentirle a la base.

**Las cuotas avisan, no cortan.** Pasarse del límite prende un aviso en la app
del cliente y una barra roja en el back-office. Cortarle el servicio a alguien
que está usando el producto de más es la peor manera de empezar una conversación
sobre plata. Cortar es una decisión nuestra, a mano, y se llama suspender.
"""

# Los precios son en pesos por mes y son un punto de partida, no una verdad:
# están para que registrar un cobro no arranque en cero, y se editan por cuenta.
PLANES = {
    "prueba": {
        "nombre": "Prueba",
        "precio": 0,
        "limites": {"clientes": 25, "mensajes_mes": 500, "ia_mes": 600},
        "para": "las dos primeras semanas, para ver si engancha",
    },
    "basico": {
        "nombre": "Básico",
        "precio": 25000,
        "limites": {"clientes": 150, "mensajes_mes": 4000, "ia_mes": 4000},
        "para": "un vendedor solo con sus canales",
    },
    "pro": {
        "nombre": "Pro",
        "precio": 60000,
        "limites": {"clientes": 1500, "mensajes_mes": 40000, "ia_mes": 40000},
        "para": "un equipo, con varios canales y volumen",
    },
}

ORDEN = ("prueba", "basico", "pro")

MEDIOS = ("transferencia", "mercadopago", "efectivo", "otro")


def plan(nombre: str) -> dict:
    return PLANES.get(nombre or "prueba", PLANES["prueba"])


def limites(nombre: str) -> dict:
    return plan(nombre)["limites"]


def precio_sugerido(nombre: str) -> int:
    return plan(nombre)["precio"]


def catalogo() -> list:
    """Para el front: la lista ordenada, con todo lo que hace falta mostrar."""
    return [dict(clave=c, **PLANES[c]) for c in ORDEN]


def pasados(uso: dict, nombre: str) -> list:
    """Qué límites se pasó esta cuenta. Devuelve una lista de avisos legibles.

    Se compara contra el plan, no contra lo que paga: alguien que se pasa del
    Básico no está haciendo nada malo, está listo para el Pro. Ese es el tono.
    """
    lim = limites(nombre)
    avisos = []
    if uso.get("clientes", 0) > lim["clientes"]:
        avisos.append(f"{uso['clientes']} clientes, y el plan {plan(nombre)['nombre']} "
                      f"llega hasta {lim['clientes']}")
    if uso.get("mensajes_mes", 0) > lim["mensajes_mes"]:
        avisos.append(f"{uso['mensajes_mes']} mensajes este mes, y el plan "
                      f"llega hasta {lim['mensajes_mes']}")
    if uso.get("ia_mes", 0) > lim["ia_mes"]:
        avisos.append(f"{uso['ia_mes']} respuestas con IA este mes, y el plan "
                      f"llega hasta {lim['ia_mes']}")
    return avisos
