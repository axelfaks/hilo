import React from 'react'

/* ---------------------------------------------------------------------------
   LA MARCA

   Un infinito que no se corta y un punto rojo que lo recorre: el hilo, y el
   mensaje dando vueltas por él. Es la idea del producto dibujada.

   Dos cosas que cambié del SVG original:
   · Los colores ya no están escritos acá. Salen de --accent, --st-yours y
     --ink, así que si Toto toca el sistema, la marca lo sigue sola.
   · El punto daba una vuelta cada 1,2 s. En una pantalla que uno mira todo el
     día eso cansa: ahora tarda 5 s y respeta a quien pidió menos movimiento.
--------------------------------------------------------------------------- */

/* El trazo del infinito. Cerrado a propósito: el punto vuelve a empezar sin salto. */
const CAMINO = 'M 15 35 C 15 22, 45 22, 60 35 C 75 48, 105 48, 105 35 ' +
               'C 105 22, 75 22, 60 35 C 45 48, 15 48, 15 35 Z'

/* Cajas medidas sobre el dibujo real, no a ojo. */
const CAJA_COMPLETA = '12 14 172 35'
const CAJA_SIMBOLO  = '11 21 98 28'

const sinMovimiento = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

export default function Marca({ alto = 22, soloSimbolo = false, animado = true, titulo = 'Hilo' }) {
  const quieto = !animado || sinMovimiento()
  const caja = soloSimbolo ? CAJA_SIMBOLO : CAJA_COMPLETA
  const [x, y, ancho, altoCaja] = caja.split(' ').map(Number)

  return (
    <svg
      viewBox={caja}
      height={alto}
      width={(alto * ancho) / altoCaja}
      role="img"
      aria-label={titulo}
      style={{ display: 'block', overflow: 'visible' }}
    >
      <title>{titulo}</title>

      <path
        d={CAMINO}
        fill="none"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ stroke: 'var(--accent)' }}
      />

      {quieto ? (
        <circle cx="15" cy="35" r="3.5" style={{ fill: 'var(--st-yours)' }} />
      ) : (
        <circle r="3.5" style={{ fill: 'var(--st-yours)' }}>
          <animateMotion dur="5s" repeatCount="indefinite" path={CAMINO} />
        </circle>
      )}

      {!soloSimbolo && (
        <text
          x="118" y="47"
          fontStyle="italic"
          fontSize="42"
          fontWeight="400"
          style={{ fontFamily: 'var(--font-serif)', fill: 'var(--ink)' }}
        >
          hilo
        </text>
      )}
    </svg>
  )
}
