/**
 * API state handling.
 *
 * Every page loads through this hook, so the three mistakes it exists to prevent would
 * otherwise each have seven chances to appear: setting state after unmount, losing a race
 * between two loads, and showing a previous cylinder's numbers under an error banner.
 */

import { act, render, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useResource } from './useResource'

/** Renders the hook and exposes its latest value to the test. */
function harness(loader, deps = [], options) {
  const seen = { current: null }
  function Probe() {
    seen.current = useResource(loader, deps, options)
    return null
  }
  const utils = render(<Probe />)
  return { seen, ...utils }
}

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useResource', () => {
  it('starts loading and then exposes the data', async () => {
    const { seen } = harness(() => Promise.resolve({ value: 42 }))
    expect(seen.current.loading).toBe(true)

    await waitFor(() => expect(seen.current.loading).toBe(false))
    expect(seen.current.data).toEqual({ value: 42 })
    expect(seen.current.error).toBeNull()
  })

  it('exposes a normalized error', async () => {
    const failure = { status: 409, message: 'No readings yet', fields: {} }
    const { seen } = harness(() => Promise.reject(failure))

    await waitFor(() => expect(seen.current.loading).toBe(false))
    expect(seen.current.error).toEqual(failure)
  })

  it('clears stale data on failure', async () => {
    // Showing the previous cylinder's numbers under an error banner is worse than
    // showing nothing: the figures would look current and be wrong.
    let shouldFail = false
    const loader = vi.fn(() =>
      shouldFail ? Promise.reject({ message: 'gone' }) : Promise.resolve({ kg: 8.2 }),
    )
    const { seen } = harness(loader)

    await waitFor(() => expect(seen.current.data).toEqual({ kg: 8.2 }))

    shouldFail = true
    await act(async () => {
      await seen.current.reload()
    })
    expect(seen.current.error).toBeTruthy()
    expect(seen.current.data).toBeNull()
  })

  it('reload refetches', async () => {
    const loader = vi.fn(() => Promise.resolve({ n: loader.mock.calls.length }))
    const { seen } = harness(loader)

    await waitFor(() => expect(seen.current.loading).toBe(false))
    expect(loader).toHaveBeenCalledTimes(1)

    await act(async () => {
      await seen.current.reload()
    })
    expect(loader).toHaveBeenCalledTimes(2)
  })

  it('a slow first response cannot overwrite a fast second one', async () => {
    // Switching cylinders fires a second request; if the first resolves later, the user
    // would be shown the cylinder they navigated away from.
    const first = deferred()
    const second = deferred()
    const loader = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    const { seen } = harness(loader)

    await act(async () => {
      seen.current.reload()
    })

    await act(async () => {
      second.resolve({ which: 'second' })
      await second.promise
    })
    expect(seen.current.data).toEqual({ which: 'second' })

    // The stale first response arrives afterwards and must be discarded.
    await act(async () => {
      first.resolve({ which: 'first' })
      await first.promise
    })
    expect(seen.current.data).toEqual({ which: 'second' })
  })

  it('does not load while disabled', async () => {
    const loader = vi.fn(() => Promise.resolve('x'))
    const { seen } = harness(loader, [], { enabled: false })

    await waitFor(() => expect(seen.current.loading).toBe(false))
    expect(loader).not.toHaveBeenCalled()
    expect(seen.current.data).toBeNull()
  })

  it('does not set state after unmount', async () => {
    // React logs a warning for this rather than throwing, so the assertion is on the
    // console: an unmounted page must not keep writing state.
    const pending = deferred()
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})

    const { unmount } = harness(() => pending.promise)
    unmount()

    await act(async () => {
      pending.resolve({ late: true })
      await pending.promise
    })

    expect(errors).not.toHaveBeenCalled()
    errors.mockRestore()
  })

  it('setData lets a page apply a mutation without refetching', async () => {
    // How Alerts drops the unread count after mark-as-read.
    const { seen } = harness(() => Promise.resolve({ unread_count: 2 }))
    await waitFor(() => expect(seen.current.data).toEqual({ unread_count: 2 }))

    await act(async () => {
      seen.current.setData((current) => ({ ...current, unread_count: 1 }))
    })
    expect(seen.current.data).toEqual({ unread_count: 1 })
  })
})
