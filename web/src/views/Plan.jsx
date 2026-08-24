import React, { useEffect, useState } from 'react'

import { api } from '../api.js'
import { ir } from '../App.jsx'

/* La pantalla donde el cliente pone la tarjeta.

   Es la única pantalla de la app que le habla de plata, y por eso tiene una sola
   regla: **decir siempre en qué situación está y qué pasa después**. Nadie pone
   una tarjeta en un lugar donde no entiende qué le van a cobrar ni cuándo.

   Aparece de tres maneras:
     · desde el botón «Tu plan», cuando la quiere mirar;
     · sola, en modo bloqueo, cuando se le terminó la prueba o no entró el cobro;
     · desde el aviso de la barra, cuando le quedan pocos días.

   La tarjeta se la queda Mercado Pago. Nosotros guardamos el id de la suscripción
   y cuatro dígitos para que reconozca cuál puso, y nada más. */

const pesos = (n) => '$ ' + (n || 0).toLocaleString('es-AR')

const fecha = (iso) => iso
  ? new Date(iso).toLocaleDateString('es-AR', { day: 'numeric', month: 'long' })
  : ''

/* Cada situación con su título, su explicación y su color. El texto es lo que
   uno le diría en persona, no el nombre del estado. */
function comoEsta(p, dias_de_prueba) {
  const d = p.dias
  switch (p.estado) {
    case 'prueba':
      return {
        tono: d <= 2 ? 'urgente' : 'calmo',
        titulo: d === 0 ? 'Hoy es el último día de tu prueba'
          : `Te ${d === 1 ? 'queda' : 'quedan'} ${d} ${d === 1 ? 'día' : 'días'} de prueba`,
        detalle: `Probás Hilo ${dias_de_prueba} días sin poner nada. Cuando se termine, `
          + 'con una tarjeta seguís donde lo dejaste: tus clientes, tus canales y tus hilos quedan como están.',
      }
    case 'al_dia':
      return {
        tono: 'ok',
        titulo: `Tu plan está al día`,
        detalle: `El próximo cobro es el ${fecha(p.pagado_hasta)}.`
          + (p.pago_automatico ? ' Se cobra solo con tu tarjeta.' : ' Todavía no hay tarjeta: lo estamos cobrando a mano.'),
      }
    case 'vence_pronto':
      return {
        tono: 'calmo',
        titulo: `Se renueva en ${p.dias} ${p.dias === 1 ? 'día' : 'días'}`,
        detalle: p.pago_automatico
          ? `El ${fecha(p.pagado_hasta)} se cobra solo. No tenés que hacer nada.`
          : `Vence el ${fecha(p.pagado_hasta)}. Poné una tarjeta y se renueva sola.`,
      }
    case 'en_gracia':
      return {
        tono: 'urgente',
        titulo: 'No pudimos cobrarte',
        detalle: `Venció el ${fecha(p.pagado_hasta)}. Te ${p.corta_en === 1 ? 'queda' : 'quedan'} `
          + `${p.corta_en} ${p.corta_en === 1 ? 'día' : 'días'} para actualizar la tarjeta. `
          + 'Después la cuenta se pausa — no se borra nada.',
      }
    case 'cortada':
      return {
        tono: 'cortada',
        titulo: p.por_que === 'se acabó la prueba' ? 'Se terminó tu prueba' : 'La cuenta está pausada',
        detalle: p.por_que === 'se acabó la prueba'
          ? 'Tus clientes, tus canales y tus hilos están intactos. Poné una tarjeta y seguís donde lo dejaste.'
          : 'No pudimos cobrarte. Actualizá la tarjeta y vuelve todo tal cual estaba, en el momento.',
      }
    default:
      return { tono: 'calmo', titulo: 'Tu plan', detalle: '' }
  }
}

export default function Plan({ bloqueada }) {
  const [d, setD] = useState(null)
  const [yendo, setYendo] = useState('')
  const [error, setError] = useState('')

  const cargar = () => api.plan().then(setD).catch(e => setError(e.message))
  useEffect(() => { cargar() }, [])

  if (error) return <p className="t-body" style={{ color: 'var(--st-yours)' }}>{error}</p>
  if (!d) return <p className="t-body"><span className="spin" /> Un segundo…</p>

  const p = d.pago
  const est = comoEsta(p, d.dias_de_prueba)
  /* "Es el tuyo" solo si de verdad lo está pagando. Marcar como propio el plan
     que alguien eligió pero nunca pagó es el peor momento para confundirse: se
     ve como si ya estuviera resuelto y el botón importante pierde peso. */
  const pagando = ['al_dia', 'vence_pronto', 'en_gracia'].includes(p.estado)

  const elegir = async (clave) => {
    setYendo(clave); setError('')
    try {
      const r = await api.suscribir(clave)
      /* Dos destinos posibles y se distinguen solos: si empieza con `#`, es una
         pantalla de esta misma app (el checkout simulado) y se navega por hash,
         sin salir del origen donde el usuario tiene su sesión. Si es una URL
         entera, es el checkout de Mercado Pago y se va para allá. */
      if (r.ir_a.startsWith('#')) {
        window.location.hash = r.ir_a.slice(1)
      } else {
        window.location.href = r.ir_a
      }
    } catch (e) {
      setError(e.message); setYendo('')
    }
  }

  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }}>
      <div className={'plan-estado plan-estado--' + est.tono}>
        <h1 className="t-title">{est.titulo}</h1>
        <p className="t-body" style={{ marginTop: 8, color: 'var(--ink-2)' }}>{est.detalle}</p>
        {p.tarjeta && (
          <p className="t-small" style={{ marginTop: 10 }}>
            Tarjeta guardada: <b>{p.tarjeta}</b>
            {p.suscripcion === 'activa' && ' · débito automático activo'}
          </p>
        )}
      </div>

      {bloqueada && (
        <p className="t-small" style={{ margin: '14px 0', textAlign: 'center' }}>
          Mientras tanto no podés entrar a tus hilos, pero <b>no se borró nada</b>.
        </p>
      )}

      <h2 className="t-heading" style={{ marginTop: 28 }}>
        {p.estado === 'al_dia' || p.estado === 'vence_pronto' ? 'Cambiar de plan' : 'Elegí un plan'}
      </h2>
      <div className="planes">
        {d.planes.filter(x => x.clave !== 'prueba').map(x => (
          <div key={x.clave} className={'plan-caja' + (pagando && p.plan === x.clave ? ' es-tuyo' : '')}>
            <span className="label">{x.nombre}</span>
            <span className="plan-precio">{pesos(p.plan === x.clave && p.precio ? p.precio : x.precio)}</span>
            <span className="t-small">por mes</span>
            <p className="t-small" style={{ margin: '10px 0 14px' }}>{x.para}</p>
            <ul className="plan-limites">
              <li>Hasta <b>{x.limites.clientes.toLocaleString('es-AR')}</b> clientes</li>
              <li><b>{x.limites.mensajes_mes.toLocaleString('es-AR')}</b> mensajes por mes</li>
              <li><b>{x.limites.ia_mes.toLocaleString('es-AR')}</b> respuestas con IA</li>
            </ul>
            <button className={'btn btn--block'
                    + (pagando && p.plan === x.clave ? '' : ' btn--primary')}
                    disabled={!!yendo || (p.pago_automatico && p.plan === x.clave)}
                    onClick={() => elegir(x.clave)}>
              {yendo === x.clave ? 'Abriendo…'
                : p.pago_automatico && p.plan === x.clave ? 'Es el tuyo'
                : p.pago_automatico ? 'Cambiarme a este'
                : 'Poner tarjeta'}
            </button>
          </div>
        ))}
      </div>

      {error && <p className="t-small" style={{ color: 'var(--st-yours)', marginTop: 12 }}>{error}</p>}

      <p className="t-small" style={{ marginTop: 16 }}>
        La tarjeta la guarda <b>Mercado Pago</b>, no nosotros: el pago se hace en su
        checkout y de la tarjeta solo vemos los últimos cuatro números.
        {d.mercadopago.simulado && <b style={{ color: 'var(--st-cooling)' }}>
          {' '}Ahora mismo esto está en modo simulado: no se cobra nada de verdad.
        </b>}
        {d.mercadopago.de_prueba && <b style={{ color: 'var(--st-cooling)' }}>
          {' '}Mercado Pago está con credenciales de prueba.
        </b>}
      </p>

      <section className="card pad" style={{ marginTop: 24 }}>
        <span className="lbl">Cuánto llevás usado este mes</span>
        <div style={{ marginTop: 12 }}>
          {[['Clientes', d.cuota.uso.clientes, d.cuota.limites.clientes],
            ['Mensajes', d.cuota.uso.mensajes_mes, d.cuota.limites.mensajes_mes],
            ['Respuestas con IA', d.cuota.uso.ia_mes, d.cuota.limites.ia_mes],
          ].map(([nombre, valor, tope]) => (
            <div className="root-cuota" key={nombre}>
              <span>{nombre}</span>
              <div className="root-cuota-riel">
                <i className={valor > tope ? 'se-paso' : ''}
                   style={{ width: `${Math.min(100, Math.round((valor / tope) * 100))}%` }} />
              </div>
              <b className={valor > tope ? 'se-paso' : ''}>
                {valor.toLocaleString('es-AR')}<small>/{tope.toLocaleString('es-AR')}</small>
              </b>
            </div>
          ))}
        </div>
        {d.cuota.pasado.length > 0 && (
          <p className="t-small" style={{ marginTop: 10, color: 'var(--st-cooling)' }}>
            {d.cuota.pasado.join(' · ')}. <b>No te cortamos nada por esto</b>: cuando quieras
            pasamos al plan que sigue.
          </p>
        )}
      </section>

      {d.cobros.length > 0 && (
        <section className="card pad" style={{ marginTop: 16 }}>
          <span className="lbl">Tus pagos</span>
          <div style={{ marginTop: 10 }}>
            {d.cobros.map(x => (
              <div className="root-linea" key={x.id}>
                <span className="grow"><b>{pesos(x.monto)}</b> <small>· {x.medio}</small></span>
                <small>
                  {new Date(x.cuando).toLocaleDateString('es-AR')}
                  {x.periodo_hasta && ` · hasta el ${fecha(x.periodo_hasta)}`}
                </small>
              </div>
            ))}
          </div>
        </section>
      )}

      {p.pago_automatico && (
        <div className="row" style={{ marginTop: 20, justifyContent: 'space-between' }}>
          <span className="t-small">
            Cancelar el débito automático no te saca nada: seguís hasta el {fecha(p.pagado_hasta)}.
          </span>
          <button className="btn btn-sm" onClick={async () => {
            await api.cancelarPlan(); cargar()
          }}>Cancelar la suscripción</button>
        </div>
      )}

      {!bloqueada && (
        <div className="row" style={{ marginTop: 24 }}>
          <button className="btn btn-sm" onClick={() => ir('/')}>Volver a mis clientes</button>
        </div>
      )}
    </div>
  )
}
