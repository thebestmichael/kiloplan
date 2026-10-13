import { useEffect, useState } from 'react'
import './App.css'
import Calculator from './Calculator.tsx'
import Nutrition from './Nutrition.tsx'
import Program from './Program.tsx'

type Theme = 'light' | 'dark'
type Page = 'calculator' | 'program' | 'nutrition'

const PAGES: { id: Page; label: string }[] = [
  { id: 'calculator', label: 'Calculator' },
  { id: 'program', label: 'Program' },
  { id: 'nutrition', label: 'Nutrition' },
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

  return (
    <>
      <header className="topbar">
        <h1>KiloPlan</h1>
        <nav aria-label="Main">
          {PAGES.map(({ id, label }) => (
            <a key={id} href={`#/${id}`} aria-current={page === id ? 'page' : undefined}>
              {label}
            </a>
          ))}
        </nav>
        <button type="button" className="theme-toggle" onClick={toggleTheme}>
          {theme === 'dark' ? 'Light mode' : 'Dark mode'}
        </button>
      </header>

      <main className={page === 'calculator' ? undefined : 'wide'}>
        {page === 'calculator' && <Calculator />}
        {page === 'program' && <Program />}
        {page === 'nutrition' && <Nutrition />}
      </main>
    </>
  )
}

export default App
