/**
 * Load one thing from the API, with loading / error / retry.
 *
 * Every page needs the same four states and the same three mistakes are easy to make:
 * setting state after unmount, losing a race between two loads, and conflating "still
 * loading" with "loaded and empty". This handles all three in one place so seven pages
 * do not each get it slightly wrong.
 *
 * `reload` is exposed for the retry button and for refreshing after a mutation.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export function useResource(loader, deps = [], { enabled = true } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(enabled)

  // Incremented per load. A response whose id is stale is discarded, so a slow first
  // request cannot overwrite a fast second one.
  const requestId = useRef(0)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const run = useCallback(async () => {
    if (!enabled) {
      setLoading(false)
      return
    }
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    try {
      const result = await loader()
      if (mounted.current && id === requestId.current) setData(result)
    } catch (failure) {
      if (mounted.current && id === requestId.current) {
        setError(failure)
        // Clear stale data: showing the previous cylinder's numbers under an error
        // banner would be worse than showing nothing.
        setData(null)
      }
    } finally {
      if (mounted.current && id === requestId.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps])

  useEffect(() => {
    run()
  }, [run])

  return { data, error, loading, reload: run, setData }
}
