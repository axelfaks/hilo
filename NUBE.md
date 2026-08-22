# Subir el backend a internet

## Lo rápido (5 minutos, sin crear ninguna cuenta)

Un túnel de Cloudflare te da una URL pública HTTPS apuntando a tu `localhost:8000`.
No hay que registrarse ni configurar nada.

En una **segunda ventana de PowerShell** (dejá el server corriendo en la primera):

```powershell
winget install --id Cloudflare.cloudflared
cloudflared tunnel --url http://localhost:8000
```

Te va a imprimir algo como `https://algo-random-aca.trycloudflare.com`. **Esa URL
es la app entera**: la API y el frontend salen del mismo puerto, así que Mars la
abre y ve todo, y el celular de cualquiera del público también.

Lo que hay que saber:

- La URL cambia cada vez que reiniciás el túnel. Si la vas a repartir, no la
  reinicies.
- Mientras el túnel esté abierto, tu app está en internet. **Creá tu cuenta
  apenas la levantes** (ver abajo): hasta que exista un usuario, la API está
  abierta a cualquiera que tenga el link.
- Si cerrás la notebook, se cae. Para la demo alcanza; para algo que dure, no.

### Que no se caiga

`tunel.ps1` levanta el túnel, escribe la dirección en `url-publica.txt` y lo
vuelve a levantar solo si se cae:

```powershell
.\tunel.ps1
```

## El deploy de verdad

El repo ya está listo para subir a cualquier hosting: `Dockerfile`, `Procfile` y
`render.yaml`. No queda nada por preparar, solo hace falta una cuenta.

**Con Render, que es el camino más corto:**

```powershell
git init
git add -A
git commit -m "Hilo"
```

Después: creás un repo vacío en github.com, pegás los dos comandos que te da
GitHub para subirlo, entrás a render.com, **New → Blueprint** y elegís el repo.
Render lee `render.yaml` solo: levanta el servicio, crea la base Postgres y las
conecta. Lo único que tenés que hacer a mano es pegar `GEMINI_API_KEY` en
Environment.

### Lo que ya está resuelto para que eso funcione

- **La base se adapta sola.** Si existe `DATABASE_URL` usa Postgres; si no, sigue
  con el archivo SQLite. No hay que tocar código. Para Postgres se instala también
  `requirements-nube.txt`, que el Dockerfile ya incluye.
- **El puerto también.** `run.py` y el `CMD` del Dockerfile respetan `$PORT`, que
  es lo que asignan estos hostings.
- **La base arranca vacía en la nube.** Con `HILO_SEMBRAR=1` se cargan los datos
  de demo la primera vez y nunca más: si ya hay clientes, no toca nada.
- **El `.env` no se sube** (está en `.gitignore` y en `.dockerignore`). Las claves
  se cargan como variables de entorno desde el panel.
- **`HILO_SECRETO` como variable de entorno.** Si no, cada deploy genera un secreto
  nuevo y desloguea a todo el mundo. En `render.yaml` ya está declarado para que
  Render lo genere una vez.

## El login

La API se protege sola **en cuanto existe el primer usuario**. Hasta ese momento
la app funciona abierta y te ofrece crear la cuenta: así nunca te quedás afuera
de tu propia instalación por un problema de configuración.

1. Abrí la app y creá tu cuenta. Esa primera cuenta es la dueña.
2. A partir de ahí, todo `/api/*` pide el token. Las dos excepciones son a
   propósito: `/api/auth/*` y `/api/cliente/{token}`, que es la pantalla que
   abre el cliente en su celular y no tiene por qué tener cuenta.

Para sumar a alguien más al equipo, ya logueado:

```
POST /api/auth/usuarios   { "email": "...", "password": "...", "nombre": "...", "rol": "vendedor" }
```

### Detalles que importan

- La contraseña no se guarda: se guarda `scrypt` con sal aleatoria por usuario.
- El token es un JSON firmado con HMAC-SHA256 y vence a los 30 días. No hay
  sesiones en memoria, así que reiniciar el server no deslogea a nadie.
- La firma sale de `.hilo_secreto`, un archivo que se crea solo la primera vez y
  está en el `.gitignore`. Si lo borrás, se caen todas las sesiones y hay que
  volver a entrar. En un hosting, poné `HILO_SECRETO` como variable de entorno.
- `python seed.py` **no borra los usuarios**. Podés resetear la demo todas las
  veces que quieras sin perder tu cuenta.
- Para apagar el login mientras programás: `HILO_AUTH=0` en el `.env`.

### Endpoints

| | |
|---|---|
| `GET /api/auth/estado` | si ya hay cuenta creada y si la API está protegida |
| `POST /api/auth/registro` | crea la primera cuenta; después devuelve 403 |
| `POST /api/auth/login` | `{email, password}` → `{token, usuario}` |
| `GET /api/auth/yo` | el usuario del token |
| `GET/POST /api/auth/usuarios` | listar e invitar (requiere estar logueado) |

El frontend guarda el token en `localStorage` y lo manda en `Authorization:
Bearer`. Si el backend contesta 401, borra el token y vuelve a la pantalla de
entrada solo.
