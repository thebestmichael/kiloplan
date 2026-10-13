import type { ReactNode } from 'react'

/** A circular progress ring with content in the middle. */
function Ring({
  value,
  max,
  colour,
  size,
  thickness = 10,
  children,
}: {
  value: number
  max: number | undefined
  colour: string
  size: number
  thickness?: number
  children: ReactNode
}) {
  const radius = (size - thickness) / 2
  const circumference = 2 * Math.PI * radius
  const share = max && max > 0 ? Math.min(1, Math.max(0, value / max)) : 0
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle className="ring-track" cx={size / 2} cy={size / 2} r={radius} strokeWidth={thickness} />
        {share > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={colour}
            strokeWidth={thickness}
            strokeLinecap="round"
            strokeDasharray={`${share * circumference} ${circumference}`}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        )}
      </svg>
      <div className="ring-label">{children}</div>
    </div>
  )
}

export default Ring
