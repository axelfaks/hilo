import React, { useEffect, useState } from 'react'
import { api, cuandoCaigaLaSesion, sesion } from './api.js'
import Cola from './views/Cola.jsx'
import Ficha from './views/Ficha.jsx'
import Admin from './views/Admin.jsx'
import Cliente from './views/Cliente.jsx'
import Onboarding from './views/Onboarding.jsx'
import Login from './views/Login.jsx'

/** Ruteo por hash: sin dependencias y funciona igual al abrirlo desde el celular.
 *  #/            cola
 *  #/a/3         ficha del cliente 3
 *  #/admin       panel del administrador
 *  #/c/laespiga  vista del cliente (la que se usa en la demo en vivo)
 */
function useRuta() {
  const [hash, setHash] = useState(window.location.hash || '#/')
  useEffect(() => {
    const on = () => setHash(window.location.hash || '#/')
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return hash.replace(/^#/, '').split('/').filter(Boolean)
}

export const ir = (ruta) => { window.location.hash = ruta }

export default function App() {
  const partes = useRuta()
  const [negocio, setNegocio] = useState(null)
  const [entrada, setEntrada] = useState(null)   // {protegida, adentro}

  const cargar = () => api.negocio().then(setNegocio).catch(() => setNegocio({ onboarding_hecho: true }))

  const revisarPuerta = async () => {
    try {
      const e = await api.authEstado()
      if (!e.protegida) { setEntrada({ protegida: false, adentro: true, sinCuenta: !e.hay_usuarios }); return true }
      if (!sesion.token()) { setEntrada({ protegida: true, adentro: false }); return false }
      await api.yo()
      setEntrada({ protegida: true, adentro: true })
      return true
    } catch {
      setEntrada({ protegida: true, adentro: false })
      return false
    }
  }

  useEffect(() => {
    cuandoCaigaLaSesion(() => setEntrada({ protegida: true, adentro: false }))
    revisarPuerta().then(ok => { if (ok) cargar() })
  }, [])

  // la vista del cliente no pasa por la puerta: es de otra persona
  if (partes[0] === 'c') return <Cliente token={partes[1]} />
  if (!entrada) return null
  const volver = () => revisarPuerta().then(ok => { if (ok) { cargar(); ir('/') } })
  // #/entrar siempre muestra la pantalla de cuenta, esté protegida o no
  if (!entrada.adentro || partes[0] === 'entrar') return <Login onEntro={volver} />
  if (!negocio) return null

  const pendiente = negocio.onboarding_hecho === false
  if (pendiente || partes[0] === 'onboarding') {
    return <Onboarding onListo={() => { cargar(); ir('/') }} />
  }

  const marco = (hijo) => <Marco sinCuenta={entrada.sinCuenta}>{hijo}</Marco>
  if (partes[0] === 'admin') return marco(<Admin />)
  if (partes[0] === 'a') return marco(<Ficha id={Number(partes[1])} />)
  return marco(<Cola />)
}

function Marco({ children, sinCuenta }) {
  return (
    <>
      <Barra />
      {sinCuenta && <AvisoSinCuenta />}
      <div className="wrap-page">{children}</div>
    </>
  )
}

/** Mientras no exista ninguna cuenta, la API está abierta a cualquiera que tenga
 *  el link. Si la app está publicada, eso hay que resolverlo ya. */
function AvisoSinCuenta() {
  const publica = typeof window !== 'undefined' && !['localhost', '127.0.0.1'].includes(window.location.hostname)
  return (
    <div style={{
      background: publica ? 'var(--st-yours-soft)' : 'var(--st-cooling-soft)',
      borderBottom: `1px solid ${publica ? '#F0D2CB' : 'var(--st-cooling)'}`,
    }}>
      <div className="bar-in" style={{ height: 'auto', padding: '12px var(--sp-7)' }}>
        <span className="label" style={{ color: publica ? 'var(--st-yours)' : 'var(--st-cooling)' }}>
          {publica ? 'Tu app está abierta en internet' : 'Todavía no tenés cuenta'}
        </span>
        <span className="t-small" style={{ color: 'var(--ink-2)' }}>
          Cualquiera con este link puede entrar y ver tus clientes. Se cierra sola en cuanto crees tu cuenta.
        </span>
        <div className="grow" />
        <button className="btn btn--primary btn-sm" onClick={() => ir('/entrar')}>Crear mi cuenta</button>
      </div>
    </div>
  )
}

function Barra() {
  const [c, setC] = useState(null)
  useEffect(() => {
    let vivo = true
    const tick = () => api.cola().then(d => vivo && setC(d.contadores)).catch(() => {})
    tick()
    const t = setInterval(tick, 5000)
    return () => { vivo = false; clearInterval(t) }
  }, [])
  return (
    <div className="bar">
      <div className="bar-in">
        <button className="logo" onClick={() => ir('/')}>Hilo</button>
        <span className="crumb">Clientes</span>
        <div className="bar-right">
          {c && <>
            <span className="tag"><b>{c.te_esperan}</b> te esperan</span>
            <span className="tag"><b>{c.enfriandose}</b> enfriándose</span>
            <span className="tag"><b>{c.sin_identificar}</b> sin identificar</span>
            {c.etapas_por_aprobar > 0 && <span className="tag"><b>{c.etapas_por_aprobar}</b> etapas por aprobar</span>}
          </>}
          <button className="btn btn-sm" onClick={() => ir('/admin')}>Configuración</button>
        </div>
      </div>
    </div>
  )
}
