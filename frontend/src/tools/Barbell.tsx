import { useId } from 'react'
import { plateShape } from './plateShapes.ts'
import type { Unit } from '../units.ts'

const HEIGHT = 196
const CENTRE = 88
const MAX_DIAMETER = 164
const GAP = 1.5
const SHAFT = 70
const FLANGE = 12
const SLEEVE_TAIL = 46
// thin plates are labelled underneath, on two rows so neighbours do not collide
const LABEL_ROWS = [HEIGHT - 15, HEIGHT - 4]

/** One end of a loaded barbell, seen side-on. Plates are listed from the inside out. */
function Barbell({
  perSide,
  unit,
  onRemove,
}: {
  perSide: number[]
  unit: Unit
  onRemove?: (index: number) => void
}) {
  const id = useId()
  const shapes = perSide.map((weight) => plateShape(weight, unit))
  const platesStart = SHAFT + FLANGE + 3
  const platesWidth = shapes.reduce((sum, shape) => sum + shape.thickness + GAP, 0)
  const width = platesStart + platesWidth + SLEEVE_TAIL
  const thinBefore = shapes.map(
    (_, index) => shapes.slice(0, index).filter((shape) => shape.thickness < 19).length,
  )
  const starts = shapes.map((_, index) =>
    shapes.slice(0, index).reduce((sum, shape) => sum + shape.thickness + GAP, platesStart),
  )

  return (
    <div className="barbell">
      <svg
        viewBox={`0 0 ${width} ${HEIGHT}`}
        width={width}
        height={HEIGHT}
        role="img"
        aria-label={`One side of the bar: ${perSide.length ? perSide.join(', ') : 'empty'} ${unit}`}
      >
        <defs>
          {/* light from above: a highlight near the top edge, shadow underneath */}
          <linearGradient id={`${id}-round`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#000000" stopOpacity="0.28" />
            <stop offset="0.07" stopColor="#ffffff" stopOpacity="0.5" />
            <stop offset="0.22" stopColor="#ffffff" stopOpacity="0.12" />
            <stop offset="0.5" stopColor="#000000" stopOpacity="0" />
            <stop offset="0.86" stopColor="#000000" stopOpacity="0.32" />
            <stop offset="1" stopColor="#000000" stopOpacity="0.55" />
          </linearGradient>
          <linearGradient id={`${id}-steel`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#6f757e" />
            <stop offset="0.2" stopColor="#f4f6f8" />
            <stop offset="0.45" stopColor="#b3b9c1" />
            <stop offset="0.8" stopColor="#6b7079" />
            <stop offset="1" stopColor="#3f434a" />
          </linearGradient>
          <pattern id={`${id}-knurl`} width="4" height="4" patternUnits="userSpaceOnUse">
            <path d="M0 4 4 0M-1 1 1 -1M3 5 5 3" stroke="#000000" strokeOpacity="0.28" strokeWidth="0.7" />
          </pattern>
          <radialGradient id={`${id}-shadow`}>
            <stop offset="0" stopColor="#000000" stopOpacity="0.35" />
            <stop offset="1" stopColor="#000000" stopOpacity="0" />
          </radialGradient>
        </defs>

        {shapes.length > 0 && (
          <ellipse
            cx={platesStart + platesWidth / 2}
            cy={CENTRE + MAX_DIAMETER / 2 + 3}
            rx={platesWidth / 2 + 16}
            ry="6"
            fill={`url(#${id}-shadow)`}
          />
        )}

        {/* shaft with knurling, then the shoulder the plates sit against */}
        <rect x="0" y={CENTRE - 7} width={SHAFT} height="14" fill={`url(#${id}-steel)`} />
        <rect x="0" y={CENTRE - 7} width={SHAFT - 14} height="14" fill={`url(#${id}-knurl)`} />
        <rect x={SHAFT} y={CENTRE - 19} width={FLANGE} height="38" rx="2.5" fill={`url(#${id}-steel)`} />
        {/* sleeve */}
        <rect
          x={SHAFT + FLANGE}
          y={CENTRE - 12}
          width={width - SHAFT - FLANGE - 2}
          height="24"
          rx="2"
          fill={`url(#${id}-steel)`}
        />
        <rect x={width - 5} y={CENTRE - 12} width="3" height="24" rx="1.5" fill="#3f434a" />

        {shapes.map((shape, index) => {
          const diameter = shape.diameter * MAX_DIAMETER
          const x = starts[index]
          const y = CENTRE - diameter / 2
          const weight = perSide[index]
          return (
            <g
              key={index}
              className={onRemove ? 'plate removable' : 'plate'}
              onClick={onRemove ? () => onRemove(index) : undefined}
            >
              <title>
                {weight} {unit}
              </title>
              <rect x={x} y={y} width={shape.thickness} height={diameter} rx="3.5" fill={shape.colour} />
              <rect
                x={x}
                y={y}
                width={shape.thickness}
                height={diameter}
                rx="3.5"
                fill={`url(#${id}-round)`}
              />
              {/* bevelled edges where the plate's faces meet its rim */}
              <rect x={x + 0.6} y={y + 3} width="1.4" height={diameter - 6} fill="#ffffff" opacity="0.28" />
              <rect
                x={x + shape.thickness - 2}
                y={y + 3}
                width="1.4"
                height={diameter - 6}
                fill="#000000"
                opacity="0.3"
              />
              <rect
                x={x}
                y={y}
                width={shape.thickness}
                height={diameter}
                rx="3.5"
                fill="none"
                stroke="#000000"
                strokeOpacity="0.45"
              />
              {shape.thickness >= 19 && (
                <text
                  x={x + shape.thickness / 2}
                  y={CENTRE}
                  fill={shape.ink}
                  transform={`rotate(-90 ${x + shape.thickness / 2} ${CENTRE})`}
                >
                  {weight}
                </text>
              )}
              {shape.thickness < 19 && (
                <text
                  className="below"
                  x={x + shape.thickness / 2}
                  y={LABEL_ROWS[thinBefore[index] % 2]}
                >
                  {weight}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

export default Barbell
