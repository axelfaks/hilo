import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import Marca from '../Marca.jsx'
import { salir } from '../App.jsx'

/* ---------------------------------------------------------------------------
   ONBOARDING — dos pasos. Diseño de Mars.

   La idea que sostiene la pantalla: la persona escribe TRES COSAS y el resto
   aparece armado. No le pedimos que configure, le pedimos que corrija. Por eso
   el paso 2 no es un formulario más: es el resultado, ya hecho.

     Paso 1   · Contame de tu negocio    -> WhatsApp, cómo se llama, qué vende
     (carga)  · Estoy leyendo tu negocio -> la llamada real a /onboarding/proponer
     Paso 2   · Listo, es tuyo           -> lo que quedó armado + canales opcionales

   Antes eran cuatro pasos con todos los campos a la vista. Mars los plegó en
   dos y la diferencia es enorme: se pasa de "configurá tu CRM" a "contame y yo
   lo armo". Lo editable no desapareció, se mudó a Configuración.
--------------------------------------------------------------------------- */

const BORRADOR = 'hilo.onboarding.borrador'
const NEGOCIO_NUEVO = 'hilo_negocio_recien_configurado'

const EJEMPLOS = [
  ['Distribuidora', 'Vendo insumos de limpieza y descartables a kioscos, almacenes y rotiserías del barrio. Me piden precio de dos o tres cosas y después desaparecen. Se me traba cuando quieren pagar a 30 días.'],
  ['Corralón', 'Tengo un corralón. Vendo materiales de obra a albañiles y a gente que refacciona la casa. Piden presupuesto, comparan con otros dos y tardan una semana en decidir.'],
  ['Ropa por mayor', 'Vendo ropa por mayor a locales del interior. Arman el pedido de a poco y pagan por transferencia. El quilombo es cuando cambia el precio de la temporada y quedan pedidos viejos colgados.'],
  ['Servicios', 'Instalo y hago service de aires acondicionados en casas y locales. Paso presupuesto y ahí queda. En verano no doy abasto y se me pierden mensajes.'],
]

/* Las dos pistas del textarea. No son validación: son una forma de decirle
   "esto que escribiste me sirve", que es lo que la gente necesita saber. */
const TRABA = /precio|pag|plata|entrega|stock|descuento|competencia|demora|presupuesto|cotiz|tarda|pierd|desaparec|cuenta corriente|traba|quilombo|olvid|abasto|compar/i

const PASOS_CARGA = [
  ['Entendí qué vendés', 'Y a quién le vendés.'],
  ['Armando el camino de tu venta', 'Del primer mensaje al pedido confirmado.'],
  ['Escribiendo cómo te habla el agente', 'Tono, horarios, insistencia y qué te tiene que consultar.'],
]

const OPCIONALES = [
  ['mail', 'Mail', 'Los pedidos grandes y las facturas.'],
  ['instagram', 'Instagram', 'Los mensajes del perfil del negocio.'],
  ['linkedin', 'LinkedIn', 'Si te llegan consultas por ahí.'],
]

export default function Onboarding({ onListo }) {
  const [pantalla, setPantalla] = useState('form')   // form · carga · luego · cierre
  const [wa, setWa] = useState('')
  const [firma, setFirma] = useState('')
  const [desc, setDesc] = useState('')
  const [prop, setProp] = useState(null)             // lo que devolvió la IA
  const [extra, setExtra] = useState([])             // canales opcionales conectados
  const [activo, setActivo] = useState(-1)           // animación de la carga
  const [corriendo, setCorriendo] = useState(-1)
  const [guardando, setGuardando] = useState(false)
  const [demorado, setDemorado] = useState(false)
  const [aviso, setAviso] = useState('')

  /* Recuperar el borrador: es lo que hace verdadera la promesa de "seguir después". */
  useEffect(() => {
    try {
      const b = JSON.parse(localStorage.getItem(BORRADOR) || 'null')
      if (b) { setWa(b.wa || ''); setFirma(b.firma || ''); setDesc(b.desc || '') }
    } catch { /* si el navegador no deja, se arranca de cero y listo */ }
  }, [])

  const guardarBorrador = () => {
    try { localStorage.setItem(BORRADOR, JSON.stringify({ wa, firma, desc })) } catch { /* da igual */ }
  }

  const telOk = wa.replace(/\D/g, '').length >= 8
  const yaEsta = telOk && firma.trim().length > 1
  const puedeArrancar = yaEsta && desc.trim().length >= 40
  const pistas = [desc.trim().length > 30, TRABA.test(desc)]

  /* La animación de la carga. Corre en paralelo a la llamada real: si la IA
     tarda más, la última línea queda girando; si tarda menos, igual se ven los
     tres pasos porque abajo esperamos el mínimo. */
  useEffect(() => {
    if (pantalla !== 'carga') return
    const t = []
    PASOS_CARGA.forEach((_, i) => {
      t.push(setTimeout(() => { setActivo(i); setCorriendo(i) }, i * 950))
      /* El último NO se apaga: mientras esta pantalla esté a la vista, la IA
         sigue trabajando. Apagar todo cuando termina la animación hace parecer
         que se colgó, y Gemini a veces tarda diez segundos o más. */
      if (i < PASOS_CARGA.length - 1) {
        t.push(setTimeout(() => setCorriendo(c => (c === i ? -1 : c)), i * 950 + 900))
      }
    })
    return () => t.forEach(clearTimeout)
  }, [pantalla])

  const arrancar = async () => {
    setAviso(''); setActivo(-1); setCorriendo(-1); setDemorado(false); setPantalla('carga')
    guardarBorrador()
    const minimo = new Promise(r => setTimeout(r, PASOS_CARGA.length * 950 + 700))
    // si la IA tarda de más, decirlo: el silencio se lee como "se rompió"
    const tarde = setTimeout(() => setDemorado(true), 11000)
    try {
      const [r] = await Promise.all([api.onboardingProponer(desc.trim()), minimo])
      setProp(r)
      /* Los canales que sugiere la IA NO se marcan solos: decir "Conectado"
         sin que nadie lo haya tocado es mentir. Se ofrecen y listo. */
      setPantalla('cierre')
    } catch (e) {
      setAviso('No pude hablar con el servidor: ' + e.message)
      setPantalla('form')
    } finally {
      clearTimeout(tarde)
    }
  }

  const guardar = async (destino) => {
    setGuardando(true); setAviso('')
    /* estados_cerrados viaja adentro de reglas: es de donde lo lee el backend
       (pl.reglas(b).get("estados_cerrados")). Suelto en la raíz se perdía y la
       app caía a la lista por defecto. */
    const reglas = { ...(prop.reglas || {}), estados_cerrados: prop.estados_cerrados || [] }
    try {
      const guardado = await api.onboardingGuardar({
        nombre: (prop.rubro || '').trim() || 'Negocio de ' + firma.trim(),
        descripcion: desc.trim(),
        rubro: prop.rubro || '',
        vendedor: firma.trim(),
        estados: prop.estados || [],
        reglas,
        canales: [{ canal: 'whatsapp', valor: wa.trim() }, ...extra.map(c => ({ canal: c, valor: '' }))],
        autonomia_default: 3,
      })
      /* El id del negocio que se acaba de configurar. La cuenta se crea DESPUÉS
         del onboarding, así que sin esto la config queda huérfana y el usuario
         entra a un negocio vacío: se pierde todo lo que acaba de contestar. */
      try {
        if (guardado?.negocio_id) localStorage.setItem(NEGOCIO_NUEVO, String(guardado.negocio_id))
      } catch { /* da igual */ }
      try { localStorage.removeItem(BORRADOR) } catch { /* da igual */ }
      onListo(destino)
    } catch (e) {
      setAviso('No pude guardar: ' + e.message)
      setGuardando(false)
    }
  }

  const etiqueta = { form: 'Paso 1 de 2', carga: 'Armando', luego: 'Guardado', cierre: 'Todo listo' }[pantalla]
  const barras = pantalla === 'cierre' ? 2 : 1

  return (
    <>
      <div className="ob-top">
        <Marca alto={22} />
        <span className="ob-top-der">
          <span className="label">{etiqueta}</span>
          {/* sin barra arriba, sin esto uno queda encerrado en el onboarding */}
          <button className="btn btn--link ob-salir" onClick={salir}>Salir</button>
        </span>
      </div>
      <div className="ob-bars">
        <i className="is-on" />
        <i className={barras === 2 ? 'is-on' : ''} />
      </div>

      <main className="ob">
        {aviso && (
          <div className="ob-note ob-note--ojo" style={{ marginBottom: 'var(--sp-5)' }}>{aviso}</div>
        )}

        {pantalla === 'form' && (
          <Formulario
            wa={wa} setWa={setWa} firma={firma} setFirma={setFirma}
            desc={desc} setDesc={setDesc} yaEsta={yaEsta} pistas={pistas}
          />
        )}

        {pantalla === 'carga' && (
          <Cargando desc={desc} activo={activo} corriendo={corriendo} demorado={demorado} />
        )}

        {pantalla === 'luego' && <Luego firma={firma} />}

        {pantalla === 'cierre' && prop && (
          <Cierre
            firma={firma} wa={wa} prop={prop} extra={extra}
            alternar={c => setExtra(x => (x.includes(c) ? x.filter(y => y !== c) : [...x, c]))}
            aConfig={() => guardar('/admin')}
          />
        )}
      </main>

      <div className="ob-actions">
        <div>
          {pantalla === 'form' && (
            <>
              <button className="btn btn--primary btn--block" disabled={!puedeArrancar} onClick={arrancar}>
                Armar mi Hilo
              </button>
              <button className="btn btn--link" onClick={() => { guardarBorrador(); setPantalla('luego') }}>
                Seguir después
              </button>
            </>
          )}
          {pantalla === 'luego' && (
            <button className="btn btn--link" onClick={() => setPantalla('form')}>Volver</button>
          )}
          {pantalla === 'cierre' && (
            <button className="btn btn--primary btn--block" disabled={guardando} onClick={() => guardar()}>
              {guardando ? 'Guardando…' : 'Empezar'}
            </button>
          )}
        </div>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ paso 1 */

function Formulario({ wa, setWa, firma, setFirma, desc, setDesc, yaEsta, pistas }) {
  return (
    <section>
      <h1 className="t-display">Contame de tu negocio</h1>
      <p className="ob-lede">
        Tres cosas y lo armo entero: el camino de tu venta, cómo te escribe el agente
        y cuándo te consulta. Dos minutos.
      </p>

      <div className="ob-field">
        <label className="ob-label" htmlFor="ob-wa">¿A qué WhatsApp te escriben tus clientes?</label>
        <input className="ob-input" type="tel" id="ob-wa" inputMode="tel" autoComplete="tel"
          placeholder="11 5555-1234" value={wa} onChange={e => setWa(e.target.value)} />
        <p className="ob-help" style={{ marginTop: 'var(--sp-2)' }}>
          Ahí van a caer los mensajes de tus clientes, todos en un mismo hilo.
        </p>
      </div>

      <div className="ob-field">
        <label className="ob-label" htmlFor="ob-firma">¿Cómo te llamás?</label>
        <input className="ob-input" type="text" id="ob-firma" autoComplete="given-name"
          placeholder="Caro" value={firma} onChange={e => setFirma(e.target.value)} />
        <p className="ob-help" style={{ marginTop: 'var(--sp-2)' }}>Con ese nombre te firma los mensajes.</p>
      </div>

      <div className={'ob-note ob-saved' + (yaEsta ? ' is-on' : '')}>
        <span className="ob-check">✓</span>
        <span>Listo, ya te tengo. <strong>Cortá cuando quieras</strong>: lo que pongas queda guardado.</span>
      </div>

      <div className="ob-field">
        <label className="ob-label" htmlFor="ob-desc">¿Qué vendés y a quién?</label>
        <p className="ob-help">Tres renglones alcanzan. Contámelo como se lo contarías a alguien en el asado.</p>

        <div className="ob-examples" role="group" aria-label="Ejemplos para empezar">
          {EJEMPLOS.map(([titulo, texto]) => (
            <button key={titulo} className="btn" type="button" onClick={() => setDesc(texto)}>{titulo}</button>
          ))}
        </div>
        <p className="ob-help" style={{ margin: 'var(--sp-2) 0 var(--sp-3)' }}>
          Tocá el que más se te parezca y editalo. Nadie arranca de cero.
        </p>

        <textarea className="ob-textarea" id="ob-desc" rows={6} value={desc}
          onChange={e => setDesc(e.target.value)}
          placeholder="Vendo… Me compran… Se me traba cuando…" />

        <div className="ob-hints">
          <div className={'ob-hint' + (pistas[0] ? ' is-ok' : '')}>
            <span className="ob-tick">✓</span> Qué vendés y a quién
          </div>
          <div className={'ob-hint' + (pistas[1] ? ' is-ok' : '')}>
            <span className="ob-tick">✓</span> Dónde se te traba la venta
          </div>
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------- la carga */

function Cargando({ desc, activo, corriendo, demorado }) {
  const t = desc.trim()
  return (
    <section aria-live="polite">
      <h1 className="t-display">Estoy leyendo tu negocio</h1>
      <p className="ob-lede" style={{ marginBottom: 'var(--sp-6)' }}>
        Unos segundos. De acá sale todo lo demás.
      </p>
      <p className="ob-quote">«{t.slice(0, 150)}{t.length > 150 ? '…' : ''}»</p>
      <ul className="ob-steps">
        {PASOS_CARGA.map(([titulo, detalle], i) => (
          <li key={titulo} className={(i <= activo ? 'is-on' : '') + (i === corriendo ? ' is-run' : '')}>
            <span className="ob-dot">✓</span>
            <span><b>{titulo}</b><small>{detalle}</small></span>
          </li>
        ))}
      </ul>
      {demorado && (
        <p className="ob-help" style={{ marginTop: 'var(--sp-6)' }}>
          Está tardando un poco más de lo normal. Sigo esperando: no cierres la pantalla.
        </p>
      )}
    </section>
  )
}

/* -------------------------------------------------------- seguir después */

function Luego({ firma }) {
  const nombre = firma.trim() || 'Hola'
  return (
    <section aria-live="polite">
      <h1 className="t-display">Te lo guardo</h1>
      <p className="ob-lede">
        Guardé lo que pusiste en este navegador. Cuando vuelvas, seguís desde donde quedaste.
      </p>
      <div className="ob-chat">
        <p className="ob-when">
          <span className="label">Así te escribiría para recordártelo</span>
        </p>
        <div className="bubble bubble--in">
          <strong>Hilo</strong><br />
          {firma.trim() ? nombre + '! ' : ''}Te dejé el armado a mitad de camino.
          Seguí desde acá cuando tengas dos minutos.
        </div>
      </div>
      <p className="ob-help" style={{ marginTop: 'var(--sp-4)' }}>
        Un solo mensaje. Si no querés seguir, respondés <strong>BAJA</strong> y no te escribe más.
      </p>
    </section>
  )
}

/* ------------------------------------------------------------------ paso 2 */

function Cierre({ firma, wa, prop, extra, alternar, aConfig }) {
  const cerrados = prop.estados_cerrados || []
  const todas = prop.estados || []
  const camino = todas.filter(e => !cerrados.includes(e))
  const finales = todas.filter(e => cerrados.includes(e))

  return (
    <section>
      <h1 className="t-display">Listo{firma.trim() ? ', ' + firma.trim() : ''}. Hilo ya es tuyo.</h1>
      <p className="ob-lede">
        Tu agente sabe qué vendés, cómo hablás y cuándo tiene que consultarte. Ya está
        escuchando tu WhatsApp: cuando entre el primer mensaje, el cliente aparece solo.
      </p>

      {prop.sin_ia && (
        <div className="ob-note ob-note--ojo" style={{ marginTop: 'var(--sp-5)' }}>
          La IA no estaba disponible, así que te dejé una configuración genérica.
          Se cambia entera desde Configuración.
        </div>
      )}

      <div className="ob-channel ob-channel--live">
        <Logo canal="whatsapp" />
        <span className="ob-ch-name">
          WhatsApp · {wa.trim()}
          <span className="ob-ch-sub">Conectado y escuchando.</span>
        </span>
      </div>

      <div className="card card--pad" style={{ marginTop: 'var(--sp-4)' }}>
        <span className="label">Lo que te dejé armado</span>

        <div className="ob-flow" style={{ marginTop: 'var(--sp-3)' }}>
          {camino.map((e, i) => (
            <React.Fragment key={e}>
              <span className="ob-stage">{e}</span>
              {i < camino.length - 1 && <span className="ob-arrow">→</span>}
            </React.Fragment>
          ))}
        </div>

        {finales.length > 0 && (
          <div className="ob-ends">
            <span className="ob-help">Termina en</span>
            {finales.map(e => <span key={e} className="ob-stage ob-stage--end">{e}</span>)}
          </div>
        )}

        <p className="ob-help" style={{ marginTop: 'var(--sp-4)' }}>{frase(prop.reglas)}</p>

        <button className="btn" type="button" style={{ marginTop: 'var(--sp-4)' }} onClick={aConfig}>
          Cambiar algo de esto
        </button>
      </div>

      <section className="ob-section">
        <span className="label">Opcional</span>
        <h2 className="t-heading">¿Te escriben por otro lado?</h2>
        <p className="ob-help" style={{ marginBottom: 'var(--sp-4)' }}>
          Conectalos y las conversaciones caen en el mismo hilo. También podés hacerlo más adelante.
        </p>

        {OPCIONALES.map(([canal, label, sub]) => {
          const puesto = extra.includes(canal)
          return (
            <div key={canal} className={'ob-channel' + (puesto ? ' is-done' : '')}>
              <Logo canal={canal} />
              <span className="ob-ch-name">{label}<span className="ob-ch-sub">{sub}</span></span>
              <button className="btn" type="button" onClick={() => alternar(canal)}>
                {puesto ? 'Conectado ✓' : 'Conectar'}
              </button>
            </div>
          )
        })}
      </section>
    </section>
  )
}

/* Las reglas, dichas como se las contarías a alguien. Todo sale de lo que
   propuso la IA: si mañana cambia el reglamento, esta frase cambia sola. */
function frase(reglas) {
  const r = reglas || {}
  const [h0, h1] = r.horario || [9, 19]
  const veces = r.max_insistencias ?? 3
  const dias = r.insistir_cada_dias ?? 3
  const dto = r.descuento_max ?? 0
  const temas = (r.temas_escalan || []).filter(Boolean)

  let t = 'Te escribe de ' + h0 + ' a ' + h1 + ', insiste hasta ' + veces +
          (veces === 1 ? ' vez' : ' veces') + ' cada ' + dias + (dias === 1 ? ' día' : ' días')
  if (dto > 0) t += ', puede hacer hasta ' + dto + '% de descuento'
  if (temas.length) {
    const lista = temas.length > 1
      ? temas.slice(0, -1).join(', ') + ' o ' + temas[temas.length - 1]
      : temas[0]
    t += ' y te consulta si aparece ' + lista
  }
  return t + '. Cuando tiene una respuesta lista, te avisa y la mandás vos.'
}

/* ------------------------------------------------------------------ logos */

const TRAZOS = {
  whatsapp: 'M12 2a10 10 0 0 0-8.7 15L2 22l5.2-1.3A10 10 0 1 0 12 2Zm0 18.1a8.1 8.1 0 0 1-4.1-1.1l-.3-.2-3.1.8.8-3-.2-.3A8.1 8.1 0 1 1 12 20.1Zm4.5-6c-.2-.1-1.4-.7-1.7-.8-.2-.1-.4-.1-.5.1l-.7.9c-.1.2-.3.2-.5.1a6.6 6.6 0 0 1-3.2-2.8c-.1-.2 0-.4.1-.5l.4-.5c.1-.2.1-.3 0-.5l-.7-1.7c-.2-.4-.4-.4-.5-.4h-.5c-.2 0-.5.1-.7.3-.8.8-.9 1.9-.4 3a10 10 0 0 0 4 4c1.3.6 2.3.7 3 .4.5-.2 1.1-.6 1.3-1.1.1-.4.1-.8.1-.9 0-.1-.2-.2-.4-.3Z',
  mail: 'M3 4.5h18c.6 0 1 .4 1 1v13c0 .6-.4 1-1 1H3c-.6 0-1-.4-1-1v-13c0-.6.4-1 1-1Zm1 2.7v10.3h16V7.2l-8 5.3-8-5.3Zm15.4-.7H4.6l7.4 4.9 7.4-4.9Z',
  instagram: 'M8 2.2h8A5.8 5.8 0 0 1 21.8 8v8A5.8 5.8 0 0 1 16 21.8H8A5.8 5.8 0 0 1 2.2 16V8A5.8 5.8 0 0 1 8 2.2Zm0 2A3.8 3.8 0 0 0 4.2 8v8A3.8 3.8 0 0 0 8 19.8h8a3.8 3.8 0 0 0 3.8-3.8V8A3.8 3.8 0 0 0 16 4.2H8Zm4 3.3a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9Zm0 2a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5Zm5.4-3.1a1.2 1.2 0 1 1 0 2.4 1.2 1.2 0 0 1 0-2.4Z',
  linkedin: 'M3.6 2.2h16.8c.8 0 1.4.6 1.4 1.4v16.8c0 .8-.6 1.4-1.4 1.4H3.6c-.8 0-1.4-.6-1.4-1.4V3.6c0-.8.6-1.4 1.4-1.4ZM8.3 18.6v-8.2H5.7v8.2h2.6ZM7 9.3a1.5 1.5 0 1 0 0-3.1 1.5 1.5 0 0 0 0 3.1Zm11.3 9.3V14c0-2.2-1.2-3.3-2.8-3.3-1.3 0-1.9.7-2.2 1.2v-1.5h-2.6v8.2h2.6V14c0-1 .2-1.9 1.4-1.9s1.4 1 1.4 2v4.5h2.2Z',
}

function Logo({ canal }) {
  return (
    <span className={'ob-logo ob-logo--' + canal}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d={TRAZOS[canal]} /></svg>
    </span>
  )
}
