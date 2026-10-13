import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

interface Macros {
  kcal: number
  protein_g: number
  carbs_g: number
  fat_g: number
}

interface Food extends Macros {
  id: number
  name: string
  category: string
  source: string
  portions: { description: string; grams: number }[]
}

interface Entry extends Macros {
  id: number
  description: string
  grams: number | null
}

interface MealData {
  meal: string
  entries: Entry[]
  totals: Macros
}

interface Day {
  day: string
  meals: MealData[]
  totals: Macros
  goal: Macros | null
  remaining: Macros | null
}

interface SavedMeal {
  id: number
  name: string
  items: { description: string; grams: number | null }[]
  totals: Macros
}

const MEAL_LABELS: Record<string, string> = {
  breakfast: 'Breakfast',
  lunch: 'Lunch',
  dinner: 'Dinner',
  snacks: 'Snacks',
}
const MACROS: { key: keyof Macros; label: string; unit: string }[] = [
  { key: 'kcal', label: 'Calories', unit: 'kcal' },
  { key: 'protein_g', label: 'Protein', unit: 'g' },
  { key: 'carbs_g', label: 'Carbs', unit: 'g' },
  { key: 'fat_g', label: 'Fat', unit: 'g' },
]
const EMPTY_MACROS = { kcal: '', protein_g: '', carbs_g: '', fat_g: '' }
const SEARCH_DELAY_MS = 250

function isoDate(date: Date): string {
  return date.toLocaleDateString('en-CA')
}

function shiftDay(day: string, days: number): string {
  const date = new Date(`${day}T12:00:00`)
  date.setDate(date.getDate() + days)
  return isoDate(date)
}

function macroLine(macros: Macros): string {
  return `${Math.round(macros.kcal)} kcal · P ${macros.protein_g.toFixed(0)} · C ${macros.carbs_g.toFixed(0)} · F ${macros.fat_g.toFixed(0)}`
}

async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api/nutrition${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail
    throw new Error(typeof detail === 'string' ? detail : 'That did not work. Check the values.')
  }
  return (response.status === 204 ? null : await response.json()) as T
}

function numbers(values: Record<string, string>): Record<string, number> {
  return Object.fromEntries(Object.entries(values).map(([key, value]) => [key, Number(value) || 0]))
}

function MacroInputs({
  values,
  onChange,
}: {
  values: Record<string, string>
  onChange: (values: Record<string, string>) => void
}) {
  return (
    <>
      {MACROS.map(({ key, label, unit }) => (
        <label key={key}>
          {label} ({unit})
          <input
            type="number"
            min="0"
            step="any"
            value={values[key]}
            onChange={(event) => onChange({ ...values, [key]: event.target.value })}
          />
        </label>
      ))}
    </>
  )
}

function AddFood({ day, meal, onDone }: { day: string; meal: string; onDone: () => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Food[]>([])
  const [food, setFood] = useState<Food | null>(null)
  const [amount, setAmount] = useState('100')
  const [portion, setPortion] = useState(-1)
  const [creating, setCreating] = useState(false)
  const [custom, setCustom] = useState({ name: '', ...EMPTY_MACROS })
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!query.trim()) return
    const timer = setTimeout(() => {
      api<Food[]>(`/foods?q=${encodeURIComponent(query)}`)
        .then(setResults)
        .catch(() => setResults([]))
    }, SEARCH_DELAY_MS)
    return () => clearTimeout(timer)
  }, [query])

  const gramsEach = food && portion >= 0 ? food.portions[portion].grams : 1
  const grams = Number(amount) * gramsEach
  const valid = food !== null && Number.isFinite(grams) && grams > 0

  function choose(chosen: Food) {
    setFood(chosen)
    setPortion(-1)
    setAmount('100')
  }

  async function add() {
    if (!food || !valid) return
    try {
      await api('/diary', 'POST', { day, meal, food_id: food.id, grams })
      onDone()
    } catch (problem) {
      setError((problem as Error).message)
    }
  }

  async function createFood(event: FormEvent) {
    event.preventDefault()
    try {
      const { name, ...macros } = custom
      choose(await api<Food>('/foods', 'POST', { name, ...numbers(macros) }))
      setCreating(false)
      setError(null)
    } catch (problem) {
      setError((problem as Error).message)
    }
  }

  return (
    <div className="add-food">
      {!food && !creating && (
        <>
          <input
            type="search"
            autoFocus
            placeholder="Search foods, e.g. chicken breast"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {query.trim() && (
            <ul className="food-results">
              {results.map((result) => (
                <li key={result.id}>
                  <button type="button" onClick={() => choose(result)}>
                    <span>{result.name}</span>
                    <small>per 100 g: {macroLine(result)}</small>
                  </button>
                </li>
              ))}
              {results.length === 0 && <li className="muted">No foods found.</li>}
            </ul>
          )}
          <button type="button" className="quiet" onClick={() => setCreating(true)}>
            Create my own food
          </button>
        </>
      )}

      {creating && (
        <form className="inline-form" onSubmit={createFood}>
          <label className="wide-field">
            Food name
            <input
              type="text"
              required
              value={custom.name}
              onChange={(event) => setCustom({ ...custom, name: event.target.value })}
            />
          </label>
          <p className="panel-note wide-field">Values per 100 g.</p>
          <MacroInputs values={custom} onChange={(values) => setCustom({ ...custom, ...values })} />
          <button type="submit">Save food</button>
          <button type="button" className="quiet" onClick={() => setCreating(false)}>
            Back
          </button>
        </form>
      )}

      {food && (
        <div className="inline-form">
          <p className="wide-field">
            <strong>{food.name}</strong>
          </p>
          <label>
            Amount
            <input
              type="number"
              min="0"
              step="any"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </label>
          <label>
            Unit
            <select
              value={portion}
              onChange={(event) => {
                const next = Number(event.target.value)
                setPortion(next)
                setAmount(next >= 0 ? '1' : '100')
              }}
            >
              <option value={-1}>grams</option>
              {food.portions.map((item, index) => (
                <option key={index} value={index}>
                  {item.description} ({item.grams} g)
                </option>
              ))}
            </select>
          </label>
          {valid && (
            <p className="panel-note wide-field">
              {grams.toFixed(0)} g:{' '}
              {macroLine({
                kcal: (food.kcal * grams) / 100,
                protein_g: (food.protein_g * grams) / 100,
                carbs_g: (food.carbs_g * grams) / 100,
                fat_g: (food.fat_g * grams) / 100,
              })}
            </p>
          )}
          <button type="button" disabled={!valid} onClick={add}>
            Add to {MEAL_LABELS[meal].toLowerCase()}
          </button>
          <button type="button" className="quiet" onClick={() => setFood(null)}>
            Back
          </button>
        </div>
      )}

      {error && <p className="error">{error}</p>}
    </div>
  )
}

function QuickAdd({ day, meal, onDone }: { day: string; meal: string; onDone: () => void }) {
  const [description, setDescription] = useState('')
  const [macros, setMacros] = useState<Record<string, string>>(EMPTY_MACROS)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    try {
      await api('/diary/quick-add', 'POST', { day, meal, description, ...numbers(macros) })
      onDone()
    } catch (problem) {
      setError((problem as Error).message)
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <label className="wide-field">
        What was it?
        <input
          type="text"
          placeholder="Quick add"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      <MacroInputs values={macros} onChange={setMacros} />
      <button type="submit">Add</button>
      {error && <p className="error wide-field">{error}</p>}
    </form>
  )
}

type Open = { meal: string; panel: 'food' | 'quick' | 'save' } | null

function Nutrition() {
  const [day, setDay] = useState(() => isoDate(new Date()))
  const [data, setData] = useState<Day | null>(null)
  const [meals, setMeals] = useState<SavedMeal[]>([])
  const [open, setOpen] = useState<Open>(null)
  const [mealName, setMealName] = useState('')
  const [editingGoal, setEditingGoal] = useState(false)
  const [goal, setGoal] = useState<Record<string, string>>(EMPTY_MACROS)
  const [error, setError] = useState<string | null>(null)

  // bumped after every change, to load the day again
  const [version, setVersion] = useState(0)
  const [today] = useState(() => isoDate(new Date()))

  useEffect(() => {
    let cancelled = false
    Promise.all([api<Day>(`/diary?day=${day}`), api<SavedMeal[]>('/meals')])
      .then(([dayData, saved]) => {
        if (cancelled) return
        setData(dayData)
        setMeals(saved)
        setError(null)
      })
      .catch(() => {
        if (!cancelled) setError('Could not reach the API. Is it running on port 8000?')
      })
    return () => {
      cancelled = true
    }
  }, [day, version])

  async function run(action: () => Promise<unknown>) {
    try {
      await action()
      setOpen(null)
      setVersion((current) => current + 1)
    } catch (problem) {
      setError((problem as Error).message)
    }
  }

  function toggle(meal: string, panel: 'food' | 'quick' | 'save') {
    setOpen(open?.meal === meal && open.panel === panel ? null : { meal, panel })
    setMealName('')
  }

  function startGoal() {
    const current = data?.goal
    setGoal(
      current
        ? Object.fromEntries(MACROS.map(({ key }) => [key, String(current[key])]))
        : EMPTY_MACROS,
    )
    setEditingGoal(true)
  }

  return (
    <>
      <div className="day-nav">
        <button type="button" className="quiet" aria-label="Previous day" onClick={() => setDay(shiftDay(day, -1))}>
          ‹
        </button>
        <input type="date" value={day} onChange={(event) => event.target.value && setDay(event.target.value)} />
        <button type="button" className="quiet" aria-label="Next day" onClick={() => setDay(shiftDay(day, 1))}>
          ›
        </button>
        {day !== today && (
          <button type="button" className="quiet" onClick={() => setDay(today)}>
            Today
          </button>
        )}
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {data && (
        <>
          <section className="panel">
            <div className="macro-grid">
              {MACROS.map(({ key, label, unit }) => {
                const eaten = data.totals[key]
                const target = data.goal?.[key]
                const share = target ? Math.min(100, (eaten / target) * 100) : 0
                return (
                  <div key={key} className="macro">
                    <p className="result-label">{label}</p>
                    <p className="macro-value">
                      {Math.round(eaten)}
                      <small>
                        {target ? ` / ${Math.round(target)}` : ''} {unit}
                      </small>
                    </p>
                    <div className="bar" data-over={target !== undefined && eaten > target}>
                      <span style={{ width: `${share}%` }} />
                    </div>
                    {data.remaining && (
                      <p className="panel-note">
                        {data.remaining[key] >= 0
                          ? `${Math.round(data.remaining[key])} left`
                          : `${Math.round(-data.remaining[key])} over`}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
            {editingGoal ? (
              <form
                className="inline-form"
                onSubmit={(event) => {
                  event.preventDefault()
                  void run(() => api('/goal', 'PUT', numbers(goal))).then(() => setEditingGoal(false))
                }}
              >
                <MacroInputs values={goal} onChange={setGoal} />
                <button type="submit">Save goals</button>
                <button type="button" className="quiet" onClick={() => setEditingGoal(false)}>
                  Cancel
                </button>
              </form>
            ) : (
              <button type="button" className="quiet" onClick={startGoal}>
                {data.goal ? 'Change daily goals' : 'Set daily goals'}
              </button>
            )}
          </section>

          {data.meals.map((meal) => (
            <section key={meal.meal} className="panel">
              <div className="meal-head">
                <h2>{MEAL_LABELS[meal.meal]}</h2>
                <span className="muted">{macroLine(meal.totals)}</span>
              </div>
              <ul className="entries">
                {meal.entries.map((entry) => (
                  <li key={entry.id}>
                    <div>
                      <span>{entry.description}</span>
                      <small>
                        {entry.grams !== null ? `${Number(entry.grams.toFixed(1))} g · ` : ''}
                        {macroLine(entry)}
                      </small>
                    </div>
                    <button
                      type="button"
                      className="quiet"
                      aria-label={`Remove ${entry.description}`}
                      onClick={() => void run(() => api(`/diary/${entry.id}`, 'DELETE'))}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
              <div className="meal-actions">
                <button type="button" className="quiet" onClick={() => toggle(meal.meal, 'food')}>
                  Add food
                </button>
                <button type="button" className="quiet" onClick={() => toggle(meal.meal, 'quick')}>
                  Quick add
                </button>
                {meals.length > 0 && (
                  <select
                    value=""
                    aria-label="Add a saved meal"
                    onChange={(event) =>
                      void run(() =>
                        api(`/meals/${event.target.value}/log`, 'POST', { day, meal: meal.meal }),
                      )
                    }
                  >
                    <option value="">Add saved meal…</option>
                    {meals.map((saved) => (
                      <option key={saved.id} value={saved.id}>
                        {saved.name} ({Math.round(saved.totals.kcal)} kcal)
                      </option>
                    ))}
                  </select>
                )}
                {meal.entries.length > 0 && (
                  <button type="button" className="quiet" onClick={() => toggle(meal.meal, 'save')}>
                    Save as meal
                  </button>
                )}
              </div>
              {open?.meal === meal.meal && open.panel === 'food' && (
                <AddFood day={day} meal={meal.meal} onDone={() => void run(async () => {})} />
              )}
              {open?.meal === meal.meal && open.panel === 'quick' && (
                <QuickAdd day={day} meal={meal.meal} onDone={() => void run(async () => {})} />
              )}
              {open?.meal === meal.meal && open.panel === 'save' && (
                <form
                  className="inline-form"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void run(() => api('/meals', 'POST', { name: mealName, day, meal: meal.meal }))
                  }}
                >
                  <label className="wide-field">
                    Name for this meal
                    <input
                      type="text"
                      required
                      autoFocus
                      value={mealName}
                      onChange={(event) => setMealName(event.target.value)}
                    />
                  </label>
                  <button type="submit">Save meal</button>
                </form>
              )}
            </section>
          ))}

          {meals.length > 0 && (
            <section className="panel">
              <h2>Saved meals</h2>
              <ul className="entries">
                {meals.map((saved) => (
                  <li key={saved.id}>
                    <div>
                      <span>{saved.name}</span>
                      <small>
                        {saved.items.map((item) => item.description).join(', ')} ·{' '}
                        {macroLine(saved.totals)}
                      </small>
                    </div>
                    <button
                      type="button"
                      className="quiet"
                      aria-label={`Delete saved meal ${saved.name}`}
                      onClick={() => void run(() => api(`/meals/${saved.id}`, 'DELETE'))}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </>
  )
}

export default Nutrition
