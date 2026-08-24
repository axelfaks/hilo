const base = ''  // en dev lo resuelve el proxy de Vite
const LLAVE = 'hilo.token'

export const sesion = {
  token: () => { try { return localStorage.getItem(LLAVE) || '' } catch { return '' } },
  guardar: (t) => { try { localStorage.setItem(LLAVE, t) } catch { /* modo privado */ } },
  borrar: () => { try { localStorage.removeItem(LLAVE) } catch { /* nada */ } },
}

/** "Ver como": mientras esté puesto, TODOS los pedidos van a esa cuenta.

    Vive en localStorage y no en el estado de React a propósito: si se pierde al
    recargar, uno recarga por costumbre y sigue clickeando creyendo que está en
    la cuenta del cliente cuando ya volvió a la suya. Salir es borrarlo. */
const CUENTA = 'hilo.vercomo'

export const verComo = {
  actual: () => { try { return JSON.parse(localStorage.getItem(CUENTA) || 'null') } catch { return null } },
  poner: (cuenta) => { try { localStorage.setItem(CUENTA, JSON.stringify(cuenta)) } catch { /* modo privado */ } },
  salir: () => { try { localStorage.removeItem(CUENTA) } catch { /* nada */ } },
}

/** Se dispara cuando el backend nos dice que la sesión no vale más. */
let alCaerLaSesion = () => {}
export const cuandoCaigaLaSesion = (fn) => { alCaerLaSesion = fn }

/** Se dispara con el 402: se terminó la prueba o no entró el pago.

    Es un evento y no un error más porque la respuesta correcta no es "mostrar un
    cartel rojo" sino "llevarlo a la pantalla donde puede pagar". */
let alCortarse = () => {}
export const cuandoSeCorte = (fn) => { alCortarse = fn }

async function pedir(url, opciones) {
  const token = sesion.token()
  // El back-office se mira SIEMPRE desde nuestra cuenta: si el header viajara
  // también ahí, "ver como" se vería a sí mismo y la lista de cuentas cambiaría
  // según a quién estás mirando. Ese header, además, no es un permiso: el
  // backend lo ignora si el usuario no es root.
  const mirando = url.startsWith('/api/root') ? null : verComo.actual()
  const r = await fetch(base + url, {
    ...opciones,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(mirando ? { 'X-Hilo-Negocio': String(mirando.id) } : {}),
      ...(opciones?.headers || {}),
    },
  })
  // un 401 al intentar entrar es "contraseña equivocada", no "se venció la sesión"
  if (r.status === 401 && !url.startsWith('/api/auth/')) {
    sesion.borrar()
    alCaerLaSesion()
    throw new Error('Necesitás entrar con tu cuenta')
  }
  // 402 = pagar. El backend lo manda cuando se acabó la prueba o no entró el
  // cobro, y viene con el estado adentro para que la pantalla lo explique.
  if (r.status === 402) {
    let cuerpo = {}
    try { cuerpo = await r.json() } catch { /* sin cuerpo */ }
    alCortarse(cuerpo)
    throw new Error(cuerpo.detail || 'Hay que poner una tarjeta para seguir')
  }
  if (!r.ok) {
    let detalle = `${r.status} en ${url}`
    try { const j = await r.json(); if (j.detail) detalle = j.detail } catch { /* sin cuerpo */ }
    /* FastAPI contesta exactamente {"detail":"Not Found"} cuando la RUTA no
       existe. Los 404 nuestros están todos escritos en castellano ("No existe
       ese cliente"), así que este "Not Found" pelado significa una sola cosa: el
       server que está corriendo no tiene ese endpoint.

       Y eso, en esta app, casi siempre es lo mismo: el front se recargó solo
       (Vite) y el backend no. Decirlo acá ahorra media hora de buscar el
       problema en el lugar equivocado — ya nos pasó dos veces. */
    if (r.status === 404 && /^not found$/i.test(detalle.trim())) {
      detalle = `El backend que está corriendo no conoce ${url}. `
        + 'Casi siempre es que quedó viejo: frená `python run.py` y volvé a '
        + 'levantarlo. Python no recarga solo, aunque el front sí.'
    }
    throw new Error(detalle)
  }
  return r.json()
}

export const api = {
  authEstado:  ()            => pedir('/api/auth/estado'),
  login:       (body)        => pedir('/api/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  registro:    (body)        => pedir('/api/auth/registro', { method: 'POST', body: JSON.stringify(body) }),
  yo:          ()            => pedir('/api/auth/yo'),
  cola:        ()            => pedir('/api/cola'),
  panorama:    ()            => pedir('/api/panorama'),
  ficha:       (id)          => pedir(`/api/alias/${id}`),
  negocio:     ()            => pedir('/api/negocio'),
  guardarNegocio: (body)     => pedir('/api/negocio', { method: 'POST', body: JSON.stringify(body) }),
  onboardingProponer: (desc) => pedir('/api/onboarding/proponer', { method: 'POST', body: JSON.stringify({ descripcion: desc }) }),
  onboardingGuardar: (body)  => pedir('/api/onboarding/guardar', { method: 'POST', body: JSON.stringify(body) }),
  onboardingReabrir: ()      => pedir('/api/onboarding/reabrir', { method: 'POST' }),
  sugerirEstados: (desc)     => pedir('/api/negocio/sugerir-estados', { method: 'POST', body: JSON.stringify({ descripcion: desc }) }),
  responder:   (id, body)    => pedir(`/api/alias/${id}/responder`, { method: 'POST', body: JSON.stringify(body) }),
  nota:        (id, body)    => pedir(`/api/alias/${id}/nota`, { method: 'POST', body: JSON.stringify(body) }),
  estado:      (id, body)    => pedir(`/api/alias/${id}/estado`, { method: 'POST', body: JSON.stringify(body) }),
  importancia: (id, imp)     => pedir(`/api/alias/${id}/importancia`, { method: 'POST', body: JSON.stringify({ importancia: imp }) }),
  borrador:    (id, body)    => pedir(`/api/alias/${id}/borrador`, { method: 'POST', body: JSON.stringify(body) }),
  autonomia:   (id, nivel)   => pedir(`/api/alias/${id}/autonomia`, { method: 'POST', body: JSON.stringify({ nivel }) }),
  refrescar:   (id)          => pedir(`/api/alias/${id}/refrescar`, { method: 'POST' }),
  fusionar:    (msgId, alias)=> pedir(`/api/no-identificados/${msgId}/fusionar?alias_id=${alias}`, { method: 'POST' }),
  simular:     (id, body)    => pedir(`/api/alias/${id}/simular`, { method: 'POST', body: JSON.stringify(body) }),
  nuevoDesdeMensaje: (msgId, body) => pedir(`/api/no-identificados/${msgId}/nuevo`, { method: 'POST', body: JSON.stringify(body) }),
  borrarMensaje: (msgId)     => pedir(`/api/mensajes/${msgId}`, { method: 'DELETE' }),
  correoEstado: ()           => pedir('/api/correo/estado'),
  correoRevisar: ()          => pedir('/api/correo/revisar', { method: 'POST' }),
  limpiarSim:  (id)          => pedir(`/api/alias/${id}/limpiar-simulados`, { method: 'POST' }),
  cliente:     (token)       => pedir(`/api/cliente/${token}`),
  clienteSimula:(token)      => pedir(`/api/cliente/${token}/simular`, { method: 'POST' }),
  clienteEnvia:(token, body) => pedir(`/api/cliente/${token}/enviar`, { method: 'POST', body: JSON.stringify(body) }),

  // --- los canales: conectar las cuentas de afuera ---
  canales:          ()        => pedir('/api/canales'),
  vincularTelegram: ()        => pedir('/api/canales/telegram/vincular', { method: 'POST' }),
  desconectarCanal: (canal)   => pedir(`/api/canales/${canal}/desconectar`, { method: 'POST' }),

  // --- el plan y la tarjeta, del lado del cliente ---
  plan:        ()            => pedir('/api/plan'),
  suscribir:   (plan)        => pedir('/api/plan/suscribir', { method: 'POST', body: JSON.stringify({ plan }) }),
  cancelarPlan:()            => pedir('/api/plan/cancelar', { method: 'POST' }),
  pagoSimulado:(sid)         => pedir(`/api/pagos/simulado/${sid}`, { method: 'POST' }),

  // --- el back-office nuestro (#/root). Todos piden es_root del otro lado ---
  rootResumen: ()            => pedir('/api/root/resumen'),
  rootCuenta:  (id)          => pedir(`/api/root/cuenta/${id}`),
  rootEditar:  (id, body)    => pedir(`/api/root/cuenta/${id}`, { method: 'POST', body: JSON.stringify(body) }),
  rootVerComo: (id)          => pedir(`/api/root/ver-como/${id}`, { method: 'POST' }),
  rootCobrar:  (id, body)    => pedir(`/api/root/cuenta/${id}/cobro`, { method: 'POST', body: JSON.stringify(body) }),
  rootCobros:  ()            => pedir('/api/root/cobros'),
  rootProbarWhatsapp: ()     => pedir('/api/root/probar-whatsapp', { method: 'POST' }),
  rootAccesos: ()            => pedir('/api/root/accesos'),
  rootFallas:  ()            => pedir('/api/root/fallas'),
}

// --- helpers de presentación, compartidos por las pantallas ---

export const CANAL_LABEL = {
  mail: 'Mail', whatsapp: 'WhatsApp', instagram: 'Instagram',
  telegram: 'Telegram', llamada: 'Llamada', presencial: 'Visita',
}

export const canalColor = (c) => `var(--ch-${c || 'mail'})`

export function hace(iso) {
  const ms = Date.now() - new Date(iso).getTime()
  const h = ms / 3600000
  if (h < 1) return `hace ${Math.max(1, Math.round(ms / 60000))} min`
  if (h < 24) return `hace ${Math.round(h)} h`
  const d = Math.round(h / 24)
  return d === 1 ? 'hace 1 día' : `hace ${d} días`
}

export function fecha(iso) {
  const d = new Date(iso)
  return d.toLocaleDateString('es-AR', { day: 'numeric', month: 'short' }) +
         ' · ' + d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })
}

export function claseBadge(fila) {
  if (fila.cerrado) return 'b-off'
  if (fila.pelota?.de === 'nosotros') return 'b-me'
  if (['enfriandose', 'frio'].includes(fila.temperatura?.nivel)) return 'b-cold'
  return 'b-them'
}
