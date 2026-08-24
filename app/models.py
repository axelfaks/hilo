from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class Business(SQLModel, table=True):
    """Un negocio = un inquilino = un cliente NUESTRO.

    Todo lo demás cuelga de acá por `business_id`. El filtro no se escribe a mano
    en ninguna consulta: lo pone `app/inquilino.py` solo.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = "Mi negocio"
    descripcion: str = ""
    rubro: str = ""                   # como lo diria el dueño: "panaderias", "estudio contable"
    codigo_publico: str = ""          # va en el link que el vendedor le pasa a SUS
                                      # clientes (t.me/HiloBot?start=neg_xxxx). Es
                                      # público a propósito, pero random: con el id
                                      # del negocio a secas cualquiera se cuelga de
                                      # la cola de otro escribiendo n-1, n-2, n-3.
    vendedor: str = ""                # quien firma los mensajes
    estados_json: str = "[]"          # ["Nuevo", "Calificado", ...] editable por el admin
    reglas_json: str = "{}"           # tono, horario, descuento_max, temas_escalan, insistencias
    canales_json: str = "[]"          # [{"canal": "mail", "valor": "ventas@..."}] los tuyos
    autonomia_default: int = 3
    onboarding_hecho: bool = False    # False = la app arranca preguntando

    # --- lo que miramos NOSOTROS desde el back-office (#/root) ---
    plan: str = "prueba"              # prueba | basico | pro — comercial, lo ponemos a mano
    estado: str = "activa"            # activa | suspendida
    nota: str = ""                    # nota interna nuestra, el cliente no la ve
    creado: Optional[datetime] = Field(default_factory=datetime.now)

    # --- plata. El precio vive acá y no en el plan: los primeros clientes de
    # cualquier producto pagan precios distintos, y una tabla rígida obliga a
    # mentirle a la base. `pagado_hasta` es LA fecha: todo lo demás se deduce.
    precio_mensual: int = 0           # en pesos. 0 = todavía no paga
    paga_desde: Optional[datetime] = None
    pagado_hasta: Optional[datetime] = None

    # La prueba gratis. Funciona EXACTAMENTE igual que `pagado_hasta`: son las dos
    # caras de una sola pregunta —¿hasta cuándo tiene acceso?— y por eso el corte
    # se calcula con `max()` de las dos y no con dos caminos distintos.
    prueba_hasta: Optional[datetime] = None

    # La suscripción con tarjeta, del lado de Mercado Pago. Nosotros NO guardamos
    # ni un dígito de la tarjeta: solo el id de la suscripción y cuatro números
    # para que el cliente reconozca cuál puso.
    suscripcion_id: str = ""          # el preapproval_id de Mercado Pago
    suscripcion_estado: str = ""      # "" | pendiente | activa | pausada | cancelada
    tarjeta: str = ""                 # "Visa ····4242", para mostrar y nada más


class Alias(SQLModel, table=True):
    """Un cliente o lead. Es la entidad que unifica todos los canales."""
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, index=True)   # el inquilino dueño
    nombre: str
    contacto: str = ""
    rubro: str = ""
    notas: str = ""
    importancia: str = "media"        # baja | media | alta, la pone el vendedor
    visto_at: Optional[datetime] = None   # hasta cuándo leíste el hilo
    persona: str = ""                 # como actúa este cliente cuando la IA lo interpreta
    respuestas_demo_json: str = "[]"  # respuestas de reserva para cuando no hay IA
    estado: str = "Nuevo"             # la etapa confirmada por el vendedor
    estado_sugerido: str = ""         # la que propone la IA, esperando aprobación
    estado_sugerido_motivo: str = ""
    autonomia: Optional[int] = None   # None = hereda la del negocio
    primer_contacto: datetime = Field(default_factory=datetime.now)
    token: str = ""                   # para la vista del cliente en /#/c/<token>


class Identity(SQLModel, table=True):
    """Una puerta de entrada. Varias apuntan al mismo alias."""
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, index=True)   # el inquilino dueño
    alias_id: int = Field(index=True)
    canal: str                        # mail | whatsapp | instagram | telegram | telefono
    valor: str = Field(index=True)


class Message(SQLModel, table=True):
    """Todo es un mensaje: los digitales y también la llamada y la visita."""
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, index=True)   # el inquilino dueño
    alias_id: Optional[int] = Field(default=None, index=True)   # None = sin identificar
    canal: str                        # ... | llamada | presencial
    direccion: str                    # entrante | saliente
    autor: str                        # cliente | humano | ia
    asunto: str = ""                  # solo el mail lo usa
    texto: str                        # el texto plano, limpio de citas y firma
    html: str = ""                    # el cuerpo original del mail, para verlo como en Gmail
    cc: str = ""                      # con copia (solo mail)
    cco: str = ""                     # con copia oculta: la ve quien envió, nadie más
    resumen: str = ""                 # una linea: que pasó en este mensaje
    adjuntos_json: str = "[]"
    aprobado_por: str = ""            # si la IA la escribió y un humano la aprobó
    simulado: bool = False            # lo generó el simulador, no pasó de verdad
    creado: datetime = Field(default_factory=datetime.now)
    remitente: str = ""               # el valor crudo por el que entró
    remitente_nombre: str = ""        # como se llama en ese canal: el perfil de WhatsApp,
                                      # el "De:" del mail. De un número no sale un nombre.
    externo_id: str = ""              # el id del mensaje en el proveedor (wamid de Meta)
    sugerencia_alias_id: Optional[int] = None
    sugerencia_score: int = 0
    sugerencia_motivo: str = ""


class Briefing(SQLModel, table=True):
    """Cacheado. Se recalcula al entrar un mensaje, nunca al abrir la ficha."""
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, index=True)   # el inquilino dueño
    alias_id: int = Field(index=True, unique=True)
    data_json: str = "{}"
    generado: datetime = Field(default_factory=datetime.now)


class Commitment(SQLModel, table=True):
    """Lo que quedó prometido, de los dos lados. Lo extrae la IA del hilo."""
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, index=True)   # el inquilino dueño
    alias_id: int = Field(index=True)
    de_quien: str                     # nosotros | cliente
    texto: str
    vence: Optional[datetime] = None
    cumplido: bool = False


class Usuario(SQLModel, table=True):
    """Quien entra a la app. La contraseña nunca se guarda: solo su hash."""
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, index=True)   # a qué negocio entra
    es_root: bool = False             # nosotros dos: ve el back-office de TODAS las cuentas
    email: str = Field(index=True, unique=True)
    nombre: str = ""
    hash: str = ""
    rol: str = "dueño"                # dueño | vendedor
    activo: bool = True
    creado: datetime = Field(default_factory=datetime.now)
    ultimo_acceso: Optional[datetime] = None   # lo escribe la puerta, cada 10 min


class Credencial(SQLModel, table=True):
    """Las llaves de un canal, para UN negocio.

    Acá vive el token de WhatsApp de cada cliente, su casilla de correo, su bot de
    Telegram. Hasta hoy esto vivía en el `.env`, que alcanza cuando hay un solo
    negocio y deja de alcanzar en el momento en que hay dos.

    `datos_json` va CIFRADO (ver `app/secreto.py`). Un token de WhatsApp deja
    mandar mensajes en nombre del cliente: una copia de la base no puede ser una
    copia de las llaves de todos.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, index=True)
    canal: str = Field(index=True)    # whatsapp | mail | telegram | instagram
    datos_json: str = ""              # cifrado: tokens, claves, ids
    externo_id: str = ""              # el id del proveedor: phone_number_id, chat_id...
    referencia: str = ""              # el OTRO id que necesita el canal, en claro y
                                      # consultable. En Telegram es el
                                      # `business_connection_id`: no es un secreto
                                      # (el token del bot es nuestro, no del cliente)
                                      # y hay que poder buscar por él cuando entra
                                      # un mensaje.
    etiqueta: str = ""                # lo que ve el usuario: "+54 9 11 2265 7773"
    activo: bool = True
    ultimo_error: str = ""
    ultimo_ok: Optional[datetime] = None
    creado: datetime = Field(default_factory=datetime.now)


# ===========================================================================
# Lo que necesitamos NOSOTROS para operar (el back-office de #/root).
#
# Las tres tablas de acá abajo no las ve ningún cliente: son el tablero con el
# que Axel y Toto miran todas las cuentas. Van en la misma base a propósito —
# un back-office aparte es una segunda app que mantener, y todavía somos dos.
# ===========================================================================


class UsoIA(SQLModel, table=True):
    """Cuánta IA gastó cada cuenta, por día.

    Es nuestro único costo variable directo y hasta hoy no se medía: sabíamos
    que la factura existía, no de quién era. Una fila por negocio y por día;
    `app/uso.py` la va sumando y nunca crece por mensaje.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, index=True)
    dia: str = Field(default="", index=True)   # "2026-08-23", ordenable como texto
    llamadas: int = 0
    fallos: int = 0                   # llamadas que volvieron sin respuesta
    tokens_entrada: int = 0
    tokens_salida: int = 0
    modelo: str = ""                  # el último que contestó ese día


class Falla(SQLModel, table=True):
    """Algo que salió mal, con nombre y apellido de cuenta.

    Sin esto, "no me llegan los mensajes" se responde pidiendo capturas. El
    back-office muestra las últimas 50 de cada cuenta y ahí se termina la
    adivinanza.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, index=True)
    cuando: datetime = Field(default_factory=datetime.now, index=True)
    donde: str = ""                   # ia | whatsapp | correo | webhook | app
    detalle: str = ""


class Cobro(SQLModel, table=True):
    """Un cobro que entró. Es el libro contable, y por ahora se escribe a mano.

    No hay pasarela y está bien que no la haya: construir billing antes de tener
    diez clientes pagando es construir la parte más aburrida del producto para
    nadie. Alguien transfiere, nosotros lo marcamos acá, y `pagado_hasta` se
    corre sola.

    Lo que sí importa desde el primer peso es que quede **el registro**: cuánto,
    cuándo, por qué medio y hasta cuándo paga. Eso no se reconstruye después.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, index=True)
    cuando: datetime = Field(default_factory=datetime.now, index=True)
    monto: int = 0                    # en pesos
    medio: str = "transferencia"      # transferencia | mercadopago | efectivo | otro
    meses: int = 1
    periodo_hasta: Optional[datetime] = None   # hasta dónde quedó paga con esto
    nota: str = ""
    quien: str = ""                   # el mail nuestro que lo marcó, o "mercadopago"
    externo_id: str = ""              # el id del pago en Mercado Pago. Es la llave
                                      # contra los reintentos: MP manda el mismo
                                      # aviso varias veces y sin esto el mismo
                                      # cobro sumaría tres meses.


class Vinculo(SQLModel, table=True):
    """Un código de un solo uso para enganchar una cuenta de afuera con la de acá.

    Es la pieza que hace que conectar un canal sea fácil. El problema de fondo es
    siempre el mismo: alguien abre Telegram (o WhatsApp, o su mail) y del otro
    lado llega un mensaje… **de un desconocido**. Nada en ese mensaje dice a qué
    cuenta de Hilo pertenece.

    La solución es un código corto que el cliente lleva puesto: lo genera la
    pantalla, viaja adentro del link (`t.me/HiloBot?start=A7K2M9`) y vuelve con
    el primer mensaje. Ahí sabemos de quién es, y recién ahí guardamos nada.

    Un solo uso y con vencimiento a propósito: un código que no vence es una
    llave permanente a la cuenta de alguien tirada en un historial de chat.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, index=True)
    canal: str = ""                   # telegram | mail | instagram…
    codigo: str = Field(default="", index=True)
    creado: datetime = Field(default_factory=datetime.now)
    vence: Optional[datetime] = None
    usado: Optional[datetime] = None
    quien: str = ""                   # el mail del usuario que lo pidió
    datos_json: str = "{}"            # lo que dejó la vinculación: nombre, id externo…


class Acceso(SQLModel, table=True):
    """El log de "ver como": quién entró, cuándo y a qué cuenta.

    Impersonar sin dejar rastro es exactamente la clase de poder que después no
    se puede explicar. Esta tabla no se filtra por inquilino: es nuestra.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    cuando: datetime = Field(default_factory=datetime.now, index=True)
    usuario_id: Optional[int] = None
    usuario_email: str = ""
    negocio_id: Optional[int] = None
    negocio_nombre: str = ""
