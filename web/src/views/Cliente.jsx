import React, { useEffect, useRef, useState } from 'react'
import { api, CANAL_LABEL } from '../api.js'

/** La pantalla que se abre en el celular del público durante la demo.
 *  Se ve como una app de mensajería cualquiera: ni un rastro de Hilo ni de la IA.
 *  Lo que escriba acá entra por POST /api/ingest, la misma puerta por la que
 *  entraría un mail real el día que conectemos una casilla. */
export default function Cliente({ token }) {
  const [d, setD] = useState(null)
  const [texto, setTexto] = useState('Che, seguimos esperando el precio')
  const [canal, setCanal] = useState('mail')
  const [enviando, setEnviando] = useState(false)
  const [pensando, setPensando] = useState(false)
  const finRef = useRef(null)

  useEffect(() => {
    let vivo = true
    const tick = () => api.cliente(token).then(x => vivo && setD(x)).catch(() => {})
    tick()
    const t = setInterval(tick, 2000)
    return () => { vivo = false; clearInterval(t) }
  }, [token])

  useEffect(() => { finRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [d?.mensajes?.length])

  if (!d) return <p style={{ padding: 24 }}>Cargando…</p>

  const canales = Object.keys(d.identidades || {}).filter(c => !['llamada', 'presencial'].includes(c))

  return (
    <div style={{
      maxWidth: 390, margin: '0 auto', minHeight: '100dvh',
      display: 'flex', flexDirection: 'column', background: '#fff',
      borderLeft: '1px solid var(--line)', borderRight: '1px solid var(--line)',
    }}>
      <header style={{
        padding: '14px 18px', borderBottom: '1px solid var(--line)',
        display: 'flex', alignItems: 'center', gap: 11, position: 'sticky', top: 0, background: '#fff', zIndex: 2,
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: '50%', background: 'var(--teal)', color: '#fff',
          display: 'grid', placeItems: 'center', fontWeight: 700,
        }}>{d.vendedor.slice(0, 1)}</div>
        <div>
          <div style={{ fontWeight: 700, letterSpacing: '-.01em' }}>{d.vendedor}</div>
          <div className="t-small">en línea</div>
        </div>
      </header>

      <div style={{ flex: 1, padding: '16px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {d.mensajes.map((m, i) => (
          <div key={i} style={{ alignSelf: m.mio ? 'flex-end' : 'flex-start', maxWidth: '84%' }}>
            <div style={{
              borderRadius: 16, padding: '10px 14px', fontSize: 14.5, lineHeight: 1.5,
              borderBottomRightRadius: m.mio ? 5 : 16, borderBottomLeftRadius: m.mio ? 16 : 5,
              background: m.mio ? 'var(--teal)' : 'var(--paper)',
              color: m.mio ? '#fff' : 'var(--ink)',
              border: m.mio ? 'none' : '1px solid var(--line)',
              whiteSpace: 'pre-wrap',
            }}>{m.texto}</div>
            <div className="t-small" style={{ textAlign: m.mio ? 'right' : 'left', marginTop: 3, fontSize: 11 }}>
              {CANAL_LABEL[m.canal] || m.canal}
            </div>
          </div>
        ))}
        <div ref={finRef} />
      </div>

      <footer style={{
        borderTop: '1px solid var(--line)', padding: '10px 12px 16px',
        position: 'sticky', bottom: 0, background: '#fff',
      }}>
        <div style={{ display: 'flex', gap: 5, marginBottom: 8, flexWrap: 'wrap' }}>
          {canales.map(c => (
            <button key={c} className={`btn btn-sm ${canal === c ? 'btn-primary' : ''}`} onClick={() => setCanal(c)}>
              {CANAL_LABEL[c]}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <textarea
            rows={2} value={texto} onChange={e => setTexto(e.target.value)}
            aria-label="Escribí tu mensaje" style={{ flex: 1 }}
          />
          <button
            className="btn" disabled={pensando || enviando}
            title="Que la IA escriba como este cliente"
            onClick={async () => {
              setPensando(true)
              try { await api.clienteSimula(token); await api.cliente(token).then(setD) }
              finally { setPensando(false) }
            }}
          >{pensando ? '…' : 'IA'}</button>
          <button
            className="btn btn-primary" disabled={enviando || !texto.trim()}
            onClick={async () => {
              setEnviando(true)
              await api.clienteEnvia(token, { texto, canal })
              setTexto(''); setEnviando(false)
              api.cliente(token).then(setD)
            }}
          >{enviando ? '…' : 'Enviar'}</button>
        </div>
      </footer>
    </div>
  )
}
