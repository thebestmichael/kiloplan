import { useState } from 'react'
import { convertInput, isNumber, toKg, useUnitChange } from '../units.ts'
import type { Unit } from '../units.ts'
import { useCalculation } from '../useCalculation.ts'

interface PointsResponse {
  wilks: number
  wilks_2020: number
  dots: number
  ipf_gl: number
}

type Sex = 'male' | 'female'

const SEXES: { value: Sex; label: string }[] = [
  { value: 'male', label: 'Men' },
  { value: 'female', label: 'Women' },
]

function Points({ unit }: { unit: Unit }) {
  const [sex, setSex] = useState<Sex>('male')
  const [bodyweight, setBodyweight] = useState('90')
  const [total, setTotal] = useState('600')
  const [equipped, setEquipped] = useState(false)
  const [benchOnly, setBenchOnly] = useState(false)

  useUnitChange(unit, (from, to) => {
    setBodyweight(convertInput(bodyweight, from, to))
    setTotal(convertInput(total, from, to))
  })

  const complete = [bodyweight, total].every(isNumber)
  const { result, error } = useCalculation<PointsResponse>(
    '/api/points',
    complete
      ? JSON.stringify({
          sex,
          bodyweight_kg: toKg(Number(bodyweight), unit),
          total_kg: toKg(Number(total), unit),
          equipped,
          bench_only: benchOnly,
        })
      : null,
  )

  const scores: [string, number][] = result
    ? [
        ['DOTS', result.dots],
        ['IPF GL', result.ipf_gl],
        ['Wilks', result.wilks],
        ['Wilks 2020', result.wilks_2020],
      ]
    : []

  return (
    <>
      <form onSubmit={(event) => event.preventDefault()}>
        <fieldset>
          <legend>Lifter</legend>
          <div className="choice" role="group" aria-label="Category">
            {SEXES.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={sex === option.value}
                onClick={() => setSex(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <label>
            Bodyweight ({unit})
            <input
              type="number"
              min="0"
              step="any"
              value={bodyweight}
              onChange={(event) => setBodyweight(event.target.value)}
            />
          </label>
          <label>
            {benchOnly ? 'Bench' : 'Total'} ({unit})
            <input
              type="number"
              min="0"
              step="any"
              value={total}
              onChange={(event) => setTotal(event.target.value)}
            />
          </label>
        </fieldset>
        <fieldset>
          <legend>IPF GL Options</legend>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={equipped}
              onChange={(event) => setEquipped(event.target.checked)}
            />
            Equipped
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={benchOnly}
              onChange={(event) => setBenchOnly(event.target.checked)}
            />
            Bench only
          </label>
        </fieldset>
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <section className="score-grid" aria-live="polite">
          {scores.map(([label, value]) => (
            <div key={label} className="score">
              <p className="result-label">{label}</p>
              <p className="score-value">{value.toFixed(2)}</p>
            </div>
          ))}
        </section>
      )}
    </>
  )
}

export default Points
