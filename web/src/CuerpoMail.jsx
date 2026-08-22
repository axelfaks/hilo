import React, { useEffect, useRef, useState } from 'react'

/* ---------------------------------------------------------------------------
   EL CUERPO DE UN MAIL

   Un mail no es texto plano: tiene negritas, listas, links y el logo de la
   firma. Mostrarlo como texto pelado es perder la mitad de la información —
   y encima se veía el `[image: Logo]` crudo, que es ruido puro.

   Por qué un iframe con sandbox:
   este HTML lo escribió un desconocido. Meterlo en la página con
   dangerouslySetInnerHTML es abrirle la puerta a que ejecute lo que quiera.
   El sandbox se lo impide a nivel navegador, sin depender de que yo escriba un
   sanitizador correcto a último momento.

   Va `allow-same-origin` PERO NO `allow-scripts`: sin scripts no corre nada, y
   con mismo origen puedo medir el alto para que el marco crezca con el
   contenido en vez de dejar una barra de scroll adentro. Las dos juntas serían
   un agujero — sin `allow-scripts` no lo es.
--------------------------------------------------------------------------- */

const ESTILO = `
  <style>
    :root{color-scheme:light}
    body{margin:0;font:14.5px/1.6 "Public Sans",-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
         color:#41504B;background:transparent;word-break:break-word}
    img{max-width:100%;height:auto}
    table{max-width:100%}
    a{color:#0E6B5C}
    blockquote{margin:0 0 0 12px;padding-left:12px;border-left:2px solid #E1E7E4;color:#879591}
    pre{white-space:pre-wrap}
  </style>
`

export default function CuerpoMail({ html, texto, max = 260 }) {
  const [abierto, setAbierto] = useState(false)
  const [alto, setAlto] = useState(0)
  const marco = useRef(null)
  const bloque = useRef(null)
  const [largo, setLargo] = useState(false)

  // el alto real del mail, para que el marco crezca con él
  const medir = () => {
    try {
      const d = marco.current?.contentDocument
      if (d) setAlto(Math.min(d.body.scrollHeight + 8, 4000))
    } catch { /* si el navegador no deja medir, queda el alto por defecto */ }
  }

  useEffect(() => {
    if (html) return
    const el = bloque.current
    if (el) setLargo(el.scrollHeight > max + 40)
  }, [html, texto, max])

  useEffect(() => {
    if (!html || !alto) return
    setLargo(alto > max + 40)
  }, [html, alto, max])

  const recortado = largo && !abierto

  const boton = largo && (
    <button className="btn btn-sm mail-mas" onClick={() => setAbierto(a => !a)}>
      {abierto ? 'Ver menos' : 'Ver el mail completo'}
    </button>
  )

  if (html) {
    return (
      <div className="mail-cuerpo">
        <div className={`mail-caja ${recortado ? 'is-corto' : ''}`}
             style={{ maxHeight: recortado ? max : 'none' }}>
          <iframe
            ref={marco}
            title="Cuerpo del mail"
            sandbox="allow-same-origin"
            referrerPolicy="no-referrer"
            onLoad={medir}
            style={{ width: '100%', border: 0, display: 'block', height: (alto || 120) + 'px' }}
            srcDoc={ESTILO + html}
          />
        </div>
        {boton}
      </div>
    )
  }

  return (
    <div className="mail-cuerpo">
      <div ref={bloque} className={`mail-caja mail-plano ${recortado ? 'is-corto' : ''}`}
           style={{ maxHeight: recortado ? max : 'none' }}>
        {texto}
      </div>
      {boton}
    </div>
  )
}
