import React, { useEffect, useRef } from 'react'
import '../landing.css'
import Marca from '../Marca.jsx'
import { ir } from '../App.jsx'

/* ---------------------------------------------------------------------------
   LA LANDING — diseño de Mars.

   Es la puerta de calle: lo que ve alguien que todavía no tiene cuenta. Antes
   la app te tiraba directo al formulario de login, que es pedirle la contraseña
   a quien todavía no sabe qué es esto.

   Todo el markup y las animaciones son de Mars. Lo que cambié:
   · el logo genérico por la marca de Hilo, que ya existe como componente;
   · los "Entrar" apuntan al login de verdad en vez de a "#";
   · su CSS quedó encapsulado bajo .lp (ver landing.css y por qué).

   La animación de los canales cayendo al blob manipula el DOM a mano, así que
   vive en un useEffect con su limpieza: si no se sacan los listeners al salir,
   siguen corriendo sobre nodos que ya no están.
--------------------------------------------------------------------------- */

const CANALES = ['Mail', 'WhatsApp', 'Instagram', 'Telegram', 'LinkedIn', 'Teléfono']

const FUNCIONES = [
  ['M5 5c6 0 4 14 10 14', 'Un hilo por cliente',
   'Todo lo que te escribió por mail, WhatsApp o Instagram, en orden, en una sola pantalla.',
   '<circle cx="5" cy="5" r="2"/><circle cx="15" cy="19" r="2"/>'],
  ['M4 20h16 M14.5 4.5l5 5L9 20H4v-5z', 'Borradores listos',
   'El agente redacta la respuesta con el tono de tu negocio. Vos apretás enviar.', ''],
  ['M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6 M10.5 19a2 2 0 0 0 3 0', 'Nadie sin respuesta',
   'Hilo marca quién te debe respuesta y a quién le debés vos, sin que tengas que acordarte.', ''],
  ['M9 4h6l-1 6 4 3v2H6v-2l4-3z M12 15v5', 'Compromisos a la vista',
   'Extrae lo que prometiste y lo que te prometieron, de los dos lados del hilo.', ''],
  ['M5 20V5 M5 6h10l-2 3 2 3H5', 'Tus etapas de venta',
   'Propone en qué etapa está cada cliente, con las etapas de tu negocio y no las de un CRM.', ''],
  ['M8.5 12h7', 'Frena cuando corresponde',
   'Los temas que marcaste como delicados te los pasa a vos antes de contestar.',
   '<circle cx="12" cy="12" r="8.5"/>'],
]

const PASOS = [
  ['PASO 01', 'Conectás tus canales',
   'Mail, WhatsApp, Instagram, Telegram o LinkedIn. Marcás los que usás y ponés tu dirección en cada uno.'],
  ['PASO 02', 'Contás qué vendés',
   'Dos o tres oraciones sobre tu negocio. Con eso Hilo propone tus etapas, tu tono y tus reglas. Vos corregís lo que no te cierra.'],
  ['PASO 03', 'Todo cae en un hilo',
   'Cada cliente pasa a ser uno solo, escriba por donde escriba. El agente redacta y vos decidís cuánto lo dejás hacer.'],
]

const PRIVACIDAD = [
  ['left', '🔒', 'Tus conversaciones con clientes ', 'no entrenan', ' modelos públicos.'],
  ['right', '🛡️', 'Cada mensaje viaja ', 'cifrado', ' y directo al canal del que salió.'],
  ['left', '💳', 'Hilo cobra una suscripción mensual, ', 'no vende', ' tus datos.'],
]

/* Los recuadritos que flotan detrás del hero. Iban en índice; van en el teal
   de la marca, que es de lo que se trata la página. */
const BURBUJAS = [
  { depth: 26, pos: { left: '6%', top: '14%' }, w: 120, h: 86, fondo: '#E4EFEC', p: ['#7FBFB1', '#3E9E8B', '#0E6B5C'] },
  { depth: -18, pos: { right: '7%', top: '22%' }, w: 96, h: 70, fondo: '#DFEDE9', p: ['#8CC7BA', '#4EA795', '#0E6B5C'] },
  { depth: 20, pos: { left: '11%', bottom: '12%' }, w: 104, h: 76, fondo: '#E7F1EE', p: ['#95CCC0', '#59AC9B', '#0E6B5C'] },
  { depth: -24, pos: { right: '10%', bottom: '8%' }, w: 132, h: 94, fondo: '#E2EFEB', p: ['#86C3B6', '#45A18E', '#0E6B5C'] },
]

export default function Landing() {
  const raiz = useRef(null)

  useEffect(() => {
    const cont = raiz.current
    if (!cont) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const q = (s) => cont.querySelector(s)
    const qa = (s) => Array.prototype.slice.call(cont.querySelectorAll(s))

    const nav = q('.nav')
    const navState = () => nav && nav.classList.toggle('is-stuck', window.scrollY > 8)
    navState()

    const S = 'fill="none" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"'
    const CH = [
      { x: -400, y: -150, t: -14, c: '#EA4335', g: '<rect x="3" y="6" width="18" height="12" rx="2.4"/><path d="m3.8 7.4 8.2 5.6 8.2-5.6"/>' },
      { x: 380, y: -190, t: 15, c: '#25D366', g: '<path d="M12 3.2a8.8 8.8 0 0 0-7.6 13.2L3.3 20.7l4.4-1.1A8.8 8.8 0 1 0 12 3.2Z"/><path d="M9.2 9.1c.4 1.9 2 3.6 3.9 4.1"/>' },
      { x: -310, y: 130, t: -10, c: '#E1306C', g: '<rect x="3.2" y="3.2" width="17.6" height="17.6" rx="5"/><circle cx="12" cy="12" r="3.6"/><circle cx="16.9" cy="7.1" r=".9" fill="#E1306C"/>' },
      { x: 330, y: 155, t: 12, c: '#229ED9', g: '<path d="m21 4.2-9.4 15.6-2.1-6.4L3.2 11 21 4.2Z"/><path d="M21 4.2 9.5 13.4"/>' },
      { x: -95, y: -300, t: 8, c: '#0A66C2', g: '<rect x="3.2" y="3.2" width="17.6" height="17.6" rx="4"/><path d="M7.6 10.6v6.2M7.6 7.6v.1M11.7 16.8v-6.2M11.7 13.1c0-1.4 1-2.5 2.4-2.5s2.3 1 2.3 2.5v3.7"/>' },
      { x: 125, y: 290, t: -9, c: '#6B7280', g: '<path d="M6.1 3.4h2.8l1.9 4.7-2.1 1.3a11.6 11.6 0 0 0 5.7 5.7l1.3-2.1 4.7 1.9v2.8a1.9 1.9 0 0 1-2.1 1.9A16.4 16.4 0 0 1 4.2 5.5a1.9 1.9 0 0 1 1.9-2.1Z"/>' },
    ]
    const BASE = 900, STAGGER = 0.11, SPAN = 0.40, HOP = 150, TILE = 168
    const stage = q('.stage'), blob = q('.blob')
    const tiles = []
    if (stage) {
      CH.forEach((ch) => {
        const el = document.createElement('div')
        el.className = 'tile'
        el.innerHTML = '<svg viewBox="0 0 24 24" stroke="' + ch.c + '" ' + S + '>' + ch.g + '</svg>'
        stage.appendChild(el)
        tiles.push(el)
      })
    }

    let k = 1, tam = TILE
    const medir = () => {
      if (!stage || !blob) return
      const w = stage.getBoundingClientRect().width || BASE
      k = Math.max(0.32, Math.min(1, w / BASE))
      tam = Math.round(TILE * Math.max(0.34, k))
      const b = Math.round(260 * (0.5 + 0.5 * k))
      blob.style.width = b + 'px'; blob.style.height = b + 'px'
      tiles.forEach((el) => {
        el.style.width = tam + 'px'; el.style.height = tam + 'px'
        el.style.borderRadius = (tam * 0.26) + 'px'
        const s = el.firstChild
        s.setAttribute('width', Math.round(tam * 0.5))
        s.setAttribute('height', Math.round(tam * 0.5))
      })
    }
    const c01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v)
    const avance = () => {
      if (!stage) return 1
      const r = stage.getBoundingClientRect(), vh = window.innerHeight || 800
      const ini = vh * 0.92, fin = vh * 0.32, total = r.height + ini - fin
      return total <= 0 ? 1 : c01((ini - r.top) / total)
    }
    const props = qa('.prop')
    const pintar = () => {
      const P = avance()
      for (let i = 0; i < CH.length; i++) {
        const ch = CH[i], el = tiles[i]
        if (!el) continue
        const p = c01((P - i * STAGGER) / SPAN)
        const e = 1 - Math.pow(1 - p, 2.2)
        const x = (ch.x * k) * (1 - e)
        const y = (ch.y * k) * (1 - e) - (HOP * k) * Math.sin(Math.pow(p, 0.9) * Math.PI)
        let sc
        if (p <= 0) sc = 0.55
        else if (p < 0.10) sc = 0.55 + (p / 0.10) * 0.45
        else if (p > 0.84) sc = Math.max(0.10, 1 - ((p - 0.84) / 0.16) * 0.90)
        else sc = 1
        let sy = 1
        if (p > 0.78 && p < 0.90) sy = 1 - Math.sin(((p - 0.78) / 0.12) * Math.PI) * 0.18
        let op
        if (p <= 0) op = 0
        else if (p < 0.09) op = p / 0.09
        else if (p > 0.90) op = Math.max(0, 1 - (p - 0.90) / 0.10)
        else op = 1
        const rot = ch.t * (1 - p) + Math.sin(p * Math.PI * 2) * 7
        el.style.opacity = op
        el.style.transform = 'translate(' + x.toFixed(1) + 'px,' + y.toFixed(1) + 'px) rotate(' +
          rot.toFixed(2) + 'deg) scale(' + sc.toFixed(3) + ',' + (sc * sy).toFixed(3) + ')'
      }
      if (blob) {
        let bs = 1
        for (let j = 0; j < CH.length; j++) {
          const d = Math.abs(P - (j * STAGGER + SPAN * 0.86))
          if (d < 0.035) bs += (1 - d / 0.035) * 0.14
        }
        blob.style.transform = 'scale(' + bs.toFixed(3) + ')'
      }
      const sy2 = window.scrollY
      props.forEach((el) => {
        const d = parseFloat(el.getAttribute('data-depth')) || 0
        el.style.transform = 'translateY(' + (sy2 * d / 100).toFixed(1) + 'px)'
      })
    }
    const quieto = () => tiles.forEach((el, i) => {
      el.style.opacity = 1
      el.style.transform = 'translate(' + (CH[i].x * k) + 'px,' + (CH[i].y * k) + 'px) rotate(' + CH[i].t + 'deg)'
    })

    // las palabras que se descifran solas
    const POOL = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#$%&/*+-<>'
    const relojes = []
    const descifrar = (el) => {
      const texto = el.getAttribute('data-word') || el.textContent
      if (reduce) { el.textContent = texto; return }
      let f = 0
      const total = texto.length * 3 + 10
      const id = window.setInterval(() => {
        f++
        const visto = Math.floor((f / total) * texto.length)
        if (f >= total) { window.clearInterval(id); el.textContent = texto; return }
        let out = ''
        for (let i = 0; i < texto.length; i++) {
          const c = texto.charAt(i)
          out += (i < visto || c === ' ') ? c : POOL.charAt(Math.floor(Math.random() * POOL.length))
        }
        el.textContent = out
      }, 45)
      relojes.push(id)
    }

    const filas = qa('.row')
    let io = null
    if ('IntersectionObserver' in window) {
      io = new IntersectionObserver((entradas) => {
        entradas.forEach((e) => {
          if (!e.isIntersecting) return
          e.target.classList.add('in')
          const w = e.target.querySelector('.scr')
          if (w && !w.dataset.done) { w.dataset.done = '1'; descifrar(w) }
          io.unobserve(e.target)
        })
      }, { threshold: 0.55 })
      filas.forEach((r) => io.observe(r))
    } else {
      filas.forEach((r) => r.classList.add('in'))
    }

    let esperando = false
    const alScrollear = () => {
      navState()
      if (reduce || esperando) return
      esperando = true
      window.requestAnimationFrame(() => { pintar(); esperando = false })
    }
    const alRedimensionar = () => { medir(); reduce ? quieto() : pintar() }

    medir()
    reduce ? quieto() : pintar()
    window.addEventListener('scroll', alScrollear, { passive: true })
    window.addEventListener('resize', alRedimensionar)

    return () => {
      window.removeEventListener('scroll', alScrollear)
      window.removeEventListener('resize', alRedimensionar)
      relojes.forEach(window.clearInterval)
      if (io) io.disconnect()
      tiles.forEach((el) => el.remove())
    }
  }, [])

  const entrar = (e) => { e.preventDefault(); ir('/entrar') }
  /* Crear una cuenta empieza por el onboarding, no por un formulario de
     registro: lo primero que hace Hilo es preguntarte qué vendés, y recién
     después te pide una contraseña. Pedir credenciales antes de mostrar nada
     es la forma más rápida de perder a alguien que todavía no sabe qué es esto. */
  const crear = (e) => { e.preventDefault(); ir('/onboarding') }
  const irA = (id) => (e) => {
    e.preventDefault()
    const t = raiz.current?.querySelector(id)
    if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="lp" ref={raiz}>
      <nav className="nav">
        <div className="nav-in">
          <a className="brand" href="#top" onClick={irA('#top')}><Marca alto={24} /></a>
          <div className="nav-links">
            <a href="#canales" onClick={irA('#canales')}>Canales</a>
            <a href="#funciones" onClick={irA('#funciones')}>Funciones</a>
            <a href="#pasos" onClick={irA('#pasos')}>Cómo funciona</a>
            <a className="btn" href="#entrar" onClick={entrar}>Entrar →</a>
          </div>
        </div>
      </nav>

      <header className="hero" id="top">
        {BURBUJAS.map((b, i) => (
          <div className="prop" data-depth={b.depth} style={{ position: 'absolute', ...b.pos }} key={i}>
            <svg width={b.w} height={b.h} viewBox="0 0 120 86" fill="none">
              <rect x="4" y="4" width="112" height="70" rx="18" fill={b.fondo} />
              <circle cx="40" cy="39" r="8" fill={b.p[0]} />
              <circle cx="62" cy="39" r="8" fill={b.p[1]} />
              <circle cx="84" cy="39" r="8" fill={b.p[2]} />
            </svg>
          </div>
        ))}
        <div className="wrap hero-stack">
          <p className="eyebrow">Para negocios que venden conversando</p>
          <h1>Todos tus <span className="accent">clientes</span><br />en una sola bandeja</h1>
          <p className="lead">
            Mail, WhatsApp, Instagram, Telegram y LinkedIn caen en un mismo hilo por cliente.
            Con una IA que resume, redacta y te avisa a quién le debés respuesta.
          </p>
          <Acciones crear={crear} entrar={entrar} id="entrar" />
        </div>
      </header>

      <section className="section" id="canales">
        <div className="wrap">
          <div className="section-head">
            <h2>Todo en uno.</h2>
            <p className="lead">Hilo recibe y contesta por todos los canales por los que te escriben tus clientes.</p>
          </div>
          <div className="stage" aria-hidden="true"><div className="blob" /></div>
          <div className="chips">{CANALES.map(c => <span className="chip" key={c}>{c}</span>)}</div>
        </div>
      </section>

      <section className="section">
        <div className="wrap">
          <div className="section-head">
            <h2>Tu información es tuya.</h2>
            <p className="lead">Las conversaciones con tus clientes son lo más sensible que tiene tu negocio. Las tratamos así.</p>
          </div>
          <div className="spine">
            {PRIVACIDAD.map(([lado, emoji, antes, palabra, despues], i) => (
              <div className={`row ${lado}`} key={i}>
                {lado === 'right' && <div className="half" />}
                {lado === 'left' && (
                  <div className="half"><p className="copy">{antes}<span className="scr" data-word={palabra}>{palabra}</span>{despues}</p></div>
                )}
                <div className="badge">{emoji}</div>
                {lado === 'right' && (
                  <div className="half"><p className="copy">{antes}<span className="scr" data-word={palabra}>{palabra}</span>{despues}</p></div>
                )}
                {lado === 'left' && <div className="half" />}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section" id="funciones">
        <div className="wrap">
          <div className="section-head">
            <h2>Funciones</h2>
            <p className="lead">Lo que hace Hilo mientras vos atendés el negocio.</p>
          </div>
          <div className="grid">
            {FUNCIONES.map(([d, titulo, bajada, extra]) => (
              <div className="feat" key={titulo}>
                <span className="ic">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
                    dangerouslySetInnerHTML={{ __html: `<path d="${d}"/>${extra}` }} />
                </span>
                <h3>{titulo}</h3>
                <p>{bajada}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section" id="pasos">
        <div className="wrap">
          <div className="section-head">
            <h2>Cómo funciona</h2>
            <p className="lead">Tres pasos y ya tenés el hilo entero de cada cliente.</p>
          </div>
          <div className="steps">
            {PASOS.map(([n, titulo, bajada]) => (
              <div className="step" key={n}>
                <span className="n">{n}</span>
                <h3>{titulo}</h3>
                <p>{bajada}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section cta">
        <div className="wrap section-head">
          <h2>Poné tus conversaciones en orden.</h2>
          <p className="lead">Conectá tus canales en dos minutos y empezá a ver cada cliente en un solo hilo.</p>
          <Acciones crear={crear} entrar={entrar} />
        </div>
      </section>

      <footer>
        <div className="foot">
          <a className="brand" href="#top" onClick={irA('#top')}><Marca alto={18} /></a>
          <nav>
            <a href="#funciones" onClick={irA('#funciones')}>Funciones</a>
            <a href="#pasos" onClick={irA('#pasos')}>Cómo funciona</a>
            <a href="#entrar" onClick={entrar}>Entrar</a>
          </nav>
        </div>
      </footer>
    </div>
  )
}


/* Los botones de acción, iguales en el hero y en el cierre. */
function Acciones({ crear, entrar, id }) {
  return (
    <div className="actions" id={id}>
      <a className="btn btn-lg" href="#onboarding" onClick={crear}>Crear una cuenta →</a>
      <a className="btn-quiet" href="#entrar" onClick={entrar}>Ya tengo cuenta, entrar →</a>
    </div>
  )
}
