"""La plata: quién paga, hasta cuándo, y cuánto entró.

Hoy no hay pasarela y está bien que no la haya. Alguien transfiere, nosotros lo
marcamos en el back-office y `Business.pagado_hasta` se corre sola. Todo el resto
—al día, vencido, cuánto falta cobrar— **se deduce de esa fecha**: no hay dos
lugares que puedan contradecirse.

Cuando haya diez clientes pagando y valga la pena enchufar Mercado Pago, lo único
que cambia es quién llama a `registrar()`. El libro ya va a estar escrito.
"""
import calendar
from datetime import datetime, timedelta

from sqlmodel import func, select

from . import planes
from .models import Alias, Business, Cobro, Message, UsoIA

# Cuántos días antes de vencer una cuenta se pone amarilla. Una semana alcanza
# para mandar un mensaje y que el otro tenga tiempo de pagar sin apuro.
DIAS_DE_AVISO = 7

# La prueba gratis: entra sin tarjeta, carga sus canales y ve su Hilo con datos
# de verdad. Es lo que convence; pedir la tarjeta antes de mostrar nada no.
DIAS_DE_PRUEBA = 7

# Los días que la cuenta sigue andando DESPUÉS de vencer, con el aviso en rojo.
#
# Se los damos solo a quien ya pagó alguna vez, y el motivo es que la gracia
# existe para una tarjeta que rebota, no para postergar una decisión: al que
# venía pagando no se le apaga el producto por un accidente de cobro, y al que
# nunca puso una tarjeta la prueba se le termina el día que se le termina.
DIAS_DE_GRACIA = 3


def sumar_meses(desde: datetime, meses: int) -> datetime:
    """Un mes es "el mismo día del mes que viene", no 30 días.

    Con 30 días, el que paga el 31 de enero termina cobrado el 2 de marzo y a los
    dos años le regalaste un mes. Y el 31 de un mes que no tiene 31 cae al último
    día que exista.
    """
    total = desde.month - 1 + meses
    anio = desde.year + total // 12
    mes = total % 12 + 1
    dia = min(desde.day, calendar.monthrange(anio, mes)[1])
    return desde.replace(year=anio, month=mes, day=dia)


def acceso_hasta(b: Business):
    """Hasta cuándo tiene acceso esta cuenta. UNA fecha, no dos.

    La prueba y lo pagado contestan la misma pregunta, así que se resuelven
    juntas con un `max()`. Tener dos caminos —uno para el que prueba y otro para
    el que paga— es tener dos lugares donde el corte puede fallar distinto.
    """
    fechas = [f for f in (b.prueba_hasta, b.pagado_hasta) if f]
    return max(fechas) if fechas else None


def dias_de_gracia(b: Business) -> int:
    """Solo para el que ya pagó alguna vez. Ver el comentario de DIAS_DE_GRACIA."""
    return DIAS_DE_GRACIA if b.paga_desde else 0


def estado(b: Business) -> dict:
    """En qué anda esta cuenta. Una palabra, los días, y si puede entrar.

    prueba       · adentro de la prueba gratis, nunca pagó
    al_dia       · pagada, le sobra tiempo
    vence_pronto · le quedan 7 días o menos
    en_gracia    · se le pasó la fecha pero sigue entrando (3 días, y solo si ya
                   pagó alguna vez): una tarjeta que rebota no apaga el producto
    cortada      · se acabó todo. La app le pide la tarjeta y no la deja pasar
    sin_precio   · no le pusimos precio ni prueba — el caso de las cuentas viejas

    **`puede_entrar` es lo único que mira la puerta.** El corte no es un campo
    que alguien tiene que acordarse de escribir: se deduce de la fecha. Un cron
    que no corrió no puede regalar meses.
    """
    hasta = acceso_hasta(b)
    gracia = dias_de_gracia(b)
    base = {
        "precio": b.precio_mensual or 0,
        "plan": b.plan or "prueba",
        "pagado_hasta": b.pagado_hasta.isoformat() if b.pagado_hasta else "",
        "prueba_hasta": b.prueba_hasta.isoformat() if b.prueba_hasta else "",
        "paga_desde": b.paga_desde.isoformat() if b.paga_desde else "",
        "acceso_hasta": hasta.isoformat() if hasta else "",
        "dias_de_gracia": gracia,
        "tarjeta": b.tarjeta or "",
        "suscripcion": b.suscripcion_estado or "",
        "pago_automatico": b.suscripcion_estado == "activa",
    }
    if not hasta:
        # Nunca tuvo prueba ni pago: son las cuentas de antes de que esto
        # existiera. No se les corta nada; hay que ponerles precio a mano.
        return dict(base, estado="sin_precio", dias=None, puede_entrar=True)

    dias = (hasta.date() - datetime.now().date()).days
    en_prueba = not b.paga_desde
    if dias < -gracia:
        return dict(base, estado="cortada", dias=dias, puede_entrar=False,
                    por_que="se acabó la prueba" if en_prueba else "no entró el pago")
    if dias < 0:
        return dict(base, estado="en_gracia", dias=dias, puede_entrar=True,
                    corta_en=gracia + dias)
    if en_prueba:
        return dict(base, estado="prueba", dias=dias, puede_entrar=True)
    if dias <= DIAS_DE_AVISO:
        return dict(base, estado="vence_pronto", dias=dias, puede_entrar=True)
    return dict(base, estado="al_dia", dias=dias, puede_entrar=True)


def puede_entrar(b: Business) -> bool:
    """Lo que pregunta la puerta en cada request. Barato: son dos restas."""
    return bool(estado(b)["puede_entrar"])


def empezar_la_prueba(b: Business):
    """Le arranca la prueba a una cuenta nueva. Se llama al crearla."""
    if not b.prueba_hasta:
        b.prueba_hasta = datetime.now() + timedelta(days=DIAS_DE_PRUEBA)
    return b


def ya_registrado(s, externo_id: str) -> bool:
    """¿Ya anotamos este pago? Mercado Pago manda el mismo aviso varias veces."""
    if not externo_id:
        return False
    return s.exec(select(Cobro).where(Cobro.externo_id == externo_id)).first() is not None


def registrar(s, b: Business, monto: int, medio: str, meses: int,
              nota: str = "", quien: str = "", externo_id: str = "") -> Cobro:
    """Marca que entró plata y corre la fecha hasta dónde está paga la cuenta.

    El período nuevo arranca en `pagado_hasta` si todavía no venció —así el que
    paga adelantado no pierde los días que le quedaban— y en hoy si ya venció:
    cobrarle a alguien tres meses después de que se fue no le regala los meses
    que estuvo sin usar el producto.
    """
    hoy = datetime.now()
    arranque = b.pagado_hasta if (b.pagado_hasta and b.pagado_hasta > hoy) else hoy
    b.pagado_hasta = sumar_meses(arranque, max(1, meses))
    if not b.paga_desde:
        b.paga_desde = hoy
    if not b.precio_mensual and monto:
        b.precio_mensual = monto // max(1, meses)
    c = Cobro(business_id=b.id, monto=monto, medio=medio, meses=max(1, meses),
              periodo_hasta=b.pagado_hasta, nota=nota[:500], quien=quien,
              externo_id=externo_id)
    s.add(b)
    s.add(c)
    s.commit()
    s.refresh(c)
    return c


# --------------------------------------------------------------------- uso

def _primero_del_mes() -> datetime:
    hoy = datetime.now()
    return hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def uso_del_mes(s, negocio_id: int) -> dict:
    """Lo que consumió esta cuenta: clientes en total, y del mes en curso los
    mensajes y las llamadas a la IA. Es contra esto que se miden las cuotas."""
    desde = _primero_del_mes()
    clientes = s.exec(select(func.count()).select_from(Alias)
                      .where(Alias.business_id == negocio_id)).one() or 0
    mensajes = s.exec(select(func.count()).select_from(Message)
                      .where(Message.business_id == negocio_id,
                             Message.simulado == False,                  # noqa: E712
                             Message.creado >= desde)).one() or 0
    ia = sum(f.llamadas for f in s.exec(
        select(UsoIA).where(UsoIA.business_id == negocio_id,
                            UsoIA.dia >= desde.strftime("%Y-%m-%d"))))
    return {"clientes": clientes, "mensajes_mes": mensajes, "ia_mes": ia}


def cuota(s, b: Business) -> dict:
    """El bloque que ve el cliente en su propia app: uso, límites y avisos.

    Avisa, no corta. Si se pasó, el mensaje dice que está listo para el plan que
    sigue, no que hizo algo mal.
    """
    uso = uso_del_mes(s, b.id)
    return {"plan": b.plan or "prueba",
            "limites": planes.limites(b.plan),
            "uso": uso,
            "pasado": planes.pasados(uso, b.plan)}


# ------------------------------------------------------------------ totales

def resumen(s, negocios: list) -> dict:
    """Los cuatro números de plata del back-office.

    `mrr` no cuenta las suspendidas: si no puede entrar, no es ingreso recurrente
    por más que la fila siga en la base.
    """
    desde = _primero_del_mes()
    cobrado = sum(c.monto for c in s.exec(select(Cobro).where(Cobro.cuando >= desde)))
    mrr = vencido = por_vencer = 0
    cuentas_vencidas = cuentas_por_vencer = 0
    en_prueba = cortadas = con_tarjeta = 0
    for b in negocios:
        e = estado(b)
        if b.estado != "suspendida" and e["estado"] in ("al_dia", "vence_pronto"):
            mrr += e["precio"]
        if e["estado"] in ("en_gracia", "cortada"):
            vencido += e["precio"]
            cuentas_vencidas += 1
        elif e["estado"] == "vence_pronto":
            por_vencer += e["precio"]
            cuentas_por_vencer += 1
        if e["estado"] == "prueba":
            en_prueba += 1
        if e["estado"] == "cortada":
            cortadas += 1
        if e["pago_automatico"]:
            con_tarjeta += 1
    return {"mrr": mrr, "cobrado_mes": cobrado,
            "vencido": vencido, "cuentas_vencidas": cuentas_vencidas,
            "por_vencer": por_vencer, "cuentas_por_vencer": cuentas_por_vencer,
            "en_prueba": en_prueba, "cortadas": cortadas, "con_tarjeta": con_tarjeta}


def historial(s, negocio_id: int | None = None, cuantos: int = 50) -> list:
    q = select(Cobro).order_by(Cobro.cuando.desc()).limit(cuantos)
    if negocio_id is not None:
        q = q.where(Cobro.business_id == negocio_id)
    return [{"id": c.id, "negocio_id": c.business_id, "externo_id": c.externo_id,
             "cuando": c.cuando.isoformat(), "monto": c.monto, "medio": c.medio,
             "meses": c.meses, "nota": c.nota, "quien": c.quien,
             "periodo_hasta": c.periodo_hasta.isoformat() if c.periodo_hasta else ""}
            for c in s.exec(q)]


def vencen_en(s, negocios: list, dias: int = 7) -> list:
    """Las cuentas a las que hay que escribirles esta semana."""
    limite = datetime.now() + timedelta(days=dias)
    salida = []
    for b in negocios:
        e = estado(b)
        if e["estado"] in ("cortada", "en_gracia", "vence_pronto") or (
                e["estado"] == "prueba" and e["dias"] is not None and e["dias"] <= dias):
            salida.append({"id": b.id, "nombre": b.nombre, **e})
    return sorted(salida, key=lambda x: x["dias"] if x["dias"] is not None else 0)
