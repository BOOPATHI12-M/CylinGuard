/**
 * Device connectivity, and whether the page is actually live.
 *
 * Two different things that look alike and must not be confused:
 *
 * * **Device status** - is the ESP32 reporting? Derived by the backend from `last_seen`.
 * * **Socket status** - is *this browser tab* receiving pushes? If the socket is
 *   reconnecting, the numbers on screen are stale even though the device is fine.
 *
 * Showing only the first would let a user trust a frozen dashboard. So when the device
 * is offline the component says the readings are the last received, not current.
 */

import { Radio, RefreshCw, WifiOff } from 'lucide-react'

import { STATUS } from '../hooks/useWebSocket'
import { StatusBadge } from './StatusBadge'

function relativeTime(value) {
  if (!value) return 'never'
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`
  return `${Math.round(seconds / 86400)}d ago`
}

export function DeviceStatus({ device, socketStatus, className = '' }) {
  if (!device) {
    return (
      <div className={`glass p-4 ${className}`}>
        <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">Device</p>
        <p className="mt-2 text-sm text-ink-muted">No device registered for this cylinder.</p>
      </div>
    )
  }

  const offline = device.status === 'OFFLINE'

  return (
    <div className={`glass p-4 ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">Device</p>
          <p className="mt-1 truncate font-mono text-sm text-ink">{device.device_code}</p>
        </div>
        <StatusBadge state={device.status} size="sm" />
      </div>

      <dl className="mt-3 space-y-1.5 text-xs">
        <div className="flex justify-between gap-2">
          <dt className="text-ink-faint">Last reported</dt>
          <dd className="tabular text-ink-muted">{relativeTime(device.last_seen)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-ink-faint">WiFi</dt>
          <dd className="text-ink-muted">{device.wifi_status}</dd>
        </div>
        {device.firmware_version ? (
          <div className="flex justify-between gap-2">
            <dt className="text-ink-faint">Firmware</dt>
            <dd className="font-mono text-ink-muted">{device.firmware_version}</dd>
          </div>
        ) : null}
      </dl>

      {offline ? (
        <p className="mt-3 rounded-lg border border-hairline bg-surface-overlay/60 px-2.5 py-2 text-[11px] leading-relaxed text-ink-muted">
          Readings shown are the last received, not current. Check the device power and WiFi.
        </p>
      ) : null}

      <ConnectivityLine socketStatus={socketStatus} className="mt-3" />
    </div>
  )
}

/**
 * The live-connection line from spec §10-11. Also used in the sidebar footer, which is
 * why it is exported separately.
 */
export function ConnectivityLine({ socketStatus, className = '' }) {
  const presentation = {
    [STATUS.open]: { icon: Radio, text: 'Live', tone: 'text-safe' },
    [STATUS.connecting]: { icon: RefreshCw, text: 'Connecting…', tone: 'text-ink-muted' },
    [STATUS.reconnecting]: { icon: RefreshCw, text: 'Reconnecting…', tone: 'text-warn' },
    [STATUS.closed]: { icon: WifiOff, text: 'Not connected', tone: 'text-ink-muted' },
    // Terminal: no amount of waiting fixes a rejected token, so do not imply a retry.
    [STATUS.unauthorized]: { icon: WifiOff, text: 'Live updates unavailable', tone: 'text-danger' },
  }[socketStatus] ?? { icon: WifiOff, text: 'Not connected', tone: 'text-ink-muted' }

  const Icon = presentation.icon
  const spinning = socketStatus === STATUS.connecting || socketStatus === STATUS.reconnecting

  return (
    <p className={`flex items-center gap-1.5 text-[11px] ${presentation.tone} ${className}`}>
      <Icon
        aria-hidden="true"
        className={`h-3 w-3 ${spinning ? 'animate-spin motion-reduce:animate-none' : ''}`}
      />
      {presentation.text}
    </p>
  )
}
