import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import Icon from './Icon.tsx'
import Ring from './Ring.tsx'

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
  water_ml: number
  bodyweight_kg: number | null
  water_recommended_ml: number | null
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
const RING_MACROS: { key: keyof Macros; label: string; colour: string }[] = [
  { key: 'carbs_g', label: 'Carbs', colour: 'var(--carbs)' },
  { key: 'protein_g', label: 'Protein', colour: 'var(--protein)' },
  { key: 'fat_g', label: 'Fat', colour: 'var(--fat)' },
]
const KG_PER_LB = 0.45359237

type WaterUnit = 'L' | 'ml' | 'oz'

// millilitres per unit; oz is the US fluid ounce
const WATER_UNITS: Record<WaterUnit, { ml: number; example: string; digits: number }> = {
  L: { ml: 1000, example: '0.5', digits: 2 },
  ml: { ml: 1, example: '500', digits: 0 },
  oz: { ml: 29.5735, example: '16', digits: 0 },
}
const WATER_UNIT_KEY = 'water-unit'

function savedWaterUnit(): WaterUnit {
  try {
    const saved = localStorage.getItem(WATER_UNIT_KEY)
    if (saved === 'L' || saved === 'ml' || saved === 'oz') return saved
  } catch {
    // storage unavailable: use the default
  }
  return 'L'
}

function showWater(ml: number, unit: WaterUnit): string {
  const { ml: size, digits } = WATER_UNITS[unit]
  return `${Number((ml / size).toFixed(digits))} ${unit}`
}
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
  const [waterAmount, setWaterAmount] = useState('')
  const [waterUnit, setWaterUnit] = useState<WaterUnit>(savedWaterUnit)
  const [editingWeight, setEditingWeight] = useState(false)
  const [weight, setWeight] = useState('')
  const [weightUnit, setWeightUnit] = useState<'kg' | 'lb'>('kg')

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

  function changeWaterUnit(unit: WaterUnit) {
    setWaterUnit(unit)
    setWaterAmount('')
    try {
      localStorage.setItem(WATER_UNIT_KEY, unit)
    } catch {
      // storage unavailable: the choice just lasts for this page load
    }
  }

  return (
    <>
      <div className="day-nav">
        <button type="button" className="icon-button" aria-label="Previous day" onClick={() => setDay(shiftDay(day, -1))}>
          <Icon name="left" size={20} />
        </button>
        <input type="date" value={day} onChange={(event) => event.target.value && setDay(event.target.value)} />
        <button type="button" className="icon-button" aria-label="Next day" onClick={() => setDay(shiftDay(day, 1))}>
          <Icon name="right" size={20} />
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
          <section className="card calories">
            <div className="stat">
              <span>Consumed</span>
              <strong>{Math.round(data.totals.kcal)}</strong>
              <span>kcal</span>
            </div>
            <Ring value={data.totals.kcal} max={data.goal?.kcal} colour="var(--accent)" size={116} thickness={11}>
              {data.remaining ? (
                <>
                  <strong>{Math.abs(Math.round(data.remaining.kcal))}</strong>
                  <span>{data.remaining.kcal >= 0 ? 'left' : 'over'}</span>
                </>
              ) : (
                <span>no goal</span>
              )}
            </Ring>
            <div className="stat end">
              <span>Goal</span>
              <strong>{data.goal ? Math.round(data.goal.kcal) : '–'}</strong>
              <span>kcal</span>
            </div>
          </section>

          <section className="card">
            <div className="card-head">
              <h2>Macronutrients</h2>
              {!editingGoal && (
                <button type="button" className="text-button" onClick={startGoal}>
                  {data.goal ? 'Edit goals' : 'Set goals'}
                </button>
              )}
            </div>
            <div className="macro-rings">
              {RING_MACROS.map(({ key, label, colour }) => (
                <div key={key} className="macro-ring">
                  <Ring value={data.totals[key]} max={data.goal?.[key]} colour={colour} size={84} thickness={7}>
                    <strong>{Math.round(data.totals[key])}g</strong>
                  </Ring>
                  <span>{label}</span>
                  <span>{data.goal ? `/ ${Math.round(data.goal[key])}g` : 'no goal'}</span>
                </div>
              ))}
            </div>
            {editingGoal && (
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
            )}
          </section>

          <section className="card water">
            <div className="water-row">
              <span className="badge water-badge">
                <Icon name="water" />
              </span>
              <div className="grow">
                <h2>Water Intake</h2>
                <span className="muted">
                  {showWater(data.water_ml, waterUnit)}
                  {data.water_recommended_ml !== null &&
                    ` of ${showWater(data.water_recommended_ml, waterUnit)} recommended`}
                </span>
              </div>
            </div>

            {data.water_recommended_ml !== null && (
              <div className="bar">
                <span
                  style={{ width: `${Math.min(100, (data.water_ml / data.water_recommended_ml) * 100)}%` }}
                />
              </div>
            )}

            <form
              className="water-add"
              onSubmit={(event) => {
                event.preventDefault()
                const ml = Number(waterAmount) * WATER_UNITS[waterUnit].ml
                if (!(ml > 0)) return
                void run(() => api('/water', 'POST', { day, ml })).then(() => setWaterAmount(''))
              }}
            >
              <label>
                Add water
                <input
                  type="number"
                  min="0"
                  step="any"
                  inputMode="decimal"
                  placeholder={`e.g. ${WATER_UNITS[waterUnit].example}`}
                  value={waterAmount}
                  onChange={(event) => setWaterAmount(event.target.value)}
                />
              </label>
              <label className="unit-field">
                Unit
                <select
                  value={waterUnit}
                  onChange={(event) => changeWaterUnit(event.target.value as WaterUnit)}
                >
                  <option value="L">L</option>
                  <option value="ml">ml</option>
                  <option value="oz">fl oz</option>
                </select>
              </label>
              <button type="submit" className="round-button" aria-label="Add water" disabled={!(Number(waterAmount) > 0)}>
                <Icon name="plus" size={20} />
              </button>
            </form>

            <div className="meal-actions">
              {data.water_ml > 0 && (
                <button
                  type="button"
                  className="text-button"
                  onClick={() => void run(() => api('/water', 'POST', { day, ml: -data.water_ml }))}
                >
                  Reset today's water
                </button>
              )}
              {!editingWeight && (
                <button
                  type="button"
                  className="text-button"
                  onClick={() => {
                    setWeight(data.bodyweight_kg ? String(Number(data.bodyweight_kg.toFixed(1))) : '')
                    setWeightUnit('kg')
                    setEditingWeight(true)
                  }}
                >
                  {data.bodyweight_kg
                    ? `Bodyweight ${Number(data.bodyweight_kg.toFixed(1))} kg · change`
                    : 'Add your bodyweight for a recommended amount'}
                </button>
              )}
            </div>

            {editingWeight && (
              <form
                className="inline-form"
                onSubmit={(event) => {
                  event.preventDefault()
                  const kg = Number(weight) * (weightUnit === 'lb' ? KG_PER_LB : 1)
                  if (!(kg > 0)) return
                  void run(() => api('/bodyweight', 'PUT', { bodyweight_kg: kg })).then(() =>
                    setEditingWeight(false),
                  )
                }}
              >
                <label>
                  Bodyweight
                  <input
                    type="number"
                    min="0"
                    step="any"
                    autoFocus
                    value={weight}
                    onChange={(event) => setWeight(event.target.value)}
                  />
                </label>
                <label>
                  Unit
                  <select value={weightUnit} onChange={(event) => setWeightUnit(event.target.value as 'kg' | 'lb')}>
                    <option value="kg">kg</option>
                    <option value="lb">lb</option>
                  </select>
                </label>
                <button type="submit">Save</button>
                <button type="button" className="quiet" onClick={() => setEditingWeight(false)}>
                  Cancel
                </button>
                <p className="panel-note wide-field">
                  The recommendation is about 35 ml per kg of bodyweight: a common starting point,
                  not a limit.
                </p>
              </form>
            )}
          </section>

          <h2 className="section-title">{day === today ? "Today's Meals" : 'Meals'}</h2>

          {data.meals.map((meal) => (
            <section key={meal.meal} className="card meal">
              <div className="meal-head">
                <span className="badge">
                  <Icon name={meal.meal} />
                </span>
                <div className="grow">
                  <h2>{MEAL_LABELS[meal.meal]}</h2>
                  <span className="muted">
                    P {meal.totals.protein_g.toFixed(0)} · C {meal.totals.carbs_g.toFixed(0)} · F{' '}
                    {meal.totals.fat_g.toFixed(0)}
                  </span>
                </div>
                <div className="stat end small">
                  <strong>{Math.round(meal.totals.kcal)}</strong>
                  <span>kcal</span>
                </div>
              </div>

              {meal.entries.length > 0 && (
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
                        className="icon-button plain"
                        aria-label={`Remove ${entry.description}`}
                        onClick={() => void run(() => api(`/diary/${entry.id}`, 'DELETE'))}
                      >
                        <Icon name="close" size={16} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <button type="button" className="add-button" onClick={() => toggle(meal.meal, 'food')}>
                <Icon name="plus" size={18} /> Add Food
              </button>
              <div className="meal-actions">
                <button type="button" className="text-button" onClick={() => toggle(meal.meal, 'quick')}>
                  Quick add
                </button>
                {meal.entries.length > 0 && (
                  <button type="button" className="text-button" onClick={() => toggle(meal.meal, 'save')}>
                    Save as meal
                  </button>
                )}
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
            <>
              <h2 className="section-title">Saved Meals</h2>
              <section className="card">
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
                        className="icon-button plain"
                        aria-label={`Delete saved meal ${saved.name}`}
                        onClick={() => void run(() => api(`/meals/${saved.id}`, 'DELETE'))}
                      >
                        <Icon name="close" size={16} />
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}
        </>
      )}
    </>
  )
}

export default Nutrition
