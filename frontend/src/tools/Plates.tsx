import { useState } from 'react'
import { convertInput, isNumber, useUnitChange } from '../units.ts'
import type { Unit } from '../units.ts'
import { useCalculation } from '../useCalculation.ts'

interface PlateStock {
  weight: number
  pairs: number
}

interface PlateResponse {
  per_side: number[]
  total: number
  shortfall: number
}

type Mode = 'load' | 'reverse'

const DEFAULT_STOCK: Record<Unit, PlateStock[]> = {
  kg: [25, 20, 15, 10, 5, 2.5, 1.25, 0.5, 0.25].map((weight) => ({
    weight,
    pairs: weight === 25 ? 8 : 1,
  })),
  lb: [45, 35, 25, 10, 5, 2.5].map((weight) => ({
    weight,
    pairs: weight === 45 ? 8 : weight === 10 ? 2 : 1,
  })),
}
const DEFAULT_BAR: Record<Unit, string> = { kg: '20', lb: '45' }
const STORAGE_KEY = 'plate-stock'

// competition colours for kg plates; lb plates get the same colour as their nearest kg plate
const COLOURS: [number, string][] = [
  [25, '#c8102e'],
  [20, '#1d4ed8'],
  [15, '#eab308'],
  [10, '#15803d'],
  [5, '#e5e7eb'],
  [2.5, '#111827'],
  [0, '#9ca3af'],
]

function plateColour(weight: number, unit: Unit): string {
  const kg = unit === 'lb' ? weight / 2.2 : weight
  return COLOURS.find(([threshold]) => kg >= threshold - 0.01)![1]
}

function loadStock(): Record<Unit, PlateStock[]> {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null')
    if (saved?.kg && saved?.lb) return saved as Record<Unit, PlateStock[]>
  } catch {
    // unreadable or blocked storage: fall back to the defaults
  }
  return DEFAULT_STOCK
}

function Barbell({ perSide, unit }: { perSide: number[]; unit: Unit }) {
  const heaviest = unit === 'lb' ? 45 : 25
  return (
    <div className="barbell" role="img" aria-label={`One side: ${perSide.join(', ') || 'empty'}`}>
      <span className="barbell-shaft" />
      <span className="barbell-collar" />
      {perSide.map((weight, index) => (
        <span
          key={index}
          className="plate"
          style={{
            height: `${Math.max(34, Math.min(100, (weight / heaviest) * 100))}%`,
            background: plateColour(weight, unit),
          }}
          title={`${weight} ${unit}`}
        >
          {weight}
        </span>
      ))}
      <span className="barbell-end" />
    </div>
  )
}

function Plates({ unit }: { unit: Unit }) {
  const [mode, setMode] = useState<Mode>('load')
  const [target, setTarget] = useState('100')
  const [bar, setBar] = useState(DEFAULT_BAR[unit])
  const [collar, setCollar] = useState('0')
  const [stock, setStock] = useState(loadStock)
  const [onBar, setOnBar] = useState<number[]>([])
  const [showStock, setShowStock] = useState(false)

  useUnitChange(unit, (from, to) => {
    setTarget(convertInput(target, from, to))
    setBar(DEFAULT_BAR[to])
    setCollar('0')
    setOnBar([])
  })

  function updateStock(index: number, pairs: number) {
    const next = { ...stock, [unit]: stock[unit].map((plate, i) => (i === index ? { ...plate, pairs } : plate)) }
    setStock(next)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      // storage unavailable: the change just lasts for this page load
    }
  }

  const barReady = isNumber(bar) && isNumber(collar)
  const base = { bar: Number(bar), collar: Number(collar) }
  const load = useCalculation<PlateResponse>(
    '/api/plates',
    mode === 'load' && barReady && isNumber(target)
      ? JSON.stringify({ ...base, target: Number(target), plates: stock[unit] })
      : null,
  )
  const reverse = useCalculation<{ total: number }>(
    '/api/plates/total',
    mode === 'reverse' && barReady ? JSON.stringify({ ...base, per_side: onBar }) : null,
  )
  const error = load.error ?? reverse.error
  const sorted = [...onBar].sort((a, b) => b - a)

  return (
    <>
      <div className="choice centred" role="group" aria-label="Plate calculator mode">
        <button type="button" aria-pressed={mode === 'load'} onClick={() => setMode('load')}>
          Load a weight
        </button>
        <button type="button" aria-pressed={mode === 'reverse'} onClick={() => setMode('reverse')}>
          What's on the bar
        </button>
      </div>

      <form onSubmit={(event) => event.preventDefault()}>
        <fieldset>
          <legend>Bar</legend>
          {mode === 'load' && (
            <label>
              Target ({unit})
              <input
                type="number"
                min="0"
                step="any"
                value={target}
                onChange={(event) => setTarget(event.target.value)}
              />
            </label>
          )}
          <label>
            Bar ({unit})
            <input
              type="number"
              min="0"
              step="any"
              value={bar}
              onChange={(event) => setBar(event.target.value)}
            />
          </label>
          <label>
            Each collar ({unit})
            <input
              type="number"
              min="0"
              step="any"
              value={collar}
              onChange={(event) => setCollar(event.target.value)}
            />
          </label>
        </fieldset>
      </form>

      {mode === 'reverse' && (
        <section className="panel">
          <h2>Plates on one side</h2>
          <p className="panel-note">Tap a plate to add it. Tap a plate on the bar to take it off.</p>
          <div className="plate-buttons">
            {stock[unit].map((plate) => (
              <button
                key={plate.weight}
                type="button"
                style={{ borderColor: plateColour(plate.weight, unit) }}
                onClick={() => setOnBar([...onBar, plate.weight])}
              >
                {plate.weight}
              </button>
            ))}
            <button type="button" className="quiet" onClick={() => setOnBar([])}>
              Clear
            </button>
          </div>
        </section>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {mode === 'load' && load.result && (
        <section className="result" aria-live="polite">
          <Barbell perSide={load.result.per_side} unit={unit} />
          <p className="result-label">Each side</p>
          <p className="plate-list">
            {load.result.per_side.length > 0 ? load.result.per_side.join(' + ') : 'Empty bar'}
          </p>
          <dl>
            <div>
              <dt>Loaded</dt>
              <dd>
                {load.result.total} {unit}
              </dd>
            </div>
            {load.result.shortfall > 0.001 && (
              <div>
                <dt>Short of target by</dt>
                <dd>
                  {Number(load.result.shortfall.toFixed(2))} {unit}
                </dd>
              </div>
            )}
          </dl>
        </section>
      )}

      {mode === 'reverse' && reverse.result && (
        <section className="result" aria-live="polite">
          <div
            onClick={(event) => {
              const index = (event.target as HTMLElement).dataset.index
              if (index !== undefined) setOnBar(sorted.filter((_, i) => i !== Number(index)))
            }}
          >
            <div className="barbell" role="img" aria-label={`One side: ${sorted.join(', ') || 'empty'}`}>
              <span className="barbell-shaft" />
              <span className="barbell-collar" />
              {sorted.map((weight, index) => (
                <span
                  key={index}
                  data-index={index}
                  className="plate removable"
                  style={{
                    height: `${Math.max(34, Math.min(100, (weight / (unit === 'lb' ? 45 : 25)) * 100))}%`,
                    background: plateColour(weight, unit),
                  }}
                >
                  {weight}
                </span>
              ))}
              <span className="barbell-end" />
            </div>
          </div>
          <p className="result-label">Total</p>
          <p className="result-value">
            {reverse.result.total} {unit}
          </p>
        </section>
      )}

      <section className="panel">
        <button type="button" className="quiet" onClick={() => setShowStock(!showStock)}>
          {showStock ? 'Hide' : 'Edit'} my plates ({unit})
        </button>
        {showStock && (
          <div className="stock">
            {stock[unit].map((plate, index) => (
              <label key={plate.weight}>
                {plate.weight} {unit} pairs
                <input
                  type="number"
                  min="0"
                  max="50"
                  step="1"
                  value={plate.pairs}
                  onChange={(event) => updateStock(index, Math.max(0, Number(event.target.value) || 0))}
                />
              </label>
            ))}
          </div>
        )}
      </section>
    </>
  )
}

export default Plates
