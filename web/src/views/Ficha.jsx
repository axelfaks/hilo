import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api, CANAL_LABEL, canalColor, fecha } from '../api.js'

/* Ficha del cliente — estructura y sistema visual de Toto (iteración 2).
   Orden de lectura: cuánto hace que no pasa nada, qué hay que hacer, en qué
   etapa está, y recién después el detalle de dónde salió todo eso. */

const NO_ESCRIBIBLES = ['llamada', 'presencial']
const PAGINA = 5

function duracion(h) {
  if (!h || h < 1) return 'recién'
  if (h < 48) return `${Math.round(h)} h`
  return `${Math.round(h / 24)} días`
}

export default function Ficha({ id }) {
  const [d, setD] = useState(null)
  const [error, setError] = useState('')
  const [canal, setCanal] = useState(null)
  const [mostrar, setMostrar] = useState(PAGINA)
  const [verDetras, setVerDetras] = useState(false)
  const [verAuto, setVerAuto] = useState(false)
  const [modal, setModal] = useState(false)
  const [aviso, setAviso] = useState('')
  const convRef = useRef(null)

  const traer = () => api.ficha(id).then(setD).catch(e => setError(e.message))
  useEffect(() => {
    let vivo = true
    const tick = () => api.ficha(id).then(x => vivo && setD(x)).catch(e => vivo && setError(e.message))
    tick()
    const t = setInterval(tick, 2000)
    return () => { vivo = false; clearInterval(t) }
  }, [id])
  useEffect(() => { setMostrar(PAGINA) }, [canal])
  useEffect(() => {
    if (!aviso) return
    const t = setTimeout(() => setAviso(''), 2600)
    return () => clearTimeout(t)
  }, [aviso])

  if (error) return <p className="t-body">No pude cargar la ficha: {error}</p>
  if (!d) return <p className="t-body"><span className="spin" /> Cargando…</p>

  const b = d.briefing || {}
  const nuestra = b.pelota?.de === 'nosotros'
  const cortes = b.por_canal || []
  const visibles = canal ? d.mensajes.filter(m => m.canal === canal) : d.mensajes
  const recortados = visibles.slice(Math.max(0, visibles.length - mostrar))
  const vencidos = d.compromisos.filter(c => c.vencido)

  return (
    <>
      <Encabezado ficha={d} onCambio={setD} verAuto={verAuto} setVerAuto={setVerAuto} />
      {verAuto && <PanelAutonomia ficha={d} onCambio={setD} />}

      <Foco
        ficha={d} nuestra={nuestra} vencidos={vencidos}
        onIA={() => setModal(true)}
        onConversacion={() => convRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
      />

      <Etapa ficha={d} onCambio={setD} />

      <section className="second">
        <div className="second-head">
          <h2 className="sec-title">El detrás de escena</h2>
          <span className="hint">
            Todo lo que la IA leyó para llegar a lo de arriba.{' '}
            <button className="link" onClick={() => setVerDetras(!verDetras)}>
              {verDetras ? 'Ocultar' : 'Ver'}
            </button>
          </span>
        </div>
        {verDetras && <Detras ficha={d} />}
      </section>

      <Puertas ficha={d} />

      <div ref={convRef} id="conversacion">
        <div className="conv-head">
          <div>
            <h2 className="sec-title">
              {canal ? `La conversación por ${CANAL_LABEL[canal] || canal}` : 'La conversación completa'}
            </h2>
            <p className="sec-note">Recibís a la izquierda, enviás a la derecha. Sin importar por dónde entró.</p>
          </div>
          <div className="filters">
            <button className={`fbtn ${canal === null ? 'on' : ''}`} onClick={() => setCanal(null)}>
              Todos <span className="num">{d.mensajes.length}</span>
            </button>
            {cortes.map(c => (
              <button key={c.canal} className={`fbtn ${canal === c.canal ? 'on' : ''}`}
                onClick={() => setCanal(canal === c.canal ? null : c.canal)}>
                {c.label} <span className="num">{c.cantidad}</span>
              </button>
            ))}
          </div>
        </div>

        {canal && <ResumenCanal corte={cortes.find(c => c.canal === canal)} />}

        <div className="sides">
          <span>← {d.contacto || 'El cliente'} (recibido)</span>
          <span>Vos / Hilo (enviado) →</span>
        </div>

        <div className="thread">
          {recortados.length === 0 && <p className="t-small">Todavía no hay nada por acá.</p>}
          {recortados.map(m => <Mensaje key={m.id} m={m} ficha={d} ultimo={m.id === d.mensajes[d.mensajes.length - 1]?.id} />)}
        </div>

        {visibles.length > mostrar && (
          <div className="more-wrap">
            <button className="btn btn--secondary" onClick={() => setMostrar(mostrar + PAGINA)}>
              Ver más mensajes ({visibles.length - mostrar})
            </button>
          </div>
        )}
      </div>

      <Redactor ficha={d} canalSugerido={canal} onEnviado={() => { traer(); setAviso('Mensaje enviado') }} />
      <Simulador ficha={d} onCambio={setD} />

      {modal && (
        <ModalBorrador
          ficha={d} onCerrar={() => setModal(false)}
          onCambio={setD}
          onEnviado={() => { setModal(false); traer(); setAviso('Respuesta enviada') }}
        />
      )}
      <div className={`toast ${aviso ? 'show' : ''}`} role="status">
        <span className="tk">✓</span>{aviso}
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ cabezal */

function Encabezado({ ficha, onCambio, verAuto, setVerAuto }) {
  const b = ficha.briefing || {}
  const niveles = ['Silencio', 'Observa', 'Sugiere', 'Pide permiso', 'Con barandas', 'Autónoma']
  return (
    <div className="head">
      <div>
        <h1 className="h-name">{ficha.nombre}</h1>
        <p className="h-sub">
          <b>{ficha.contacto}</b>{ficha.rubro ? `, ${ficha.rubro}` : ''}<i>·</i>
          {b.dias_contacto === 1 ? '1 día de contacto' : `${b.dias_contacto || 1} días de contacto`}<i>·</i>
          {(b.canales || []).length === 1 ? '1 canal' : `${(b.canales || []).length} canales`}
        </p>
      </div>
      <div className="head-controls">
        <div className="score">
          <span className="score-lbl">Importancia</span>
          <div className="seg seg--imp">
            {[['baja', 'Poca'], ['media', 'Media'], ['alta', 'Mucha']].map(([k, t]) => (
              <button key={k} data-imp={k} className={ficha.importancia === k ? 'on' : ''}
                onClick={() => api.importancia(ficha.id, k).then(onCambio)}>{t}</button>
            ))}
          </div>
        </div>
        <button className="auto-btn" onClick={() => setVerAuto(!verAuto)} aria-expanded={verAuto}>
          <span className="auto-spark">✦</span>
          <span className="auto-txt">
            <span className="k">Autonomía</span>
            <span className="v">Nivel <b>{ficha.autonomia}</b> · {niveles[ficha.autonomia]}</span>
          </span>
          <span className="auto-caret">{verAuto ? '▲' : '▼'}</span>
        </button>
      </div>
    </div>
  )
}

function PanelAutonomia({ ficha, onCambio }) {
  const [niveles, setNiveles] = useState([])
  useEffect(() => { api.negocio().then(n => setNiveles(n.niveles)) }, [])
  return (
    <div className="card auto-panel">
      <span className="label">Cuánto lo dejás hacer solo con {ficha.contacto || 'este cliente'}</span>
      <div style={{ marginTop: 10 }}>
        {niveles.map(n => (
          <button key={n.n} className={`lvl ${n.n === ficha.autonomia ? 'on' : ''}`}
            onClick={() => api.autonomia(ficha.id, n.n).then(onCambio)}>
            <span className="n">{n.n}</span><span className="t">{n.nombre}</span><span className="d">{n.detalle}</span>
          </button>
        ))}
      </div>
      <p className="guard">
        {ficha.autonomia_propia ? 'Configurado para este cliente.' : 'Heredado del negocio.'}{' '}
        {(ficha.reglas?.temas_escalan || []).length > 0 &&
          <>Escala si aparece: <b>{ficha.reglas.temas_escalan.join(', ')}</b>.</>}
      </p>
    </div>
  )
}

/* -------------------------------------------------------------------- foco */

function Foco({ ficha, nuestra, vencidos, onIA, onConversacion }) {
  const b = ficha.briefing || {}
  const horas = b.pelota?.horas || 0
  const ultimo = ficha.mensajes[ficha.mensajes.length - 1]
  const clase = !nuestra ? 'ok' : horas >= 48 ? 'late' : horas >= 12 ? 'warn' : ''
  const prom = b.ritmo?.promedio_horas
  return (
    <section className={`card focus ${nuestra ? '' : 'focus--waiting'}`}>
      <div className="focus-top">
        <span className={`state ${nuestra ? '' : 'state--waiting'}`}>
          {nuestra ? 'La pelota es tuya' : 'Esperás al cliente'}
        </span>
        <span className="meta">
          Último contacto hace <b>{duracion(horas)}</b>
          {ultimo ? ` · por ${ultimo.canal_label}` : ''}
        </span>
      </div>
      <div className="focus-grid">
        <div className="time">
          <span className="time-pre">Sin contacto desde hace</span>
          <span className={`time-num ${clase}`}>{duracion(horas)}</span>
          <span className="time-post">
            {nuestra
              ? `${ficha.contacto || 'El cliente'} te escribió y sigue esperando.`
              : `Le escribiste y todavía no contestó.`}
            {prom ? <><br />Suele responder en <b>{prom} h</b>.</> : null}
          </span>
          {vencidos.map(c => (
            <span className="time-flag" key={c.id}>
              ⚠ {c.de_quien === 'nosotros' ? 'Le prometiste' : 'Te prometió'} «{c.texto}»
              {c.dias_tarde ? ` hace ${c.dias_tarde} ${c.dias_tarde === 1 ? 'día' : 'días'}` : ''}
            </span>
          ))}
        </div>
        <div className="act">
          <span className="label">Lo que hay que hacer</span>
          <h2 className="act-h">{b.proximo_paso || 'Todavía no hay un próximo paso claro.'}</h2>
          {(b.por_que_ahora || b.senal_de_urgencia) && (
            <p className="act-why">{b.por_que_ahora || b.senal_de_urgencia}</p>
          )}
          <div className="act-cta">
            <button className="btn btn--primary btn--lg" onClick={onIA}>
              <span className="spark">✦</span> Que la IA lo resuelva
            </button>
            <button className="btn btn--secondary btn--lg" onClick={onConversacion}>Conversación</button>
          </div>
          <p className="act-foot">
            ✦ {['No hace nada','Solo resume','Deja el borrador','Redacta y te pide permiso antes de enviar',
                'Responde sola con barandas','Responde sola'][ficha.autonomia]}
            {ficha.reglas?.descuento_max ? ` · no baja de ${ficha.reglas.descuento_max} %` : ''}
            {ficha.reglas?.horario ? ` · no escribe fuera de ${ficha.reglas.horario[0]} a ${ficha.reglas.horario[1]} h` : ''}
          </p>
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------- etapa */

function Etapa({ ficha, onCambio }) {
  const { estados, estado, estado_sugerido: sug } = ficha
  const [ocupado, setOcupado] = useState(false)
  const i = estados.indexOf(estado)
  const iSug = sug ? estados.indexOf(sug) : -1
  const mandar = async (body) => {
    setOcupado(true)
    try { onCambio(await api.estado(ficha.id, body)) } finally { setOcupado(false) }
  }
  return (
    <section className="card stage-card">
      <div className="stage-top">
        <span className="now-lbl">Etapa <b>{estado}</b></span>
        <span className="prog">{i + 1} de {estados.length}</span>
      </div>
      <div className="stepper">
        {estados.map((e, n) => (
          <button key={e} type="button" disabled={ocupado || n === i}
            title={n === i ? 'Etapa actual' : `Mover a ${e}`}
            onClick={() => mandar({ estado: e })}
            className={`st ${n < i ? 'done' : ''} ${n === i ? 'now' : ''} ${n === iSug ? 'prop' : ''}`}>
            <span className="node" />
            <span className="st-k">
              {String(n + 1).padStart(2, '0')}{n === i ? ' · ahora' : n === iSug ? ' · propuesta' : ''}
            </span>
            <span className="st-t">{e}</span>
          </button>
        ))}
      </div>
      {sug ? (
        <div className="stage-prop">
          <span className="label" style={{ color: 'var(--st-cooling)' }}>La IA propone mover la etapa</span>
          <span className="tag">{estado} → <b>{sug}</b></span>
          <span className="grow" />
          <button className="btn btn--primary btn-sm" disabled={ocupado} onClick={() => mandar({ aceptar: true })}>
            Aceptar y pasar a {sug}
          </button>
          <button className="btn btn-sm" disabled={ocupado} onClick={() => mandar({ descartar: true })}>
            Dejarla como está
          </button>
          {ficha.estado_sugerido_motivo && <p>{ficha.estado_sugerido_motivo}</p>}
        </div>
      ) : (
        <p className="stage-note">
          La IA dedujo la etapa leyendo el hilo, pero no la mueve sola: confirmás vos, o hacés click en otra.
        </p>
      )}
    </section>
  )
}

/* --------------------------------------------------------- detrás de escena */

function Detras({ ficha }) {
  const b = ficha.briefing || {}
  return (
    <div className="card grid2">
      <div className="sub">
        <span className="label">Quién es</span>
        <p>{b.quien_es || '—'}</p>
      </div>
      <div className="sub">
        <span className="label">Su ritmo</span>
        <div className="ritmo">
          <span className="n">{b.ritmo?.promedio_horas ? `${b.ritmo.promedio_horas} h` : '—'}</span>
          <span className="c">
            es lo que suele tardar {ficha.contacto?.split(' ')[0] || 'el cliente'} en responder.<br />
            Van <b>{b.ritmo?.silencio_horas ?? 0} h</b> desde el último mensaje.
          </span>
        </div>
      </div>
      <div className="sub">
        <span className="label">Lo último que se habló</span>
        <ul className="bul">{(b.lo_ultimo || []).map((x, i) => <li key={i}><span>{x}</span></li>)}</ul>
      </div>
      <div className="sub">
        <span className="label">Compromisos abiertos</span>
        {ficha.compromisos.length === 0 && <p>Ninguno abierto.</p>}
        {ficha.compromisos.map(c => (
          <div className="cmt" key={c.id}>
            <span className={`cmt-ico ${c.vencido ? 'late' : 'wait'}`}>{c.vencido ? '!' : '⟳'}</span>
            <div>
              <b>{c.texto}</b>
              <small>
                {c.de_quien === 'nosotros' ? 'Vos' : ficha.contacto || 'El cliente'}
                {c.vence ? ` · ${c.vencido ? 'vencía' : 'vence'} el ${new Date(c.vence).toLocaleDateString('es-AR')}` : ''}
                {c.dias_tarde ? ` · ${c.dias_tarde} ${c.dias_tarde === 1 ? 'día' : 'días'} tarde` : ''}
              </small>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Puertas({ ficha }) {
  return (
    <section className="card puertas">
      <div className="puertas-head">
        <span className="label">
          Un alias, {ficha.identidades.length === 1 ? 'una puerta' : `${ficha.identidades.length} puertas`}
        </span>
        {ficha.token && (
          <span className="puertas-note">
            Vista del cliente: <a className="link" href={`#/c/${ficha.token}`} target="_blank" rel="noreferrer">#/c/{ficha.token}</a>
          </span>
        )}
      </div>
      <div className="puertas-row">
        {ficha.identidades.map(i => (
          <div className="puerta" key={i.valor}>
            <i className="cdot" style={{ background: canalColor(i.canal) }} />
            <span title={i.valor}>{i.valor}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function ResumenCanal({ corte }) {
  if (!corte) return null
  return (
    <div className="card canal-resumen" style={{ borderLeftColor: canalColor(corte.canal) }}>
      <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
        <span className="label">Lo último por {corte.label}</span>
        <span className="grow" />
        {corte.pelota
          ? <span className={`state ${corte.pelota.de === 'nosotros' ? '' : 'state--waiting'}`}>{corte.pelota.texto}</span>
          : <span className="state state--off">Se registra, no se contesta</span>}
      </div>
      <p>{corte.resumen}</p>
      <p className="sec-note" style={{ marginTop: 6 }}>
        {corte.cantidad} {corte.cantidad === 1 ? 'mensaje' : 'mensajes'} · el último {corte.ultimo_hace}
      </p>
    </div>
  )
}

/* ------------------------------------------------------------------ el hilo */

function Mensaje({ m, ficha, ultimo }) {
  const registro = NO_ESCRIBIBLES.includes(m.canal)
  const mio = m.direccion === 'saliente'
  const sinResponder = ultimo && !mio && m.autor === 'cliente'
  const quien = registro
    ? `Registrado por vos${m.canal === 'llamada' ? '' : ' (visita)'}`
    : mio ? (m.autor === 'ia' ? 'Hilo' : 'Vos') : ficha.contacto

  const meta = (
    <div className="msg-meta">
      <span className={`chip chip--${m.canal}`}>{m.canal_label}</span>
      <span className="msg-who">{quien}</span>
      {m.autor === 'ia' && <span className="ai-tag">{m.aprobado_por ? `IA · ${m.aprobado_por === 'simulación' ? 'automático' : 'aprobado'}` : 'IA · sola'}</span>}
      {m.simulado && <span className="sim-tag">prueba</span>}
      {sinResponder && <span className="new-tag">sin responder</span>}
      <span className="msg-date">{fecha(m.creado)}</span>
    </div>
  )

  if (registro) {
    return (
      <div className="msg log">
        {m.resumen && <div className="msg-sum">{m.resumen}</div>}
        {meta}
        <div className="logcard">
          <p>{m.texto}</p>
          {m.adjuntos.length > 0 && (
            <div className="att">{m.adjuntos.map(a => <span className="attbox" key={a}>{a}</span>)}</div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={`msg ${mio ? 'out' : 'in'} ${sinResponder ? 'hot' : ''}`}>
      {m.resumen && <div className="msg-sum">{m.resumen}</div>}
      {meta}
      <div className="msg-bubble">
        {m.asunto && <div className="msg-asunto">{m.asunto}</div>}
        {m.texto}
        {m.adjuntos.length > 0 && (
          <div className="att">{m.adjuntos.map(a => <span className="attbox" key={a}>{a}</span>)}</div>
        )}
      </div>
    </div>
  )
}

/* -------------------------------------------------- popup del borrador de IA */

function ModalBorrador({ ficha, onCerrar, onCambio, onEnviado }) {
  const b = ficha.briefing || {}
  const [texto, setTexto] = useState(b.borrador?.texto || '')
  const [asunto, setAsunto] = useState(b.borrador?.asunto || '')
  const [canal, setCanal] = useState(b.borrador?.canal || ficha.responder_por || 'mail')
  const [pensando, setPensando] = useState(!b.borrador)
  const [enviando, setEnviando] = useState(false)
  const area = useRef(null)

  const cargar = async (tono) => {
    setPensando(true)
    try {
      const f = await api.borrador(ficha.id, { tono })
      const nb = f.briefing?.borrador
      if (nb) { setTexto(nb.texto || ''); setAsunto(nb.asunto || ''); setCanal(nb.canal || canal) }
      onCambio(f)
    } finally { setPensando(false) }
  }

  useEffect(() => { if (!b.borrador) cargar('') }, [])   // sin borrador previo, lo pedimos al abrir
  useEffect(() => { if (!pensando) area.current?.focus() }, [pensando])
  useEffect(() => {
    const esc = e => { if (e.key === 'Escape') onCerrar() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onCerrar])

  const destino = (ficha.canales_salientes || []).find(c => c.canal === canal)
  const escalado = b.borrador?.escalar

  return (
    <div className="overlay open" onMouseDown={e => { if (e.target === e.currentTarget) onCerrar() }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Borrador de la IA">
        <div className="modal-head">
          <span className="auto-spark">✦</span>
          <span className="mh-txt">
            <span className="modal-title">
              {escalado ? 'El agente frenó y te lo pasa a vos' : 'La IA redactó esta respuesta'}
            </span>
            <span className="modal-sub">
              Autonomía nivel {ficha.autonomia} · {ficha.autonomia >= 4 ? 'puede enviar sola' : 'necesita tu permiso para enviar'}
            </span>
          </span>
          <button className="modal-x" onClick={onCerrar} aria-label="Cerrar">✕</button>
        </div>

        <div className="modal-body">
          {escalado ? (
            <p className="t-body" style={{ color: 'var(--ink)' }}>{b.borrador.motivo_escalada}</p>
          ) : (
            <>
              <div className="modal-to">
                <span className={`chip chip--${canal}`}>{CANAL_LABEL[canal] || canal}</span>
                {destino?.destino && <span>Para <b>{destino.destino}</b></span>}
              </div>
              {destino?.asunto && (
                <input type="text" value={asunto} onChange={e => setAsunto(e.target.value)}
                  placeholder="Asunto" aria-label="Asunto del mail"
                  style={{ marginBottom: 10, fontWeight: 700 }} />
              )}
              <textarea ref={area} className="draft-area" value={texto} disabled={pensando}
                onChange={e => setTexto(e.target.value)} aria-label="Borrador de la respuesta"
                placeholder={pensando ? 'Leyendo el hilo y escribiendo…' : ''} />
              <p className="modal-hint">
                ✎ Editá lo que quieras antes de enviar.
                {ficha.reglas?.descuento_max ? ` Respeta las barandas: no baja de ${ficha.reglas.descuento_max} %.` : ''}
              </p>
              <div className="modal-tone">
                {pensando && <span className="t-small"><span className="spin" /> pensando…</span>}
                {!pensando && <>
                  <button className="tone" onClick={() => cargar('corto')}>Más corto</button>
                  <button className="tone" onClick={() => cargar('calido')}>Más cálido</button>
                  <button className="tone" onClick={() => cargar('firme')}>Más firme</button>
                  <button className="tone" onClick={() => cargar('')}>Rehacer</button>
                </>}
              </div>
            </>
          )}
        </div>

        <div className="modal-foot">
          <span className="spacer">
            {escalado ? 'Escribile vos desde el redactor de abajo.'
              : `Se envía por ${CANAL_LABEL[canal] || canal}, el último canal que usó ${ficha.contacto?.split(' ')[0] || 'el cliente'}.`}
          </span>
          <button className="btn btn--secondary" onClick={onCerrar}>Descartar</button>
          {!escalado && (
            <button className="btn btn--primary" disabled={pensando || enviando || !texto.trim()}
              onClick={async () => {
                setEnviando(true)
                await api.responder(ficha.id, { texto, canal, asunto, autor: 'ia' })
                onEnviado()
              }}>
              {enviando ? 'Enviando…' : 'Aprobar y enviar'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------ redactor manual y pruebas */

function Redactor({ ficha, canalSugerido, onEnviado }) {
  const salientes = (ficha.canales_salientes || []).filter(c => c.destino)
  const disponibles = salientes.length ? salientes : (ficha.canales_salientes || [])
  const inicial = () => {
    if (canalSugerido && disponibles.some(c => c.canal === canalSugerido)) return canalSugerido
    return ficha.responder_por || disponibles[0]?.canal || 'mail'
  }
  const [canal, setCanal] = useState(inicial)
  const [asunto, setAsunto] = useState('')
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)
  useEffect(() => { setCanal(inicial()) }, [canalSugerido, ficha.id])

  const elegido = disponibles.find(c => c.canal === canal) || disponibles[0]
  if (!elegido) return null

  return (
    <section className="card" style={{ marginTop: 'var(--sp-6)', padding: '18px 22px' }}>
      <span className="label">Escribirle vos a {ficha.contacto || ficha.nombre}</span>
      <div className="filters" style={{ margin: '12px 0 14px' }}>
        {disponibles.map(c => (
          <button key={c.canal} className={`fbtn ${canal === c.canal ? 'on' : ''}`}
            onClick={() => setCanal(c.canal)}>{c.label}</button>
        ))}
      </div>
      {elegido.destino && <p className="sec-note" style={{ marginBottom: 10 }}>Sale a <b>{elegido.destino}</b></p>}
      {elegido.asunto && (
        <input type="text" value={asunto} onChange={e => setAsunto(e.target.value)}
          placeholder="Asunto" aria-label="Asunto del mail" style={{ marginBottom: 9, fontWeight: 700 }} />
      )}
      <textarea rows={elegido.asunto ? 5 : 3} value={texto} onChange={e => setTexto(e.target.value)}
        aria-label="Mensaje" placeholder={`Escribí el mensaje de ${elegido.label}…`} />
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn btn--primary" disabled={enviando || !texto.trim()}
          onClick={async () => {
            setEnviando(true)
            await api.responder(ficha.id, { texto, canal, asunto: elegido.asunto ? asunto : '', autor: 'humano' })
            setTexto(''); setAsunto(''); setEnviando(false); onEnviado()
          }}>
          {enviando ? 'Enviando…' : `Enviar por ${elegido.label}`}
        </button>
        <RegistrarNoDigital id={ficha.id} onHecho={onEnviado} />
      </div>
    </section>
  )
}

function RegistrarNoDigital({ id, onHecho }) {
  const [abierto, setAbierto] = useState(false)
  const [texto, setTexto] = useState('')
  const [canal, setCanal] = useState('llamada')
  const [dictando, setDictando] = useState(false)
  const rec = useRef(null)

  const dictar = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { alert('Tu navegador no permite dictar. Escribilo a mano y funciona igual.'); return }
    if (dictando) { rec.current?.stop(); return }
    const r = new SR()
    r.lang = 'es-AR'; r.continuous = true; r.interimResults = false
    r.onresult = e => {
      let t = ''
      for (let i = e.resultIndex; i < e.results.length; i++) t += e.results[i][0].transcript
      setTexto(prev => (prev ? prev + ' ' : '') + t.trim())
    }
    r.onend = () => setDictando(false)
    r.start(); rec.current = r; setDictando(true)
  }

  if (!abierto) {
    return <button className="btn btn--secondary" onClick={() => setAbierto(true)}>Registrar una llamada o una visita</button>
  }
  return (
    <div style={{ width: '100%', marginTop: 12, paddingTop: 14, borderTop: '1px solid var(--line-soft)' }}>
      <span className="label">Lo que se habló fuera de los canales digitales</span>
      <div className="filters" style={{ margin: '11px 0' }}>
        {['llamada', 'presencial'].map(c => (
          <button key={c} className={`fbtn ${canal === c ? 'on' : ''}`} onClick={() => setCanal(c)}>
            {CANAL_LABEL[c]}
          </button>
        ))}
        <button className={`fbtn ${dictando ? 'on' : ''}`} onClick={dictar}>
          {dictando ? 'Escuchando… tocá para parar' : 'Dictar'}
        </button>
      </div>
      <textarea rows={3} value={texto} onChange={e => setTexto(e.target.value)}
        aria-label="Qué se habló"
        placeholder="Lo llamé, quiere 20 % de descuento, lo ve con el socio el jueves…" />
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn btn--primary" disabled={!texto.trim()}
          onClick={async () => { await api.nota(id, { texto, canal }); setTexto(''); setAbierto(false); onHecho() }}>
          Guardar en el hilo
        </button>
        <button className="btn btn--secondary" onClick={() => setAbierto(false)}>Cancelar</button>
      </div>
    </div>
  )
}

function Simulador({ ficha, onCambio }) {
  const [corriendo, setCorriendo] = useState('')
  const [ultimo, setUltimo] = useState(null)
  const correr = async (turnos, auto, etiqueta) => {
    setCorriendo(etiqueta)
    try {
      const r = await api.simular(ficha.id, { turnos, auto })
      setUltimo(r.rondas[r.rondas.length - 1]?.cliente || null)
      onCambio(r.ficha)
    } finally { setCorriendo('') }
  }
  const temp = {
    mas_caliente: ['Se calentó', 'b-them'], igual: ['Quedó igual', 'b-off'], mas_frio: ['Se enfrió', 'b-cold'],
  }[ultimo?.temperatura]

  return (
    <section className="card" style={{ marginTop: 'var(--sp-5)', padding: '18px 22px' }}>
      <div className="row" style={{ flexWrap: 'wrap' }}>
        <div>
          <span className="label">Probar el agente</span>
          <p className="sec-note" style={{ marginTop: 4 }}>
            La IA se pone en el papel de {ficha.contacto || ficha.nombre} y contesta como contestaría esa persona.
          </p>
        </div>
        <span className="grow" />
        <button className="btn btn--secondary" disabled={!!corriendo} onClick={() => correr(1, false, 'uno')}>
          {corriendo === 'uno' ? <><span className="spin" /> Pensando…</> : 'Que conteste el cliente'}
        </button>
        <button className="btn btn--secondary" disabled={!!corriendo} onClick={() => correr(3, true, 'tres')}>
          {corriendo === 'tres' ? <><span className="spin" /> Conversando…</> : 'Que conversen solos ×3'}
        </button>
        {ficha.simulados > 0 && (
          <button className="btn btn--secondary" disabled={!!corriendo}
            onClick={async () => {
              setCorriendo('limpiar')
              try { const r = await api.limpiarSim(ficha.id); setUltimo(null); onCambio(r.ficha) }
              finally { setCorriendo('') }
            }}>Limpiar las {ficha.simulados} de prueba</button>
        )}
      </div>
      {ultimo && (
        <div className="row" style={{ marginTop: 14, paddingTop: 13, borderTop: '1px solid var(--line-soft)', flexWrap: 'wrap' }}>
          {temp && <span className={`badge ${temp[1]}`}>{temp[0]}</span>}
          {ultimo.listo_para_cerrar && <span className="badge b-them">Listo para cerrar</span>}
          {ultimo.se_va && <span className="badge b-me">Se va</span>}
          {ultimo.por_que && <span className="t-small">{ultimo.por_que}</span>}
        </div>
      )}
    </section>
  )
}
