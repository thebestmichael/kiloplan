import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { Theme, User } from './account.ts'

const KG_PER_LB = 0.45359237
const WATER_UNIT_KEY = 'water-unit'
const WATER_UNITS = [
  { value: 'L', label: 'Litres' },
  { value: 'ml', label: 'Millilitres' },
  { value: 'oz', label: 'Fluid ounces' },
]

function savedWaterUnit(): string {
  try {
    return localStorage.getItem(WATER_UNIT_KEY) ?? 'L'
  } catch {
    return 'L'
  }
}

function Settings({
  user,
  theme,
  onTheme,
  onLogOut,
}: {
  user: User | null
  theme: Theme
  onTheme: (theme: Theme) => void
  onLogOut: () => void
}) {
  const [weight, setWeight] = useState('')
  const [weightUnit, setWeightUnit] = useState<'kg' | 'lb'>('kg')
  const [waterUnit, setWaterUnit] = useState(savedWaterUnit)
  const [message, setMessage] = useState<string | null>(null)

  // the stored bodyweight comes back with any day of the diary
  useEffect(() => {
    let cancelled = false
    fetch(`/api/nutrition/diary?day=${new Date().toLocaleDateString('en-CA')}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((day) => {
        if (!cancelled && day?.bodyweight_kg) setWeight(String(Number(day.bodyweight_kg.toFixed(1))))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  async function saveWeight(event: FormEvent) {
    event.preventDefault()
    const kg = Number(weight) * (weightUnit === 'lb' ? KG_PER_LB : 1)
    if (!(kg > 0)) return
    const response = await fetch('/api/nutrition/bodyweight', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bodyweight_kg: kg }),
    }).catch(() => null)
    setMessage(response?.ok ? 'Bodyweight saved.' : 'Could not save your bodyweight.')
  }

  function chooseWaterUnit(unit: string) {
    setWaterUnit(unit)
    try {
      localStorage.setItem(WATER_UNIT_KEY, unit)
    } catch {
      // storage unavailable: the choice just lasts for this page load
    }
  }

  return (
    <>
      <section className="card">
        <h2>Account</h2>
        {user ? (
          <>
            <p className="panel-note">
              Signed in as {user.name} ({user.email}).
            </p>
            <button type="button" className="quiet" onClick={onLogOut}>
              Sign out
            </button>
          </>
        ) : (
          <>
            <p className="panel-note">
              You are using KiloPlan as a guest. Create an account to keep your program and food
              diary to yourself.
            </p>
            <div className="choice">
              <a className="button" href="#/signup">
                Sign up
              </a>
              <a className="button quiet" href="#/login">
                Log in
              </a>
            </div>
          </>
        )}
      </section>

      <section className="card">
        <h2>Appearance</h2>
        <div className="choice setting-row" role="group" aria-label="Theme">
          {(['light', 'dark'] as Theme[]).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={theme === option}
              onClick={() => onTheme(option)}
            >
              {option === 'light' ? 'Light' : 'Dark'}
            </button>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>Bodyweight</h2>
        <p className="panel-note">Used for your recommended water intake.</p>
        <form className="inline-form" onSubmit={saveWeight}>
          <label>
            Bodyweight
            <input
              type="number"
              min="0"
              step="any"
              value={weight}
              onChange={(event) => setWeight(event.target.value)}
            />
          </label>
          <label>
            Unit
            <select
              value={weightUnit}
              onChange={(event) => setWeightUnit(event.target.value as 'kg' | 'lb')}
            >
              <option value="kg">kg</option>
              <option value="lb">lb</option>
            </select>
          </label>
          <button type="submit">Save</button>
        </form>
        {message && <p className="panel-note">{message}</p>}
      </section>

      <section className="card">
        <h2>Water unit</h2>
        <div className="choice setting-row wrap" role="group" aria-label="Water unit">
          {WATER_UNITS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={waterUnit === option.value}
              onClick={() => chooseWaterUnit(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </section>
    </>
  )
}

export default Settings
