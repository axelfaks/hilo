import React, { useEffect, useState } from 'react'

import { api } from '../api.js'

/* La pantalla de conectar canales.

   Es donde se cae la gente, así que tiene una sola regla: **en cada momento hay
   exactamente una cosa para hacer, y está a la vista**. Nada de listas de pasos
   numerados que hay que leer enteros antes de empezar.

   El estado de cada canal se dice con una palabra y un color:

     desconectado  · gris   · hay un botón para conectarlo
     conectando    · ámbar  · te estamos esperando del otro lado
     andando       · verde  · con la fecha del último mensaje, que es la prueba
     error         · rojo   · qué pasó y qué hacer
     todavía no    · gris   · por qué no se puede, sin botón que no haga nada

   Y mientras estás conectando, la pantalla pregunta sola cada tres segundos. El
   que está del otro lado con el celular en la mano no tiene que volver acá a
   apretar «actualizar» para ver si funcionó: funciona, y la pantalla se entera. */

const ESTADOS = {
  andando: { clase: 'ok', texto: 'andando' },
  conectando: { clase: 'quieto', texto: 'conectando' },
  error: { clase: 'error', texto: 'con un problema' },
  desconectado: { clase: 'apagado', texto: 'sin conectar' },
}

function cuando(iso) {
  if (!iso) return 'todavía nada'
  const min = (Date.now() - new Date(iso).getTime()) / 60000
  if (min < 1) return 'recién'
  if (min < 60) return `hace ${Math.round(min)} min`
  if (min < 1440) return `hace ${Math.round(min / 60)} h`
  return `hace ${Math.round(min / 1440)} días`
}

function Copiable({ valor, children }) {
  const [copiado, setCopiado] = useState(false)
  return (
    <button className="btn btn-sm" onClick={async () => {
      try {
        await navigator.clipboard.writeText(valor)
        setCopiado(true); setTimeout(() => setCopiado(false), 1600)
      } catch { /* sin permiso de portapapeles: queda el texto a la vista igual */ }
    }}>{copiado ? '¡Copiado!' : (children || 'Copiar')}</button>
  )
}

export default function Canales() {
  const [d, setD] = useState(null)
  const [abierto, setAbierto] = useState('')
  const [yendo, setYendo] = useState(false)
  const [error, setError] = useState('')

  const cargar = () => api.canales().then(setD).catch(e => setError(e.message))
  useEffect(() => { cargar() }, [])

  /* El pulso: solo mientras hay algo esperando del otro lado. Una pantalla que
     pregunta cada tres segundos para siempre es una pantalla que gasta batería
     sin motivo. */
  const esperando = (d?.canales || []).some(c => c.estado === 'conectando')
  useEffect(() => {
    if (!esperando) return
    const t = setInterval(cargar, 3000)
    return () => clearInterval(t)
  }, [esperando])

  if (error) return <p className="t-body" style={{ color: 'var(--st-yours)' }}>{error}</p>
  if (!d) return <p className="t-body"><span className="spin" /> Un segundo…</p>

  const conectarTelegram = async () => {
    setYendo(true); setError('')
    try { await api.vincularTelegram(); setAbierto('telegram'); await cargar() }
    catch (e) { setError(e.message) }
    setYendo(false)
  }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto' }}>
      <h1 className="t-display">Tus canales</h1>
      <p className="t-body" style={{ marginTop: 6 }}>
        Todo lo que conectes cae en la misma bandeja, con un hilo por cliente.
        No hace falta conectar todo: con uno ya funciona.
      </p>

      <div style={{ marginTop: 24 }}>
        {d.canales.map(c => {
          const e = ESTADOS[c.estado] || ESTADOS.desconectado
          const listo = c.estado === 'andando' || c.estado === 'error'
          return (
            <section className={'canal' + (listo ? ' es-listo' : '')} key={c.canal}>
              <div className="canal-top">
                <div style={{ minWidth: 0 }}>
                  <h2 className="canal-nombre">{c.nombre}</h2>
                  <p className="t-small">
                    {listo ? (c.detalle || c.para_que) : c.para_que}
                  </p>
                </div>
                <span className={'sal sal--' + (c.puede_conectarse ? e.clase : 'apagado')}>
                  {c.puede_conectarse ? e.texto : 'todavía no'}
                </span>
              </div>

              {!c.puede_conectarse && (
                <p className="t-small canal-nota">{c.por_que_no}</p>
              )}

              {listo && (
                <div className="canal-vivo">
                  {c.etiqueta && <span className="tag"><b>{c.etiqueta}</b></span>}
                  <span className="t-small">entró {cuando(c.ultimo_entrante)}</span>
                  <span className="t-small">· salió {cuando(c.ultimo_saliente)}</span>
                  {c.canal === 'telegram' && (
                    <button className="link" onClick={() => setAbierto(
                      abierto === 'telegram' ? '' : 'telegram')}>
                      {abierto === 'telegram' ? 'ocultar' : 'cómo lo uso'}
                    </button>
                  )}
                </div>
              )}

              {c.error && <p className="t-small canal-error">{c.error}</p>}

              {/* --- Telegram: el único que se conecta solo, hoy --- */}
              {c.canal === 'telegram' && c.puede_conectarse && (
                <>
                  {c.estado === 'desconectado' && (
                    <button className="btn btn--primary" disabled={yendo}
                            onClick={conectarTelegram}>
                      {yendo ? 'Un segundo…' : 'Conectar Telegram'}
                    </button>
                  )}

                  {c.estado === 'conectando' && c.vinculo?.esperando && (
                    <div className="canal-paso">
                      <span className="label">Te estoy esperando</span>
                      <p className="t-body" style={{ margin: '8px 0 14px' }}>
                        Abrí este link y apretá <b>Iniciar</b>. Con eso queda conectado.
                      </p>
                      <div className="row" style={{ flexWrap: 'wrap', gap: 10 }}>
                        <a className="btn btn--primary btn--lg" href={c.vinculo.link}
                           target="_blank" rel="noreferrer">Abrir Telegram →</a>
                        <Copiable valor={c.vinculo.link}>Copiar el link</Copiable>
                      </div>
                      <p className="t-small" style={{ marginTop: 14 }}>
                        ¿Lo vas a hacer desde el celular? Buscá{' '}
                        <b>{d.bot ? '@' + d.bot : 'el bot de Hilo'}</b> en Telegram
                        y mandale este código:
                      </p>
                      <div className="canal-codigo">{c.vinculo.codigo}</div>
                      <p className="t-small">
                        <span className="spin" /> Vence en {Math.ceil((c.vinculo.vence_en_segundos || 0) / 60)} min.
                        Esta pantalla se entera sola cuando lo hagas.
                      </p>
                    </div>
                  )}

                  {listo && abierto === 'telegram' && (
                    <div className="canal-paso">
                      <span className="label">1 · Pasales este link a tus clientes</span>
                      <p className="t-small" style={{ margin: '6px 0 10px' }}>
                        El que lo abre te escribe y su mensaje entra acá, con su nombre.
                        Sirve en tu bio, en un cartel con QR o pegado en un mail.
                      </p>
                      <div className="row" style={{ flexWrap: 'wrap' }}>
                        <code className="canal-link">{c.link_publico}</code>
                        <Copiable valor={c.link_publico} />
                      </div>

                      <span className="label" style={{ display: 'block', marginTop: 20 }}>
                        2 · Y si tenés Telegram Premium
                      </span>
                      <p className="t-small" style={{ marginTop: 6 }}>
                        En Telegram: <b>Configuración → Telegram Business → Chatbots</b>,
                        poné <b>{d.bot ? '@' + d.bot : 'el bot de Hilo'}</b> y activá que
                        <b> pueda responder</b>.
                        Con eso Hilo ve tus conversaciones de siempre y contesta como vos:
                        el que recibe no nota la diferencia.
                        {c.modo === 'business' && <b style={{ color: 'var(--accent-strong)' }}>
                          {' '}Ya lo tenés activado.
                        </b>}
                      </p>

                      <div className="row" style={{ marginTop: 16 }}>
                        <button className="btn btn-sm" onClick={async () => {
                          await api.desconectarCanal('telegram'); cargar()
                        }}>Desconectar Telegram</button>
                        <span className="t-small">No se borra ningún mensaje.</span>
                      </div>
                    </div>
                  )}
                </>
              )}
            </section>
          )
        })}
      </div>

      <p className="t-small" style={{ marginTop: 22 }}>
        ¿Te falta un canal? Escribinos y lo ponemos en la lista. Lo que más nos piden
        es lo que hacemos primero.
      </p>
    </div>
  )
}
