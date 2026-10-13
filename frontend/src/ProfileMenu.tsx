import { useEffect, useRef, useState } from 'react'
import type { Theme, User } from './account.ts'
import Icon from './Icon.tsx'

function ProfileMenu({
  user,
  theme,
  onToggleTheme,
  onLogOut,
}: {
  user: User | null
  theme: Theme
  onToggleTheme: () => void
  onLogOut: () => void
}) {
  const [open, setOpen] = useState(false)
  const container = useRef<HTMLDivElement>(null)

  // close on a click elsewhere or on Escape
  useEffect(() => {
    if (!open) return
    const onPointer = (event: PointerEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const close = () => setOpen(false)

  return (
    <div className="profile" ref={container}>
      <button
        type="button"
        className="avatar"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={user ? `Account menu for ${user.name}` : 'Account menu'}
        onClick={() => setOpen(!open)}
      >
        {user ? user.name.trim().charAt(0).toUpperCase() : <Icon name="user" size={20} />}
      </button>

      {open && (
        <div className="profile-menu" role="menu">
          <div className="profile-who">
            <span className="avatar large" aria-hidden="true">
              {user ? user.name.trim().charAt(0).toUpperCase() : <Icon name="user" />}
            </span>
            <div>
              <strong>{user ? user.name : 'Guest'}</strong>
              <span>{user ? user.email : 'Not signed in'}</span>
            </div>
          </div>

          <hr />
          <a role="menuitem" href="#/settings" onClick={close}>
            <Icon name="settings" size={20} /> Settings
          </a>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onToggleTheme()
              close()
            }}
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={20} />
            {theme === 'dark' ? 'Light mode' : 'Dark mode'}
          </button>

          <hr />
          {user ? (
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                onLogOut()
                close()
              }}
            >
              <Icon name="log-out" size={20} /> Sign out
            </button>
          ) : (
            <>
              <a role="menuitem" href="#/login" onClick={close}>
                <Icon name="log-in" size={20} /> Log in
              </a>
              <a role="menuitem" href="#/signup" onClick={close}>
                <Icon name="sign-up" size={20} /> Sign up
              </a>
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default ProfileMenu
