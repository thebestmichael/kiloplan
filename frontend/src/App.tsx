import { useEffect, useState } from 'react'
import './App.css'
import Calculator from './Calculator.tsx'
import Icon from './Icon.tsx'
import Nutrition from './Nutrition.tsx'
import Program from './Program.tsx'

type Theme = 'light' | 'dark'
type Page = 'calculator' | 'program' | 'nutrition'

const PAGES: { id: Page; label: string; subtitle: string }[] = [
  { id: 'calculator', label: 'Calculator', subtitle: 'Loads, plates, rep maxes and points' },
  { id: 'program', label: 'Program', subtitle: 'Upload your program and ask about it' },
  { id: 'nutrition', label: 'Nutrition', subtitle: 'Track your daily intake' },
]

// the page lives in the URL hash (#/program) so reloads and links keep their place
function pageFromHash(): Page {
  const id = window.location.hash.replace(/^#\/?/, '')
  return PAGES.some((page) => page.id === id) ? (id as Page) : 'calculator'
}

function saveTheme(theme: Theme) {
  try {
    localStorage.setItem('theme', theme)
  } catch {
    // storage unavailable: the choice just lasts for this page load
  }
}

function App() {
  // index.html sets data-theme before first paint
  const [theme, setTheme] = useState<Theme>(
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  )
  const [page, setPage] = useState<Page>(pageFromHash)

  useEffect(() => {
    const onHashChange = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  function toggleTheme() {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    document.documentElement.dataset.theme = next
    saveTheme(next)
    setTheme(next)
  }

  const current = PAGES.find((item) => item.id === page)!

  return (
    <>
      <nav className="tabbar" aria-label="Main">
        <span className="brand">KiloPlan</span>
        <div className="tabs">
          {PAGES.map(({ id, label }) => (
            <a key={id} href={`#/${id}`} aria-current={page === id ? 'page' : undefined}>
              <Icon name={id} />
              <span>{label}</span>
            </a>
          ))}
        </div>
      </nav>

      <main className={page === 'calculator' ? undefined : 'wide'}>
        <header className="page-head">
          <div>
            <h1>{current.label}</h1>
            <p>{current.subtitle}</p>
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            onClick={toggleTheme}
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={20} />
          </button>
        </header>
        {page === 'calculator' && <Calculator />}
        {page === 'program' && <Program />}
        {page === 'nutrition' && <Nutrition />}
      </main>
    </>
  )
}

export default App
