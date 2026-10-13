import { useState } from 'react'
import { convertInput, formatWeight, isNumber, toKg, useUnitChange } from '../units.ts'
import type { Unit } from '../units.ts'
import { useCalculation } from '../useCalculation.ts'

interface PointsResponse {
  wilks: number
  wilks_2020: number
  dots: number
  ipf_gl: number
}

type Sex = 'male' | 'female'
type Formula = 'dots' | 'ipf_gl' | 'wilks' | 'wilks_2020'

const FORMULAS: { value: Formula; label: string }[] = [
  { value: 'dots', label: 'DOTS' },
  { value: 'ipf_gl', label: 'IPF GL' },
  { value: 'wilks', label: 'Wilks' },
  { value: 'wilks_2020', label: 'Wilks 2020' },
]
// a round score to aim at on each scale
const DEFAULT_TARGET: Record<Formula, string> = {
  dots: '400',
  ipf_gl: '85',
  wilks: '400',
  wilks_2020: '475',
}

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
  const [formula, setFormula] = useState<Formula>('dots')
  const [target, setTarget] = useState(DEFAULT_TARGET.dots)

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

  const needed = useCalculation<{ total_kg: number }>(
    '/api/points/target',
    isNumber(bodyweight) && isNumber(target)
      ? JSON.stringify({
          formula,
          sex,
          bodyweight_kg: toKg(Number(bodyweight), unit),
          target_points: Number(target),
          equipped,
          bench_only: benchOnly,
        })
      : null,
  )
  // how far the total entered above is from the one the target needs
  const gapKg =
    needed.result && isNumber(total) ? needed.result.total_kg - toKg(Number(total), unit) : null
  const lift = benchOnly ? 'bench' : 'total'

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

      <section className="card target">
        <h2>Target</h2>
        <p className="panel-note">
          The {lift} you need at this bodyweight to reach a score.
        </p>
        <div className="choice wrap" role="group" aria-label="Formula">
          {FORMULAS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={formula === option.value}
              onClick={() => {
                setFormula(option.value)
                setTarget(DEFAULT_TARGET[option.value])
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
        <label>
          Target {FORMULAS.find((option) => option.value === formula)!.label} points
          <input
            type="number"
            min="0"
            step="any"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
          />
        </label>
        {needed.error && (
          <p className="error" role="alert">
            {needed.error}
          </p>
        )}
        {needed.result && (
          <div className="target-result" aria-live="polite">
            <p className="result-label">{benchOnly ? 'Bench' : 'Total'} needed</p>
            <p className="result-value">{formatWeight(needed.result.total_kg, unit)}</p>
            {gapKg !== null && (
              <p className="panel-note">
                {gapKg > 0.05
                  ? `${formatWeight(gapKg, unit)} more than the ${lift} above.`
                  : `The ${lift} above already reaches it, with ${formatWeight(-gapKg, unit)} to spare.`}
              </p>
            )}
          </div>
        )}
      </section>
    </>
  )
}

export default Points
