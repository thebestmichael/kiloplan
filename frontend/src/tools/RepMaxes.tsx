import { useState } from 'react'
import { convertInput, formatWeight, fromKg, isNumber, toKg, useUnitChange } from '../units.ts'
import type { Unit } from '../units.ts'
import { useCalculation } from '../useCalculation.ts'

interface RepMaxResponse {
  e1rm_kg: number
  rep_maxes: { reps: number; weight_kg: number }[]
  rpe_chart: { rpe: number; weights_kg: number[] }[]
}

function RepMaxes({ unit }: { unit: Unit }) {
  const [weight, setWeight] = useState('180')
  const [reps, setReps] = useState('3')
  const [rpe, setRpe] = useState('9')

  useUnitChange(unit, (from, to) => setWeight(convertInput(weight, from, to)))

  const complete = [weight, reps, rpe].every(isNumber)
  const { result, error } = useCalculation<RepMaxResponse>(
    '/api/rep-maxes',
    complete
      ? JSON.stringify({ weight_kg: toKg(Number(weight), unit), reps: Number(reps), rpe: Number(rpe) })
      : null,
  )

  return (
    <>
      <form onSubmit={(event) => event.preventDefault()}>
        <fieldset>
          <legend>A Set You Did</legend>
          <label>
            Weight ({unit})
            <input
              type="number"
              min="0"
              step="any"
              value={weight}
              onChange={(event) => setWeight(event.target.value)}
            />
          </label>
          <label>
            Reps
            <input
              type="number"
              min="1"
              step="1"
              value={reps}
              onChange={(event) => setReps(event.target.value)}
            />
          </label>
          <label>
            RPE
            <input
              type="number"
              min="1"
              max="10"
              step="0.5"
              value={rpe}
              onChange={(event) => setRpe(event.target.value)}
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
        <>
          <section className="result" aria-live="polite">
            <p className="result-label">Estimated 1RM</p>
            <p className="result-value">{formatWeight(result.e1rm_kg, unit)}</p>
          </section>

          <section className="panel">
            <h2>Rep maxes ({unit})</h2>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {result.rep_maxes.map((row) => (
                      <th key={row.reps} className="number">
                        {row.reps}RM
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    {result.rep_maxes.map((row) => (
                      <td key={row.reps} className="number">
                        {fromKg(row.weight_kg, unit).toFixed(1)}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <h2>RPE chart ({unit})</h2>
            <p className="panel-note">Weight for each rep count at each RPE.</p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>RPE</th>
                    {result.rep_maxes.map((row) => (
                      <th key={row.reps} className="number">
                        {row.reps}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rpe_chart.map((row) => (
                    <tr key={row.rpe}>
                      <th>{row.rpe}</th>
                      {row.weights_kg.map((weightKg, index) => (
                        <td key={index} className="number">
                          {fromKg(weightKg, unit).toFixed(1)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  )
}

export default RepMaxes
