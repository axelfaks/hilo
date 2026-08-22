# Hilo

Un solo hilo por cliente, sin importar por dónde te escriba. Y un vendedor con IA
que lo sigue por vos.

## Arrancar (tres comandos)

```bash
pip install -r requirements.txt
python seed.py        # carga los 10 clientes de demo
python run.py         # -> http://localhost:8000
```

Y listo: `run.py` sirve la app compilada y la API desde un solo puerto, e imprime
la dirección de red para abrir la vista del cliente desde el celular.

> **En Windows no uses `uvicorn` a secas.** `pip` deja `uvicorn.exe` en una carpeta
> que PowerShell no tiene en el PATH y te va a decir que el término no se reconoce.
> `python run.py` (o `python -m uvicorn app.main:app --port 8000`) lo evita.

Para programar el front con recarga en caliente, en otra terminal:

```bash
cd web && npm install && npm run dev    # -> http://localhost:5173
python run.py --reload                  # el backend, en la primera terminal
```

Hacé ese `npm install` apenas puedas, mientras la red del evento funcione.
Antes de la demo, `cd web && npm run build` para que `run.py` sirva la última versión.

Así la app y la vista del cliente salen de `http://<tu-ip>:8000` y el celular del
público entra por la misma dirección.

> **Seguro contra el wifi:** el repo ya viene con `web/dist` compilado. Si `npm
> install` falla en el evento, `uvicorn app.main:app --host 0.0.0.0 --port 8000`
> igual levanta la app entera. Solo perdés el recargado en caliente mientras
> programás.

## Pantallas

| Ruta | Qué es |
|---|---|
| `#/` | La cola: quién te está esperando, ordenado por urgencia real |
| `#/a/1` | La ficha del cliente: briefing, hilo unificado, filtro por canal, redactor y autonomía |
| `#/admin` | El panel: etapas del negocio, reglamento del agente, autonomía por defecto |
| `#/c/laespiga` | **La vista del cliente.** Es la que se abre en el celular durante la demo |

## La IA

Copiá `.env.example` a `.env` y pegá **una** clave, la que tengas:

```
GEMINI_API_KEY=...          # https://aistudio.google.com/apikey  (capa gratuita)
# o
ANTHROPIC_API_KEY=sk-ant-...  # https://platform.claude.com/settings/keys
```

Nada más. `run.py` lee el `.env` solo y te avisa al arrancar qué quedó conectado.
`.env` está en el `.gitignore`.

Todo el trato con el modelo vive en `app/ai.py`, detrás de una sola función
(`_preguntar`). Cambiar de proveedor no toca ninguno de los cinco prompts. Con
Gemini la app le pregunta a Google qué modelos tiene habilitados y elige un flash
sola, así que no hay que adivinar nombres de versión.

Sin clave la app **sigue funcionando**: la pelota, el silencio, el ritmo y la
temperatura se calculan en Python y no dependen del modelo. Lo único que se
degrada es el texto cualitativo del briefing y el borrador de la respuesta.
Eso es a propósito: si se cae el wifi del evento, la demo no se cae con él.

Para forzar el modo local aunque haya clave: `export HILO_OFFLINE=1`.

Las cinco llamadas viven en `app/ai.py`, una función por prompt:
`briefing`, `redactar`, `sugerir_estados`, `identificar` y `responder_como_cliente`.

## El hilo y los canales

El hilo va en orden cronológico: **lo recibido a la izquierda, lo enviado a la
derecha**, con el color del canal en el borde de cada mensaje y el asunto arriba
cuando es un mail.

Arriba del hilo hay un filtro por canal con el conteo de cada uno. Al elegir uno,
aparece **el resumen de esa conversación en particular** — qué se habló por ahí y
de quién es la pelota en ese canal. Ese texto sale de la misma llamada que arma el
briefing, así que no cuesta ni una llamada extra ni un segundo más de espera.

La llamada y la visita aparecen como canal pero no se puede escribir por ahí: se
registran, no se contestan.

## Escribir un mensaje

El redactor está al pie del hilo. Elegís canal y el formulario se adapta: **el
campo Asunto aparece solo en el mail**, porque es el único canal que lo tiene.
Si la IA dejó un borrador, "Traer el borrador de la IA" lo carga con su asunto y
su canal para que lo edites antes de mandarlo.

## Probar el agente contra un cliente de mentira

Cada cliente sembrado tiene una **personalidad**: cómo escribe, qué objeta, qué lo
hace avanzar y qué lo hace desaparecer. Está en `seed.py`, en el diccionario
`PERSONAS`, y es lo que hace que la prueba sirva: lo importante de cada ficha son
las dos últimas líneas, las condiciones de avance y de abandono.

Desde la ficha, en la columna derecha:

- **Que conteste el cliente** — la IA se pone en ese papel y escribe el próximo
  mensaje. Entra por `/api/ingest`, igual que cualquier otro, así que dispara el
  briefing, el estado y el agente.
- **Que conversen solos ×3** — cliente y agente se responden hasta tres rondas. Se
  corta antes si el cliente se va o si está listo para cerrar.

Después de cada turno el simulador te dice si el cliente **se calentó, quedó igual
o se enfrió**, y por qué. Eso es lo que te dice si tu prompt y tus barandas están
funcionando o te están arruinando la venta.

Los mensajes que salen de acá quedan marcados como **prueba** en el hilo y se
borran con un botón, así la base vuelve limpia antes de la demo de verdad.

Sin clave de API el botón igual funciona: usa las respuestas de reserva sembradas
en cada cliente.

## Resetear entre ensayos

```bash
python seed.py                        # o POST /api/reset, sin reiniciar el server
```

Vacía y recarga las tablas sin borrar el archivo, así el servidor puede quedar
levantado.

## Cómo está armado

- `app/models.py` — las seis tablas.
- `app/logic.py` — **lo que se calcula, se calcula**: pelota, ritmo, temperatura,
  urgencia. Ningún número de estos sale del modelo, así que ninguno se alucina.
- `app/ai.py` — las cuatro llamadas, con fallback local.
- `app/pipeline.py` — qué pasa cuando entra un mensaje: identificar, rearmar el
  briefing, mover la etapa, y actuar según la autonomía del cliente.
- `app/main.py` — los endpoints.
- `web/src/` — React. `design.css` es el sistema visual de la dirección B.

## Los seis niveles de autonomía

| | | |
|---|---|---|
| 0 | Silencio | No hace nada |
| 1 | Observa | Solo mantiene el resumen al día |
| 2 | Sugiere | Deja el borrador escrito |
| 3 | Pide permiso | Redacta y te avisa; vos apretás enviar |
| 4 | Con barandas | Envía sola si no toca precio ni temas sensibles |
| 5 | Autónoma | Envía sola siempre, dentro del reglamento |

Se fija un nivel por defecto en `#/admin` y se sobreescribe cliente por cliente
desde la ficha.

## Una sola puerta de entrada

Todos los mensajes entran por `POST /api/ingest`. Hoy la usa la vista del cliente;
el día que conectemos una casilla real, el lector de mails llama al mismo endpoint
y no cambia nada más.
