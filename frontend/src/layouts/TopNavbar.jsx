/**
 * The page header: hamburger on small screens, demo badge, signed-in user, sign out.
 *
 * The demo badge lives here rather than on the dashboard because it has to be visible
 * on every page (spec §35-36). If it only appeared on the dashboard, a user reading the
 * History table would have no way to know the rows were generated.
 */

import { LogOut, Menu } from 'lucide-react'

import { DemoBadge } from '../components/StatusBadge'
import { useAuth } from '../context/AuthContext'

export function TopNavbar({ onOpenNav, title, demoMode }) {
  const { user, signOut } = useAuth()

  return (
    <header className="sticky top-0 z-30 border-b border-hairline bg-base/80 backdrop-blur-xl">
      <div className="flex items-center gap-3 px-4 py-3 sm:px-6">
        <button
          type="button"
          onClick={onOpenNav}
          className="rounded-lg border border-hairline p-2 text-ink-muted hover:text-ink lg:hidden"
          aria-label="Open navigation"
        >
          <Menu aria-hidden="true" className="h-5 w-5" />
        </button>

        <h1 className="min-w-0 flex-1 truncate text-base font-semibold text-ink sm:text-lg">
          {title}
        </h1>

        {demoMode ? <DemoBadge className="hidden sm:inline-flex" /> : null}

        <div className="flex items-center gap-2">
          {user ? (
            <span className="hidden text-xs text-ink-muted sm:inline" title={user.email}>
              {user.name}
            </span>
          ) : null}
          <button
            type="button"
            onClick={signOut}
            className="rounded-lg border border-hairline p-2 text-ink-muted hover:border-hairline-strong hover:text-ink"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* On a phone the badge would crowd the title row, so it gets its own line. */}
      {demoMode ? (
        <div className="border-t border-hairline px-4 py-2 sm:hidden">
          <DemoBadge />
        </div>
      ) : null}
    </header>
  )
}
