export interface User {
  id: number
  email: string
  name: string
}

export type Theme = 'light' | 'dark'

export function saveTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  try {
    localStorage.setItem('theme', theme)
  } catch {
    // storage unavailable: the choice just lasts for this page load
  }
}

/** Calls an auth endpoint and returns the user it answers with, or throws its message. */
export async function authRequest(path: string, body?: unknown): Promise<User | null> {
  const response = await fetch(`/api/auth/${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (response.status === 204) return null
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = data?.detail
    if (typeof detail === 'string') throw new Error(detail)
    if (Array.isArray(detail)) {
      const field = String(detail[0]?.loc?.at(-1) ?? '')
      const hints: Record<string, string> = {
        email: 'Enter a valid email address.',
        password: 'Use a password of at least 8 characters.',
        name: 'Enter your name.',
      }
      throw new Error(hints[field] ?? 'Check the details and try again.')
    }
    throw new Error('That did not work. Try again.')
  }
  return data as User
}
