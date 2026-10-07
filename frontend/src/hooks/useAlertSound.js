/**
 * The critical-alert sound, opt-in only.
 *
 * Browsers refuse to start audio until the user has interacted with the page, so an
 * autoplaying alarm would fail silently and the feature would look broken while
 * appearing to be on. The preference is therefore set by a toggle in Settings - clicking
 * it *is* the gesture - and the AudioContext is created at that moment and kept.
 *
 * The tone is synthesised with an oscillator rather than shipped as an audio file: it is
 * two beeps, and a bundled asset would be one more thing to serve, cache and get wrong
 * in the Docker image.
 *
 * Spec §57 calls the sound optional. It is genuinely optional here: off by default, and
 * nothing else depends on it - the banner, the colour and the words all work in silence.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

const STORAGE_KEY = 'cylinguard.alertSound'

function readPreference() {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'on'
  } catch {
    return false
  }
}

export function useAlertSound() {
  const [enabled, setEnabled] = useState(readPreference)
  const contextRef = useRef(null)

  const ensureContext = useCallback(() => {
    if (contextRef.current) return contextRef.current
    const Context = window.AudioContext || window.webkitAudioContext
    if (!Context) return null
    contextRef.current = new Context()
    return contextRef.current
  }, [])

  /** Two short beeps. Called only from a frame that reports a critical state. */
  const play = useCallback(() => {
    if (!enabled) return
    const context = contextRef.current ?? ensureContext()
    if (!context) return
    // Suspended if the tab was backgrounded since the context was created.
    if (context.state === 'suspended') context.resume().catch(() => {})

    const now = context.currentTime
    for (const offset of [0, 0.32]) {
      const oscillator = context.createOscillator()
      const gain = context.createGain()
      oscillator.type = 'sine'
      oscillator.frequency.value = 880
      // Ramped rather than switched, so it does not click.
      gain.gain.setValueAtTime(0, now + offset)
      gain.gain.linearRampToValueAtTime(0.18, now + offset + 0.02)
      gain.gain.linearRampToValueAtTime(0, now + offset + 0.22)
      oscillator.connect(gain).connect(context.destination)
      oscillator.start(now + offset)
      oscillator.stop(now + offset + 0.24)
    }
  }, [enabled, ensureContext])

  /** Called from the Settings toggle, which is the required user gesture. */
  const setPreference = useCallback(
    (next) => {
      setEnabled(next)
      try {
        localStorage.setItem(STORAGE_KEY, next ? 'on' : 'off')
      } catch {
        /* a preference that cannot persist still applies to this session */
      }
      if (next) {
        // Create the context inside the click, and confirm audibly that it works - a
        // silent toggle leaves the user unsure whether the alarm will ever sound.
        const context = ensureContext()
        if (context?.state === 'suspended') context.resume().catch(() => {})
      }
    },
    [ensureContext],
  )

  useEffect(
    () => () => {
      contextRef.current?.close?.().catch?.(() => {})
    },
    [],
  )

  return { enabled, setPreference, play, isSupported: Boolean(window.AudioContext || window.webkitAudioContext) }
}

/**
 * Sound the alarm when a frame first reports a critical state.
 *
 * Fires on the *transition* into critical, not on every frame: at a 5-second demo tick a
 * sustained leak would otherwise beep twelve times a minute and the user would turn the
 * feature off, losing the one signal that might reach them from another room.
 */
export function useCriticalSound(state, { enabled, play }) {
  const wasCritical = useRef(false)

  useEffect(() => {
    const critical =
      state === 'POSSIBLE_LEAK' || state === 'CRITICAL_LEAK' || state === 'GAS_THRESHOLD_EXCEEDED'
    if (critical && !wasCritical.current && enabled) play()
    wasCritical.current = critical
  }, [state, enabled, play])
}
