/**
 * Error normalisation.
 *
 * Every component reads `{ status, message, fields }`. Without this, each one would need
 * to know that FastAPI puts a string in `detail` for an HTTPException but an array of
 * field errors there for a 422, and that a network failure has no response at all.
 */

import { describe, expect, it } from 'vitest'

import { normalizeError, tokenStore } from './api'

describe('normalizeError', () => {
  it('reads a plain detail string', () => {
    const result = normalizeError({
      response: { status: 404, data: { detail: 'Cylinder not found' } },
    })
    expect(result).toEqual({ status: 404, message: 'Cylinder not found', fields: {} })
  })

  it('maps 422 field errors onto their field names', () => {
    const result = normalizeError({
      response: {
        status: 422,
        data: {
          detail: [
            { loc: ['body', 'email'], msg: 'not a valid email address' },
            { loc: ['body', 'password'], msg: 'too short' },
          ],
        },
      },
    })
    expect(result.status).toBe(422)
    expect(result.fields).toEqual({
      email: 'not a valid email address',
      password: 'too short',
    })
    expect(result.message).toBe('not a valid email address')
  })

  it('explains a 409 as a real product state, not a failure', () => {
    // The backend returns 409 when a cylinder has no readings yet - a device that has
    // never reported, not a bug.
    const result = normalizeError({ response: { status: 409, data: {} } })
    expect(result.message).toMatch(/no data has been recorded/i)
  })

  it('does not leak a raw object into the message', () => {
    const result = normalizeError({
      response: { status: 500, data: { detail: { nested: 'thing' } } },
    })
    expect(result.message).toBe('Something went wrong on the server.')
  })

  it('turns an unreachable server into advice', () => {
    const result = normalizeError({ message: 'Network Error' })
    expect(result.status).toBe(0)
    expect(result.message).toMatch(/cannot reach the server/i)
  })

  it('names a timeout as a timeout', () => {
    const result = normalizeError({ code: 'ECONNABORTED' })
    expect(result.message).toMatch(/timed out/i)
  })

  it('always returns all three keys, whatever went wrong', () => {
    for (const error of [{}, { response: { status: 418, data: null } }, { code: 'X' }]) {
      const result = normalizeError(error)
      expect(Object.keys(result).sort()).toEqual(['fields', 'message', 'status'])
    }
  })
})

describe('tokenStore', () => {
  it('round-trips and clears', () => {
    tokenStore.set('abc')
    expect(tokenStore.get()).toBe('abc')
    tokenStore.clear()
    expect(tokenStore.get()).toBeNull()
  })

  it('survives storage being unavailable', () => {
    // Safari in private mode throws rather than returning null.
    const original = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('blocked')
      },
    })

    expect(() => tokenStore.set('x')).not.toThrow()
    expect(tokenStore.get()).toBeNull()
    expect(() => tokenStore.clear()).not.toThrow()

    Object.defineProperty(globalThis, 'localStorage', original)
  })
})
