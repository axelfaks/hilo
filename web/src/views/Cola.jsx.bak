import React, { useEffect, useMemo, useState } from 'react'
import { api, canalColor } from '../api.js'
import { ir } from '../App.jsx'

/* La cola — estructura de Toto (iteración 2). Dos vistas:
   Lista, para trabajar cliente por cliente; Panorama, para ver la cartera entera. */

const IMP_N = { alta: 3, media: 2, baja: 1 }
const ETIQUETA = { yours: 'te esperan', nuevos: 'contactos nuevos', cold: 'se están enfriando' }

function palabra(n, filtro, busca) {
  if (filtro) return ETIQUETA[filtro]
  if (busca.trim()) return n === 1 ? 'resultado' : 'resultados'
  return n === 1 ? 'cliente' : 'clientes'
}
const IMP_COLOR = { alta: 'var(--score-alta)', media: 'var(--score-media)', baja: 'var(--score-baja)' }

function hace(h) {
  if (!h || h < 1) return 'recién'
  if (h < 48) return `hace ${Math.round(h)} h`
  return `hace ${Math.round(h / 24)} días`
}

/* Quién debe la respuesta manda. La temperatura solo califica al que está
   esperando al cliente: si la deuda es nuestra, es nuestra aunque esté frío. */
function estadoDe(f) {
  if (f.cerrado) return { clave: 'cerrado', texto: f.estado, clase: 'badge--off' }
  if (f.pelota?.de === 'nosotros') {
    return { clave: 'yours', texto: 'Hay que responderle', clase: 'badge--yours' }
  }
  if (['enfriandose', 'frio'].includes(f.temperatura?.nivel)) {
    return { clave: 'cold', texto: 'Enfriándose', clase: 'badge--cold' }
  }
  return { clave: 'waiting', texto: 'Esperando respuesta', clase: 'badge--waiting' }
}

export default function Cola() {
  const [d, setD] = useState(null)
  const [pan, setPan] = useState(null)
  const [error, setError] = useState('')
  const [vista, setVista] = useState('lista')
  const [filtro, setFiltro] = useState(null)
  const [orden, setOrden] = useState('urgencia')
  const [busca, setBusca] = useState('')
  const [pulso, setPulso] = useState(false)

  const filtrar = (f) => {
    setFiltro(filtro === f ? null : f)
    setTimeout(() => document.getElementById('tabla')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 30)
  }
  const mirarSinIdentificar = () => {
    document.getElementById('sinid')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setPulso(false); setTimeout(() => setPulso(true), 20); setTimeout(() => setPulso(false), 1600)
  }

  useEffect(() => {
    let vivo = true
    const traer = () => api.cola().then(x => vivo && setD(x)).catch(e => vivo && setError(e.message))
    traer()
    const t = setInterval(traer, 2000)
    return () => { vivo = false; clearInterval(t) }
  }, [])
  useEffect(() => { if (vista === 'panorama') api.panorama().then(setPan).catch(() => {}) }, [vista, d?.clientes?.length])

  const filas = useMemo(() => {
    if (!d) return []
    let f = d.clientes.map(c => ({ ...c, est: estadoDe(c) }))
    if (filtro === 'yours') f = f.filter(x => x.est.clave === 'yours')
    if (filtro === 'cold') f = f.filter(x => x.est.clave === 'cold')
    if (filtro === 'nuevos') f = f.filter(x => x.contacto_nuevo)
    if (busca.trim()) {
      const q = busca.trim().toLowerCase()
      f = f.filter(x => x.nombre.toLowerCase().includes(q) || (x.contacto || '').toLowerCase().includes(q))
    }
    const orden_fn = {
      urgencia: (a, b) => b.urgencia - a.urgencia,
      importancia: (a, b) => (IMP_N[b.importancia] - IMP_N[a.importancia]) || (b.urgencia - a.urgencia),
      actividad: (a, b) => b.horas - a.horas,
      nombre: (a, b) => a.nombre.localeCompare(b.nombre, 'es'),
    }[orden]
    return [...f].sort(orden_fn)
  }, [d, filtro, orden, busca])

  if (error) return <p className="t-body">No pude hablar con el backend: {error}</p>
  if (!d) return <p className="t-body"><span className="spin" /> Cargando…</p>
  const c = d.contadores

  return (
    <>
      <div className="head-row">
        <div>
          <h1 className="h-display">Quién te está esperando</h1>
          <p className="h-lead">Ordenado por urgencia real: lo que le debés a alguien pesa más que cualquier otra cosa.</p>
        </div>
        <div className="viewswitch">
          <button className={vista === 'lista' ? 'on' : ''} onClick={() => setVista('lista')}>Lista</button>
          <button className={vista === 'panorama' ? 'on' : ''} onClick={() => setVista('panorama')}>Panorama</button>
        </div>
      </div>

      {vista === 'lista' ? (
        <>
          <div className="stats">
            <Stat clase="stat--yours" n={c.te_esperan} texto="te esperan"
              activo={filtro === 'yours'} onClick={() => filtrar('yours')} />
            <Stat clase="stat--new" n={c.contactos_nuevos} texto={c.contactos_nuevos === 1 ? 'contacto nuevo' : 'contactos nuevos'}
              activo={filtro === 'nuevos'} onClick={() => filtrar('nuevos')} />
            <Stat clase="stat--cold" n={c.enfriandose} texto="se están enfriando"
              activo={filtro === 'cold'} onClick={() => filtrar('cold')} />
            <Stat clase="stat--unknown" n={c.sin_identificar} texto="sin identificar" flecha="Ver ↑"
              activo={false} onClick={mirarSinIdentificar} />
          </div>

          <div id="sinid">
            {d.sin_identificar.map(m => (
              <SinIdentificar key={m.mensaje_id} m={m} pulso={pulso} onHecho={() => api.cola().then(setD)} />
            ))}
          </div>

          <div className="table-head" id="tabla">
            <input className="search" type="text" value={busca} onChange={e => setBusca(e.target.value)}
              placeholder="Buscar cliente…" aria-label="Buscar cliente" />
            <span className="th-count"><b>{filas.length}</b> {palabra(filas.length, filtro, busca)}</span>
            {filtro && (
              <span className="fchip">
                Filtrado: {ETIQUETA[filtro]}
                <button onClick={() => setFiltro(null)} aria-label="Quitar filtro">✕</button>
              </span>
            )}
            <div className="sort">
              <span className="label">Ordenar</span>
              <div className="seg">
                {[['urgencia', 'Urgencia'], ['importancia', 'Importancia'],
                  ['actividad', 'Sin actividad'], ['nombre', 'Nombre']].map(([k, t]) => (
                  <button key={k} className={orden === k ? 'on' : ''} onClick={() => setOrden(k)}>{t}</button>
                ))}
              </div>
            </div>
          </div>

          <div className="qhead"><span>Cliente</span><span>Estado</span></div>
          <div className="card qlist">
            {filas.length === 0 && <p className="t-small" style={{ padding: 22 }}>No hay ningún cliente con ese filtro.</p>}
            {filas.map(f => (
              <button key={f.id} className={`qrow ${f.cerrado ? 'off' : ''}`} data-imp={IMP_N[f.importancia]}
                onClick={() => ir(`/a/${f.id}`)}>
                <div className="qmain">
                  <div className="qline1">
                    <span className="qname">{f.nombre}</span>
                    <span className="chip-stage">{f.estado}</span>
                    {f.no_leido && <span className="tag-new">Nuevo mensaje</span>}
                    {f.estado_sugerido && <span className="pastilla pastilla-aviso">etapa propuesta</span>}
                  </div>
                  <div className="qline2">
                    <span className="qch">
                      {f.canales.map(ch => <i key={ch} className="cdot" style={{ background: canalColor(ch) }} />)}
                    </span>
                    <span className="qprev">{f.ultimo}</span>
                    {f.compromisos_vencidos > 0 && (
                      <span className="tag-venc">
                        {f.compromisos_vencidos === 1 ? '1 compromiso vencido' : `${f.compromisos_vencidos} compromisos vencidos`}
                      </span>
                    )}
                  </div>
                </div>
                <div className="qright">
                  <span className={`badge ${f.est.clase}`}>{f.est.texto}</span>
                  {!f.cerrado && (
                    <span className="qtime">
                      {f.est.clave === 'cold' || f.est.clave === 'waiting' ? 'esperás ' : ''}{hace(f.horas)}
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>

          <div className="legend">
            <span><i className="leg-bar" style={{ background: 'var(--score-alta)' }} />Importancia alta</span>
            <span><i className="leg-bar" style={{ background: 'var(--score-media)' }} />Media</span>
            <span><i className="leg-bar" style={{ background: 'var(--score-baja)' }} />Baja</span>
            <span><span className="badge badge--yours" style={{ padding: '3px 9px' }}>Hay que responderle</span></span>
            <span><span className="badge badge--waiting" style={{ padding: '3px 9px' }}>Esperando respuesta</span></span>
            <span><span className="tag-new">Nuevo mensaje</span> sin leer</span>
          </div>
        </>
      ) : (
        <Panorama pan={pan} clientes={d.clientes.map(x => ({ ...x, est: estadoDe(x) }))} />
      )}
    </>
  )
}

function Stat({ clase, n, texto, activo, onClick, flecha = 'Ver ↓' }) {
  return (
    <button className={`stat ${clase}`} aria-pressed={activo} onClick={onClick}>
      <span className="go">{flecha}</span>
      <span className="n">{n}</span>
      <span className="c">{texto}</span>
    </button>
  )
}

function SinIdentificar({ m, pulso, onHecho }) {
  const [ocupado, setOcupado] = useState(false)
  if (!m.sugerencia) return null
  return (
    <div className={`card unknown-card ${pulso ? 'pulse' : ''}`}>
      <div className="uc-top">
        <span className="badge badge--unknown">Sin identificar</span>
        <span className="t-small">{m.remitente}</span>
      </div>
      <p className="uc-quote">«{m.texto}»</p>
      <p className="uc-why">
        La IA cree que es <b>{m.sugerencia.nombre}</b> con {m.sugerencia.confianza} % de confianza:{' '}
        {m.sugerencia.motivo}
      </p>
      <div className="uc-acts">
        <button className="btn btn--primary btn-sm" disabled={ocupado}
          onClick={async () => { setOcupado(true); await api.fusionar(m.mensaje_id, m.sugerencia.alias_id); onHecho() }}>
          {ocupado ? 'Fusionando…' : `Sí, es ${m.sugerencia.nombre}`}
        </button>
        <button className="btn btn--secondary btn-sm">Crear un alias nuevo</button>
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- panorama */

const COLOR_PELOTA = {
  te_toca: 'var(--st-yours)', esperando: 'var(--st-waiting)',
  enfriandose: 'var(--st-cooling)', cerrados: 'var(--ink-3)',
}

function Panorama({ pan, clientes }) {
  if (!pan) return <p className="t-body" style={{ marginTop: 24 }}><span className="spin" /> Calculando…</p>
  const maxEtapa = Math.max(1, ...pan.por_etapa.map(e => e.n))
  const totalPelota = Math.max(1, pan.pelota.reduce((a, x) => a + x.n, 0))
  const teToca = pan.pelota.find(x => x.clave === 'te_toca')?.n || 0
  const riesgo = pan.pelota.find(x => x.clave === 'enfriandose')?.n || 0
  const r = pan.ritmo
  const maxRitmo = Math.max(1, r.vos_horas || 0, r.clientes_horas || 0)
  const totalImp = Math.max(1, Object.values(pan.importancia).reduce((a, b) => a + b, 0))
  const activos = clientes.filter(x => !x.cerrado)
  const altas = activos.filter(x => x.importancia === 'alta')
  const altasQueEsperan = altas.filter(x => x.est.clave === 'yours' || x.est.clave === 'cold')
  const urgentes = [...activos].filter(x => x.est.clave === 'yours' || x.est.clave === 'cold')
    .sort((a, b) => b.urgencia - a.urgencia).slice(0, 3)

  return (
    <>
      <div className="kpis">
        <div className="card kpi"><span className="label">En la cola</span><div className="v">{pan.activos}</div>
          <p className="d">clientes activos ahora</p></div>
        <div className="card kpi k-yours"><span className="label">Te toca</span><div className="v">{teToca}</div>
          <p className="d">hay que responderles</p></div>
        <div className="card kpi k-cold"><span className="label">Riesgo</span><div className="v">{pan.riesgo_7d ?? riesgo}</div>
          <p className="d">enfriándose hace <b>+7 días</b></p></div>
        <div className="card kpi k-unknown"><span className="label">Sin identificar</span><div className="v">{pan.sin_identificar}</div>
          <p className="d">{pan.sin_identificar === 1 ? 'mensaje sin alias' : 'mensajes sin alias'}</p></div>
      </div>

      <div className="grid">
        <div className="card panel">
          <h3>Dónde están en el flujo</h3>
          <p className="psub">Cuántos clientes hay en cada etapa de venta.</p>
          {pan.por_etapa.map(e => (
            <div className="fun-row" key={e.etapa}>
              <span className="fun-label">{e.etapa}</span>
              <div className="fun-track"><div className="fun-bar" style={{ width: `${(e.n / maxEtapa) * 100}%` }} /></div>
              <span className="fun-n">{e.n}</span>
            </div>
          ))}
        </div>

        <div className="card panel">
          <h3>De quién es la pelota</h3>
          <p className="psub">Sobre los {pan.activos} activos y los cerrados.</p>
          <div className="stack">
            {pan.pelota.filter(x => x.n > 0).map(x => (
              <i key={x.clave} style={{ flex: x.n, background: COLOR_PELOTA[x.clave] }} title={`${x.label}: ${x.n}`} />
            ))}
          </div>
          <div className="stlegend">
            {pan.pelota.map(x => (
              <div className="stleg" key={x.clave}>
                <i className="d" style={{ background: COLOR_PELOTA[x.clave] }} />
                {x.label}<span className="n">{x.n}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid" style={{ marginTop: 16 }}>
        <div className="card panel">
          <h3>Ritmo de respuesta</h3>
          <p className="psub">Cuánto tardás vos contra cuánto tardan tus clientes.</p>
          <div className="cmp-row">
            <span className="cmp-label">Vos</span>
            <div className="cmp-track"><div className="cmp-bar you" style={{ width: `${((r.vos_horas || 0) / maxRitmo) * 100}%` }} /></div>
            <span className="cmp-n">{r.vos_horas != null ? `${r.vos_horas} h` : '—'}</span>
          </div>
          <div className="cmp-row">
            <span className="cmp-label">Tus clientes</span>
            <div className="cmp-track"><div className="cmp-bar them" style={{ width: `${((r.clientes_horas || 0) / maxRitmo) * 100}%` }} /></div>
            <span className="cmp-n">{r.clientes_horas != null ? `${r.clientes_horas} h` : '—'}</span>
          </div>
          <p className="cmp-note">
            {r.vos_horas != null && r.clientes_horas != null && r.vos_horas > r.clientes_horas
              ? <>Estás tardando <b>{Math.round(r.vos_horas / Math.max(r.clientes_horas, 1))} veces más</b> que ellos en contestar. Ahí se enfrían las ventas.</>
              : 'Contestás más rápido de lo que te contestan. Así se cierran.'}
          </p>
        </div>

        <div className="card panel">
          <h3>Por importancia</h3>
          <p className="psub">Cómo scoreaste tu cartera activa.</p>
          {['alta', 'media', 'baja'].map(k => (
            <div className="imp-row" key={k}>
              <i className="imp-dot" style={{ background: IMP_COLOR[k] }} />
              {{ alta: 'Alta', media: 'Media', baja: 'Baja' }[k]}
              <div className="imp-track">
                <div className="imp-fill" style={{ width: `${(pan.importancia[k] / totalImp) * 100}%`, background: IMP_COLOR[k] }} />
              </div>
              <span className="imp-n">{pan.importancia[k]}</span>
            </div>
          ))}
          {altas.length > 0 && (
            <p className="cmp-note">
              De los <b style={{ color: 'var(--ink)' }}>{altas.length} de alta importancia</b>,{' '}
              {altasQueEsperan.length === 0
                ? 'ninguno está esperando una respuesta tuya.'
                : altasQueEsperan.length === altas.length
                  ? `${altas.length === 2 ? 'a los dos' : 'a todos'} hay que responderles. Son la prioridad del día.`
                  : `hay que responderle a ${altasQueEsperan.length}. Es la prioridad del día.`}
            </p>
          )}
        </div>
      </div>

      <section className="card urg">
        <div style={{ padding: '16px 22px 4px' }}>
          <h3>Los más urgentes ahora</h3>
          <p className="psub" style={{ marginBottom: 2 }}>Los que más te están esperando. Tocá para abrir la ficha.</p>
        </div>
        {urgentes.length === 0 && <p className="t-small" style={{ padding: '4px 22px 18px' }}>Nadie está esperando una respuesta tuya. Buen momento.</p>}
        {urgentes.map(f => (
          <button className="urow" key={f.id} onClick={() => ir(`/a/${f.id}`)}>
            <span className="udot" style={{ background: IMP_COLOR[f.importancia] }} title={`Importancia ${f.importancia}`} />
            <span className="uname">{f.nombre}</span>
            <span className={`badge ${f.est.clase}`}>{f.est.texto}</span>
            <span className="utime">{hace(f.horas)}</span>
          </button>
        ))}
      </section>
    </>
  )
}
