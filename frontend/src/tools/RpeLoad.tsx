import { useState } from 'react'
import { convertInput, formatWeight, isNumber, toKg, useUnitChange } from '../units.ts'
import type { Unit } from '../units.ts'
import { useCalculation } from '../useCalculation.ts'

interface TargetLoadResponse {
  e1rm_kg: number
  target_weight_kg: number
}

function RpeLoad({ unit }: { unit: Unit }) {
  const [prWeight, setPrWeight] = useState('180')
  const [prReps, setPrReps] = useState('3')
  const [prRpe, setPrRpe] = useState('9')
  const [targetReps, setTargetReps] = useState('3')
  const [targetRpe, setTargetRpe] = useState('5')

  useUnitChange(unit, (from, to) => setPrWeight(convertInput(prWeight, from, to)))

  // null until every field holds a number; range checks are left to the API
  const complete = [prWeight, prReps, prRpe, targetReps, targetRpe].every(isNumber)
  const { result, error } = useCalculation<TargetLoadResponse>(
    '/api/target-load',
    complete
      ? JSON.stringify({
          pr_weight_kg: toKg(Number(prWeight), unit),
          pr_reps: Number(prReps),
          pr_rpe: Number(prRpe),
          target_reps: Number(targetReps),
          target_rpe: Number(targetRpe),
        })
      : null,
  )

  return (
    <>
      <form onSubmit={(event) => event.preventDefault()}>
        <fieldset>
          <legend>Last Set</legend>
          <label>
            Weight ({unit})
            <input
              type="number"
              min="0"
              step="any"
              required
              value={prWeight}
              onChange={(event) => setPrWeight(event.target.value)}
            />
          </label>
          <label>
            Reps
            <input
              type="number"
              min="1"
              step="1"
              required
              value={prReps}
              onChange={(event) => setPrReps(event.target.value)}
            />
          </label>
          <label>
            RPE
            <input
              type="number"
              min="1"
              max="10"
              step="0.5"
              required
              value={prRpe}
              onChange={(event) => setPrRpe(event.target.value)}
            />
          </label>
        </fieldset>

        <fieldset>
          <legend>Target Set</legend>
          <label>
            Reps
            <input
              type="number"
              min="1"
              step="1"
              required
              value={targetReps}
              onChange={(event) => setTargetReps(event.target.value)}
            />
          </label>
          <label>
            RPE
            <input
              type="number"
              min="1"
              max="10"
              step="0.5"
              required
              value={targetRpe}
              onChange={(event) => setTargetRpe(event.target.value)}
            />
          </label>
        </fieldset>
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <section className="result" aria-live="polite">
          <p className="result-label">Load</p>
          <p className="result-value">{formatWeight(result.target_weight_kg, unit)}</p>
          <dl>
            <div>
              <dt>Estimated 1RM:</dt>
              <dd>{formatWeight(result.e1rm_kg, unit)}</dd>
            </div>
          </dl>
        </section>
      )}
    </>
  )
}

export default RpeLoad
