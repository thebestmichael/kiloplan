import { useEffect, useState } from 'react'

const DEBOUNCE_MS = 200

interface ValidationIssue {
  loc: (string | number)[]
  msg: string
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

/**
 * Posts `body` to a calculator endpoint shortly after it stops changing.
 * Pass null while the inputs are incomplete; nothing is sent and nothing is shown.
 */
export function useCalculation<T>(path: string, body: string | null) {
  const [result, setResult] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (body === null) return
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(path, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body,
          signal: controller.signal,
        })
        const data = await response.json()
        if (response.ok) {
          setResult(data as T)
          setError(null)
        } else {
          setResult(null)
          setError(errorMessage(data.detail))
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
  }, [path, body])

  return body === null ? { result: null, error: null } : { result, error }
}
