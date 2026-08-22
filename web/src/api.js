const base = ''  // en dev lo resuelve el proxy de Vite
const LLAVE = 'hilo.token'

export const sesion = {
  token: () => { try { return localStorage.getItem(LLAVE) || '' } catch { return '' } },
  guardar: (t) => { try { localStorage.setItem(LLAVE, t) } catch { /* modo privado */ } },
  borrar: () => { try { localStorage.removeItem(LLAVE) } catch { /* nada */ } },
}

/** Se dispara cuando el backend nos dice que la sesión no vale más. */
let alCaerLaSesion = () => {}
export const cuandoCaigaLaSesion = (fn) => { alCaerLaSesion = fn }

async function pedir(url, opciones) {
  const token = sesion.token()
  const r = await fetch(base + url, {
    ...opciones,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opciones?.headers || {}),
    },
  })
  // un 401 al intentar entrar es "contraseña equivocada", no "se venció la sesión"
  if (r.status === 401 && !url.startsWith('/api/auth/')) {
    sesion.borrar()
    alCaerLaSesion()
    throw new Error('Necesitás entrar con tu cuenta')
  }
  if (!r.ok) {
    let detalle = `${r.status} en ${url}`
    try { const j = await r.json(); if (j.detail) detalle = j.detail } catch { /* sin cuerpo */ }
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
  limpiarSim:  (id)          => pedir(`/api/alias/${id}/limpiar-simulados`, { method: 'POST' }),
  cliente:     (token)       => pedir(`/api/cliente/${token}`),
  clienteSimula:(token)      => pedir(`/api/cliente/${token}/simular`, { method: 'POST' }),
  clienteEnvia:(token, body) => pedir(`/api/cliente/${token}/enviar`, { method: 'POST', body: JSON.stringify(body) }),
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
