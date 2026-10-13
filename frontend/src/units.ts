import { useEffect, useRef } from 'react'

export type Unit = 'kg' | 'lb'

export const KG_PER_LB = 0.45359237

// The API works in kg; these convert at the display layer.
export function toKg(value: number, unit: Unit): number {
  return unit === 'lb' ? value * KG_PER_LB : value
}

export function fromKg(valueKg: number, unit: Unit): number {
  return unit === 'lb' ? valueKg / KG_PER_LB : valueKg
}

export function formatWeight(valueKg: number, unit: Unit, digits = 1): string {
  return `${fromKg(valueKg, unit).toFixed(digits)} ${unit}`
}

/** A typed weight re-expressed in another unit, or left alone if it is not a number. */
export function convertInput(value: string, from: Unit, to: Unit): string {
  const number = Number(value)
  if (value === '' || !Number.isFinite(number)) return value
  return String(Number(fromKg(toKg(number, from), to).toFixed(1)))
}

/** Runs `convert` when the unit switches, so typed weights follow it. */
export function useUnitChange(unit: Unit, convert: (from: Unit, to: Unit) => void) {
  const previous = useRef(unit)
  useEffect(() => {
    if (previous.current !== unit) {
      const from = previous.current
      previous.current = unit
      convert(from, unit)
    }
  })
}

export function isNumber(value: string): boolean {
  return value !== '' && Number.isFinite(Number(value))
}
