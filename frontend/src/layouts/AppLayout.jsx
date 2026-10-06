/**
 * The authenticated shell.
 *
 * This is where the app's single WebSocket subscription lives. Mounting it once at the
 * layout, and passing the frame down through an outlet context, is what guarantees one
 * connection no matter how many panels want live data - a panel that called
 * `useWebSocket` itself would still share the socket, but keeping the subscription here
 * means page navigation does not tear it down and rebuild it.
 *
 * Landmarks are explicit: `header`, `nav`, `main`. A skip link is the first focusable
 * thing on the page, so a keyboard user does not have to tab through seven nav items on
 * every navigation to reach the content.
 */

import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { useWebSocket } from '../hooks/useWebSocket'
import { Sidebar, NAV_ITEMS } from './Sidebar'
import { TopNavbar } from './TopNavbar'

// Phase 2a/2b expose a cylinder by id and there is no cylinder-picker endpoint yet, so
// the shell watches the user's first cylinder. Phase 5 replaces this with a selector.
export const ACTIVE_CYLINDER_ID = 1

export function AppLayout() {
  const [navOpen, setNavOpen] = useState(false)
  const location = useLocation()
  const { frame, status } = useWebSocket(ACTIVE_CYLINDER_ID)

  // Close the drawer on navigation, or it stays open over the page the user chose.
  useEffect(() => setNavOpen(false), [location.pathname])

  // Escape closes the drawer: expected for any overlay, and the only way out for
  // someone not using a pointer.
  useEffect(() => {
    if (!navOpen) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setNavOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [navOpen])

  const title =
    NAV_ITEMS.find((item) => location.pathname.startsWith(item.to))?.label ?? 'CylinGuard'

  return (
    <div className="flex min-h-full">
      <a href="#main-content" className="sr-only-focusable">
        Skip to main content
      </a>

      <Sidebar
        open={navOpen}
        onClose={() => setNavOpen(false)}
        socketStatus={status}
        unreadAlerts={frame?.unread_alerts ?? 0}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopNavbar
          onOpenNav={() => setNavOpen(true)}
          title={title}
          demoMode={Boolean(frame?.demo_mode)}
        />

        <main id="main-content" className="flex-1 px-4 py-5 sm:px-6 sm:py-6">
          {/* max-w plus min-w-0 on the flex parents is what keeps wide tables from
              forcing horizontal scroll on the whole page at 360px. */}
          <div className="mx-auto w-full max-w-6xl">
            <Outlet context={{ cylinderId: ACTIVE_CYLINDER_ID, frame, socketStatus: status }} />
          </div>
        </main>
      </div>
    </div>
  )
}
