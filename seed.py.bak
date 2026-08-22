# -*- coding: utf-8 -*-
"""Rearma la base en dos segundos. Es la red de seguridad de todo el día:
si algo se rompe o si terminó un ensayo de la demo, `python seed.py` y volvés
exactamente a la posición de arranque.
"""
import json
from datetime import datetime, timedelta


from app.db import crear_tablas, engine, sesion
from app.models import Alias, Briefing, Business, Commitment, Identity, Message

AHORA = datetime.now()
HORAS_DEL_DIA = [9, 11, 14, 16, 18, 20, 8, 13, 17, 10, 12, 19, 15, 21]


def h(horas):
    return AHORA - timedelta(hours=horas)


def d(dias, hora=10):
    base = AHORA - timedelta(days=dias)
    return base.replace(hour=hora, minute=(dias * 7) % 60, second=0, microsecond=0)


NEGOCIO = dict(
    nombre="Mesa 12",
    descripcion=(
        "Vendemos un sistema de pedidos y delivery para locales gastronómicos chicos y medianos: "
        "panaderías, cafés, rotiserías. Cobramos una suscripción mensual por sucursal. "
        "El ciclo de venta dura entre dos semanas y dos meses, casi siempre con el dueño, "
        "y suele frenarse en el precio cuando el local tiene más de una sucursal."
    ),
    estados=["Nuevo", "Calificado", "Reunión hecha", "Propuesta enviada",
             "Negociación", "Cerrado ganado", "Perdido"],
    reglas={
        "tono": "Cercano y directo, de vos. Nada de 'estimado' ni de 'quedo a disposición'.",
        "horario": [8, 20],
        "insistir_cada_dias": 3,
        "max_insistencias": 3,
        "descuento_max": 15,
        "temas_escalan": ["contrato", "legal", "factura", "rescisión", "competencia"],
        "estados_cerrados": ["Cerrado ganado", "Perdido"],
    },
    autonomia_default=3,
    rubro="software de pedidos para gastronomía",
    vendedor="Axel",
    canales=[{"canal": "mail", "valor": "hola@mesa12.com.ar"},
             {"canal": "whatsapp", "valor": "+5491140001200"},
             {"canal": "instagram", "valor": "@mesa12.app"}],
)

CLIENTES = [
    dict(
        nombre="Panadería La Espiga", contacto="Juan Rodríguez", rubro="Panadería, 3 sucursales",
        estado="Negociación", autonomia=3, token="laespiga", primer=24, importancia="alta",
        notas="Dueño de tres panaderías en Villa Urquiza. Decide con su socia Marina.",
        identidades=[("mail", "juan.rodriguez@laespiga.com.ar"), ("whatsapp", "+5491155551234"),
                     ("instagram", "@laespiga.ok"), ("telegram", "@jrlaespiga")],
        mensajes=[
            (24, "instagram", "entrante", "cliente", "Hola! Vi que hacen sistemas de pedidos para panaderías. Cuánto sale?", [], "", "Primer contacto: pregunta el precio del sistema."),
            (24, "instagram", "saliente", "ia", "Hola Juan! Sí, trabajamos con panaderías. Depende de cuántas sucursales tengas y de si querés el módulo de delivery. Contame un poco y te paso números concretos.", [], "", "Pedís datos antes de dar un precio."),
            (22, "mail", "entrante", "cliente", "Buenas. Te escribo por acá que me queda más cómodo. Tenemos tres locales en Villa Urquiza. Hoy tomamos los pedidos por WhatsApp y los anotamos a mano, y los sábados es un caos.", [], "Consulta sistema de pedidos - La Espiga", "Pasa al mail y cuenta el problema: tres locales, pedidos a mano."),
            (20, "llamada", "entrante", "humano", "Lo llamé, 22 minutos. Tiene tres sucursales. Hoy toman los pedidos por WhatsApp a mano y los pasan a un cuaderno. Lo que más le duele es perder pedidos los sábados a la mañana, que es cuando se satura. La decisión la toma con su socia Marina.", ["audio-llamada.m4a", "foto-cuaderno.jpg"], "", "Relevamiento: 3 sucursales, pedidos a mano, pierde ventas los sábados."),
            (17, "mail", "saliente", "humano", "Juan, te paso la propuesta para las tres sucursales, con el módulo de pedidos y la migración de lo que ya tenés cargado incluida.", ["propuesta-laespiga-v1.pdf"], "Propuesta Mesa 12 para La Espiga (3 sucursales)", "Enviás la propuesta formal, con módulo de pedidos y migración."),
            (10, "whatsapp", "entrante", "cliente", "lo vimos con marina. nos cierra la propuesta pero el precio nos queda justo para arrancar con las tres juntas", [], "", "Aceptan la propuesta; traban con el precio de las tres sucursales juntas."),
            (8, "whatsapp", "saliente", "ia", "Juan, buenísimo que les cierre. Dejame revisar los números y te acerco una alternativa para arrancar sin resignar sucursales. Te escribo el lunes.", [], "", "Prometés una alternativa de precio para el lunes."),
            (2, "mail", "entrante", "cliente", "Buen día Axel. Quedamos en que me mandabas el número nuevo y todavía no me llegó. Seguimos interesados pero necesitamos definirlo esta semana, porque Marina se va de viaje el viernes.", [], "Re: Propuesta Mesa 12 para La Espiga (3 sucursales)", "Reclama el número prometido y pone fecha límite: Marina viaja el viernes."),
        ],
        briefing=dict(
            quien_es="Juan Rodríguez, dueño de tres panaderías en Villa Urquiza. Hoy toma los pedidos por WhatsApp a mano y pierde ventas los sábados. La decisión la comparte con su socia Marina.",
            lo_ultimo=[
                "Aceptaron la propuesta en lo funcional: el único freno es el precio de arrancar con las tres sucursales juntas.",
                "Le prometimos una alternativa el lunes y todavía no salió.",
                "Apareció una fecha dura: Marina viaja el viernes y quieren definirlo antes.",
            ],
            estado="Negociación",
            por_que_estado="Ya hay propuesta sobre la mesa y la conversación pasó a discutir precio.",
            proximo_paso="Mandarle hoy el presupuesto con 15% y proponer 15 minutos con Marina antes del viernes.",
            senal_de_urgencia="Marina viaja el viernes: si no se define esta semana, se corre tres semanas.",
            por_que_ahora="Ya aceptaron todo menos el precio y tienen fecha propia: es el único movimiento que falta para cerrar.",
            borrador={
                "canal": "mail",
                "asunto": "Presupuesto revisado - La Espiga (3 sucursales)",
                "texto": ("Juan, tenés razón, me colgué con el número y te pido disculpas. Va el "
                          "revisado: 15 % abajo por tomar las tres sucursales juntas, con la "
                          "migración de los pedidos históricos incluida. Si les sirve, lo activamos "
                          "el lunes y el sábado ya lo cubren con el sistema. ¿Lo vemos 15 minutos "
                          "mañana con Marina antes de que viaje?"),
                "escalar": False,
                "motivo_escalada": "",
            },
            accion_agente="borrador_para_aprobar",
            por_canal={
                "instagram": "Por acá empezó todo: preguntó el precio en frío y se le pidieron los datos básicos.",
                "mail": "Es el canal formal: viajó la propuesta con el PDF y por acá llegó el reclamo del precio revisado.",
                "whatsapp": "Donde hablan de verdad. Acá dijo que la propuesta les cierra pero el precio no, y acá le prometimos la alternativa.",
                "llamada": "Una sola llamada, la de calificación: tres sucursales, cuaderno a mano, y que decide con Marina.",
            },
        ),
        compromisos=[("nosotros", "Enviar el presupuesto revisado con el descuento", -4),
                     ("cliente", "Confirmar con Marina", 1)],
    ),
    dict(
        nombre="Distribuidora Kern", contacto="Sergio Kern", rubro="Distribuidora de insumos",
        estado="Propuesta enviada", autonomia=None, token="kern", primer=31, importancia="alta",
        notas="Compra para seis rotiserías propias. Es formal y responde por mail.",
        identidades=[("mail", "skern@distribuidorakern.com"), ("telegram", "@sergiokern"),
                     ("linkedin", "in/sergio-kern")],
        mensajes=[
            (34, "linkedin", "entrante", "cliente", "Hola Axel, vi lo que publicaste sobre pedidos para gastronomía. Manejamos seis puntos de venta y estamos con este tema. ¿Te puedo escribir por mail?", []),
            (33, "linkedin", "saliente", "humano", "Hola Sergio, claro. skern@distribuidorakern.com es el tuyo? Te escribo hoy mismo.", []),
            (31, "mail", "entrante", "cliente", "Buenas tardes. Nos recomendaron su sistema. Manejamos seis puntos de venta propios y necesitamos unificar los pedidos. ¿Podemos coordinar una llamada?", [], "Consulta - Distribuidora Kern"),
            (29, "mail", "saliente", "humano", "Hola Sergio, gracias por escribir. Te propongo el jueves a las 15. ¿Te sirve?", [], "Re: Consulta - Distribuidora Kern"),
            (27, "telegram", "entrante", "cliente", "Perfecto el jueves 15hs", []),
            (26, "llamada", "entrante", "humano", "Reunión de 40 minutos con Sergio y el encargado de sistemas. Seis puntos de venta, quieren integrar con lo que ya usan para facturar. Pidieron propuesta por escrito con el detalle de la integración.", []),
            (20, "mail", "saliente", "humano", "Sergio, va la propuesta con el detalle de la integración que hablamos.", ["propuesta-kern.pdf"], "Propuesta Mesa 12 - 6 puntos de venta"),
            (12, "mail", "entrante", "cliente", "Recibida. La estamos evaluando internamente, te contesto la semana que viene.", [], "Re: Propuesta Mesa 12 - 6 puntos de venta"),
            (5, "mail", "entrante", "cliente", "Axel, necesitamos el contrato para poder cerrarlo antes de fin de mes. ¿Nos lo podés mandar?", [], "Contrato para firma"),
        ],
        briefing=dict(
            quien_es="Sergio Kern, dueño de una distribuidora con seis puntos de venta propios. Llegó por LinkedIn, es formal, responde por mail y decide con su encargado de sistemas.",
            lo_ultimo=[
                "Ya evaluaron la propuesta internamente y avanzaron: pidieron el contrato.",
                "Tienen una fecha propia: quieren cerrarlo antes de fin de mes.",
                "El contrato lleva cinco días sin salir de nuestro lado.",
            ],
            estado="Propuesta enviada",
            por_que_estado="Pidieron el contrato pero todavía no hay nada firmado.",
            proximo_paso="Mandar el contrato hoy. Es la única cosa que separa esto de un cierre.",
            senal_de_urgencia="Pidió el contrato hace cinco días y quiere cerrar antes de fin de mes.",
            por_canal={
                "linkedin": "El primer contacto: te encontró por una publicación y pidió pasar al mail.",
                "mail": "Todo lo formal vive acá: propuesta, evaluación interna y el pedido del contrato.",
                "telegram": "Lo usa para cosas cortas y de coordinación, como confirmar la reunión.",
                "llamada": "La reunión de descubrimiento con él y su encargado de sistemas.",
            },
        ),
        compromisos=[("nosotros", "Enviar el contrato para firma", -3)],
    ),
    dict(
        nombre="Café Volta", contacto="Lucía Prieto", rubro="Café de especialidad",
        estado="Calificado", autonomia=5, token="volta", primer=6,
        notas="Un solo local en Palermo. Escribe por Instagram y responde rápido.",
        identidades=[("instagram", "@cafevolta"), ("mail", "hola@cafevolta.com")],
        mensajes=[
            (6, "instagram", "entrante", "cliente", "hola! me pasaron el contacto, tienen algo para tomar pedidos de delivery propio?", []),
            (6, "instagram", "saliente", "ia", "Hola Lucía! Sí, es justo lo que hacemos. ¿Tenés un local o más de uno? Con eso te paso el número exacto.", []),
            (5, "instagram", "entrante", "cliente", "uno solo, en palermo. somos chicos", []),
            (5, "instagram", "saliente", "ia", "Perfecto, para un local el plan arranca en el más simple y podés activarlo en el día. ¿Querés que te mande el detalle por mail así lo ves tranquila?", []),
            (4, "instagram", "entrante", "cliente", "dale, hola@cafevolta.com", []),
            (3, "mail", "saliente", "ia", "Lucía, va el detalle del plan para un local, con el link para probarlo una semana sin cargo. Cualquier duda escribime por acá o por Instagram, donde te quede cómodo.", ["plan-un-local.pdf"]),
            (1, "mail", "saliente", "ia", "Lucía, ¿pudiste verlo? Si querés te lo dejo activado y lo probás con los pedidos del finde, sin compromiso.", []),
        ],
        briefing=dict(
            quien_es="Lucía Prieto, dueña de un café de especialidad en Palermo. Un solo local, decide sola y contesta en el día.",
            lo_ultimo=[
                "Pidió el detalle por mail y ya se lo mandamos con una prueba de una semana.",
                "El agente hizo el primer seguimiento solo, ayer, sin que nadie lo pidiera.",
                "Todavía no respondió, pero está dentro de su ritmo habitual.",
            ],
            estado="Calificado",
            por_que_estado="Hay interés claro y necesidad concreta, pero todavía no vio la propuesta formal.",
            proximo_paso="Esperar hasta el lunes. Si no contesta, el agente insiste una vez más.",
            senal_de_urgencia="",
        ),
        compromisos=[("cliente", "Probar el sistema con los pedidos del fin de semana", 2)],
    ),
    dict(
        nombre="Gimnasio Nudo", contacto="Pablo Sarti", rubro="Gimnasio con buffet",
        estado="Propuesta enviada", autonomia=None, token="nudo", primer=45, importancia="baja",
        notas="Quiere el sistema para el buffet del gimnasio. Difícil de agarrar.",
        identidades=[("whatsapp", "+5491144442211")],
        mensajes=[
            (45, "whatsapp", "entrante", "cliente", "buenas, me hablaron de ustedes para el buffet del gym", []),
            (44, "whatsapp", "saliente", "humano", "Hola Pablo! Contame qué necesitás y vemos.", []),
            (40, "llamada", "entrante", "humano", "Charla corta. Buffet chico dentro del gimnasio, quiere que los socios pidan desde el celular y retiren. Le interesa pero dice que el dueño del buffet es otro y tiene que hablarlo.", []),
            (30, "whatsapp", "saliente", "humano", "Pablo, va la propuesta para el buffet. Cualquier cosa la vemos.", ["propuesta-nudo.pdf"]),
            (11 * 24 / 24, "whatsapp", "saliente", "ia", "Pablo, ¿pudiste hablarlo con el del buffet? Si querés lo llamo yo directamente y te lo saco de encima.", []),
        ],
        briefing=dict(
            quien_es="Pablo Sarti, encargado de un gimnasio con buffet propio. No es el que decide: el buffet lo maneja otra persona.",
            lo_ultimo=[
                "La propuesta está mandada hace tres semanas y no hubo respuesta.",
                "El freno es que Pablo no decide: tiene que hablarlo con el dueño del buffet.",
                "El agente insistió una vez hace once días y tampoco hubo respuesta.",
            ],
            estado="Propuesta enviada",
            por_que_estado="La propuesta está entregada pero la conversación se cortó.",
            proximo_paso="Pedirle el contacto directo del dueño del buffet o cerrar el caso.",
            senal_de_urgencia="Once días de silencio después de una insistencia: está muerto o casi.",
        ),
        compromisos=[("cliente", "Hablar con el dueño del buffet", -20)],
    ),
    dict(
        nombre="Bar Los Tilos", contacto="Nico Ferrer", rubro="Bar y cocina",
        estado="Reunión hecha", autonomia=None, token="tilos", primer=9,
        notas="Bar de barrio con cocina. Quiere ordenar los pedidos del delivery propio.",
        identidades=[("whatsapp", "+5491166778899"), ("mail", "nico@lostilos.bar")],
        mensajes=[
            (9, "whatsapp", "entrante", "cliente", "hola, nos pasaron tu contacto por el tema pedidos", []),
            (8, "whatsapp", "saliente", "humano", "Hola Nico! Contame, ¿cuántos locales y qué usan hoy?", []),
            (8, "whatsapp", "entrante", "cliente", "uno solo. hoy usamos el whatsapp y una planilla, un desastre", []),
            (4, "presencial", "entrante", "humano", "Pasé por el bar. Un local, cocina propia, delivery con dos motos. Nico quiere dejar de perder pedidos en horas pico y sobre todo saber cuánto vende por plato. Me pidió la propuesta para el lunes.", ["foto-mostrador.jpg"]),
            (1, "whatsapp", "entrante", "cliente", "che quedamos en la propuesta el lunes, avisame si necesitás algo mío", []),
        ],
        briefing=dict(
            quien_es="Nico Ferrer, dueño de un bar de barrio con cocina y delivery propio. Un local, decide solo y es informal.",
            lo_ultimo=[
                "Visita presencial hace cuatro días: quiere dejar de perder pedidos en hora pico y medir venta por plato.",
                "Quedamos en mandarle la propuesta el lunes y él ya lo recordó por WhatsApp.",
                "Está esperando de nuestro lado.",
            ],
            estado="Reunión hecha",
            por_que_estado="Ya hubo visita y necesidad clara, pero todavía no hay propuesta enviada.",
            proximo_paso="Armar la propuesta de un local con el módulo de reportes por plato.",
            senal_de_urgencia="Prometimos propuesta para el lunes y él ya la reclamó.",
        ),
        compromisos=[("nosotros", "Mandar la propuesta con reportes por plato", 0)],
    ),
    dict(
        nombre="Heladería Polar", contacto="Vanina Ruiz", rubro="Heladería, 2 sucursales",
        estado="Nuevo", sugerido=("Calificado", "Ya sabemos que son dos locales, que el delivery es propio y que pregunta precio: hay necesidad y volumen concreto."),
        autonomia=4, token="polar", primer=1,
        notas="Escribió hoy por Instagram. Todavía no sabemos casi nada.",
        identidades=[("instagram", "@heladospolar")],
        mensajes=[
            (3 / 24, "instagram", "entrante", "cliente", "hola, hacen sistemas de pedidos? tenemos dos heladerías", []),
            (2.5 / 24, "instagram", "saliente", "ia", "Hola Vanina! Sí, trabajamos con locales de dos o tres sucursales. ¿El delivery lo hacen ustedes o con apps?", []),
            (1 / 24, "instagram", "entrante", "cliente", "lo hacemos nosotros con dos cadetes. cuánto sale para dos locales?", []),
        ],
        briefing=dict(
            quien_es="Vanina Ruiz, de una heladería con dos sucursales. Recién aparece, no sabemos cómo trabajan hoy.",
            lo_ultimo=[
                "Escribió hoy por Instagram preguntando si hacemos sistemas de pedidos.",
                "El agente le respondió solo y ella contestó en minutos: delivery propio con dos cadetes.",
                "Preguntó precio para dos locales y todavía no se lo dimos.",
            ],
            estado="Nuevo",
            por_que_estado="Primer contacto, sin información suficiente para calificar.",
            proximo_paso="Esperar la respuesta y calificar. Si contesta, ofrecer llamada de 10 minutos.",
            senal_de_urgencia="",
        ),
        compromisos=[],
    ),
    dict(
        nombre="Almacén Belgrano", contacto="Rosa Ibáñez", rubro="Almacén de barrio con reparto",
        estado="Nuevo", autonomia=None, token="belgrano", primer=1, importancia="baja",
        notas="Almacén de barrio que empezó a repartir en la cuadra. Escribió hoy.",
        identidades=[("whatsapp", "+5491133445566")],
        mensajes=[
            (4 / 24, "whatsapp", "entrante", "cliente", "hola! una vecina me pasó el contacto. tenemos un almacén y arrancamos a repartir, sirve para eso?", [], "", "Primer contacto por recomendación de otro cliente."),
            (3.5 / 24, "whatsapp", "saliente", "ia", "Hola Rosa! Sí, sirve igual: los pedidos entran ordenados y sabés qué te falta reponer. ¿Cuántos repartos hacés por día?", [], "", "El agente responde solo y pregunta el volumen."),
            (3 / 24, "whatsapp", "entrante", "cliente", "unos 15 por dia, pero los sabados el doble. lo anoto todo en un cuaderno", []),
        ],
        briefing=dict(
            quien_es="Rosa Ibáñez, dueña de un almacén de barrio que empezó a repartir. Unos 15 pedidos por día, el doble los sábados, todo anotado en un cuaderno.",
            lo_ultimo=[
                "Llegó por recomendación de otro cliente, no por publicidad.",
                "El agente le respondió solo y ella contestó en minutos con el volumen.",
                "Todavía no le dimos precio ni le preguntamos si decide sola.",
            ],
            estado="Nuevo",
            por_que_estado="Primer contacto del día, sin calificar todavía.",
            proximo_paso="Preguntarle si decide ella y pasarle el precio de un local.",
            por_que_ahora="Contestó en minutos y viene recomendada: está caliente y todavía no le pedimos nada.",
            senal_de_urgencia="",
            por_canal={"whatsapp": "Todo pasa por acá: llegó, contó el volumen y espera precio."},
        ),
        compromisos=[],
    ),
    dict(
        nombre="Parrilla El Once", contacto="Rubén Ledesma", rubro="Parrilla con delivery",
        estado="Propuesta enviada", autonomia=None, token="elonce", primer=38,
        notas="Parrilla grande de barrio. Mucho delivery propio los fines de semana.",
        identidades=[("mail", "ruben@parrillaelonce.com"), ("whatsapp", "+5491199887766")],
        mensajes=[
            (38, "mail", "entrante", "cliente", "Buenas, queremos ver un sistema para ordenar el delivery. Los sábados se nos escapan pedidos.", []),
            (35, "llamada", "entrante", "humano", "Llamada de 20 minutos. Un local grande, tres cadetes propios, pico los viernes y sábados. Rubén decide solo pero es lento.", []),
            (28, "mail", "saliente", "humano", "Rubén, va la propuesta con el módulo de delivery y seguimiento de cadetes.", ["propuesta-elonce.pdf"]),
            (20, "whatsapp", "saliente", "ia", "Rubén, ¿pudiste mirar la propuesta? Cualquier duda te la aclaro por acá.", []),
            (14, "whatsapp", "saliente", "ia", "Rubén, te dejo el último toque por si quedó en el camino. Si no es el momento, avisame y lo retomamos más adelante.", []),
        ],
        briefing=dict(
            quien_es="Rubén Ledesma, dueño de una parrilla grande con delivery propio y tres cadetes. Decide solo pero se toma su tiempo.",
            lo_ultimo=[
                "La propuesta está entregada hace casi un mes y no hubo respuesta.",
                "El agente insistió dos veces, la última hace catorce días.",
                "Ya se usaron dos de las tres insistencias que permite el reglamento.",
            ],
            estado="Propuesta enviada",
            por_que_estado="La propuesta está entregada pero no hubo ninguna señal de vuelta.",
            proximo_paso="Un último intento por teléfono, o cerrarlo como perdido y liberar la atención.",
            senal_de_urgencia="Catorce días desde la última insistencia: está por caerse.",
        ),
        compromisos=[("cliente", "Revisar la propuesta y contestar", -18)],
    ),
    dict(
        nombre="Vinoteca Sarmiento", contacto="Clara Bove", rubro="Vinoteca con envíos",
        estado="Reunión hecha", autonomia=None, token="sarmiento", primer=22,
        notas="Vinoteca con envíos a domicilio. Quiere catálogo online además de pedidos.",
        identidades=[("mail", "clara@vinotecasarmiento.com"), ("telegram", "@clarabove")],
        mensajes=[
            (22, "telegram", "entrante", "cliente", "Hola! Nos interesa lo de pedidos online, ¿sirve para una vinoteca?", []),
            (21, "telegram", "saliente", "humano", "Hola Clara, sí. ¿Hacen envíos propios o por cadetería?", []),
            (21, "telegram", "entrante", "cliente", "Propios, tenemos un chico con moto.", []),
            (16, "presencial", "entrante", "humano", "Pasé por la vinoteca. Clara quiere catálogo online con stock además de los pedidos, porque hoy le preguntan por WhatsApp qué hay y pierde media hora por día contestando. Quedó en pensarlo y avisar.", ["foto-local.jpg"]),
            (9, "mail", "saliente", "ia", "Clara, ¿pudiste pensarlo? Si querés te armo el catálogo con veinte etiquetas para que lo veas funcionando antes de decidir.", []),
        ],
        briefing=dict(
            quien_es="Clara Bove, dueña de una vinoteca con envíos propios. Pierde media hora por día contestando por WhatsApp qué hay en stock.",
            lo_ultimo=[
                "Visita hace algo más de dos semanas: quiere catálogo online con stock, no solo pedidos.",
                "Quedó en pensarlo y avisar, y no volvió a escribir.",
                "El agente ofreció armarle una muestra hace nueve días y tampoco hubo respuesta.",
            ],
            estado="Reunión hecha",
            por_que_estado="Hubo visita y necesidad clara, pero nunca se envió propuesta formal.",
            proximo_paso="Armarle el catálogo de muestra sin pedirle permiso: es lo único que la va a mover.",
            senal_de_urgencia="Nueve días sin responder una oferta concreta.",
        ),
        compromisos=[("cliente", "Avisar si le sirve el catálogo online", -7)],
    ),
    dict(
        nombre="Rotisería Don Alfredo", contacto="Alfredo Gómez", rubro="Rotisería",
        estado="Cerrado ganado", autonomia=1, token="alfredo", primer=60,
        notas="Cliente desde hace un mes. Un local, plan simple.",
        identidades=[("mail", "donalfredo@gmail.com"), ("whatsapp", "+5491133221100")],
        mensajes=[
            (60, "mail", "entrante", "cliente", "Buenas, quería saber cómo funciona el sistema de pedidos.", []),
            (55, "llamada", "entrante", "humano", "Llamada de 15 minutos. Un local, pedidos por teléfono, quiere ordenarlos. Simple.", []),
            (50, "mail", "saliente", "humano", "Alfredo, va la propuesta del plan de un local.", ["propuesta-alfredo.pdf"]),
            (44, "whatsapp", "entrante", "cliente", "listo, arranquemos", []),
            (30, "whatsapp", "saliente", "humano", "Alfredo, ya está todo activado. Cualquier cosa me escribís.", []),
        ],
        briefing=dict(
            quien_es="Alfredo Gómez, dueño de una rotisería de un local. Cliente activo desde hace un mes.",
            lo_ultimo=["Cerró el plan de un local y está activado hace un mes.",
                       "No hubo incidencias ni pedidos de soporte.",
                       "Buen candidato para pedirle una recomendación."],
            estado="Cerrado ganado",
            por_que_estado="Contrató y está usando el sistema.",
            proximo_paso="Pedirle una referencia de otro local del barrio.",
            senal_de_urgencia="",
        ),
        compromisos=[],
    ),
    dict(
        nombre="Sushi Nagano", contacto="Emi Tanaka", rubro="Sushi, delivery",
        estado="Perdido", autonomia=0, token="nagano", primer=70,
        notas="Se cayó por precio. Ya usaban una app propia.",
        identidades=[("mail", "emi@sushinagano.com.ar")],
        mensajes=[
            (70, "mail", "entrante", "cliente", "Hola, nos interesa ver alternativas al sistema que usamos.", []),
            (66, "mail", "saliente", "humano", "Emi, va la propuesta con la migración incluida.", ["propuesta-nagano.pdf"]),
            (58, "mail", "entrante", "cliente", "Gracias, pero por ahora nos quedamos con lo que tenemos. El costo de migrar no nos cierra.", []),
        ],
        briefing=dict(
            quien_es="Emi Tanaka, de un delivery de sushi que ya tiene su propio sistema.",
            lo_ultimo=["Rechazó la propuesta por el costo de migrar.",
                       "No hubo objeción sobre el producto, solo sobre el cambio.",
                       "Vale volver a tocarlo si sacamos migración sin cargo."],
            estado="Perdido",
            por_que_estado="Dijo que no explícitamente.",
            proximo_paso="Reabrir en tres meses si hay promoción de migración.",
            senal_de_urgencia="",
        ),
        compromisos=[],
    ),
]

SIN_IDENTIFICAR = dict(
    canal="mail", remitente="marina.f@laespiga.com.ar", horas=3,
    texto=("Hola, soy Marina, socia de Juan en La Espiga. Él me reenvió la propuesta. "
           "Antes de decidir quería saber si el precio incluye la migración de los pedidos "
           "viejos y si podemos arrancar con dos sucursales en vez de tres."),
    sugerencia_nombre="Panadería La Espiga", score=92,
    motivo="Mismo dominio de mail que Juan Rodríguez y retoma la conversación de la propuesta.",
)



# ---------------------------------------------------------------------------
# Cómo actúa cada cliente cuando la IA se pone en su papel.
# Lo que hace que esto funcione no es la descripción amable: son las dos últimas
# líneas de cada uno, las que dicen qué lo hace avanzar y qué lo hace desaparecer.
# ---------------------------------------------------------------------------

PERSONAS = {
    "Panadería La Espiga": dict(
        persona=(
            "Tenés 48 años y tres panaderías que armaste vos. Sos cordial pero directo. "
            "Por WhatsApp escribís corto, en minúsculas y sin signos de pregunta; por mail "
            "sos un poco más formal y firmás.\n"
            "Te interesa el sistema de verdad: ya viste que te resuelve el sábado. El único "
            "freno es la plata de arrancar con las tres sucursales juntas.\n"
            "No decidís solo: cualquier compromiso lo tenés que pasar por Marina, tu socia, "
            "y ella se va de viaje el viernes. Si te apuran, usás eso como excusa real.\n"
            "AVANZÁS si te dan un descuento concreto con número, o si te ofrecen arrancar con "
            "menos sucursales, o si te ponen una fecha de activación clara.\n"
            "TE ENFRIÁS si te vuelven a decir 'te escribo la semana que viene' o si te contestan "
            "sin el número que pediste."
        ),
        respuestas=[
            "dale, mandame el número y lo veo con marina hoy mismo antes de que se vaya",
            "che, seguimos esperando. si no llega hoy lo dejamos para el mes que viene",
        ],
    ),
    "Distribuidora Kern": dict(
        persona=(
            "Sos dueño de una distribuidora con seis puntos de venta. Escribís mails bien "
            "redactados, con saludo y firma, y sos impaciente con la burocracia.\n"
            "Ya decidiste que querés el sistema: lo evaluaste con tu encargado de sistemas y "
            "está aprobado internamente. Lo único que falta es el contrato para firmar, y lo "
            "venís pidiendo hace días.\n"
            "AVANZÁS si te mandan el contrato o te dan una fecha exacta de cuándo llega.\n"
            "TE ENFRIÁS si te proponen otra reunión, si te vuelven a explicar el producto, o si "
            "te contestan sin mencionar el contrato."
        ),
        respuestas=[
            "Perfecto, quedo esperando el contrato para firmarlo hoy y arrancar el lunes.",
            "Axel, es la tercera vez que lo pido. Si no lo tienen listo, decímelo y lo resolvemos de otra forma.",
        ],
    ),
    "Café Volta": dict(
        persona=(
            "Tenés un café de especialidad en Palermo, un solo local, y decidís sola. "
            "Escribís todo en minúsculas, mensajes de una línea, y contestás rapidísimo.\n"
            "El precio no es tu problema: lo que te da miedo es que sea complicado, que haya "
            "que instalar algo o capacitar al personal.\n"
            "AVANZÁS si te dicen que se activa en el día, sin instalar nada, y que lo podés "
            "probar sin compromiso.\n"
            "TE ENFRIÁS si te mandan un PDF largo o si te hablan de módulos, integraciones o "
            "implementación. No lo leés."
        ),
        respuestas=[
            "buenísimo, dejamelo activado y lo pruebo con los pedidos del finde",
            "uh me perdí. hay algo más simple para arrancar?",
        ],
    ),
    "Gimnasio Nudo": dict(
        persona=(
            "Sos el encargado de un gimnasio con un buffet adentro. El buffet no es tuyo: lo "
            "maneja otra persona y vos no decidís nada.\n"
            "Contestás poco y tarde, mensajes de una línea, siempre un poco evasivo. No querés "
            "quedar mal pero tampoco querés hacerte cargo de esto.\n"
            "AVANZÁS solo si te ofrecen hablar directo con el dueño del buffet: eso te saca el "
            "problema de encima y lo agradecés.\n"
            "TE ENFRIÁS si te insisten a vos. Si es la tercera vez, contestás algo corto para "
            "cerrar el tema o no contestás."
        ),
        respuestas=[
            "mirá, hablalo directo con el del buffet, te paso el teléfono",
            "ahora estamos con otras prioridades, más adelante vemos",
        ],
    ),
    "Bar Los Tilos": dict(
        persona=(
            "Tenés un bar de barrio con cocina y delivery con dos motos. Sos entusiasta y "
            "escribís informal: 'dale', 'buenísimo', 'joya'. Decidís solo y rápido.\n"
            "Lo que más te interesa no es el pedido en sí: es saber cuánto vendés por plato, "
            "porque hoy no tenés idea.\n"
            "AVANZÁS si te muestran el reporte de venta por plato o te lo prometen con fecha.\n"
            "TE ENFRIÁS si te hablan de integraciones técnicas o si te mandan una propuesta sin "
            "mencionar los reportes."
        ),
        respuestas=[
            "dale, mandame la propuesta con eso de los reportes por plato y arrancamos",
            "che me quedó dando vueltas, se puede ver cuánto vendo de cada cosa o no?",
        ],
    ),
    "Heladería Polar": dict(
        persona=(
            "Tenés dos heladerías y hacés el delivery con dos cadetes propios. Escribís por "
            "Instagram, en minúsculas, y vas derecho al precio.\n"
            "Estás en etapa de averiguar. No te comprometés con nada hasta saber cuánto sale.\n"
            "AVANZÁS si te dan el precio de dos locales con un número concreto: ahí pedís una "
            "prueba o una reunión.\n"
            "TE ENFRIÁS si te esquivan el precio, si te piden datos antes de decirte cuánto sale, "
            "o si te ofrecen una llamada sin haberte dicho nada."
        ),
        respuestas=[
            "ah está bien ese precio. cómo seguimos?",
            "che pero cuánto sale? es lo único que pregunté",
        ],
    ),
    "Rotisería Don Alfredo": dict(
        persona=(
            "Ya sos cliente hace un mes y estás conforme. Sos mayor, escribís poco y con "
            "cortesía, agradecés siempre.\n"
            "No querés comprar nada más ni agregar módulos.\n"
            "AVANZÁS si te preguntan si conocés a alguien a quien le pueda servir: ahí das un "
            "nombre concreto de otro local del barrio.\n"
            "TE ENFRIÁS si te intentan vender algo adicional."
        ),
        respuestas=[
            "Todo bien por acá, gracias. Hay un chino a la vuelta que capaz le sirve, le paso tu contacto.",
            "Por ahora estamos bien así, gracias igual.",
        ],
    ),
    "Sushi Nagano": dict(
        persona=(
            "Manejás un delivery de sushi y ya tenés tu propio sistema. Escribís cordial y breve, "
            "sin dar vueltas.\n"
            "Ya dijiste que no: el costo de migrar no te cierra. No es el producto, es el cambio.\n"
            "AVANZÁS solo si te sacan el costo de migración o te lo hacen sin cargo.\n"
            "TE ENFRIÁS si te insisten con lo mismo que ya rechazaste. Ahí cortás amable pero "
            "definitivo."
        ),
        respuestas=[
            "Si la migración va sin cargo lo volvemos a mirar. Contame.",
            "Gracias, pero ya lo definimos. Preferiría que no insistan.",
        ],
    ),
    "Parrilla El Once": dict(
        persona=(
            "Tenés una parrilla grande con delivery propio y tres cadetes. Sos lento para todo: "
            "abrís los mensajes y los dejás para después. Escribís cortito y sin puntuación.\n"
            "El sistema te interesa pero nunca es urgente. Los sábados sufrís y el lunes te "
            "olvidás.\n"
            "AVANZÁS si te ofrecen llamarte por teléfono o pasar por el local: por escrito no "
            "resolvés nada.\n"
            "TE ENFRIÁS si te escriben una cuarta vez sin cambiar de canal. Ahí pedís que no te "
            "escriban más."
        ),
        respuestas=[
            "llamame mañana a la tarde que por acá no me organizo",
            "estamos a full ahora, no me escribas más por este tema por favor",
        ],
    ),
    "Almacén Belgrano": dict(
        persona=(
            "Tenés un almacén de barrio y hace poco empezaste a repartir en la zona. "
            "Escribís por WhatsApp, en minúsculas, corto y sin signos.\n"
            "Sos práctica y desconfiada de lo caro: no querés nada complicado ni pagar de más, "
            "pero venís recomendada por una vecina y eso te predispone bien.\n"
            "AVANZÁS si te dan un precio bajo y claro para un solo local y te dicen que se "
            "usa desde el celular.\n"
            "TE ENFRIÁS si te hablan de planes, módulos o suscripciones caras."
        ),
        respuestas=[
            "ah mirá, está bien. cómo lo pruebo?",
            "uy no, para nosotros eso es mucha plata",
        ],
    ),
    "Vinoteca Sarmiento": dict(
        persona=(
            "Tenés una vinoteca con envíos propios. Escribís educada, mensajes de largo medio, "
            "y preguntás cosas concretas.\n"
            "Lo que te interesa es el catálogo online con stock, más que los pedidos: hoy perdés "
            "media hora por día contestando por WhatsApp qué tenés.\n"
            "AVANZÁS si te muestran una muestra del catálogo funcionando, aunque sea con pocas "
            "etiquetas. Ver es lo que te decide.\n"
            "TE ENFRIÁS si te piden que decidas sin verlo o si te mandan solo un precio."
        ),
        respuestas=[
            "Si me armás esa muestra con algunas etiquetas la veo esta semana y te contesto.",
            "Prefiero verlo funcionando antes de avanzar, si no me cuesta decidir.",
        ],
    ),
}


def sembrar():
    """Vacia y vuelve a llenar las tablas SIN borrar el archivo, asi se puede
    resetear entre ensayos con el servidor levantado."""
    from sqlmodel import SQLModel
    crear_tablas()
    # los usuarios NO se tocan: sembrar de nuevo no puede dejarte afuera de tu app
    del_negocio = [t for t in SQLModel.metadata.sorted_tables if t.name != "usuario"]
    SQLModel.metadata.drop_all(engine, tables=del_negocio)
    SQLModel.metadata.create_all(engine)
    with sesion() as s:
        s.add(Business(
            nombre=NEGOCIO["nombre"], descripcion=NEGOCIO["descripcion"],
            estados_json=json.dumps(NEGOCIO["estados"], ensure_ascii=False),
            reglas_json=json.dumps(NEGOCIO["reglas"], ensure_ascii=False),
            rubro=NEGOCIO["rubro"], vendedor=NEGOCIO["vendedor"],
            canales_json=json.dumps(NEGOCIO["canales"], ensure_ascii=False),
            autonomia_default=NEGOCIO["autonomia_default"],
            onboarding_hecho=True))

        por_nombre = {}
        for c in CLIENTES:
            ficha = PERSONAS.get(c["nombre"], {})
            a = Alias(nombre=c["nombre"], contacto=c["contacto"], rubro=c["rubro"],
                      notas=c["notas"], estado=c["estado"], autonomia=c["autonomia"],
                      token=c["token"], primer_contacto=d(c["primer"]),
                      importancia=c.get("importancia", "media"),
                      # leíste el hilo hasta hace tres días: lo más nuevo aparece sin leer
                      visto_at=AHORA - timedelta(days=3),
                      estado_sugerido=(c.get("sugerido") or ("", ""))[0],
                      estado_sugerido_motivo=(c.get("sugerido") or ("", ""))[1],
                      persona=ficha.get("persona", ""),
                      respuestas_demo_json=json.dumps(ficha.get("respuestas", []),
                                                      ensure_ascii=False))
            s.add(a)
            s.commit()
            s.refresh(a)
            por_nombre[c["nombre"]] = a.id

            for canal, valor in c["identidades"]:
                s.add(Identity(alias_id=a.id, canal=canal, valor=valor))

            canales = set()
            # horas de reloj variadas pero siempre en orden: si no, todos los
            # mensajes caen a la misma hora y el hilo se ve sintetico
            anterior = None
            for i, m in enumerate(c["mensajes"]):
                dias_atras, canal, direccion, autor, texto, adj = m[:6]
                asunto = m[6] if len(m) > 6 else ""
                resumen = m[7] if len(m) > 7 else ""
                canales.add(canal)
                cuando = h(dias_atras * 24)
                if dias_atras >= 1:
                    cuando = cuando.replace(hour=HORAS_DEL_DIA[i % len(HORAS_DEL_DIA)],
                                            minute=(i * 17 + 7) % 60, second=0, microsecond=0)
                if anterior and cuando <= anterior:
                    cuando = anterior + timedelta(minutes=25 + (i * 13) % 90)
                anterior = cuando
                s.add(Message(alias_id=a.id, canal=canal, direccion=direccion, autor=autor,
                              texto=texto, asunto=asunto, resumen=resumen, creado=cuando,
                              adjuntos_json=json.dumps(adj, ensure_ascii=False)))

            for de_quien, texto, dias in c["compromisos"]:
                s.add(Commitment(alias_id=a.id, de_quien=de_quien, texto=texto,
                                 vence=AHORA + timedelta(days=dias)))
            s.commit()

        m = Message(alias_id=None, canal=SIN_IDENTIFICAR["canal"], direccion="entrante",
                    autor="cliente", texto=SIN_IDENTIFICAR["texto"],
                    remitente=SIN_IDENTIFICAR["remitente"],
                    creado=h(SIN_IDENTIFICAR["horas"]),
                    sugerencia_alias_id=por_nombre[SIN_IDENTIFICAR["sugerencia_nombre"]],
                    sugerencia_score=SIN_IDENTIFICAR["score"],
                    sugerencia_motivo=SIN_IDENTIFICAR["motivo"])
        s.add(m)
        s.commit()

        # los briefings se guardan ya calculados: ninguna ficha abre esperando a la IA
        from app.logic import dias_de_contacto, pelota, por_canal, ritmo, temperatura
        from app.pipeline import mensajes_de
        for c in CLIENTES:
            alias_id = por_nombre[c["nombre"]]
            alias = s.get(Alias, alias_id)
            msgs = mensajes_de(s, alias_id)
            data = dict(c["briefing"])
            r = ritmo(msgs)
            data["pelota"] = pelota(msgs)
            data["ritmo"] = r
            data["temperatura"] = temperatura(msgs, r)
            data["dias_contacto"] = dias_de_contacto(alias)
            data["canales"] = sorted({m.canal for m in msgs})
            textos = data.get("por_canal") or {}
            cortes = por_canal(msgs)
            for corte in cortes:
                corte["resumen"] = textos.get(corte["canal"]) or (
                    "Lo último por acá: «"
                    + [m for m in msgs if m.canal == corte["canal"]][-1].texto.strip()[:170] + "»")
            data["por_canal"] = cortes
            data["generado"] = AHORA.isoformat(timespec="seconds")
            s.add(Briefing(alias_id=alias_id, data_json=json.dumps(data, ensure_ascii=False)))
        s.commit()

    print(f"Sembrados {len(CLIENTES)} clientes y 1 mensaje sin identificar.")
    print("Token de la vista del cliente para la demo: laespiga")


if __name__ == "__main__":
    sembrar()
