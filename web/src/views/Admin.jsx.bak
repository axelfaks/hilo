import React, { useEffect, useState } from 'react'

import { api } from '../api.js'

export default function Admin() {
  const [n, setN] = useState(null)
  const [estados, setEstados] = useState([])
  const [desc, setDesc] = useState('')
  const [pensando, setPensando] = useState(false)
  const [porQue, setPorQue] = useState('')
  const [guardado, setGuardado] = useState(false)

  useEffect(() => {
    api.negocio().then(d => { setN(d); setEstados(d.estados); setDesc(d.descripcion) })
  }, [])

  if (!n) return <p className="t-body"><span className="spin" /> Cargando…</p>

  const guardar = async (extra = {}) => {
    const d = await api.guardarNegocio({ descripcion: desc, estados, ...extra })
    setN(d); setGuardado(true); setTimeout(() => setGuardado(false), 1800)
  }

  return (
    <>
      <h1 className="t-display">Cómo trabaja tu agente</h1>
      <p className="t-body" style={{ marginTop: 6 }}>
        Todo lo que decide el agente sale de esta pantalla.{' '}
        {n.ia?.activa
          ? `Conectado a ${n.ia.proveedor}${n.ia.modelo ? ` (${n.ia.modelo})` : ''}.`
          : 'Sin IA conectada: el sistema sigue andando con los cálculos locales.'}
      </p>

      {n.ia?.activa && n.ia.ultimo_error && (
        <div className="card" style={{
          marginTop: 16, padding: '14px 18px',
          borderColor: 'var(--amber-line)', background: 'var(--amber-soft)',
        }}>
          <span className="lbl" style={{ color: 'var(--amber)' }}>La última llamada a la IA falló</span>
          <p className="t-body" style={{ marginTop: 7, color: 'var(--ink)', fontFamily: 'ui-monospace, monospace', fontSize: 13 }}>
            {n.ia.ultimo_error}
          </p>
          <p className="t-small" style={{ marginTop: 7 }}>
            Mientras tanto la app sigue con los cálculos locales. Para más detalle:{' '}
            <a className="link" href="/api/diagnostico-ia" target="_blank" rel="noreferrer">/api/diagnostico-ia</a>
          </p>
        </div>
      )}

      <div className="row" style={{ marginTop: 18 }}>
        <button className="btn btn-sm" onClick={async () => {
          await api.onboardingReabrir(); window.location.hash = '/onboarding'
        }}>Volver a pasar por las preguntas iniciales</button>
      </div>

      <section className="card pad" style={{ marginTop: 18 }}>
        <span className="lbl">A · El flujo de venta de tu negocio</span>
        <p className="t-body" style={{ margin: '10px 0 12px' }}>
          Contá cómo vendés y la IA propone las etapas. Después son tuyas: renombralas, sacá las que no
          uses, agregá las que falten.
        </p>
        <textarea rows={4} value={desc} onChange={e => setDesc(e.target.value)} aria-label="Descripción del negocio" />
        <div className="row" style={{ marginTop: 12 }}>
          <button
            className="btn btn-primary" disabled={pensando}
            onClick={async () => {
              setPensando(true)
              const r = await api.sugerirEstados(desc)
              setEstados(r.estados); setPorQue(r.por_que || ''); setPensando(false)
            }}
          >
            {pensando ? <><span className="spin" /> Leyendo tu negocio…</> : 'Proponer las etapas'}
          </button>
          <button className="btn" onClick={() => guardar()}>Guardar</button>
          {guardado && <span className="t-small" style={{ color: 'var(--teal)' }}>Guardado</span>}
        </div>

        <div style={{ display: 'flex', gap: 6, marginTop: 18, flexWrap: 'wrap' }}>
          {estados.map((e, i) => (
            <div key={i} className="row" style={{
              gap: 6, background: 'var(--paper)', border: '1px solid var(--line)',
              borderRadius: 8, padding: '6px 8px 6px 12px',
            }}>
              <span className="t-small num">{String(i + 1).padStart(2, '0')}</span>
              <input
                type="text" value={e} aria-label={`Etapa ${i + 1}`}
                onChange={ev => setEstados(estados.map((x, j) => (j === i ? ev.target.value : x)))}
                style={{ width: `${Math.max(9, e.length + 1)}ch`, border: 0, background: 'transparent', padding: '2px 0', fontWeight: 600 }}
              />
              <button
                className="btn btn-sm" title="Sacar esta etapa"
                onClick={() => setEstados(estados.filter((_, j) => j !== i))}
                style={{ padding: '2px 8px' }}
              >×</button>
            </div>
          ))}
          <button className="btn btn-sm" onClick={() => setEstados([...estados, 'Etapa nueva'])}>+ Agregar</button>
        </div>
        {porQue && <p className="t-small" style={{ marginTop: 12 }}>{porQue}</p>}
      </section>

      <section className="card pad" style={{ marginTop: 16 }}>
        <span className="lbl">B · El reglamento del agente</span>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 14 }}>
          <Regla titulo="Tono" valor={n.reglas.tono} />
          <Regla titulo="Horario en el que puede escribir" valor={`De ${n.reglas.horario?.[0]} a ${n.reglas.horario?.[1]} h`} />
          <Regla titulo="Cada cuánto insiste" valor={`Cada ${n.reglas.insistir_cada_dias} días, hasta ${n.reglas.max_insistencias} veces`} />
          <Regla titulo="Descuento que puede ofrecer solo" valor={`Hasta ${n.reglas.descuento_max} %`} />
          <Regla titulo="Temas que lo obligan a escalar" valor={(n.reglas.temas_escalan || []).join(' · ')} ancho />
        </div>
      </section>

      <section className="card pad" style={{ marginTop: 16 }}>
        <span className="lbl">C · Cuánta autonomía tiene por defecto</span>
        <p className="t-body" style={{ margin: '10px 0 14px' }}>
          Este es el nivel que arranca en cada cliente nuevo. En la ficha de cada uno se puede subir o bajar.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {n.niveles.map(l => {
            const activo = l.n === n.autonomia_default
            return (
              <button
                key={l.n}
                onClick={() => guardar({ autonomia_default: l.n })}
                style={{
                  display: 'grid', gridTemplateColumns: '26px 150px 1fr', gap: 12, alignItems: 'center',
                  textAlign: 'left', padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
                  background: activo ? 'var(--teal-soft)' : 'var(--paper)',
                  border: `1px solid ${activo ? 'var(--teal-line)' : 'var(--line)'}`,
                }}
              >
                <span className="num" style={{ fontWeight: 700, color: activo ? 'var(--teal)' : 'var(--ink-3)' }}>{l.n}</span>
                <span style={{ fontWeight: 600, color: activo ? 'var(--teal-2)' : 'var(--ink)' }}>{l.nombre}</span>
                <span className="t-small">{l.detalle}</span>
              </button>
            )
          })}
        </div>
      </section>
    </>
  )
}

function Regla({ titulo, valor, ancho }) {
  return (
    <div style={{
      background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 9,
      padding: '12px 14px', gridColumn: ancho ? '1 / -1' : 'auto',
    }}>
      <span className="lbl">{titulo}</span>
      <p className="t-body" style={{ marginTop: 5, color: 'var(--ink)' }}>{valor || '—'}</p>
    </div>
  )
}
