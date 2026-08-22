import React, { useState } from 'react'
import { api, CANAL_LABEL, canalColor } from '../api.js'

/* ---------------------------------------------------------------------------
   ONBOARDING — primera iteración. Mars: esto es tuyo.

   La idea que sostiene toda la pantalla: la persona escribe DOS ORACIONES sobre
   su negocio y el resto aparece lleno. No le pedimos que configure: le pedimos
   que corrija. Ese es el momento en que la app se siente hecha para ella.

   Los cuatro pasos:
     1. Quién sos y qué vendés   -> el único que cuesta trabajo
     2. Tu flujo de venta        -> propuesto por la IA, editable
     3. Cómo escribe tu agente   -> propuesto por la IA, editable
     4. Canales y autonomía      -> elección simple
--------------------------------------------------------------------------- */

const CANALES = ['mail', 'whatsapp', 'instagram', 'telegram', 'linkedin']

const NIVELES = [
  ['Silencio', 'No hace nada. Ni siquiera resume.'],
  ['Observa', 'Solo mantiene el resumen al día.'],
  ['Sugiere', 'Deja el borrador escrito, sin avisarte.'],
  ['Pide permiso', 'Redacta y te avisa. Vos apretás enviar.'],
  ['Con barandas', 'Envía sola si no toca precio ni temas sensibles.'],
  ['Autónoma', 'Envía sola siempre, dentro del reglamento.'],
]

export default function Onboarding({ onListo }) {
  const [paso, setPaso] = useState(1)
  const [pensando, setPensando] = useState(false)
  const [guardando, setGuardando] = useState(false)
  const [aviso, setAviso] = useState('')

  const [nombre, setNombre] = useState('')
  const [vendedor, setVendedor] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [rubro, setRubro] = useState('')
  const [estados, setEstados] = useState([])
  const [porQue, setPorQue] = useState('')
  const [reglas, setReglas] = useState({})
  const [canales, setCanales] = useState({})
  const [autonomia, setAutonomia] = useState(3)

  const proponer = async () => {
    setPensando(true); setAviso('')
    try {
      const r = await api.onboardingProponer(descripcion)
      setRubro(r.rubro || '')
      setEstados(r.estados || [])
      setReglas(r.reglas || {})
      setPorQue(r.por_que || '')
      const previos = { ...canales }
      ;(r.canales || []).forEach(c => { if (!(c in previos)) previos[c] = '' })
      setCanales(previos)
      if (r.sin_ia) setAviso('La IA no estaba disponible, así que te dejé una configuración genérica. Editala.')
      setPaso(2)
    } catch (e) {
      setAviso('No pude hablar con el servidor: ' + e.message)
    } finally { setPensando(false) }
  }

  const guardar = async () => {
    setGuardando(true); setAviso('')
    try {
      await api.onboardingGuardar({
        nombre, descripcion, rubro, vendedor, estados, reglas,
        canales: Object.entries(canales).filter(([, v]) => v.trim())
          .map(([canal, valor]) => ({ canal, valor: valor.trim() })),
        autonomia_default: autonomia,
      })
      onListo()
    } catch (e) {
      setAviso('No pude guardar: ' + e.message)
      setGuardando(false)
    }
  }

  const regla = (k, v) => setReglas({ ...reglas, [k]: v })

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '48px 26px 90px' }}>
      <Progreso paso={paso} />

      {aviso && (
        <div className="card" style={{
          padding: '12px 16px', marginBottom: 18,
          borderColor: 'var(--amber-line)', background: 'var(--amber-soft)',
        }}>
          <p className="t-body" style={{ color: 'var(--ink)' }}>{aviso}</p>
        </div>
      )}

      {paso === 1 && (
        <Paso
          titulo="Empecemos por tu negocio"
          bajada="Con esto la IA arma el resto: las etapas de tu venta, el tono del agente y sus límites. Después corregís lo que no te cierre."
        >
          <Campo etiqueta="¿Cómo se llama tu negocio?">
            <input type="text" value={nombre} onChange={e => setNombre(e.target.value)}
              placeholder="Mesa 12" aria-label="Nombre del negocio" />
          </Campo>
          <Campo etiqueta="¿Quién firma los mensajes?">
            <input type="text" value={vendedor} onChange={e => setVendedor(e.target.value)}
              placeholder="Axel" aria-label="Tu nombre" />
          </Campo>
          <Campo
            etiqueta="¿Qué vendés y a quién?"
            ayuda="Dos o tres oraciones alcanzan. Contá también cuánto suele tardar una venta y dónde se suele trabar."
          >
            <textarea rows={5} value={descripcion} onChange={e => setDescripcion(e.target.value)}
              aria-label="Qué vendés y a quién"
              placeholder="Vendemos un sistema de pedidos para locales gastronómicos chicos. Cobramos por mes y por sucursal. La venta dura entre dos semanas y dos meses, siempre con el dueño, y se traba en el precio cuando tienen más de un local." />
          </Campo>
          <Acciones>
            <button className="btn btn-primary" disabled={pensando || !nombre.trim() || descripcion.trim().length < 30}
              onClick={proponer}>
              {pensando ? <><span className="spin" /> Leyendo tu negocio…</> : 'Configurar mi agente'}
            </button>
            {descripcion.trim().length < 30 && descripcion.length > 0 && (
              <span className="t-small">Contame un poco más para que valga la pena.</span>
            )}
          </Acciones>
        </Paso>
      )}

      {paso === 2 && (
        <Paso
          titulo="Así entendí tu flujo de venta"
          bajada="Estas son las etapas por las que va a pasar cada cliente. Renombrá, sacá o agregá lo que haga falta: después la IA va a proponer los cambios de etapa y vos los aceptás."
        >
          {porQue && <p className="t-body" style={{ marginBottom: 16 }}>{porQue}</p>}
          <Etapas estados={estados} setEstados={setEstados} />
          <Acciones>
            <button className="btn btn-primary" disabled={estados.length < 2} onClick={() => setPaso(3)}>
              Está bien, seguimos
            </button>
            <button className="btn" onClick={() => setPaso(1)}>Volver</button>
          </Acciones>
        </Paso>
      )}

      {paso === 3 && (
        <Paso
          titulo="Cómo escribe tu agente"
          bajada="Estos son los límites dentro de los que se mueve solo. Todo esto se puede cambiar después."
        >
          <Campo etiqueta="Tono">
            <textarea rows={2} value={reglas.tono || ''} onChange={e => regla('tono', e.target.value)}
              aria-label="Tono del agente" />
          </Campo>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <Campo etiqueta="Puede escribir entre">
              <div className="row" style={{ gap: 8 }}>
                <input type="text" inputMode="numeric" style={{ width: 70 }}
                  value={reglas.horario?.[0] ?? 9} aria-label="Hora desde"
                  onChange={e => regla('horario', [+e.target.value || 0, reglas.horario?.[1] ?? 19])} />
                <span className="t-small">y</span>
                <input type="text" inputMode="numeric" style={{ width: 70 }}
                  value={reglas.horario?.[1] ?? 19} aria-label="Hora hasta"
                  onChange={e => regla('horario', [reglas.horario?.[0] ?? 9, +e.target.value || 0])} />
                <span className="t-small">hs</span>
              </div>
            </Campo>
            <Campo etiqueta="Descuento que puede dar solo">
              <div className="row" style={{ gap: 8 }}>
                <input type="text" inputMode="numeric" style={{ width: 80 }}
                  value={reglas.descuento_max ?? 0} aria-label="Descuento máximo"
                  onChange={e => regla('descuento_max', +e.target.value || 0)} />
                <span className="t-small">%</span>
              </div>
            </Campo>
            <Campo etiqueta="Insiste cada">
              <div className="row" style={{ gap: 8 }}>
                <input type="text" inputMode="numeric" style={{ width: 70 }}
                  value={reglas.insistir_cada_dias ?? 3} aria-label="Días entre insistencias"
                  onChange={e => regla('insistir_cada_dias', +e.target.value || 1)} />
                <span className="t-small">días</span>
              </div>
            </Campo>
            <Campo etiqueta="Como máximo">
              <div className="row" style={{ gap: 8 }}>
                <input type="text" inputMode="numeric" style={{ width: 70 }}
                  value={reglas.max_insistencias ?? 3} aria-label="Máximo de insistencias"
                  onChange={e => regla('max_insistencias', +e.target.value || 1)} />
                <span className="t-small">veces</span>
              </div>
            </Campo>
          </div>
          <Campo
            etiqueta="Temas que lo obligan a escalar a un humano"
            ayuda="Si el cliente menciona alguna de estas palabras, el agente frena y te lo pasa a vos."
          >
            <input type="text" aria-label="Temas que escalan"
              value={(reglas.temas_escalan || []).join(', ')}
              onChange={e => regla('temas_escalan', e.target.value.split(',').map(t => t.trim()).filter(Boolean))} />
          </Campo>
          <Acciones>
            <button className="btn btn-primary" onClick={() => setPaso(4)}>Seguimos</button>
            <button className="btn" onClick={() => setPaso(2)}>Volver</button>
          </Acciones>
        </Paso>
      )}

      {paso === 4 && (
        <Paso
          titulo="Por dónde te escriben, y cuánto lo dejás hacer solo"
          bajada="Marcá los canales que usás y poné tu dirección o usuario en cada uno."
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 9, marginBottom: 26 }}>
            {CANALES.map(c => {
              const activo = c in canales
              return (
                <div key={c} className="row" style={{ gap: 11 }}>
                  <button
                    className={`filtro ${activo ? '' : ''}`} aria-pressed={activo}
                    style={{ minWidth: 132, justifyContent: 'flex-start' }}
                    onClick={() => {
                      const copia = { ...canales }
                      if (activo) delete copia[c]; else copia[c] = ''
                      setCanales(copia)
                    }}
                  >
                    <i className="cdot" style={{ background: canalColor(c) }} />
                    {CANAL_LABEL[c]}
                  </button>
                  <input
                    type="text" disabled={!activo} value={canales[c] ?? ''}
                    aria-label={`Tu dirección de ${CANAL_LABEL[c]}`}
                    placeholder={activo ? PISTAS[c] : 'no lo usás'}
                    style={{ opacity: activo ? 1 : .45 }}
                    onChange={e => setCanales({ ...canales, [c]: e.target.value })}
                  />
                </div>
              )
            })}
          </div>

          <Campo
            etiqueta="Cuánta autonomía le das al agente por defecto"
            ayuda="Después podés subirla o bajarla cliente por cliente. Para arrancar, el nivel 3 es el más tranquilo."
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 4 }}>
              {NIVELES.map(([titulo, detalle], n) => (
                <button key={n} onClick={() => setAutonomia(n)}
                  style={{
                    display: 'grid', gridTemplateColumns: '26px 130px 1fr', gap: 12, alignItems: 'center',
                    textAlign: 'left', padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
                    background: autonomia === n ? 'var(--teal-soft)' : 'var(--card)',
                    border: `1px solid ${autonomia === n ? 'var(--teal-line)' : 'var(--line)'}`,
                  }}>
                  <span className="num" style={{ fontWeight: 700, color: autonomia === n ? 'var(--teal)' : 'var(--ink-3)' }}>{n}</span>
                  <span style={{ fontWeight: 600, color: autonomia === n ? 'var(--teal-2)' : 'var(--ink)' }}>{titulo}</span>
                  <span className="t-small">{detalle}</span>
                </button>
              ))}
            </div>
          </Campo>

          <Acciones>
            <button className="btn btn-primary" disabled={guardando} onClick={guardar}>
              {guardando ? 'Guardando…' : 'Listo, empezar a usar Hilo'}
            </button>
            <button className="btn" onClick={() => setPaso(3)}>Volver</button>
          </Acciones>
        </Paso>
      )}
    </div>
  )
}

const PISTAS = {
  mail: 'ventas@tunegocio.com', whatsapp: '+54 9 11 ...', instagram: '@tunegocio',
  telegram: '@tunegocio', linkedin: 'in/tu-usuario',
}

function Progreso({ paso }) {
  const nombres = ['Tu negocio', 'Tu flujo', 'Tu agente', 'Canales']
  return (
    <div style={{ marginBottom: 34 }}>
      <span className="t-sec" style={{ color: 'var(--teal)', display: 'block', marginBottom: 26 }}>Hilo</span>
      <div className="row" style={{ gap: 6 }}>
        {nombres.map((n, i) => (
          <div key={n} style={{ flex: 1 }}>
            <div style={{
              height: 3, borderRadius: 2, marginBottom: 7,
              background: i < paso ? 'var(--teal)' : 'var(--line)',
            }} />
            <span className="lbl" style={{ color: i < paso ? 'var(--teal)' : 'var(--ink-3)' }}>{n}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Paso({ titulo, bajada, children }) {
  return (
    <>
      <h1 className="t-display" style={{ fontSize: 32 }}>{titulo}</h1>
      <p className="t-body" style={{ marginTop: 8, marginBottom: 26 }}>{bajada}</p>
      {children}
    </>
  )
}

function Campo({ etiqueta, ayuda, children }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <label className="lbl" style={{ display: 'block', marginBottom: 7 }}>{etiqueta}</label>
      {ayuda && <p className="t-small" style={{ marginBottom: 8 }}>{ayuda}</p>}
      {children}
    </div>
  )
}

function Acciones({ children }) {
  return <div className="row" style={{ marginTop: 26, gap: 10, flexWrap: 'wrap' }}>{children}</div>
}

function Etapas({ estados, setEstados }) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {estados.map((e, i) => (
        <div key={i} className="row" style={{
          gap: 6, background: 'var(--card)', border: '1px solid var(--line)',
          borderRadius: 8, padding: '6px 8px 6px 12px',
        }}>
          <span className="t-small num">{String(i + 1).padStart(2, '0')}</span>
          <input type="text" value={e} aria-label={`Etapa ${i + 1}`}
            onChange={ev => setEstados(estados.map((x, j) => (j === i ? ev.target.value : x)))}
            style={{ width: `${Math.max(9, e.length + 1)}ch`, border: 0, background: 'transparent', padding: '2px 0', fontWeight: 600 }} />
          <button className="btn btn-sm" title="Sacar esta etapa" style={{ padding: '2px 8px' }}
            onClick={() => setEstados(estados.filter((_, j) => j !== i))}>×</button>
        </div>
      ))}
      <button className="btn btn-sm" onClick={() => setEstados([...estados, 'Etapa nueva'])}>+ Agregar</button>
    </div>
  )
}
