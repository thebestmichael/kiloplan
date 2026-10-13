import { useState } from 'react'
import type { FormEvent } from 'react'
import { authRequest } from './account.ts'
import type { User } from './account.ts'

function AuthForm({ mode, onDone }: { mode: 'login' | 'signup'; onDone: (user: User) => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const signingUp = mode === 'signup'

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const body = signingUp ? { name, email, password } : { email, password }
      const user = await authRequest(mode, body)
      if (user) onDone(user)
    } catch (problem) {
      setError((problem as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <form className="auth-form" onSubmit={submit}>
        {signingUp && (
          <label>
            Name
            <input
              type="text"
              required
              autoComplete="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
        )}
        <label>
          Email
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            required
            minLength={signingUp ? 8 : undefined}
            autoComplete={signingUp ? 'new-password' : 'current-password'}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {signingUp && <p className="panel-note">At least 8 characters.</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {signingUp ? 'Create account' : 'Log in'}
        </button>
      </form>
      <p className="panel-note auth-switch">
        {signingUp ? 'Already have an account? ' : 'New here? '}
        <a href={signingUp ? '#/login' : '#/signup'}>{signingUp ? 'Log in' : 'Sign up'}</a>
      </p>
    </section>
  )
}

export default AuthForm
