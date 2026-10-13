import { useState } from 'react'
import type { FormEvent } from 'react'

interface BasisSet {
  description: string
  tab: string
  sheet_cell: string
}

interface Calculation {
  tool: string
  arguments: Record<string, unknown>
  result: Record<string, unknown>
}

interface AssistantResponse {
  status: 'answered' | 'needs_clarification' | 'referred'
  answer: string
  basis_set: BasisSet | null
  calculations: Calculation[]
  flags: string[]
}

const FLAG_LABELS: Record<string, string> = {
  below_chart_range: 'RPE below chart range',
  answer_corrected: 'Answer rewritten after a number check',
  not_checked_against_log: 'Not checked against your log',
  conflict: 'Disagrees with your log',
  ambiguous: 'Several sets match',
  no_match: 'No matching set',
  no_program: 'No program stored',
  cannot_calculate: 'Set cannot be used',
  pain_or_injury: 'Pain or injury',
  no_tool_result: 'Nothing to base an answer on',
}

const EXAMPLE =
  "I took 405 for 3 reps on squat in week 4 at RPE 9. Now I'm on week 1 of a new block and have squat for 2 reps at RPE 5. What weight should I take?"

function Assistant() {
  const [question, setQuestion] = useState('')
  const [response, setResponse] = useState<AssistantResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!question.trim()) return
    setLoading(true)
    setError(null)
    setResponse(null)
    try {
      const result = await fetch('/api/assistant/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      const body = await result.json()
      if (result.ok) {
        setResponse(body as AssistantResponse)
      } else {
        setError(typeof body.detail === 'string' ? body.detail : 'The assistant could not answer.')
      }
    } catch {
      setError('Could not reach the API. Is it running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="panel">
      <h2>Ask about your program</h2>
      <p className="panel-note">
        Answers use your stored sets. Every number comes from a lookup or a calculator, not from
        the language model.
      </p>
      <form className="ask" onSubmit={handleSubmit}>
        <textarea
          rows={3}
          placeholder={EXAMPLE}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {response && (
        <div className="assistant-answer" aria-live="polite">
          <p className="answer-text">{response.answer}</p>
          {response.flags.length > 0 && (
            <p className="flags">
              {response.flags.map((flag) => (
                <span key={flag} className="flag">
                  {FLAG_LABELS[flag] ?? flag}
                </span>
              ))}
            </p>
          )}
          {response.basis_set && (
            <p className="basis">
              <strong>Based on</strong> {response.basis_set.description}
            </p>
          )}
          {response.calculations.length > 0 && (
            <details>
              <summary>How this was worked out ({response.calculations.length} steps)</summary>
              {response.calculations.map((calculation, index) => (
                <pre key={index}>
                  {calculation.tool}({JSON.stringify(calculation.arguments)}){'\n'}
                  {JSON.stringify(calculation.result, null, 2)}
                </pre>
              ))}
            </details>
          )}
        </div>
      )}
    </section>
  )
}

export default Assistant
