import { useState } from 'react'
import Attempts from './tools/Attempts.tsx'
import Plates from './tools/Plates.tsx'
import Points from './tools/Points.tsx'
import RepMaxes from './tools/RepMaxes.tsx'
import RpeLoad from './tools/RpeLoad.tsx'
import type { Unit } from './units.ts'

const TOOLS = [
  { id: 'rpe', label: 'RPE load', description: 'Calculate target weights based on Rate of Perceived Exertion' },
  { id: 'plates', label: 'Plates', description: 'Work out which plates to load, or what a loaded bar weighs' },
  { id: 'rep-maxes', label: 'Rep maxes', description: 'Estimate 1 to 10 rep maxes and an RPE chart from one set' },
  { id: 'points', label: 'Points', description: 'Wilks, DOTS and IPF GL points for a total' },
  { id: 'attempts', label: 'Attempts', description: 'Pick an opener, second and third attempt for a meet' },
] as const

type ToolId = (typeof TOOLS)[number]['id']

function Calculator() {
  const [tool, setTool] = useState<ToolId>('rpe')
  const [unit, setUnit] = useState<Unit>('kg')
  const active = TOOLS.find((item) => item.id === tool)!

  return (
    <>
      <div className="tool-tabs" role="tablist" aria-label="Calculators">
        {TOOLS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tool === item.id}
            onClick={() => setTool(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="page-intro">
        <p>{active.description}</p>
        <div className="toolbar">
          <button
            type="button"
            className="unit-switch"
            role="switch"
            aria-checked={unit === 'lb'}
            aria-label="Show weights in pounds"
            data-unit={unit}
            onClick={() => setUnit(unit === 'kg' ? 'lb' : 'kg')}
          >
            <span className="unit-switch-thumb" />
            <span className="unit-switch-label">kg</span>
            <span className="unit-switch-label">lb</span>
          </button>
        </div>
      </div>

      {/* every tool stays mounted so its inputs survive switching tabs */}
      <div hidden={tool !== 'rpe'}>
        <RpeLoad unit={unit} />
      </div>
      <div hidden={tool !== 'plates'}>
        <Plates unit={unit} />
      </div>
      <div hidden={tool !== 'rep-maxes'}>
        <RepMaxes unit={unit} />
      </div>
      <div hidden={tool !== 'points'}>
        <Points unit={unit} />
      </div>
      <div hidden={tool !== 'attempts'}>
        <Attempts unit={unit} />
      </div>
    </>
  )
}

export default Calculator
