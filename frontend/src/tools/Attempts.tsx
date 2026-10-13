import { useState } from 'react'
import { convertInput, fromKg, isNumber, toKg, useUnitChange } from '../units.ts'
import type { Unit } from '../units.ts'
import { useCalculation } from '../useCalculation.ts'

interface AttemptsResponse {
  attempts_kg: Record<string, number[]>
  total_kg: number
}

const LIFTS = ['squat', 'bench', 'deadlift'] as const
const LABELS = { squat: 'Squat', bench: 'Bench', deadlift: 'Deadlift' }

function Attempts({ unit }: { unit: Unit }) {
  const [goals, setGoals] = useState({ squat: '200', bench: '130', deadlift: '240' })

  useUnitChange(unit, (from, to) =>
    setGoals({
      squat: convertInput(goals.squat, from, to),
      bench: convertInput(goals.bench, from, to),
      deadlift: convertInput(goals.deadlift, from, to),
    }),
  )

  const entered = LIFTS.filter((lift) => isNumber(goals[lift]) && Number(goals[lift]) > 0)
  const { result, error } = useCalculation<AttemptsResponse>(
    '/api/attempts',
    entered.length > 0
      ? JSON.stringify(
          Object.fromEntries(entered.map((lift) => [`${lift}_kg`, toKg(Number(goals[lift]), unit)])),
        )
      : null,
  )

  // meets are loaded in kg, so attempts are always shown in kg first
  function show(weightKg: number): string {
    const kg = `${weightKg.toFixed(1)} kg`
    return unit === 'lb' ? `${kg} (${fromKg(weightKg, 'lb').toFixed(1)} lb)` : kg
  }

  return (
    <>
      <form onSubmit={(event) => event.preventDefault()}>
        <fieldset>
          <legend>Goal Lifts</legend>
          {LIFTS.map((lift) => (
            <label key={lift}>
              {LABELS[lift]} ({unit})
              <input
                type="number"
                min="0"
                step="any"
                value={goals[lift]}
                onChange={(event) => setGoals({ ...goals, [lift]: event.target.value })}
              />
            </label>
          ))}
        </fieldset>
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <section className="panel" aria-live="polite">
          <h2>Attempts</h2>
          <p className="panel-note">
            Opener at 91% and second at 96% of the goal, on 2.5 kg meet jumps. A rule of thumb, not
            a substitute for how warm-ups move on the day.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Lift</th>
                  <th className="number">Opener</th>
                  <th className="number">Second</th>
                  <th className="number">Third</th>
                </tr>
              </thead>
              <tbody>
                {LIFTS.filter((lift) => result.attempts_kg[lift]).map((lift) => (
                  <tr key={lift}>
                    <th>{LABELS[lift]}</th>
                    {result.attempts_kg[lift].map((weightKg, index) => (
                      <td key={index} className="number">
                        {show(weightKg)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="total-line">
            Total on third attempts: <strong>{show(result.total_kg)}</strong>
          </p>
        </section>
      )}
    </>
  )
}

export default Attempts
