/**
 * Status is never colour alone (spec §59).
 *
 * The component has no prop that produces a bare coloured dot, and these tests are what
 * stop one being added: every state must render a readable word.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DemoBadge, EstimateBadge, StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('shows the word SAFE, not just a green dot', () => {
    render(<StatusBadge state="SAFE" />)
    expect(screen.getByText('SAFE')).toBeInTheDocument()
  })

  it.each([
    ['NORMAL', 'NORMAL'],
    ['LOW', 'LOW'],
    ['CRITICAL', 'CRITICAL'],
    ['ONLINE', 'ONLINE'],
    ['OFFLINE', 'OFFLINE'],
    ['UNUSUAL_CONSUMPTION', 'UNUSUAL USE'],
    ['POSSIBLE_LEAK', 'POSSIBLE LEAK'],
    ['CRITICAL_LEAK', 'CRITICAL LEAK'],
    ['GAS_THRESHOLD_EXCEEDED', 'GAS DETECTED'],
  ])('renders a word for %s', (state, expected) => {
    render(<StatusBadge state={state} />)
    expect(screen.getByText(expected)).toBeInTheDocument()
  })

  it('keeps "POSSIBLE" in the leak wording', () => {
    // The MQ-6 is a prototype detector. The UI must not upgrade a suspicion to a fact.
    render(<StatusBadge state="POSSIBLE_LEAK" />)
    expect(screen.getByText('POSSIBLE LEAK')).toBeInTheDocument()
  })

  it('shows an unstyled state verbatim rather than silently dropping it', () => {
    render(<StatusBadge state="SOMETHING_NEW" />)
    expect(screen.getByText('SOMETHING NEW')).toBeInTheDocument()
  })

  it('does not fall over on a missing state', () => {
    render(<StatusBadge state={undefined} />)
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument()
  })
})

describe('EstimateBadge', () => {
  it('says ESTIMATE while no model has run', () => {
    render(<EstimateBadge isEstimate />)
    expect(screen.getByText('ESTIMATE')).toBeInTheDocument()
  })

  it('claims ML only when the backend said the model produced it', () => {
    render(<EstimateBadge isEstimate={false} />)
    expect(screen.getByText('POWERED BY ML')).toBeInTheDocument()
  })
})

describe('DemoBadge', () => {
  it('names simulated data as simulated', () => {
    render(<DemoBadge />)
    expect(screen.getByText(/DEMO MODE/)).toBeInTheDocument()
  })
})
