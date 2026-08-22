import React, { useEffect, useState } from 'react'
import { api, sesion } from '../api.js'

/* Pantalla mínima hasta que llegue el diseño de Mars.
   Si todavía no hay ninguna cuenta, ofrece crear la primera en vez de pedir
   una que no existe: es el primer arranque de la app, no un olvido de contraseña. */

export default function Login({ onEntro }) {
  const [primera, setPrimera] = useState(null)
  const [email, setEmail] = useState('')
  const [nombre, setNombre] = useState('')
  const [pass, setPass] = useState('')
  const [error, setError] = useState('')
  const [yendo, setYendo] = useState(false)

  useEffect(() => { api.authEstado().then(e => setPrimera(!e.hay_usuarios)).catch(() => setPrimera(false)) }, [])

  if (primera === null) return null

  const enviar = async (e) => {
    e.preventDefault()
    setError(''); setYendo(true)
    try {
      const r = primera
        ? await api.registro({ email, password: pass, nombre })
        : await api.login({ email, password: pass })
      sesion.guardar(r.token)
      onEntro(r.usuario)
    } catch (err) {
      setError(err.message); setYendo(false)
    }
  }

  return (
    <div style={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <form className="card" onSubmit={enviar} style={{ width: '100%', maxWidth: 400, padding: '30px 32px' }}>
        <span className="t-sec" style={{ color: 'var(--accent)', display: 'block' }}>Hilo</span>
        <h1 className="t-title" style={{ marginTop: 18 }}>
          {primera ? 'Creá tu cuenta' : 'Entrá a tu cuenta'}
        </h1>
        <p className="t-small" style={{ marginTop: 6, marginBottom: 22 }}>
          {primera
            ? 'Es la primera vez que se abre esta instalación. La cuenta que crees es la dueña.'
            : 'Con el mail y la contraseña con los que la creaste.'}
        </p>

        {primera && (
          <label style={{ display: 'block', marginBottom: 14 }}>
            <span className="label" style={{ display: 'block', marginBottom: 6 }}>Tu nombre</span>
            <input type="text" value={nombre} onChange={e => setNombre(e.target.value)}
              placeholder="Axel" aria-label="Tu nombre" />
          </label>
        )}
        <label style={{ display: 'block', marginBottom: 14 }}>
          <span className="label" style={{ display: 'block', marginBottom: 6 }}>Mail</span>
          <input type="text" value={email} onChange={e => setEmail(e.target.value)}
            autoComplete="username" aria-label="Mail" placeholder="vos@tunegocio.com" />
        </label>
        <label style={{ display: 'block', marginBottom: 4 }}>
          <span className="label" style={{ display: 'block', marginBottom: 6 }}>Contraseña</span>
          <input type="password" value={pass} onChange={e => setPass(e.target.value)}
            autoComplete={primera ? 'new-password' : 'current-password'} aria-label="Contraseña"
            style={{
              fontFamily: 'var(--font-sans)', fontSize: '14.5px', color: 'var(--ink)',
              background: 'var(--surface)', border: '1px solid var(--line)',
              borderRadius: 'var(--r-md)', padding: '10px 12px', width: '100%',
            }} />
        </label>
        {primera && <p className="t-small" style={{ marginTop: 7 }}>Al menos 8 caracteres, con letras y números.</p>}

        {error && (
          <p className="t-body" style={{ color: 'var(--st-yours)', marginTop: 14 }}>{error}</p>
        )}

        <button className="btn btn--primary btn--lg" type="submit" disabled={yendo || !email.trim() || !pass}
          style={{ width: '100%', marginTop: 22 }}>
          {yendo ? 'Un segundo…' : primera ? 'Crear la cuenta y entrar' : 'Entrar'}
        </button>
      </form>
    </div>
  )
}
