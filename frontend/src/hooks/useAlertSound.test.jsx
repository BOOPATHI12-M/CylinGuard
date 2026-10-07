/**
 * The alarm fires on the transition into a critical state, never per frame.
 *
 * At a 5-second demo tick a sustained leak would otherwise beep twelve times a minute,
 * the user would switch the feature off, and the one signal that might reach them from
 * another room would be gone.
 */

import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useCriticalSound } from './useAlertSound'

function Harness({ state, play, enabled = true }) {
  useCriticalSound(state, { enabled, play })
  return null
}

describe('useCriticalSound', () => {
  it('stays silent while the state is normal', () => {
    const play = vi.fn()
    render(<Harness state="SAFE" play={play} />)
    expect(play).not.toHaveBeenCalled()
  })

  it('sounds once when the state turns critical', () => {
    const play = vi.fn()
    const { rerender } = render(<Harness state="SAFE" play={play} />)
    rerender(<Harness state="GAS_THRESHOLD_EXCEEDED" play={play} />)
    expect(play).toHaveBeenCalledTimes(1)
  })

  it('does not repeat while the alarm persists', () => {
    const play = vi.fn()
    const { rerender } = render(<Harness state="SAFE" play={play} />)
    rerender(<Harness state="POSSIBLE_LEAK" play={play} />)
    for (let i = 0; i < 12; i += 1) {
      rerender(<Harness state="POSSIBLE_LEAK" play={play} />)
    }
    expect(play).toHaveBeenCalledTimes(1)
  })

  it('sounds again for a new episode after clearing', () => {
    const play = vi.fn()
    const { rerender } = render(<Harness state="SAFE" play={play} />)
    rerender(<Harness state="POSSIBLE_LEAK" play={play} />)
    rerender(<Harness state="SAFE" play={play} />)
    rerender(<Harness state="CRITICAL_LEAK" play={play} />)
    expect(play).toHaveBeenCalledTimes(2)
  })

  it('never sounds while the preference is off', () => {
    const play = vi.fn()
    const { rerender } = render(<Harness state="SAFE" play={play} enabled={false} />)
    rerender(<Harness state="CRITICAL_LEAK" play={play} enabled={false} />)
    expect(play).not.toHaveBeenCalled()
  })

  it('treats a missing state as not critical', () => {
    const play = vi.fn()
    render(<Harness state={undefined} play={play} />)
    expect(play).not.toHaveBeenCalled()
  })
})
