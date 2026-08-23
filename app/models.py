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
    vendedor: str = ""                # quien firma los mensajes
    estados_json: str = "[]"          # ["Nuevo", "Calificado", ...] editable por el admin
    reglas_json: str = "{}"           # tono, horario, descuento_max, temas_escalan, insistencias
    canales_json: str = "[]"          # [{"canal": "mail", "valor": "ventas@..."}] los tuyos
    autonomia_default: int = 3
    onboarding_hecho: bool = False    # False = la app arranca preguntando


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
    etiqueta: str = ""                # lo que ve el usuario: "+54 9 11 2265 7773"
    activo: bool = True
    ultimo_error: str = ""
    ultimo_ok: Optional[datetime] = None
    creado: datetime = Field(default_factory=datetime.now)
