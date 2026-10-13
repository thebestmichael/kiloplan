import type { Unit } from '../units.ts'

interface PlateShape {
  /** share of the largest plate's diameter */
  diameter: number
  /** drawn thickness in px */
  thickness: number
  colour: string
  /** colour of the weight printed on the plate's edge */
  ink: string
}

const STEEL = '#b9bec6'

// Competition colours and rough calibrated-plate proportions, seen edge-on.
const KG_PLATES: Record<number, PlateShape> = {
  25: { diameter: 1, thickness: 30, colour: '#d3202f', ink: '#ffffff' },
  20: { diameter: 1, thickness: 26, colour: '#1d55c8', ink: '#ffffff' },
  15: { diameter: 0.89, thickness: 23, colour: '#f1bf1f', ink: '#1a1a1a' },
  10: { diameter: 0.72, thickness: 21, colour: '#179447', ink: '#ffffff' },
  5: { diameter: 0.51, thickness: 19, colour: '#f2f2f2', ink: '#1a1a1a' },
  2.5: { diameter: 0.42, thickness: 15, colour: '#1c1c1f', ink: '#ffffff' },
  1.25: { diameter: 0.36, thickness: 12, colour: STEEL, ink: '#1a1a1a' },
  0.5: { diameter: 0.3, thickness: 9, colour: STEEL, ink: '#1a1a1a' },
  0.25: { diameter: 0.25, thickness: 7, colour: STEEL, ink: '#1a1a1a' },
}
const LB_PLATES: Record<number, PlateShape> = {
  55: { diameter: 1, thickness: 30, colour: '#d3202f', ink: '#ffffff' },
  45: { diameter: 1, thickness: 26, colour: '#1d55c8', ink: '#ffffff' },
  35: { diameter: 0.89, thickness: 23, colour: '#f1bf1f', ink: '#1a1a1a' },
  25: { diameter: 0.72, thickness: 21, colour: '#179447', ink: '#ffffff' },
  10: { diameter: 0.51, thickness: 19, colour: '#f2f2f2', ink: '#1a1a1a' },
  5: { diameter: 0.42, thickness: 15, colour: '#1c1c1f', ink: '#ffffff' },
  2.5: { diameter: 0.36, thickness: 12, colour: STEEL, ink: '#1a1a1a' },
}
const UNKNOWN: PlateShape = { diameter: 0.45, thickness: 14, colour: STEEL, ink: '#1a1a1a' }

export function plateShape(weight: number, unit: Unit): PlateShape {
  return (unit === 'lb' ? LB_PLATES : KG_PLATES)[weight] ?? UNKNOWN
}
