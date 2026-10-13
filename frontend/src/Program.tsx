import { useEffect, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import Assistant from './Assistant.tsx'

interface StoredProgram {
  filename: string
}

function Program() {
  const [fileName, setFileName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [dragging, setDragging] = useState(false)

  // find out whether a program is already stored
  useEffect(() => {
    let cancelled = false
    fetch('/api/program')
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (!cancelled && body) setFileName((body as StoredProgram).filename)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  async function upload(file: File) {
    setLoading(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const response = await fetch('/api/program/upload', { method: 'POST', body: form })
      const body = await response.json()
      if (response.ok) {
        setFileName((body as StoredProgram).filename)
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

  return (
    <>
      <div className="page-intro">
        <p>Upload your coach's spreadsheet, then ask questions about your program.</p>
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
            : 'The file is read and stored for the assistant to use.'}
        </span>
      </label>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {fileName && <Assistant />}
    </>
  )
}

export default Program
