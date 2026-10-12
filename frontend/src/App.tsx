import { useEffect, useState } from 'react'
import './App.css'

type Formula = 'epley' | 'brzycki'
type Unit = 'kg' | 'lb'
type Theme = 'light' | 'dark'

interface TargetLoadResponse {
  e1rm_kg: number
  target_weight_kg: number
  rounded_weight_kg: number
}

interface ValidationIssue {
  loc: (string | number)[]
  msg: string
}

const DEBOUNCE_MS = 200
const KG_PER_LB = 0.45359237
const UNITS: Unit[] = ['kg', 'lb']
const INCREMENTS: Record<Unit, number[]> = { kg: [1, 2.5, 5], lb: [2.5, 5, 10] }
const DEFAULT_INCREMENT: Record<Unit, string> = { kg: '2.5', lb: '5' }

// The API works in kg only; these convert at the display layer.
function toKg(value: number, unit: Unit): number {
  return unit === 'lb' ? value * KG_PER_LB : value
}

function fromKg(valueKg: number, unit: Unit): number {
  return unit === 'lb' ? valueKg / KG_PER_LB : valueKg
}

function saveTheme(theme: Theme) {
  try {
    localStorage.setItem('theme', theme)
  } catch {
    // storage unavailable: the choice just lasts for this page load
  }
}

function errorMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return (detail as ValidationIssue[])
      .map((issue) => `${issue.loc[issue.loc.length - 1]}: ${issue.msg}`)
      .join('; ')
  }
  return 'Something went wrong.'
}

function formatWeight(valueKg: number, unit: Unit, digits: number): string {
  return `${fromKg(valueKg, unit).toFixed(digits)} ${unit}`
}

function App() {
  // index.html sets data-theme before first paint
  const [theme, setTheme] = useState<Theme>(
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  )
  const [unit, setUnit] = useState<Unit>('kg')
  const [prWeight, setPrWeight] = useState('180')
  const [prReps, setPrReps] = useState('3')
  const [prRpe, setPrRpe] = useState('9')
  const [targetReps, setTargetReps] = useState('3')
  const [targetRpe, setTargetRpe] = useState('5')
  const [formula, setFormula] = useState<Formula>('epley')
  const [increment, setIncrement] = useState('2.5')

  const [result, setResult] = useState<TargetLoadResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  function toggleTheme() {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    document.documentElement.dataset.theme = next
    saveTheme(next)
    setTheme(next)
  }

  function changeUnit(next: Unit) {
    if (next === unit) return
    const weight = Number(prWeight)
    if (prWeight !== '' && Number.isFinite(weight)) {
      setPrWeight(String(Number(fromKg(toKg(weight, unit), next).toFixed(1))))
    }
    setIncrement(DEFAULT_INCREMENT[next])
    setUnit(next)
  }

  // null until every field holds a number; range checks are left to the API
  const fields = [prWeight, prReps, prRpe, targetReps, targetRpe]
  const complete = fields.every((value) => value !== '' && Number.isFinite(Number(value)))
  const requestBody = complete
    ? JSON.stringify({
        pr_weight_kg: toKg(Number(prWeight), unit),
        pr_reps: Number(prReps),
        pr_rpe: Number(prRpe),
        target_reps: Number(targetReps),
        target_rpe: Number(targetRpe),
        formula,
        increment_kg: toKg(Number(increment), unit),
      })
    : null

  useEffect(() => {
    if (requestBody === null) return
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const response = await fetch('/api/target-load', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: requestBody,
          signal: controller.signal,
        })
        const body = await response.json()
        if (response.ok) {
          setResult(body as TargetLoadResponse)
          setError(null)
        } else {
          setResult(null)
          setError(errorMessage(body.detail))
        }
      } catch {
        if (controller.signal.aborted) return
        setResult(null)
        setError('Could not reach the API. Is it running on port 8000?')
      }
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [requestBody])

  return (
    <main>
      <header>
        <h1>KiloPlan</h1>
        <p>Work out what to load for a set, from a past set of the same lift.</p>
        <div className="toolbar">
          <div className="unit-toggle" role="group" aria-label="Weight unit">
            {UNITS.map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={unit === option}
                onClick={() => changeUnit(option)}
              >
                {option}
              </button>
            ))}
          </div>
          <button type="button" className="theme-toggle" onClick={toggleTheme}>
            {theme === 'dark' ? 'Light mode' : 'Dark mode'}
          </button>
        </div>
      </header>

      <form onSubmit={(event) => event.preventDefault()}>
        <fieldset>
          <legend>Your best set</legend>
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
              {INCREMENTS[unit].map((value) => (
                <option key={value} value={value}>
                  {value} {unit}
                </option>
              ))}
            </select>
          </label>
        </fieldset>
      </form>

      {complete && error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {complete && result && (
        <section className="result" aria-live="polite">
          <p className="result-label">Load</p>
          <p className="result-value">{formatWeight(result.rounded_weight_kg, unit, 1)}</p>
          <dl>
            <div>
              <dt>Exact</dt>
              <dd>{formatWeight(result.target_weight_kg, unit, 2)}</dd>
            </div>
            <div>
              <dt>Estimated 1RM</dt>
              <dd>{formatWeight(result.e1rm_kg, unit, 1)}</dd>
            </div>
          </dl>
        </section>
      )}
    </main>
  )
}

export default App
