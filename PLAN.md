# Hilo — decisiones y plan del hackatón

**Página del plan (completa, con los prompts copiables):** https://claude.ai/code/artifact/1a0da5ce-7142-4f3a-b323-f11b3a850bb9

## Qué es
Una app donde cada cliente o lead es un **alias** con varias identidades colgando (mail, WhatsApp,
Instagram, Telegram, teléfono). Todo lo que entra por cualquiera de esas puertas cae en un **único hilo
cronológico**, junto con las conversaciones no digitales que el vendedor registra a mano.
Encima del hilo corre una IA que resume, detecta de quién es la pelota, extrae compromisos, deduce la
etapa de venta y responde con la autonomía que el administrador le dé, cliente por cliente.

**Frase de pitch:** un solo hilo por cliente, sin importar por dónde te escriba, y un vendedor con IA
que lo sigue por vos.

**Problema:** se pierden ventas porque el ida y vuelta con el lead está desparramado en cinco lugares
y el seguimiento depende de que el vendedor se acuerde.

## Decisiones tomadas
| Decisión | Elegido | Por qué |
|---|---|---|
| Stack | FastAPI + SQLModel + SQLite / React + Vite | Axel construye más rápido así |
| Proveedor de IA | Gemini (capa gratuita) con Claude como alternativa | Una sola función habla con el modelo: cambiar cuesta nada |
| Canales | **Todos simulados**, con un canal propio en vivo | Sin OAuth ni plomería; el loop igual es real |
| Actualización en pantalla | Polling cada 2 s, no WebSocket | Media hora que no hay, efecto idéntico |
| Roles | Axel backend + IA · Toto diseño | La integración se hace en la sesión con Claude |
| Audio | Web Speech API del navegador | Gratis, instantáneo, sin backend |
| Nombre | Hilo | Es literalmente lo que hace |

## El truco que sostiene la demo
Los canales son simulados pero **el loop es real**. Hay una segunda URL (`/c/<token>`) que se ve como
el celular del cliente: alguien del público escribe ahí y el mensaje entra al sistema por el mismo
endpoint `POST /ingest` por el que entraría un mail. De ahí para adentro no hay nada falso.
Dejar un mensaje sugerido precargado ("Che, seguimos esperando el precio") para que el voluntario
solo tenga que apretar enviar.

## Alcance: cinco features y nada más
1. Alias con identidades multicanal y hilo unificado.
2. Briefing de la IA al abrir la ficha: quién es, lo último, pelota, compromisos, ritmo.
3. Estados que la IA propone para el negocio y el admin edita; después se deducen del hilo.
4. Registro de conversación no digital con dictado y adjuntos.
5. Autonomía configurable por cliente, niveles 0 a 5, con barandas.

**Fuera:** login real, multiusuario, integraciones reales, mobile de la app de gestión, tests.
**Orden de descarte si vamos tarde:** wizard de estados → adjuntos → transcripción → canales extra.
El briefing y el agente respondiendo solo no se tocan.

## Modelo de datos (6 tablas)
- `business` — nombre, descripción libre, estados (JSON), reglas del agente, autonomía por defecto
- `alias` — nombre, contacto, notas, estado, autonomía propia, primer contacto
- `identity` — alias_id, canal, valor
- `message` — alias_id, canal, dirección, autor (cliente/humano/IA), texto, adjuntos, fecha
- `briefing` — alias_id, JSON del resumen, generado_at (cacheado, se recalcula al entrar un mensaje)
- `commitment` — alias_id, de quién, texto, vence_at, cumplido

Los mensajes sin alias son `message` con `alias_id = null` más una sugerencia de la IA con su confianza.

## Cinco llamadas a la IA
1. **Briefing** — entra el hilo, sale JSON estructurado. Incluye el resumen por canal.
2. **Redactor** — respuesta con el contexto del hilo y las reglas del negocio.
3. **Propuesta de estados** — el admin describe su negocio, salen las etapas.
4. **Matcher de identidades** — a qué alias se parece un mensaje huérfano y con cuánta confianza.
5. **El cliente interpretado** — la IA se pone en el papel de un cliente sembrado y escribe
   su próximo mensaje, para probar el agente sin esperar a un humano.

Todas pasan por `_preguntar()` en `app/ai.py`, que despacha a Gemini o a Claude según qué
clave haya en el `.env`. Con Gemini la app le pregunta a Google qué modelos tiene y elige
un flash sola.

Temperatura baja y salida JSON estricta en las cuatro. Regla explícita: si un dato no está en el hilo,
el campo va vacío.

## Dirección visual elegida
**Opción B — "Ficha"**: clara, serif, acento verde petróleo, con el briefing de la IA como
protagonista de la pantalla. El sistema está en `hilo/web/src/design.css`.

## Estado: el esqueleto ya funciona
El repo está en `Hackaton/hilo/` y corre de punta a punta. Probado: se manda un mensaje desde
la vista del cliente, entra por `/api/ingest`, la IA lo procesa, el hilo se actualiza solo en
la pantalla grande y el agente deja el borrador según su nivel de autonomía.

Hecho:
- Las seis tablas y el seed con 10 clientes (4 te esperan · 3 enfriándose · 1 sin identificar).
- `POST /api/ingest` como única puerta de entrada.
- Las cuatro llamadas a la IA con fallback local: sin API key la app igual anda.
- Cola, ficha, panel de admin y vista del cliente para el celular, en React.
- Autonomía 0–5 por cliente, con barandas y escalada.
- Registro de conversación no digital con dictado por voz del navegador.
- `python seed.py` o `POST /api/reset` vuelve a la posición de demo sin reiniciar nada.

También hecho después:
- Filtro por canal con resumen propio de cada uno (sale de la misma llamada del briefing).
- Hilo cronológico: recibido a la izquierda, enviado a la derecha, asunto solo en mail.
- Redactor al pie del hilo con el campo Asunto que aparece únicamente en mail.
- LinkedIn como canal.
- Simulador: cada cliente tiene una personalidad con condiciones de avance y de abandono,
  y se lo puede hacer contestar o dejar que converse solo con el agente hasta 3 rondas.

Falta:
- Poner la clave en `hilo/.env` (`GEMINI_API_KEY=...`): es lo único que separa el briefing
  genérico del bueno. Google bloqueó la creación automatizada de la clave desde el navegador,
  así que ese click lo tiene que hacer Axel.
- Que Toto corra sus 6 prompts y reemplace `design.css` y las maquetas.
- Wizard de estados: el backend ya lo tiene, falta que el admin lo dispare desde la UI real.
- Ensayar la demo tres veces con el reset entre medio.
