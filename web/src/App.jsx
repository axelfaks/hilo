import React, { useEffect, useState } from 'react'
import { api, cuandoCaigaLaSesion, cuandoSeCorte, sesion, verComo } from './api.js'
import Cola from './views/Cola.jsx'
import Ficha from './views/Ficha.jsx'
import Admin from './views/Admin.jsx'
import Cliente from './views/Cliente.jsx'
import Onboarding from './views/Onboarding.jsx'
import Marca from './Marca.jsx'
import Landing from './views/Landing.jsx'
import Login from './views/Login.jsx'
import Root from './views/Root.jsx'
import Plan from './views/Plan.jsx'
import Canales from './views/Canales.jsx'
import Tarjeta from './views/Tarjeta.jsx'

/** Ruteo por hash: sin dependencias y funciona igual al abrirlo desde el celular.
 *  #/            cola
 *  #/a/3         ficha del cliente 3
 *  #/admin       panel del administrador
 *  #/c/laespiga  vista del cliente (la que se usa en la demo en vivo)
 *  #/root        el back-office NUESTRO: todas las cuentas (solo es_root)
 *  #/canales     conectar Telegram, WhatsApp, mail…
 *  #/plan        el plan del cliente: acá pone la tarjeta
 *  #/tarjeta     el checkout simulado (solo sin credenciales de Mercado Pago)
 */
function useRuta() {
  const [hash, setHash] = useState(window.location.hash || '#/')
  useEffect(() => {
    const on = () => setHash(window.location.hash || '#/')
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  // El `?` se corta antes de partir la ruta: `#/tarjeta?s=SIM-3` es la ruta
  // "tarjeta" con un parámetro, no una ruta que se llama "tarjeta?s=SIM-3".
  return hash.replace(/^#/, '').split('?')[0].split('/').filter(Boolean)
}

export const ir = (ruta) => { window.location.hash = ruta }

export default function App() {
  const partes = useRuta()
  const [negocio, setNegocio] = useState(null)
  const [entrada, setEntrada] = useState(null)   // {protegida, adentro}
  const [yo, setYo] = useState(null)             // el usuario: de acá sale es_root
  const [cortada, setCortada] = useState(false) // 402: se acabó la prueba o el pago

  const cargar = () => api.negocio().then(setNegocio).catch(() => setNegocio({ onboarding_hecho: true }))

  const revisarPuerta = async () => {
    try {
      const e = await api.authEstado()
      if (!e.protegida) {
        // Sin dueño la API está abierta entera, back-office incluido: el backend
        // hace lo mismo. Esconder el botón acá sería teatro, no seguridad.
        setYo({ es_root: true, email: '' })
        setEntrada({ protegida: false, adentro: true, sinCuenta: !e.hay_usuarios })
        return true
      }
      if (!sesion.token()) { setEntrada({ protegida: true, adentro: false }); return false }
      setYo(await api.yo())
      setEntrada({ protegida: true, adentro: true })
      return true
    } catch {
      setEntrada({ protegida: true, adentro: false })
      return false
    }
  }

  useEffect(() => {
    cuandoCaigaLaSesion(() => setEntrada({ protegida: true, adentro: false }))
    /* El 402 no es un error que se muestra: es una pantalla a la que hay que ir.
       Lo que sigue andando es todo lo demás —la sesión, el marco, el plan—, así
       que no se desloguea a nadie. */
    cuandoSeCorte(() => setCortada(true))
    revisarPuerta().then(ok => { if (ok) cargar() })
  }, [])

  // la vista del cliente no pasa por la puerta: es de otra persona
  if (partes[0] === 'c') return <Cliente token={partes[1]} />
  if (!entrada) return null
  const volver = () => revisarPuerta().then(ok => { if (ok) { cargar(); ir('/') } })
  // #/entrar y #/crear siempre muestran la pantalla de cuenta, esté protegida
  // o no. La diferencia es con cuál de las dos caras abre.
  if (partes[0] === 'entrar') return <Login onEntro={volver} />
  if (partes[0] === 'crear') return <Login onEntro={volver} quiereCrear />

  /* El onboarding es el embudo de alta y se hace SIN cuenta: primero contás qué
     vendés y ves tu Hilo armado, después ponés una contraseña. */
  if (partes[0] === 'onboarding' && !entrada.adentro) {
    return <Onboarding onListo={() => ir('/crear')} />
  }

  // Sin sesión, la puerta de calle es la landing y no el formulario: pedirle la
  // contraseña a alguien que todavía no sabe qué es esto no lleva a ningún lado.
  if (!entrada.adentro) return <Landing />

  /* Y también es la puerta de calle cuando la instalación TODAVÍA NO TIENE
     DUEÑO. Sin esto, el que abre Hilo por primera vez caía directo en el
     onboarding sin haber visto nunca de qué se trata: la landing quedaba
     escrita pero nadie la veía jamás. Las demás rutas siguen abiertas, así que
     nadie queda afuera de su propia instalación. */
  if (entrada.sinCuenta && partes.length === 0) return <Landing />
  if (!negocio) return null

  const marcoPago = (hijo, ancho) => (
    <Marco sinCuenta={entrada.sinCuenta} yo={yo} ancho={ancho} negocio={negocio}>{hijo}</Marco>
  )

  /* El pago va ANTES que el onboarding y que todo lo demás. A alguien a quien se
     le terminó la prueba no tiene sentido mostrarle una pantalla que le pide que
     configure algo: lo único que puede hacer es poner una tarjeta. */
  if (partes[0] === 'tarjeta') {
    // El checkout simulado va sin marco: es una pantalla de pago, no la app.
    return <Tarjeta sid={new URLSearchParams(window.location.hash.split('?')[1] || '').get('s')} />
  }
  if (partes[0] === 'plan') return marcoPago(<Plan />)
  if (cortada) return marcoPago(<Plan bloqueada />)

  const pendiente = negocio.onboarding_hecho === false
  if (pendiente || partes[0] === 'onboarding') {
    return <Onboarding onListo={(destino) => {
      cargar()
      /* Recién acá se pide la cuenta: primero contás qué vendés y ves tu Hilo
         armado, después ponés una contraseña. Al revés se pierde a la gente
         antes de haberle mostrado nada. Si ya hay dueño, va derecho a la cola. */
      ir(destino || (entrada.sinCuenta ? '/crear' : '/'))
    }} />
  }

  const marco = (hijo, ancho) => (
    <Marco sinCuenta={entrada.sinCuenta} yo={yo} ancho={ancho} negocio={negocio}>{hijo}</Marco>
  )

  /* El back-office. La comprobación de verdad está en el backend (`es_root` en
     la puerta): esto solo evita mostrar una pantalla que va a devolver 403. */
  if (partes[0] === 'root') {
    return marco(yo?.es_root ? <Root /> : (
      <p className="t-body">Esta pantalla es del equipo de Hilo.</p>
    ), true)
  }
  if (partes[0] === 'canales') return marco(<Canales />)
  if (partes[0] === 'admin') return marco(<Admin />)
  if (partes[0] === 'a') return marco(<Ficha id={Number(partes[1])} />)
  return marco(<Cola />)
}

/* Cerrar sesión.

   El token vive en localStorage, así que salir es borrarlo. Lo que no alcanza es
   borrarlo y nada más: el estado de React sigue creyendo que hay sesión y la
   pantalla no cambia. Por eso además se vuelve a la raíz y se recarga — así el
   siguiente arranque es idéntico al de alguien que nunca entró, que es
   justamente lo que uno quiere ver cuando prueba la landing. */
export function salir() {
  sesion.borrar()
  verComo.salir()          // si estabas mirando la cuenta de un cliente, se suelta
  window.location.hash = '/'
  window.location.reload()
}


function Marco({ children, sinCuenta, yo, ancho, negocio }) {
  return (
    <>
      <Suplantando />
      <Barra yo={yo} />
      {sinCuenta && <AvisoSinCuenta />}
      <AvisoDePago pago={negocio?.pago} />
      <AvisoDeCuota plan={negocio?.plan} />
      <div className={'wrap-page' + (ancho ? ' wrap-page--ancho' : '')}>
        <SiSeRompe>{children}</SiSeRompe>
      </div>
    </>
  )
}

/* Una excepción adentro de una pantalla desmonta TODO el árbol de React y deja
   la ventana en blanco. En blanco de verdad: sin texto, sin error, sin nada que
   te diga dónde mirar. Pasó una vez con el back-office y un backend sin
   reiniciar, y en una demo en vivo eso es el final de la demo.

   Esto lo convierte en un cartel que se puede leer. React solo deja hacerlo con
   una clase: `componentDidCatch` no existe en los hooks. */
class SiSeRompe extends React.Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  componentDidCatch(error) { console.error('[hilo] se rompió la pantalla:', error) }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="card pad" style={{ borderColor: 'var(--red-line)', background: 'var(--red-soft)' }}>
        <span className="lbl" style={{ color: 'var(--red)' }}>Se rompió esta pantalla</span>
        <p className="t-body" style={{ marginTop: 8, color: 'var(--ink)' }}>
          {String(this.state.error?.message || this.state.error)}
        </p>
        <p className="t-small" style={{ marginTop: 10 }}>
          Lo más probable: el backend quedó viejo. Frená <code>python run.py</code> y
          volvé a levantarlo — Python no recarga solo, aunque el front sí. El resto de
          la app sigue andando.
        </p>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn btn-sm" onClick={() => window.location.reload()}>Reintentar</button>
          <button className="btn btn-sm" onClick={() => { window.location.hash = '/'; window.location.reload() }}>
            Volver a la cola
          </button>
        </div>
      </div>
    )
  }
}

/** Los días que le quedan, cuando quedan pocos.

    Aparece solo cuando hay algo que hacer: los últimos días de la prueba, o un
    cobro que no entró. El resto del tiempo no dice nada — una barra que avisa
    todos los días es una barra que nadie lee. */
function AvisoDePago({ pago }) {
  if (!pago) return null
  const p = pago
  const mostrar = (p.estado === 'prueba' && p.dias <= 3)
    || p.estado === 'en_gracia'
    || (p.estado === 'vence_pronto' && !p.pago_automatico && p.dias <= 3)
  if (!mostrar) return null

  const urgente = p.estado === 'en_gracia'
  const texto = p.estado === 'en_gracia'
    ? `No pudimos cobrarte. Te ${p.corta_en === 1 ? 'queda' : 'quedan'} ${p.corta_en} `
      + `${p.corta_en === 1 ? 'día' : 'días'} para actualizar la tarjeta.`
    : p.dias === 0 ? 'Hoy es el último día de tu prueba.'
      : `Te ${p.dias === 1 ? 'queda' : 'quedan'} ${p.dias} ${p.dias === 1 ? 'día' : 'días'} de prueba.`

  return (
    <div style={{
      background: urgente ? 'var(--st-yours-soft)' : 'var(--st-cooling-soft)',
      borderBottom: `1px solid ${urgente ? '#F0D2CB' : 'var(--amber-line)'}`,
    }}>
      <div className="bar-in" style={{ height: 'auto', padding: '12px var(--sp-7)' }}>
        <span className="label" style={{ color: urgente ? 'var(--st-yours)' : 'var(--st-cooling)' }}>
          {urgente ? 'La tarjeta' : 'Tu prueba'}
        </span>
        <span className="t-small" style={{ color: 'var(--ink-2)' }}>
          {texto} Tus clientes y tus hilos quedan como están.
        </span>
        <div className="grow" style={{ flex: 1 }} />
        <button className="btn btn--primary btn-sm" onClick={() => ir('/plan')}>
          {urgente ? 'Actualizar la tarjeta' : 'Poner una tarjeta'}
        </button>
      </div>
    </div>
  )
}

/** Se pasó de lo que incluye su plan.

    Avisa y nada más. No hay un botón que apague nada, ni un contador en rojo que
    corra: cortarle el producto a alguien que lo está usando de más es la peor
    manera de empezar una conversación sobre plata. El tono también es ese —no
    hizo nada mal, le quedó chico el plan. */
function AvisoDeCuota({ plan }) {
  if (!plan?.pasado?.length) return null
  return (
    <div style={{ background: 'var(--st-cooling-soft)', borderBottom: '1px solid var(--amber-line)' }}>
      <div className="bar-in" style={{ height: 'auto', padding: '12px var(--sp-7)' }}>
        <span className="label" style={{ color: 'var(--st-cooling)' }}>
          Se te quedó chico el plan {plan.nombre}
        </span>
        <span className="t-small" style={{ color: 'var(--ink-2)' }}>
          {plan.pasado.join(' · ')}. Sigue andando todo igual: cuando quieras lo charlamos.
        </span>
      </div>
    </div>
  )
}

/** La barra negra de "estás adentro de la cuenta de otro".

    Fea a propósito y arriba de todo: lo único peor que no poder ver la cuenta de
    un cliente es creer que estás en la tuya y no estarlo. Todo lo que se toque
    acá —una respuesta, un estado, una nota— queda en la cuenta del cliente. */
function Suplantando() {
  const mirando = verComo.actual()
  if (!mirando) return null
  return (
    <div className="root-suplantando">
      <div className="bar-in">
        <span className="label" style={{ color: '#fff' }}>Ver como</span>
        <span className="t-small" style={{ color: '#fff' }}>
          Estás viendo <b>{mirando.nombre}</b> como si fueras ellos. Lo que hagas queda en su cuenta.
        </span>
        <div className="grow" style={{ flex: 1 }} />
        <button className="btn btn-sm" onClick={() => {
          verComo.salir()
          window.location.hash = '/root'
          window.location.reload()
        }}>Volver a lo mío</button>
      </div>
    </div>
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

function Barra({ yo }) {
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
        <button className="logo" onClick={() => ir('/')} aria-label="Ir a la cola">
          <Marca alto={22} />
        </button>
        <span className="crumb">Clientes</span>
        <div className="bar-right">
          {c && <>
            <span className="tag"><b>{c.te_esperan}</b> te esperan</span>
            <span className="tag"><b>{c.enfriandose}</b> enfriándose</span>
            <span className="tag"><b>{c.sin_identificar}</b> sin identificar</span>
            {c.etapas_por_aprobar > 0 && <span className="tag"><b>{c.etapas_por_aprobar}</b> etapas por aprobar</span>}
          </>}
          {yo?.es_root && (
            <button className="btn btn-sm" onClick={() => ir('/root')}
              title="Todas las cuentas de Hilo">Back-office</button>
          )}
          <button className="btn btn-sm" onClick={() => ir('/canales')}>Canales</button>
          <button className="btn btn-sm" onClick={() => ir('/plan')}>Tu plan</button>
          <button className="btn btn-sm" onClick={() => ir('/admin')}>Configuración</button>
          <button className="btn btn-sm" onClick={salir}
            title="Cerrar sesión y volver a la portada">Salir</button>
        </div>
      </div>
    </div>
  )
}
