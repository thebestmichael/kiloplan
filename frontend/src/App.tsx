import { useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type Formula = 'epley' | 'brzycki'

interface TargetLoadResponse {
  e1rm_kg: number
  target_weight_kg: number
  rounded_weight_kg: number
}

interface ValidationIssue {
  loc: (string | number)[]
  msg: string
}

const INCREMENTS_KG = [1, 2.5, 5]

function errorMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return (detail as ValidationIssue[])
      .map((issue) => `${issue.loc[issue.loc.length - 1]}: ${issue.msg}`)
      .join('; ')
  }
  return 'Something went wrong.'
}

function formatKg(value: number, digits: number): string {
  return `${value.toFixed(digits)} kg`
}

function App() {
  const [prWeight, setPrWeight] = useState('180')
  const [prReps, setPrReps] = useState('3')
  const [prRpe, setPrRpe] = useState('9')
  const [targetReps, setTargetReps] = useState('3')
  const [targetRpe, setTargetRpe] = useState('5')
  const [formula, setFormula] = useState<Formula>('epley')
  const [increment, setIncrement] = useState('2.5')

  const [result, setResult] = useState<TargetLoadResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const response = await fetch('/api/target-load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pr_weight_kg: Number(prWeight),
          pr_reps: Number(prReps),
          pr_rpe: Number(prRpe),
          target_reps: Number(targetReps),
          target_rpe: Number(targetRpe),
          formula,
          increment_kg: Number(increment),
        }),
      })
      const body = await response.json()
      if (!response.ok) {
        setResult(null)
        setError(errorMessage(body.detail))
        return
      }
      setResult(body as TargetLoadResponse)
    } catch {
      setResult(null)
      setError('Could not reach the API. Is it running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <header>
        <h1>KiloPlan</h1>
        <p>Work out what to load for a set, from a past set of the same lift.</p>
      </header>

      <form onSubmit={handleSubmit}>
        <fieldset>
          <legend>Your best set</legend>
          <label>
            Weight (kg)
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
          <legend>Target set</legend>
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

        <fieldset>
          <legend>Options</legend>
          <label>
            Formula
            <select value={formula} onChange={(event) => setFormula(event.target.value as Formula)}>
              <option value="epley">Epley</option>
              <option value="brzycki">Brzycki</option>
            </select>
          </label>
          <label>
            Round to
            <select value={increment} onChange={(event) => setIncrement(event.target.value)}>
              {INCREMENTS_KG.map((value) => (
                <option key={value} value={value}>
                  {value} kg
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <button type="submit" disabled={loading}>
          {loading ? 'Calculating…' : 'Calculate'}
        </button>
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <section className="result" aria-live="polite">
          <p className="result-label">Load</p>
          <p className="result-value">{formatKg(result.rounded_weight_kg, 1)}</p>
          <dl>
            <div>
              <dt>Exact</dt>
              <dd>{formatKg(result.target_weight_kg, 2)}</dd>
            </div>
            <div>
              <dt>Estimated 1RM</dt>
              <dd>{formatKg(result.e1rm_kg, 1)}</dd>
            </div>
          </dl>
        </section>
      )}
    </main>
  )
}

export default App
