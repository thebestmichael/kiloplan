import { useEffect, useMemo, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'

interface SheetSummary {
  name: string
  blocks: number
  weeks: number
  lines: number
  first_week: string | null
  last_week: string | null
}

interface Issue {
  sheet: string
  cell: string
  message: string
}

interface ProgramRow {
  id: number
  block_index: number
  sheet: string
  cell: string
  week_label: string
  week_start: string | null
  day_label: string
  movement: string
  lift: string
  variation: string
  sets: number | null
  reps_raw: string
  intensity_raw: string
  target_load_raw: string
  actual_load_raw: string
  actual_load_kg: number | null
  rpe: number | null
  rpe_below_5: boolean
  assumed_kg: boolean
}

interface ParseResponse {
  filename: string
  uploaded_at: string
  note_count: number
  sheets: SheetSummary[]
  skipped_sheets: string[]
  issues: Issue[]
  rows: ProgramRow[]
}

const ALL_SHEETS = ''
const MAX_VISIBLE_ROWS = 300

function formatRpe(row: ProgramRow): string {
  if (row.rpe_below_5) return '<5'
  return row.rpe === null ? '' : String(row.rpe)
}

function formatDates(sheet: SheetSummary): string {
  if (!sheet.first_week) return 'no dates'
  return sheet.first_week === sheet.last_week
    ? sheet.first_week
    : `${sheet.first_week} to ${sheet.last_week}`
}

function Program() {
  const [fileName, setFileName] = useState<string | null>(null)
  const [data, setData] = useState<ParseResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [dragging, setDragging] = useState(false)

  const [sheetFilter, setSheetFilter] = useState(ALL_SHEETS)
  const [movementFilter, setMovementFilter] = useState('')
  const [loadedOnly, setLoadedOnly] = useState(false)

  // show the stored program, if there is one
  useEffect(() => {
    let cancelled = false
    fetch('/api/program')
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (!cancelled && body) {
          setData(body as ParseResponse)
          setFileName((body as ParseResponse).filename)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  async function upload(file: File) {
    setFileName(file.name)
    setLoading(true)
    setError(null)
    setData(null)
    setSheetFilter(ALL_SHEETS)
    try {
      const form = new FormData()
      form.append('file', file)
      const response = await fetch('/api/program/upload', { method: 'POST', body: form })
      const body = await response.json()
      if (response.ok) {
        setData(body as ParseResponse)
      } else {
        setError(typeof body.detail === 'string' ? body.detail : 'Could not read this file.')
      }
    } catch {
      setError('Could not reach the API. Is it running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  function handlePick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (file) void upload(file)
    // lets the same file be picked again after a change on disk
    event.target.value = ''
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files[0]
    if (file) void upload(file)
  }

  const filtered = useMemo(() => {
    if (!data) return []
    const search = movementFilter.trim().toLowerCase()
    return data.rows.filter(
      (row) =>
        (sheetFilter === ALL_SHEETS || row.sheet === sheetFilter) &&
        (!search || row.movement.toLowerCase().includes(search)) &&
        (!loadedOnly || row.actual_load_kg !== null),
    )
  }, [data, sheetFilter, movementFilter, loadedOnly])

  const issues = data
    ? data.issues.filter((issue) => sheetFilter === ALL_SHEETS || issue.sheet === sheetFilter)
    : []

  return (
    <>
      <div className="page-intro">
        <p>Upload your coach's spreadsheet to store your program and check what was read.</p>
      </div>

      <label
        className="dropzone"
        data-dragging={dragging}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <input type="file" accept=".xlsx" onChange={handlePick} />
        <strong>{loading ? 'Reading…' : 'Choose an .xlsx file or drop it here'}</strong>
        <span>
          {fileName
            ? `${fileName} is stored. Uploading again replaces it.`
            : 'The file is read, stored and shown below.'}
        </span>
      </label>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {data && (
        <>
          <section className="panel">
            <h2>Summary</h2>
            <p className="panel-note">
              {data.rows.length} lines and {data.note_count} notes stored from {data.sheets.length}{' '}
              tabs.
              {data.skipped_sheets.length > 0 &&
                ` Skipped tabs with no weeks: ${data.skipped_sheets.join(', ')}.`}
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Tab</th>
                    <th className="number">Blocks</th>
                    <th className="number">Weeks</th>
                    <th className="number">Lines</th>
                    <th>Week dates</th>
                  </tr>
                </thead>
                <tbody>
                  {data.sheets.map((sheet) => (
                    <tr key={sheet.name}>
                      <td>{sheet.name}</td>
                      <td className="number">{sheet.blocks}</td>
                      <td className="number">{sheet.weeks}</td>
                      <td className="number">{sheet.lines}</td>
                      <td>{formatDates(sheet)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <h2>Parsed lines</h2>
            <div className="filters">
              <label>
                Tab
                <select value={sheetFilter} onChange={(event) => setSheetFilter(event.target.value)}>
                  <option value={ALL_SHEETS}>All tabs</option>
                  {data.sheets.map((sheet) => (
                    <option key={sheet.name} value={sheet.name}>
                      {sheet.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Movement
                <input
                  type="search"
                  placeholder="e.g. squat"
                  value={movementFilter}
                  onChange={(event) => setMovementFilter(event.target.value)}
                />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={loadedOnly}
                  onChange={(event) => setLoadedOnly(event.target.checked)}
                />
                Only lines with a load
              </label>
            </div>
            <p className="panel-note">
              {filtered.length > MAX_VISIBLE_ROWS
                ? `Showing the first ${MAX_VISIBLE_ROWS} of ${filtered.length} lines. Filter to narrow it down.`
                : `${filtered.length} lines.`}
            </p>
            <div className="table-scroll tall">
              <table>
                <thead>
                  <tr>
                    <th>Tab</th>
                    <th className="number">Block</th>
                    <th>Week</th>
                    <th>Week of</th>
                    <th>Day</th>
                    <th>Movement</th>
                    <th>Lift</th>
                    <th className="number">Sets</th>
                    <th>Reps</th>
                    <th>Intensity</th>
                    <th>Target</th>
                    <th>Load in sheet</th>
                    <th className="number">Load (kg)</th>
                    <th>RPE</th>
                    <th>Cell</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.slice(0, MAX_VISIBLE_ROWS).map((row) => (
                    <tr key={row.id}>
                      <td>{row.sheet}</td>
                      <td className="number">{row.block_index + 1}</td>
                      <td>{row.week_label}</td>
                      <td>{row.week_start ?? ''}</td>
                      <td>{row.day_label}</td>
                      <td>{row.movement}</td>
                      <td>{row.lift === 'other' ? '' : `${row.lift}, ${row.variation}`}</td>
                      <td className="number">{row.sets ?? ''}</td>
                      <td>{row.reps_raw}</td>
                      <td>{row.intensity_raw}</td>
                      <td>{row.target_load_raw}</td>
                      <td>{row.actual_load_raw}</td>
                      <td className="number">
                        {row.actual_load_kg === null ? '' : row.actual_load_kg.toFixed(1)}
                        {row.assumed_kg && <span className="tag">typed in kg</span>}
                      </td>
                      <td>{formatRpe(row)}</td>
                      <td>{row.cell}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <h2>Needs review</h2>
            <p className="panel-note">
              {issues.length === 0
                ? 'Nothing to review.'
                : `${issues.length} things the parser corrected or could not read.`}
            </p>
            {issues.length > 0 && (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Tab</th>
                      <th>Cell</th>
                      <th>What was found</th>
                    </tr>
                  </thead>
                  <tbody>
                    {issues.map((issue, index) => (
                      <tr key={index}>
                        <td>{issue.sheet}</td>
                        <td>{issue.cell}</td>
                        <td>{issue.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </>
  )
}

export default Program
