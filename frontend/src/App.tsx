import { useEffect, useState } from 'react'
import './App.css'
import { authRequest, saveTheme } from './account.ts'
import type { Theme, User } from './account.ts'
import AuthForm from './AuthForm.tsx'
import Calculator from './Calculator.tsx'
import Icon from './Icon.tsx'
import Nutrition from './Nutrition.tsx'
import ProfileMenu from './ProfileMenu.tsx'
import Program from './Program.tsx'
import Settings from './Settings.tsx'

const TABS = ['calculator', 'program', 'nutrition'] as const
const PAGES = {
  calculator: { label: 'Calculator', subtitle: 'Loads, plates, rep maxes and points' },
  program: { label: 'Program', subtitle: 'Upload your program and ask about it' },
  nutrition: { label: 'Nutrition', subtitle: 'Track your daily intake' },
  settings: { label: 'Settings', subtitle: 'Your account and preferences' },
  login: { label: 'Log in', subtitle: 'Welcome back' },
  signup: { label: 'Sign up', subtitle: 'Keep your program and diary to yourself' },
}

type Page = keyof typeof PAGES

// the page lives in the URL hash (#/program) so reloads and links keep their place
function pageFromHash(): Page {
  const id = window.location.hash.replace(/^#\/?/, '')
  return id in PAGES ? (id as Page) : 'calculator'
}

function App() {
  // index.html sets data-theme before first paint
  const [theme, setTheme] = useState<Theme>(
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  )
  const [page, setPage] = useState<Page>(pageFromHash)
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    const onHashChange = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    let cancelled = false
    fetch('/api/auth/me')
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (!cancelled && body) setUser(body.user as User | null)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  function chooseTheme(next: Theme) {
    saveTheme(next)
    setTheme(next)
  }

  async function logOut() {
    await authRequest('logout').catch(() => null)
    setUser(null)
  }

  function signedIn(next: User) {
    setUser(next)
    window.location.hash = '#/nutrition'
  }

  const current = PAGES[page]

  return (
    <>
      <nav className="tabbar" aria-label="Main">
        <span className="brand">KiloPlan</span>
        <div className="tabs">
          {TABS.map((id) => (
            <a key={id} href={`#/${id}`} aria-current={page === id ? 'page' : undefined}>
              <Icon name={id} />
              <span>{PAGES[id].label}</span>
            </a>
          ))}
        </div>
      </nav>

      {/* remounting on a change of account makes every page load that account's data */}
      <main key={user?.id ?? 'guest'} className={page === 'calculator' ? undefined : 'wide'}>
        <header className="page-head">
          <div>
            <h1>{current.label}</h1>
            <p>{current.subtitle}</p>
          </div>
          <ProfileMenu
            user={user}
            theme={theme}
            onToggleTheme={() => chooseTheme(theme === 'dark' ? 'light' : 'dark')}
            onLogOut={() => void logOut()}
          />
        </header>
        {page === 'calculator' && <Calculator />}
        {page === 'program' && <Program />}
        {page === 'nutrition' && <Nutrition />}
        {page === 'settings' && (
          <Settings user={user} theme={theme} onTheme={chooseTheme} onLogOut={() => void logOut()} />
        )}
        {(page === 'login' || page === 'signup') && (
          <AuthForm key={page} mode={page} onDone={signedIn} />
        )}
      </main>
    </>
  )
}

export default App
