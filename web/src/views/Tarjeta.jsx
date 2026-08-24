import React, { useState } from 'react'

import { api } from '../api.js'

/* El checkout de mentira.

   Existe por una sola razón: poder mostrar el circuito entero —se acaba la
   prueba, pone la tarjeta, la cuenta vuelve— sin credenciales de Mercado Pago.
   Con credenciales de verdad este archivo no se abre nunca: el `init_point` de
   MP apunta a SU checkout, que es donde tiene que ir una tarjeta.

   Por eso está pintado de "simulación" por todos lados. Una pantalla que pide
   una tarjeta y no aclara que es falsa es una pantalla peligrosa, aunque sea
   nuestra y aunque sea por un rato. */

export default function Tarjeta({ sid }) {
  const [yendo, setYendo] = useState(false)
  const [error, setError] = useState('')

  const pagar = async () => {
    setYendo(true); setError('')
    try {
      await api.pagoSimulado(sid)
      window.location.hash = '/plan'
      window.location.reload()
    } catch (e) { setError(e.message); setYendo(false) }
  }

  return (
    <div style={{ maxWidth: 460, margin: '40px auto' }}>
      <div className="ob-note ob-note--ojo" style={{ marginBottom: 18 }}>
        <b>Esto es una simulación.</b> No hay ninguna tarjeta y no se cobra nada.
        Cuando estén las credenciales de Mercado Pago, acá se abre el checkout de
        ellos y esta pantalla no se usa más.
      </div>

      <section className="card pad">
        <span className="lbl">Pagar con tarjeta</span>
        <h2 className="t-heading" style={{ margin: '8px 0 18px' }}>Hilo · plan mensual</h2>

        <label className="ob-label">Número de tarjeta</label>
        <input className="ob-input" defaultValue="4242 4242 4242 4242" readOnly />

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
          <div>
            <label className="ob-label">Vence</label>
            <input className="ob-input" defaultValue="12/30" readOnly />
          </div>
          <div>
            <label className="ob-label">Código</label>
            <input className="ob-input" defaultValue="123" readOnly />
          </div>
        </div>

        <label className="ob-label" style={{ marginTop: 12 }}>Nombre en la tarjeta</label>
        <input className="ob-input" defaultValue="COMO FIGURA EN LA TARJETA" readOnly />

        <button className="btn btn--primary btn--block btn--lg" style={{ marginTop: 20 }}
                disabled={yendo} onClick={pagar}>
          {yendo ? 'Cobrando…' : 'Pagar y activar mi cuenta'}
        </button>
        {error && <p className="t-small" style={{ color: 'var(--st-yours)', marginTop: 10 }}>{error}</p>}

        <p className="t-small" style={{ marginTop: 14 }}>
          Se cobra todos los meses el mismo día. Cancelás cuando quieras desde tu plan.
        </p>
      </section>
    </div>
  )
}
