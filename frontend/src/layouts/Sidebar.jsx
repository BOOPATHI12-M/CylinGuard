/**
 * The fixed navigation (spec §10-11), collapsing to an off-canvas drawer on phones.
 *
 * The drawer is rendered in the same DOM order as the desktop rail rather than being
 * teleported elsewhere, so tab order follows reading order on both. On mobile it is
 * `aria-hidden` while closed, which keeps a closed drawer out of the tab order - an
 * invisible but focusable menu is a classic keyboard trap.
 */

import {
  Activity,
  BellRing,
  Gauge,
  History,
  Settings,
  ShieldCheck,
  TrendingUp,
  X,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'

import { ConnectivityLine } from '../components/DeviceStatus'

export const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: Gauge },
  { to: '/consumption', label: 'Consumption', icon: Activity },
  { to: '/prediction', label: 'Prediction', icon: TrendingUp },
  { to: '/safety', label: 'Safety', icon: ShieldCheck },
  { to: '/history', label: 'History', icon: History },
  { to: '/alerts', label: 'Alerts', icon: BellRing },
  { to: '/settings', label: 'Settings', icon: Settings },
]

function NavItems({ onNavigate, unreadAlerts }) {
  return (
    <ul className="space-y-1">
      {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
        <li key={to}>
          <NavLink
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl2 px-3 py-2.5 text-sm transition-colors ${
                isActive
                  ? 'border border-accent/30 bg-accent-soft text-accent'
                  : 'border border-transparent text-ink-muted hover:bg-surface-raised/60 hover:text-ink'
              }`
            }
          >
            <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
            <span className="flex-1">{label}</span>
            {label === 'Alerts' && unreadAlerts > 0 ? (
              <span
                className="tabular rounded-full bg-danger px-1.5 py-0.5 text-[10px] font-bold text-base"
                // The count alone would read as a bare number out of context.
                aria-label={`${unreadAlerts} unread alerts`}
              >
                {unreadAlerts}
              </span>
            ) : null}
          </NavLink>
        </li>
      ))}
    </ul>
  )
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-1">
      <span
        aria-hidden="true"
        className="grid h-8 w-8 place-items-center rounded-xl2 border border-accent/30 bg-accent-soft text-accent"
      >
        <ShieldCheck className="h-4 w-4" />
      </span>
      <div className="leading-tight">
        <p className="text-sm font-semibold text-ink">CylinGuard</p>
        <p className="text-[10px] uppercase tracking-wider text-ink-faint">LPG Guardian</p>
      </div>
    </div>
  )
}

export function Sidebar({ open, onClose, socketStatus, unreadAlerts = 0 }) {
  return (
    <>
      {/* Desktop rail */}
      <nav
        aria-label="Main navigation"
        className="hidden w-60 shrink-0 flex-col border-r border-hairline bg-surface/40 p-4 backdrop-blur-xl lg:flex"
      >
        <Brand />
        <div className="mt-6 flex-1">
          <NavItems unreadAlerts={unreadAlerts} />
        </div>
        <div className="border-t border-hairline pt-3">
          <ConnectivityLine socketStatus={socketStatus} />
          <p className="mt-1.5 text-[10px] leading-relaxed text-ink-faint">
            Prototype monitoring. Not a certified gas-safety device.
          </p>
        </div>
      </nav>

      {/* Mobile drawer */}
      <div
        className={`fixed inset-0 z-40 lg:hidden ${open ? '' : 'pointer-events-none'}`}
        aria-hidden={!open}
      >
        <div
          className={`absolute inset-0 bg-base/80 backdrop-blur-sm transition-opacity ${
            open ? 'opacity-100' : 'opacity-0'
          }`}
          onClick={onClose}
        />
        <nav
          aria-label="Main navigation"
          className={`absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-hairline bg-surface p-4 transition-transform ${
            open ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          <div className="flex items-center justify-between">
            <Brand />
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-ink-muted hover:text-ink"
              aria-label="Close navigation"
            >
              <X aria-hidden="true" className="h-5 w-5" />
            </button>
          </div>
          <div className="mt-6 flex-1 overflow-y-auto">
            <NavItems onNavigate={onClose} unreadAlerts={unreadAlerts} />
          </div>
          <div className="border-t border-hairline pt-3">
            <ConnectivityLine socketStatus={socketStatus} />
          </div>
        </nav>
      </div>
    </>
  )
}
