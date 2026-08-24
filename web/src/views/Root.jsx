import React, { useEffect, useState } from 'react'

import { api, verComo } from '../api.js'

/* El back-office: todas las cuentas de Hilo en una pantalla.
 *
 * No es el panel del cliente ni la configuración de su negocio: es el tercero,
 * el nuestro. Contesta cuatro preguntas y ninguna más:
 *
 *   ¿a quién se le cayó un canal?   ← la causa número uno de soporte
 *   ¿cuánta IA gasta cada cuenta?   ← nuestro único costo variable
 *   ¿quién está vivo y quién no?
 *   ¿puedo ver lo que ve el cliente sin pedirle una captura?
 *
 * Todo lo demás —gráficos, cohortes, filtros de veinte campos— es tiempo que
 * rinde diez veces más en la pantalla de conectar canales, que es donde se cae
 * la gente. Por eso esto es una tabla densa y nada más.
 */

const CANAL = {
  mail: 'Mail', whatsapp: 'WhatsApp', instagram: 'Instagram', telegram: 'Telegram',
  linkedin: 'LinkedIn', llamada: 'Llamada', presencial: 'Visita',
}

const SALUD = {
  ok: 'anda', error: 'error', quieto: 'quieto',
  'sin-trafico': 'sin tráfico', apagado: 'apagado',
}

const num = (n) => (n || 0).toLocaleString('es-AR')
const pesos = (n) => '$ ' + (n || 0).toLocaleString('es-AR')

/* Cómo se ve cada estado de pago. El texto es el que uno diría en voz alta
   cuando pregunta "¿este pagó?", no el nombre del campo. */
const PAGO = {
  prueba:      { clase: 'quieto',  texto: 'prueba' },
  al_dia:      { clase: 'ok',      texto: 'al día' },
  vence_pronto:{ clase: 'quieto',  texto: 'vence' },
  en_gracia:   { clase: 'error',   texto: 'no cobró' },
  cortada:     { clase: 'error',   texto: 'cortada' },
  sin_precio:  { clase: 'apagado', texto: 'sin precio' },
}

/** "vence en 5 días" / "vencido hace 3" / "" — el detalle abajo del chip. */
function detallePago(p) {
  if (p.estado === 'sin_precio') return 'a mano'
  if (p.dias === null) return ''
  if (p.estado === 'cortada') return `cortada hace ${Math.abs(p.dias)} d`
  if (p.estado === 'en_gracia') return `corta en ${p.corta_en} d`
  if (p.dias === 0) return 'hoy'
  return `en ${p.dias} d`
}

const debe = (c) => ['cortada', 'en_gracia'].includes(c.pago?.estado)

/** 1.240.000 tokens no se leen. 1,2 M sí. */
function corto(n) {
  if (!n) return '0'
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace('.', ',') + ' M'
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace('.', ',') + ' k'
  return String(n)
}

function cuando(iso, vacio = '—') {
  if (!iso) return vacio
  const ms = Date.now() - new Date(iso).getTime()
  const min = ms / 60000
  if (min < 1) return 'recién'
  if (min < 60) return `hace ${Math.round(min)} min`
  const h = min / 60
  if (h < 24) return `hace ${Math.round(h)} h`
  const d = Math.round(h / 24)
  return d === 1 ? 'ayer' : `hace ${d} días`
}

/* En una tabla densa la fecha va corta: "14/08/26". El mes escrito ocupa tres
   veces más y acá no se lee ninguna fecha en voz alta. */
function dia(iso, vacio = '—') {
  if (!iso) return vacio
  return new Date(iso).toLocaleDateString('es-AR', {
    day: '2-digit', month: '2-digit', year: '2-digit',
  })
}

/** Una cuenta necesita atención si algo se le rompió o si nunca arrancó. */
const necesitaAtencion = (c) =>
  c.canales_caidos > 0 || c.fallas_24h > 0 || (c.usuarios.length > 0 && !c.onboarding_hecho)

const SIN_PAGO = { estado: 'prueba', precio: 0, dias: null, pagado_hasta: '', paga_desde: '' }
const SIN_CUOTA = { limites: { clientes: 0, mensajes_mes: 0, ia_mes: 0 },
                    uso: { clientes: 0, mensajes_mes: 0, ia_mes: 0 }, pasado: [] }

/** La fila, con todo lo que la pantalla espera aunque el backend no lo mande. */
const completa = (c) => ({ ...c, pago: c.pago || SIN_PAGO, cuota: c.cuota || SIN_CUOTA,
                           ia: c.ia || { llamadas: 0, tokens: 0, fallos: 0 },
                           usuarios: c.usuarios || [], canales: c.canales || [] })

export default function Root() {
  const [d, setD] = useState(null)
  const [error, setError] = useState('')
  const [busca, setBusca] = useState('')
  const [soloRotas, setSoloRotas] = useState(false)
  const [soloDeben, setSoloDeben] = useState(false)
  const [abierta, setAbierta] = useState(null)

  const cargar = () => api.rootResumen().then(r => { setD(r); setError('') })
    .catch(e => setError(e.message))

  useEffect(() => {
    cargar()
    const t = setInterval(cargar, 15000)
    return () => clearInterval(t)
  }, [])

  if (error) return <p className="t-body" style={{ color: 'var(--st-yours)' }}>{error}</p>
  if (!d) return <p className="t-body"><span className="spin" /> Cargando todas las cuentas…</p>

  /* Los `|| {}` no son paranoia: si el backend quedó viejo —o sea, si alguien
     actualizó el código y no reinició `python run.py`— el resumen llega sin los
     campos nuevos, `d.plata.mrr` explota y React desmonta TODO. El resultado es
     una pantalla en blanco que no dice nada y manda a buscar el problema al
     lugar equivocado. Con esto, la pantalla se dibuja igual y el aviso de abajo
     explica qué pasa. */
  const t = d.totales || {}
  const plata = d.plata || {}
  const desactualizado = !d.plata
  const cuentas = (d.cuentas || []).map(completa)
    .filter(c => !soloRotas || necesitaAtencion(c))
    .filter(c => !soloDeben || debe(c))
    .filter(c => !busca || (c.nombre + ' ' + c.usuarios.map(u => u.email).join(' '))
      .toLowerCase().includes(busca.toLowerCase()))
    // primero lo que arde, después lo más activo
    .sort((a, b) => (necesitaAtencion(b) - necesitaAtencion(a)) || (b.mensajes_7d - a.mensajes_7d))

  const editar = async (id, cambio) => {
    await api.rootEditar(id, cambio)
    cargar()
  }

  const mirarComo = async (c) => {
    await api.rootVerComo(c.id)
    verComo.poner({ id: c.id, nombre: c.nombre })
    window.location.hash = '/'
    window.location.reload()   // el estado de React ya cargó datos de otra cuenta
  }

  return (
    <>
      <div className="root-top">
        <div>
          <h1 className="t-display">Back-office</h1>
          <p className="t-body" style={{ marginTop: 4 }}>
            Todas las cuentas de Hilo. Esta pantalla la vemos solo nosotros.
          </p>
        </div>
        <div style={{ textAlign: 'right' }}>
          <span className="root-vivo"><i />se actualiza sola cada 15 s</span>
          <Plataforma p={d.plataforma || {}} />
        </div>
      </div>

      <div className="kpis" style={{ gridTemplateColumns: 'repeat(5,1fr)' }}>
        <Kpi n={t.cuentas} q="cuentas"
             d={<>{t.con_dueño} con dueño{t.huerfanas ? `, ${t.huerfanas} sin terminar el alta` : ''}</>} />
        <Kpi n={t.clientes} q="clientes de ellos" d={<>{num(t.mensajes)} mensajes en total</>} />
        <Kpi n={t.mensajes_7d} q="mensajes · 7 días" d={<>lo que de verdad se usó</>} />
        <Kpi n={corto(t.ia?.llamadas || 0)} q="llamadas IA · 30 días"
             d={<>{corto(t.ia?.tokens || 0)} tokens{t.ia?.modelo ? ` · ${t.ia.modelo}` : ''}</>} />
        <Kpi n={t.canales_caidos} q="canales caídos" alerta={t.canales_caidos > 0}
             d={<>en {t.cuentas_con_canal_caido} cuenta{t.cuentas_con_canal_caido === 1 ? '' : 's'}</>} />
      </div>

      {desactualizado && (
        <div className="root-alerta" style={{ marginBottom: 4 }}>
          <b>El backend quedó viejo.</b>
          <span className="t-small" style={{ color: 'var(--ink-2)' }}>
            Esta pantalla pide datos que el server que está corriendo todavía no tiene.
            Frená <code>python run.py</code> y volvé a levantarlo: Python no recarga
            solo, aunque el front sí.
          </span>
        </div>
      )}

      {/* La plata va junta y arriba: son cuatro números que se leen de un saque
          y contestan «¿de qué vivimos y a quién hay que escribirle hoy?». */}
      <div className="root-plata">
        <div className="root-plata-n">
          <span className="lbl">por mes (MRR)</span>
          <b>{pesos(plata.mrr)}</b>
          <small>de las cuentas al día</small>
        </div>
        <div className="root-plata-n">
          <span className="lbl">cobrado este mes</span>
          <b>{pesos(plata.cobrado_mes)}</b>
          <small>lo que entró de verdad</small>
        </div>
        <div className={'root-plata-n' + (plata.vencido ? ' es-rojo' : '')}>
          <span className="lbl">por cobrar</span>
          <b>{pesos(plata.vencido)}</b>
          <small>
            {plata.cuentas_vencidas || 0} sin cobrar
            {plata.cortadas ? ` · ${plata.cortadas} ya cortada(s)` : ''}
          </small>
        </div>
        <div className="root-plata-n">
          <span className="lbl">vence esta semana</span>
          <b>{pesos(plata.por_vencer)}</b>
          <small>{plata.cuentas_por_vencer || 0} cuenta(s) — escribiles ahora</small>
        </div>
        <div className="root-plata-n">
          <span className="lbl">en prueba</span>
          <b>{num(plata.en_prueba || 0)}</b>
          <small>{plata.con_tarjeta || 0} cuenta(s) con tarjeta puesta</small>
        </div>
        {(d.vencen || []).length > 0 && (
          <div className="root-plata-lista">
            <span className="lbl">a quién escribirle</span>
            {(d.vencen || []).slice(0, 4).map(v => (
              <button key={v.id} className="link" onClick={() => setAbierta(v.id)}>
                {v.nombre} <small>{detallePago(v)}</small>
              </button>
            ))}
          </div>
        )}
      </div>

      {(t.canales_caidos > 0 || t.fallas_24h > 0)
        ? <div className="root-alerta">
            <b>Hay que mirar esto.</b>
            <span className="t-small" style={{ color: 'var(--ink-2)' }}>
              {t.canales_caidos > 0 && <>{t.canales_caidos} canal(es) con error · </>}
              {t.fallas_24h > 0 && <>{t.fallas_24h} falla(s) en las últimas 24 h · </>}
              «No me llegan los mensajes» casi siempre es esto, y el cliente se entera antes que vos.
            </span>
          </div>
        : <div className="root-alerta root-alerta--calma">
            <b>Todo en pie.</b>
            <span className="t-small" style={{ color: 'var(--ink-2)' }}>
              Ningún canal con error y ninguna falla en 24 h.
            </span>
          </div>}

      <div className="table-head" style={{ marginTop: 20 }}>
        <input className="search" placeholder="Buscar por nombre o mail…"
               value={busca} onChange={e => setBusca(e.target.value)} />
        <button className={'btn btn-sm' + (soloRotas ? ' btn--primary' : '')}
                onClick={() => setSoloRotas(!soloRotas)}>
          Solo las que necesitan atención
        </button>
        <button className={'btn btn-sm' + (soloDeben ? ' btn--primary' : '')}
                onClick={() => setSoloDeben(!soloDeben)}>
          Solo las que deben
        </button>
        <span className="th-count"><b>{cuentas.length}</b> de {d.cuentas.length}</span>
      </div>

      <div className="root-scroll">
        <table className="root-tabla">
          <thead>
            <tr>
              <th>Cuenta</th>
              <th>Plan</th>
              <th>Pago</th>
              <th>Último acceso</th>
              <th className="num">Clientes</th>
              <th className="num">Mensajes</th>
              <th className="num">7 días</th>
              <th>Canales</th>
              <th className="num">IA 30 d</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {cuentas.map(c => (
              <React.Fragment key={c.id}>
                <tr className={'root-fila'
                      + (abierta === c.id ? ' is-abierta' : '')
                      + (c.estado === 'suspendida' ? ' is-suspendida' : '')}
                    onClick={() => setAbierta(abierta === c.id ? null : c.id)}>
                  <td>
                    <span className="root-nombre">{c.nombre || 'Sin nombre'}</span>
                    <span className="root-sub">
                      {c.usuarios.length
                        ? c.usuarios.map(u => u.email).join(' · ')
                        : 'nadie terminó el alta'}
                      {!c.onboarding_hecho && c.usuarios.length ? ' · onboarding sin terminar' : ''}
                      {c.cuota.pasado.length > 0 && (
                        <b style={{ color: 'var(--st-cooling)' }}> · pasada de cuota</b>
                      )}
                    </span>
                  </td>
                  <td>
                    <span className={'root-plan'
                          + (c.estado === 'suspendida' ? ' root-plan--suspendida'
                             : c.plan === 'pro' ? ' root-plan--pro' : '')}>
                      {c.estado === 'suspendida' ? 'suspendida' : c.plan}
                    </span>
                    <span className="root-sub">
                      {c.pago.precio ? pesos(c.pago.precio) + '/mes' : 'sin precio'}
                    </span>
                  </td>
                  <td>
                    <span className={'sal sal--' + (PAGO[c.pago.estado] || PAGO.prueba).clase}>
                      {(PAGO[c.pago.estado] || PAGO.prueba).texto}
                    </span>
                    <span className="root-sub">{detallePago(c.pago)}</span>
                  </td>
                  <td className="t-small">{cuando(c.ultimo_acceso, 'nunca')}</td>
                  <td className="num">{num(c.clientes)}</td>
                  <td className="num">{num(c.mensajes)}</td>
                  <td className="num"><b>{num(c.mensajes_7d)}</b></td>
                  <td>
                    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                      {c.canales.length === 0 && <span className="sal">sin canales</span>}
                      {c.canales.map(ch => (
                        <span key={ch.canal} className={'sal sal--' + ch.salud}
                              title={ch.ultimo_error || `último mensaje ${cuando(ch.ultimo_entrante || ch.ultimo_saliente)}`}>
                          {CANAL[ch.canal] || ch.canal}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="num">
                    {num(c.ia.llamadas)}
                    <span className="root-sub">{corto(c.ia.tokens)} tok</span>
                  </td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <button className="btn btn-sm"
                            onClick={e => { e.stopPropagation(); mirarComo(c) }}>Ver como</button>
                  </td>
                </tr>
                {abierta === c.id && (
                  <tr>
                    <td colSpan={10} style={{ padding: 0 }}>
                      <Detalle cuenta={c} onEditar={editar} onCambio={cargar} />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {cuentas.length === 0 && (
        <p className="t-body" style={{ marginTop: 16 }}>
          Ninguna cuenta con ese filtro.
        </p>
      )}
    </>
  )
}

/* La caja de plata de una cuenta: en qué anda, registrar un cobro y el libro.

   Registrar un cobro es UN formulario de tres campos y ningún paso más. Es a
   propósito: mientras esto se haga a mano, cada campo de más es una excusa para
   no anotarlo, y un cobro sin anotar es plata que no se sabe si entró. */
function Plata({ cuenta, cobros, onCobrado }) {
  const p = cuenta.pago
  const [monto, setMonto] = useState(p.precio || 0)
  const [medio, setMedio] = useState('transferencia')
  const [meses, setMeses] = useState(1)
  const [nota, setNota] = useState('')
  const [yendo, setYendo] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { setMonto((cuenta.pago.precio || 0) * meses) }, [cuenta.pago.precio, meses])

  const cobrar = async () => {
    setYendo(true); setError('')
    try {
      await api.rootCobrar(cuenta.id, { monto: Number(monto), medio, meses: Number(meses), nota })
      setNota('')
      onCobrado()
    } catch (e) { setError(e.message) }
    setYendo(false)
  }

  const lim = cuenta.cuota.limites
  const usoCuota = cuenta.cuota.uso
  const barras = [
    ['Clientes', usoCuota.clientes, lim.clientes],
    ['Mensajes del mes', usoCuota.mensajes_mes, lim.mensajes_mes],
    ['IA del mes', usoCuota.ia_mes, lim.ia_mes],
  ]

  return (
    <div className="root-caja">
      <h4>Plata</h4>
      <div className="root-linea">
        <span className={'sal sal--' + (PAGO[p.estado] || PAGO.prueba).clase}>
          {(PAGO[p.estado] || PAGO.prueba).texto}
        </span>
        <span className="grow">
          {p.pagado_hasta
            ? <>paga hasta <b>{dia(p.pagado_hasta)}</b> · {detallePago(p)}</>
            : p.precio ? 'nunca pagó' : 'todavía no le pusimos precio'}
        </span>
      </div>
      {p.paga_desde && (
        <div className="root-linea">
          <span className="grow">Cliente desde</span><b>{dia(p.paga_desde)}</b>
        </div>
      )}

      <h4 style={{ marginTop: 16 }}>Registrar un cobro</h4>
      <div className="root-acciones">
        <input type="number" value={monto} onChange={e => setMonto(e.target.value)}
               style={{ maxWidth: 110 }} aria-label="Monto" />
        <select value={meses} onChange={e => setMeses(Number(e.target.value))} aria-label="Meses">
          {[1, 2, 3, 6, 12].map(m => <option key={m} value={m}>{m} mes{m > 1 ? 'es' : ''}</option>)}
        </select>
        <select value={medio} onChange={e => setMedio(e.target.value)} aria-label="Medio">
          <option value="transferencia">transferencia</option>
          <option value="mercadopago">Mercado Pago</option>
          <option value="efectivo">efectivo</option>
          <option value="otro">otro</option>
        </select>
      </div>
      <div className="root-acciones">
        <input value={nota} placeholder="Nota (opcional): número de operación…"
               onChange={e => setNota(e.target.value)} />
        <button className="btn btn-sm btn--primary" disabled={yendo} onClick={cobrar}>
          {yendo ? 'Anotando…' : 'Cobrado'}
        </button>
      </div>
      {error && <p className="t-small" style={{ color: 'var(--st-yours)', marginTop: 8 }}>{error}</p>}
      <p className="t-small" style={{ marginTop: 8 }}>
        Corre la fecha de vencimiento {meses} mes{meses > 1 ? 'es' : ''} desde
        {p.estado === 'vencido' || !p.pagado_hasta ? ' hoy' : ' el vencimiento actual'}.
        Si estaba suspendida, la reactiva.
      </p>

      <h4 style={{ marginTop: 16 }}>Cuotas del plan</h4>
      {barras.map(([nombre, valor, tope]) => (
        <div className="root-cuota" key={nombre}>
          <span>{nombre}</span>
          <div className="root-cuota-riel">
            <i className={valor > tope ? 'se-paso' : ''}
               style={{ width: `${Math.min(100, Math.round((valor / tope) * 100))}%` }} />
          </div>
          <b className={valor > tope ? 'se-paso' : ''}>{num(valor)}<small>/{num(tope)}</small></b>
        </div>
      ))}
      {cuenta.cuota.pasado.length > 0 && (
        <p className="t-small" style={{ marginTop: 8, color: 'var(--st-cooling)' }}>
          Se pasó del plan. <b>No se le corta nada</b>: es la señal de que está listo
          para el que sigue.
        </p>
      )}

      <h4 style={{ marginTop: 16 }}>Últimos cobros</h4>
      {!cobros && <p className="t-small"><span className="spin" /> buscando…</p>}
      {cobros && !cobros.length && <p className="t-small">Todavía no pagó nunca.</p>}
      {(cobros || []).map(x => (
        <div className="root-linea" key={x.id}>
          <span className="grow">
            <b>{pesos(x.monto)}</b> <small>· {x.medio} · {x.meses} mes(es)</small>
            {x.nota && <small style={{ display: 'block' }}>{x.nota}</small>}
          </span>
          <small>{dia(x.cuando)}</small>
        </div>
      ))}
    </div>
  )
}

/* La línea de la plataforma: lo que es de la instalación entera y no de ninguna
   cuenta. Sirve para saber, en un vistazo, si el problema es de un cliente o es
   nuestro.

   El botón del token está acá porque es el chequeo que hay que hacer ANTES de
   una demo: el token temporal de Meta dura 24 h y cuando vence no avisa —los
   mensajes simplemente dejan de salir. Ya nos pasó una vez. */
function Plataforma({ p }) {
  const [probando, setProbando] = useState(false)
  const [r, setR] = useState(null)

  const ok = r ? r.ok : p.wa_token_ok
  const detalle = r ? r.detalle : p.wa_token_detalle

  return (
    <p className="t-small" style={{ marginTop: 4 }}>
      Plataforma: IA {p.ia?.activa ? p.ia.proveedor : 'apagada'}
      {' · '}correo {p.correo_env ? 'sí' : 'no'}
      {' · '}WhatsApp{' '}
      {!p.whatsapp_env ? 'sin configurar'
        : ok === true ? <b style={{ color: 'var(--accent-strong)' }}>token OK</b>
        : ok === false ? <b style={{ color: 'var(--st-yours)' }}>token caído</b>
        : 'token sin probar'}
      {' '}
      <button className="link" disabled={probando} onClick={async () => {
        setProbando(true)
        try { setR(await api.rootProbarWhatsapp()) } catch (e) { setR({ ok: false, detalle: e.message }) }
        setProbando(false)
      }}>{probando ? 'probando…' : 'probar'}</button>
      {detalle && (
        <span style={{ display: 'block', color: ok ? 'var(--ink-3)' : 'var(--st-yours)' }}>
          {detalle}
        </span>
      )}
    </p>
  )
}

function Kpi({ n, q, d, alerta }) {
  return (
    <div className={'card kpi' + (alerta ? ' k-yours' : '')}>
      <span className="lbl">{q}</span>
      <span className="v">{typeof n === 'number' ? num(n) : n}</span>
      <span className="d">{d}</span>
    </div>
  )
}

/* El detalle de una cuenta. Se pide recién al abrirla: traer las fallas y el
   consumo día por día de TODAS las cuentas en el resumen sería pagar por
   información que casi nunca se mira. */
function Detalle({ cuenta, onEditar, onCambio }) {
  const [d, setD] = useState(null)
  const [nota, setNota] = useState(cuenta.nota || '')
  const [guardada, setGuardada] = useState(false)

  const traer = () => api.rootCuenta(cuenta.id).then(setD).catch(() => setD({ error: true }))
  useEffect(() => { setD(null); traer() }, [cuenta.id])

  /* Después de un cobro hay que refrescar las dos mitades: el historial de esta
     caja y los totales de arriba, que cambiaron. */
  const onCobrado = () => { traer(); onCambio() }

  const tope = Math.max(1, ...((d?.ia_por_dia || []).map(x => x.llamadas)))

  return (
    <div className="root-detalle">
      <div className="root-cols">
        {/* --- canales: el motivo por el que existe esta pantalla --- */}
        <div className="root-caja">
          <h4>Canales</h4>
          {(d?.canales || cuenta.canales).map(ch => (
            <div className="root-linea" key={ch.canal}>
              <span className={'sal sal--' + ch.salud}>{SALUD[ch.salud] || ch.salud}</span>
              <span className="grow">
                <b>{CANAL[ch.canal] || ch.canal}</b>
                {ch.etiqueta ? ` · ${ch.etiqueta}` : ''}
                <small style={{ display: 'block' }}>
                  {ch.propio ? 'credencial propia' : 'anda por la plataforma (.env nuestro)'}
                  {' · entró '}{cuando(ch.ultimo_entrante, 'nunca')}
                  {' · salió '}{cuando(ch.ultimo_saliente, 'nunca')}
                </small>
                {ch.ultimo_error && (
                  <small style={{ display: 'block', color: 'var(--st-yours)' }}>{ch.ultimo_error}</small>
                )}
              </span>
            </div>
          ))}
          {!(d?.canales || cuenta.canales).length && (
            <p className="t-small">Todavía no habló por ningún canal.</p>
          )}

        </div>

        {/* --- lo que nos cuesta --- */}
        <div className="root-caja">
          <h4>Consumo de IA · 14 días</h4>
          <div className="root-barras">
            {(d?.ia_por_dia || []).map(x => (
              <i key={x.dia}
                 className={x.fallos ? 'fallo' : x.llamadas ? 'tiene' : ''}
                 style={{ height: `${Math.round((x.llamadas / tope) * 100)}%` }}
                 title={`${x.dia}: ${x.llamadas} llamadas, ${corto(x.tokens)} tokens${x.fallos ? `, ${x.fallos} fallaron` : ''}`} />
            ))}
          </div>
          <div className="root-pie">
            <span>hace 14 días</span><span>hoy</span>
          </div>
          <div className="root-linea" style={{ marginTop: 12 }}>
            <span className="grow">Llamadas en 30 días</span><b>{num(cuenta.ia.llamadas)}</b>
          </div>
          <div className="root-linea">
            <span className="grow">Tokens</span><b>{corto(cuenta.ia.tokens)}</b>
          </div>
          <div className="root-linea">
            <span className="grow">Que fallaron</span>
            <b style={{ color: cuenta.ia.fallos ? 'var(--st-yours)' : 'inherit' }}>{num(cuenta.ia.fallos)}</b>
          </div>
          {cuenta.ia.modelo && <p className="t-small" style={{ marginTop: 8 }}>Último modelo: {cuenta.ia.modelo}</p>}
        </div>

        {/* --- qué hacemos con la cuenta: el cobro a mano de los primeros clientes --- */}
        <div className="root-caja">
          <h4>La cuenta</h4>
          <div className="root-linea">
            <span className="grow">Alta</span><b>{dia(cuenta.creado)}</b>
          </div>
          <div className="root-linea">
            <span className="grow">Onboarding</span>
            <b>{cuenta.onboarding_hecho ? 'terminado' : 'sin terminar'}</b>
          </div>
          {cuenta.usuarios.map(u => (
            <div className="root-linea" key={u.email}>
              <span className="grow">{u.email} <small>· {u.rol}{u.es_root ? ' · root' : ''}</small></span>
              <small>{cuando(u.ultimo_acceso, 'nunca entró')}</small>
            </div>
          ))}
          {!cuenta.usuarios.length && (
            <p className="t-small" style={{ marginTop: 8 }}>
              Nadie creó cuenta: quedó del onboarding a medias.
            </p>
          )}
          <div className="root-linea">
            <span className="grow">Precio</span>
            <b>{cuenta.pago.precio ? pesos(cuenta.pago.precio) + ' /mes' : '—'}</b>
          </div>
          <div className="root-linea">
            <span className="grow">Tarjeta</span>
            <b>{cuenta.pago.tarjeta || 'sin tarjeta'}</b>
          </div>
          <div className="root-linea">
            <span className="grow">Acceso hasta</span>
            <b>{dia(cuenta.pago.acceso_hasta)}</b>
          </div>
          <div className="root-acciones">
            <select value={cuenta.plan} onChange={e => onEditar(cuenta.id, { plan: e.target.value })}>
              <option value="prueba">prueba</option>
              <option value="basico">básico</option>
              <option value="pro">pro</option>
            </select>
            <button className="btn btn-sm"
                    onClick={() => onEditar(cuenta.id, {
                      estado: cuenta.estado === 'suspendida' ? 'activa' : 'suspendida' })}>
              {cuenta.estado === 'suspendida' ? 'Reactivar' : 'Suspender'}
            </button>
          </div>
          <div className="root-acciones">
            <span className="t-small">Regalarle prueba:</span>
            {[7, 14, 30].map(n => (
              <button key={n} className="btn btn-sm"
                      onClick={() => onEditar(cuenta.id, { prueba_dias: n })}>{n} días</button>
            ))}
          </div>
          <div className="root-acciones">
            <input value={nota} placeholder="Nota interna: qué pasó, qué prometimos…"
                   onChange={e => { setNota(e.target.value); setGuardada(false) }} />
            <button className="btn btn-sm" onClick={async () => {
              await onEditar(cuenta.id, { nota }); setGuardada(true)
            }}>Guardar</button>
            {guardada && <span className="t-small" style={{ color: 'var(--accent)' }}>guardada</span>}
          </div>
          <p className="t-small" style={{ marginTop: 10 }}>
            Suspender no borra nada: le corta la entrada a su gente con un mensaje claro y los
            datos quedan intactos.
          </p>
        </div>
      </div>

      <div className="root-cols root-cols--abajo">
        <Plata cuenta={cuenta} cobros={d?.cobros} onCobrado={onCobrado} />

        <div className="root-caja">
          <h4>Últimas fallas</h4>
          {!d && <p className="t-small"><span className="spin" /> buscando…</p>}
          {d && !d.fallas?.length && <p className="t-small">Ninguna. Buena señal.</p>}
          {d?.fallas?.length > 0 && (
            <div className="root-fallas">
              {d.fallas.map((f, i) => (
                <div key={i}>
                  <time>{dia(f.cuando)} {cuando(f.cuando)}</time> <b>{f.donde}</b><br />{f.detalle}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="root-caja">
          <h4>Lo último que pasó en esa cuenta</h4>
          {!d?.ultimos_mensajes?.length && <p className="t-small">Todavía no pasó nada.</p>}
          {(d?.ultimos_mensajes || []).map((m, i) => (
            <div className="root-linea" key={i}>
              <span className={'sal sal--' + (m.direccion === 'entrante' ? 'ok' : 'apagado')}>
                {CANAL[m.canal] || m.canal}
              </span>
              <span className="grow" style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {m.texto || <i>(sin texto)</i>}
              </span>
              <small style={{ whiteSpace: 'nowrap' }}>{m.autor} · {cuando(m.cuando)}</small>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
