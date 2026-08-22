"""Las cuatro llamadas a la IA.

Regla de oro en los cuatro prompts: si un dato no esta en el hilo, el campo va
vacio. Un briefing con un campo vacio es honesto; uno con un dato inventado te
hunde la presentacion.

Si no hay clave de API o HILO_OFFLINE=1, todo sigue funcionando con respuestas
calculadas localmente. La app nunca se cae por el wifi del evento.
"""
import json
import os
import re
import time

from .logic import CANALES

# ---------------------------------------------------------------------------
# Un solo lugar habla con un modelo. Cambiar de proveedor es cambiar esta parte
# y nada mas: los cinco prompts de abajo no saben quien les contesta.
#
#   GEMINI_API_KEY  -> usa Gemini (tiene capa gratuita, no pide tarjeta)
#   ANTHROPIC_API_KEY -> usa Claude
#
# Si estan las dos, gana la que diga HILO_PROVEEDOR (gemini | anthropic).
# ---------------------------------------------------------------------------

_estado = {"modelo": None, "candidatos": [], "cliente": None, "error": "",
           "llamadas": 0, "errores": [], "ultimo_pedido": 0.0}

# La capa gratuita limita pedidos por minuto. Si mandamos tres llamadas juntas
# (briefing + redactor + cliente simulado) nos come la cuota y todo se cae al
# modo local. Un espaciado minimo entre pedidos evita el problema entero.
ESPACIADO_SEG = 1.2


def _esperar_turno():
    falta = ESPACIADO_SEG - (time.monotonic() - _estado["ultimo_pedido"])
    if falta > 0:
        time.sleep(falta)
    _estado["ultimo_pedido"] = time.monotonic()


def _anotar_error(modelo: str, e: Exception):
    _estado["errores"] = ([f"{modelo}: {str(e)[:160]}"] + _estado["errores"])[:6]

MODELOS_ANTHROPIC = ["claude-sonnet-4-5", "claude-sonnet-4-20250514", "claude-3-5-sonnet-latest"]
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def clave_gemini() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


def clave_anthropic() -> str:
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def proveedor() -> str:
    """Cual de los dos se usa. Vacio = modo local, sin IA."""
    if os.environ.get("HILO_OFFLINE") == "1":
        return ""
    preferido = (os.environ.get("HILO_PROVEEDOR") or "").strip().lower()
    if preferido == "gemini" and clave_gemini():
        return "gemini"
    if preferido == "anthropic" and clave_anthropic():
        return "anthropic"
    if clave_gemini():
        return "gemini"
    if clave_anthropic():
        return "anthropic"
    return ""


def offline() -> bool:
    return not proveedor()


def como_esta() -> dict:
    """Para mostrar en la pantalla de configuracion que hay conectado."""
    p = proveedor()
    return {"proveedor": p or "local", "modelo": _estado["modelo"] or "",
            "activa": bool(p), "ultimo_error": _estado["error"],
            "llamadas": _estado["llamadas"], "errores": _estado["errores"]}


def _json_de(texto: str) -> dict:
    """Los modelos a veces envuelven el JSON en prosa o en un bloque de codigo."""
    texto = (texto or "").strip()
    texto = re.sub(r"^```(?:json)?|```$", "", texto, flags=re.MULTILINE).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio >= 0 and fin > inicio:
        try:
            return json.loads(texto[inicio:fin + 1])
        except json.JSONDecodeError:
            pass
    return {}


# ------------------------------------------------------------------- Gemini

def _http_json(url: str, cuerpo: dict | None = None, timeout: int = 60) -> dict:
    import urllib.error
    import urllib.request
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(
        url, data=datos, method="POST" if datos else "GET",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code}: {detalle}") from e


def _candidatos_gemini(clave: str) -> list:
    """Le preguntamos a Google que modelos tiene habilitados la cuenta y armamos
    una lista ordenada. No elegimos uno solo: si el primero esta retirado, se cae
    al siguiente. Los nombres de version cambian seguido y no queremos que eso
    rompa la app en el medio de una demo."""
    if _estado["candidatos"]:
        return _estado["candidatos"]

    fijado = (os.environ.get("GEMINI_MODEL") or "").strip()
    if fijado:
        _estado["candidatos"] = [fijado]
        return _estado["candidatos"]

    datos = _http_json(f"{GEMINI_BASE}/models?key={clave}&pageSize=200", timeout=25)
    utiles = [m["name"].split("/")[-1] for m in datos.get("models", [])
              if "generateContent" in m.get("supportedGenerationMethods", [])]

    def sirve(m: str) -> bool:  # nada de voz, imagen ni embeddings
        return not any(x in m for x in ("tts", "image", "embedding", "vision",
                                        "live", "audio", "native", "gemma"))

    def version(m: str) -> float:
        n = re.findall(r"(\d+(?:\.\d+)?)", m)
        return float(n[0]) if n else 0.0

    flash = [m for m in utiles if "flash" in m and sirve(m)]
    orden = []
    # los alias "latest" son la apuesta segura: Google los mueve solo
    if "gemini-flash-latest" in flash:
        orden.append("gemini-flash-latest")
    orden += [m for m in flash if m.endswith("-latest") and "lite" not in m and m not in orden]
    estables = [m for m in flash if m not in orden and "preview" not in m and "lite" not in m]
    orden += sorted(estables, key=version, reverse=True)
    orden += sorted([m for m in flash if m not in orden], key=version, reverse=True)
    orden += [m for m in utiles if "pro" in m and sirve(m) and m not in orden][:2]

    if not orden:
        raise RuntimeError("la cuenta no tiene ningun modelo de texto habilitado")
    _estado["candidatos"] = orden[:4]   # acotado: cada intento fallido suma segundos
    print(f"[hilo] Gemini: voy a probar {_estado['candidatos']}")
    return _estado["candidatos"]


def _cuerpo_gemini(system: str, prompt: str, max_tokens: int, sin_pensar: bool) -> dict:
    gen = {
        "temperature": 0.35,
        # los modelos nuevos gastan parte del techo de salida "pensando": si queda
        # corto devuelven MAX_TOKENS y ni una linea de texto. Damos aire de sobra.
        "maxOutputTokens": max(max_tokens, 2048),
        "responseMimeType": "application/json",
    }
    if sin_pensar:
        gen["thinkingConfig"] = {"thinkingBudget": 0}
    return {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen,
    }


def _texto_de_gemini(r: dict) -> str:
    cand = (r.get("candidates") or [{}])[0]
    partes = (cand.get("content") or {}).get("parts") or []
    texto = "".join(p.get("text", "") for p in partes)
    if not texto:
        motivo = cand.get("finishReason") or r.get("promptFeedback") or "respuesta vacia"
        raise RuntimeError(f"el modelo no devolvio texto ({motivo})")
    return texto


def _demora_sugerida(texto: str) -> float:
    """Cuando es cuota, Google dice cuanto esperar. Le hacemos caso, con techo."""
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', texto)
    return min(float(m.group(1)), 6.0) if m else 0.0


def _un_intento(modelo: str, clave: str, system: str, prompt: str, max_tokens: int) -> dict:
    _esperar_turno()
    url = f"{GEMINI_BASE}/models/{modelo}:generateContent?key={clave}"
    try:
        return _json_de(_texto_de_gemini(
            _http_json(url, _cuerpo_gemini(system, prompt, max_tokens, True))))
    except RuntimeError as e:
        # los modelos viejos no conocen thinkingConfig: reintentamos sin eso
        if "HTTP 400" not in str(e):
            raise
        return _json_de(_texto_de_gemini(
            _http_json(url, _cuerpo_gemini(system, prompt, max_tokens, False))))


# El modelo esta retirado: no vuelve nunca, hay que cambiarlo.
RETIRADOS = ("404", "no longer available", "NOT_FOUND")
# El modelo esta saturado o nos pasamos de cuota: puede andar en un rato, y casi
# siempre hay otro modelo libre. Es lo mas comun en la capa gratuita.
TRANSITORIOS = ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED",
                "high demand", "overloaded", "500", "INTERNAL")


def _es(texto: str, marcas: tuple) -> bool:
    return any(m.lower() in texto.lower() for m in marcas)


def _preguntar_gemini(system: str, prompt: str, max_tokens: int) -> dict:
    """Recorre los modelos disponibles hasta que uno conteste. En la capa gratuita
    los 503 son moneda corriente: en vez de fallar, se prueba el que sigue."""
    clave = clave_gemini()
    intentos = list(_candidatos_gemini(clave))
    if _estado["modelo"]:                      # el que venia andando va primero
        intentos = [_estado["modelo"]] + [m for m in intentos if m != _estado["modelo"]]

    ultimo = None
    for modelo in [m for m in intentos if m]:
        for reintento in range(2):
            try:
                r = _un_intento(modelo, clave, system, prompt, max_tokens)
                if _estado["modelo"] != modelo:
                    print(f"[hilo] Gemini: uso {modelo}")
                _estado["modelo"] = modelo
                return r
            except RuntimeError as e:
                ultimo, texto = e, str(e)
                _anotar_error(modelo, e)
                if _es(texto, TRANSITORIOS) and reintento == 0:
                    time.sleep(_demora_sugerida(texto) or 0.8)
                    continue
                if _es(texto, RETIRADOS):
                    sugerido = re.search(r"models/([A-Za-z0-9.\-]+)", texto.split("use")[-1])
                    if sugerido and sugerido.group(1) not in intentos:
                        intentos.append(sugerido.group(1))
                elif not _es(texto, TRANSITORIOS):
                    raise                      # esto no se arregla cambiando de modelo
                if _estado["modelo"] == modelo:
                    _estado["modelo"] = None   # el fijado dejo de servir
                print(f"[hilo] Gemini: {modelo} no contesto, pruebo el siguiente")
                break
    raise RuntimeError(f"ningun modelo contesto. Ultimo: {ultimo}")


# ------------------------------------------------------------------ Anthropic

def _preguntar_anthropic(system: str, prompt: str, max_tokens: int) -> dict:
    if _estado["cliente"] is None:
        from anthropic import Anthropic
        _estado["cliente"] = Anthropic()
    fijado = (os.environ.get("ANTHROPIC_MODEL") or "").strip()
    candidatos = [_estado["modelo"]] if _estado["modelo"] else ([fijado] if fijado else []) + MODELOS_ANTHROPIC
    ultimo = None
    for modelo in [c for c in candidatos if c]:
        try:
            r = _estado["cliente"].messages.create(
                model=modelo, max_tokens=max_tokens, temperature=0.35,
                system=system, messages=[{"role": "user", "content": prompt}],
            )
            _estado["modelo"] = modelo
            return _json_de(r.content[0].text)
        except Exception as e:
            ultimo = e
            if "model" not in str(e).lower():
                break
    raise RuntimeError(str(ultimo))


# --------------------------------------------------------------------- puerta

def _preguntar(system: str, prompt: str, max_tokens: int = 1200) -> dict:
    """Devuelve {} si algo falla. Nunca revienta: la app tiene que seguir viva."""
    p = proveedor()
    try:
        if p == "gemini":
            r = _preguntar_gemini(system, prompt, max_tokens)
        elif p == "anthropic":
            r = _preguntar_anthropic(system, prompt, max_tokens)
        else:
            return {}
        _estado["error"] = ""
        _estado["llamadas"] += 1
        return r
    except Exception as e:
        _estado["error"] = f"{type(e).__name__}: {e}"[:400]
        print(f"[hilo] la IA no respondio ({e}); sigo con el calculo local")
    return {}


# ---------------------------------------------------------------- 1. briefing

SYS_BRIEFING = """Sos el analista de un equipo de ventas chico. Leés la conversación
completa con un cliente y devolvés una ficha para que el vendedor entienda la
situación en cinco segundos, sin leer el hilo.

Reglas que no se negocian:
- Español rioplatense, directo, sin adjetivos de relleno.
- Si un dato no está explícito en el hilo, dejá el campo vacío. Nunca lo deduzcas
  ni lo inventes: preferimos un campo vacío a un dato falso.
- "quien_es" es una sola oración con lo que importa para venderle.
- Cada punto de "lo_ultimo" es un hecho concreto del hilo, no un resumen genérico.
- Los compromisos son promesas explícitas, de cualquiera de los dos lados.
- "estado" tiene que ser una de las etapas que te paso, tal cual está escrita.
- "por_canal" lleva UNA entrada por cada canal que aparezca en el hilo, con una o
  dos oraciones sobre qué se habló específicamente por ahí. No repitas el resumen
  general: lo que importa es qué conversación vive en cada canal.
- "por_que_ahora": una sola oración que justifique el próximo paso. Es lo que lee
  el vendedor antes de decidir si le hace caso, así que tiene que dar la razón, no
  repetir la instrucción.
- "resumen_mensajes": una línea por cada mensaje marcado SIN-RESUMEN, con su
  número de #id como clave. Cada línea dice QUÉ PASÓ en ese mensaje, en presente y
  en menos de doce palabras: "Reclama el número prometido y pone fecha límite",
  "Prometés una alternativa de precio para el lunes". No es un resumen del texto:
  es qué significó ese mensaje dentro de la negociación. Si un mensaje no está
  marcado SIN-RESUMEN, no lo incluyas.

Devolvés SOLO un objeto JSON, sin texto alrededor, con esta forma:
{"quien_es": str,
 "lo_ultimo": [str, str, str],
 "estado": str,
 "por_que_estado": str,
 "compromisos": [{"de_quien": "nosotros"|"cliente", "texto": str, "vence": "AAAA-MM-DD"|""}],
 "proximo_paso": str,
 "senal_de_urgencia": str,
 "por_que_ahora": str,
 "por_canal": {"<canal>": str},
 "resumen_mensajes": {"<id>": str}}"""


def briefing(hilo: str, etapas: list, nombre: str) -> dict:
    if offline():
        return {}
    return _preguntar(
        SYS_BRIEFING,
        f"Cliente: {nombre}\nEtapas posibles: {', '.join(etapas)}\n\nCONVERSACIÓN:\n{hilo}",
    )


# ---------------------------------------------------------------- 2. redactor

SYS_REDACTOR = """Sos el vendedor de este negocio escribiendo la próxima respuesta.
Te digo por qué canal sale, y eso cambia cómo se escribe: un mail lleva asunto y
puede ser un poco más formal; un WhatsApp o un Instagram son cortos, sin asunto y
sin saludo protocolar.
Escribís como una persona, no como un chatbot: sin "estimado", sin "quedo a
disposición", sin entusiasmo de más.

Reglas:
- Español rioplatense. Corto: cuatro oraciones como máximo.
- Retomá lo último que dijo el cliente y hacete cargo si le debemos algo.
- Terminá siempre con un próximo paso concreto y fácil de aceptar.
- Respetá el reglamento del negocio que te paso. Si para contestar bien tendrías
  que romperlo, no escribas la respuesta: marcá escalar=true y decí por qué.

Devolvés SOLO un objeto JSON:
{"asunto": str, "texto": str, "escalar": bool, "motivo_escalada": str}"""


AJUSTES_DE_TONO = {
    "corto": "Escribilo MÁS CORTO que tu primer instinto: dos oraciones como máximo, sin preámbulo.",
    "calido": "Escribilo MÁS CÁLIDO: reconocé el momento de la persona antes de ir al punto, sin volverte meloso.",
    "firme": "Escribilo MÁS FIRME: sin disculpas de más, con una fecha o un compromiso concreto y un pedido claro.",
}


def redactar(hilo: str, reglas: dict, nombre: str, canal: str, tono: str = "") -> dict:
    if offline():
        return {}
    extra = AJUSTES_DE_TONO.get(tono, "")
    return _preguntar(
        SYS_REDACTOR + (f"\n\nAJUSTE PEDIDO PARA ESTA VERSIÓN\n{extra}" if extra else ""),
        f"Cliente: {nombre}\nCanal por el que vas a responder: {CANALES.get(canal, canal)}\n"
        f"Reglamento del negocio: {json.dumps(reglas, ensure_ascii=False)}\n\n"
        f"CONVERSACIÓN:\n{hilo}",
        max_tokens=700,
    )


# ------------------------------------------------------- 3. estados del negocio

SYS_ESTADOS = """Sos consultor comercial. Te describen un negocio y proponés las
etapas por las que pasa un cliente desde que aparece hasta que compra o se pierde.

Reglas:
- Entre 5 y 7 etapas, en orden.
- Nombres cortos, en español rioplatense, que un vendedor de ese rubro usaría de
  verdad. Nada de jerga de CRM importada.
- Incluí siempre una etapa final ganada y una perdida.

Devolvés SOLO un objeto JSON:
{"estados": [str], "por_que": str}"""


def sugerir_estados(descripcion: str) -> dict:
    if offline():
        return {}
    return _preguntar(SYS_ESTADOS, f"El negocio:\n{descripcion}", max_tokens=500)


# ------------------------------------------------- 3 bis. configurar el negocio

SYS_CONFIG = """Sos consultor comercial y estás configurando el agente de ventas de
un negocio del que solo sabés lo que su dueño te acaba de contar en dos o tres
oraciones. Tenés que dejarle todo propuesto para que él solo corrija lo que no le
cierre.

Reglas:
- Las etapas: entre 5 y 7, en orden, con nombres que un vendedor de ESE rubro usaría
  de verdad. Nada de jerga de CRM importada. Siempre una etapa ganada y una perdida.
- El tono: describilo en una oración, como una instrucción para quien escribe. Que
  refleje el rubro: no escribe igual una panadería de barrio que un estudio jurídico.
- El horario: en qué franja tiene sentido que este negocio le escriba a un cliente.
- La insistencia: cada cuántos días y cuántas veces, según lo largo que sea el ciclo
  de venta de ese rubro.
- El descuento máximo que el agente puede ofrecer solo: si no hay señales de que
  manejen descuentos, poné 0.
- Los temas que obligan a escalar a un humano: los que en ese rubro son delicados
  (plata grande, contratos, reclamos, temas legales o de salud).
- Los canales: por dónde le escriben los clientes a un negocio así.
- Si algo no se puede deducir de lo que te contaron, elegí el valor más conservador.
  No inventes datos del negocio.

Devolvés SOLO un objeto JSON:
{"rubro": str,
 "estados": [str],
 "estados_cerrados": [str],
 "reglas": {"tono": str, "horario": [int, int], "insistir_cada_dias": int,
            "max_insistencias": int, "descuento_max": int, "temas_escalan": [str]},
 "canales": [str],
 "por_que": str}"""


def configurar_negocio(descripcion: str) -> dict:
    """El corazón del onboarding: de dos oraciones a la app configurada."""
    if offline():
        return {}
    return _preguntar(SYS_CONFIG, f"Esto me contó el dueño:\n{descripcion}", max_tokens=1600)


# ------------------------------------------------------ 4. matcher de identidad

SYS_MATCH = """Llegó un mensaje de alguien que el sistema no tiene registrado.
Decidís si pertenece a algún cliente que ya existe.

Pistas válidas: el dominio del mail, la firma, la empresa que menciona, que
retome un tema que ya venía conversándose, nombres propios compartidos.

Sé conservador: fusionar dos clientes distintos es peor que dejar uno sin
identificar. Si dudás, devolvé alias_id null.

Devolvés SOLO un objeto JSON:
{"alias_id": int|null, "confianza": 0-100, "motivo": str}"""


def identificar(remitente: str, texto: str, candidatos: list) -> dict:
    if offline():
        return {}
    resumen = "\n".join(
        f"- id {c['id']}: {c['nombre']} ({c['contacto']}) — identidades: {', '.join(c['identidades'])}"
        for c in candidatos
    )
    return _preguntar(
        SYS_MATCH,
        f"Mensaje nuevo de: {remitente}\nTexto: {texto}\n\nClientes existentes:\n{resumen}",
        max_tokens=400,
    )


# --------------------------------------------------- 5. el cliente, interpretado

SYS_CLIENTE = """Estás actuando como un cliente real en una conversación de venta.
No sos un asistente: sos esta persona, con su plata, su desconfianza y su apuro.

Cómo se juega:
- Escribí como escribe esa persona según su ficha: si es de mandar mensajes cortos
  y sin mayúsculas, mandalos así; si es formal, escribí formal. Uno o dos párrafos
  como máximo, y muchas veces una sola línea.
- No seas complaciente. Si el vendedor no te resolvió lo que te importa, decilo,
  repetí tu objeción o directamente dilatá.
- No compres porque te lo pidieron. Comprá solamente si pasó lo que tu ficha dice
  que te haría avanzar. Si pasó lo que te haría abandonar, abandoná.
- Nunca menciones que sos una IA ni que esto es una simulación.
- Nunca inventes datos nuevos de tu negocio que contradigan el historial.

Además de escribir el mensaje, evaluás honestamente cómo te dejó el último
movimiento del vendedor.

Devolvés SOLO un objeto JSON:
{"texto": str,
 "canal": "<uno de los canales disponibles>",
 "temperatura": "mas_caliente" | "igual" | "mas_frio",
 "por_que": str,
 "listo_para_cerrar": bool,
 "se_va": bool}"""


def responder_como_cliente(alias_nombre: str, contacto: str, persona: str,
                           negocio: str, hilo: str, canales: list) -> dict:
    if offline():
        return {}
    return _preguntar(
        SYS_CLIENTE,
        f"TU FICHA\n"
        f"Sos {contacto or alias_nombre}, de {alias_nombre}.\n{persona}\n\n"
        f"QUIÉN TE ESTÁ VENDIENDO\n{negocio}\n\n"
        f"CANALES POR LOS QUE PODÉS ESCRIBIR\n{', '.join(canales)}\n\n"
        f"LA CONVERSACIÓN HASTA ACÁ (vos sos el CLIENTE)\n{hilo}\n\n"
        f"Escribí tu próximo mensaje.",
        max_tokens=700,
    )


# ------------------------------------------------------------------ diagnostico

def diagnostico() -> dict:
    """Que esta pasando de verdad con la IA. No devuelve la clave, solo su forma."""
    p = proveedor()
    clave = clave_gemini() if p == "gemini" else clave_anthropic()
    info = {
        "proveedor": p or "local",
        "clave_largo": len(clave),
        "clave_empieza": clave[:6] + "…" if clave else "",
        "clave_tiene_espacios": (" " in clave) or ("\n" in clave) or ("\r" in clave),
        "modelo_elegido": _estado["modelo"] or "",
        "ultimo_error": _estado["error"],
        "llamadas_ok": _estado["llamadas"],
    }
    info["errores_recientes"] = _estado["errores"]
    if p != "gemini":
        return info
    try:
        info["candidatos"] = _candidatos_gemini(clave)
        info["listar_modelos"] = "ok"
    except Exception as e:
        info["listar_modelos"] = f"FALLO -> {e}"
        return info
    try:
        r = _preguntar(
            "Devolvés SOLO un objeto JSON.",
            'Respondé exactamente {"ok": true, "saludo": "hola"}',
            max_tokens=200,
        )
        info["modelo_elegido"] = _estado["modelo"] or ""
        info["prueba_generacion"] = r if r else f"vacio -> {_estado['error']}"
    except Exception as e:
        info["prueba_generacion"] = f"FALLO -> {e}"
    return info
