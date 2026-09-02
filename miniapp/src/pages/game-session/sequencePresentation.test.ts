import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  SEQUENCE_TRANSITION_MS,
  advanceSequenceRevealCursor,
  buildSequenceAnswerSlots,
  createSequenceRevealScheduler,
  sequenceRevealDelay,
  type SequenceRevealCursor,
} from './sequencePresentation'

describe('sequence reveal cursor', () => {
  it('inserts a 500ms transition only between items', () => {
    const first: SequenceRevealCursor = { index: 0, phase: 'item' }
    const gap = advanceSequenceRevealCursor(first, 3)
    const second = gap ? advanceSequenceRevealCursor(gap, 3) : null

    expect(gap).toEqual({ index: 1, phase: 'transition' })
    expect(sequenceRevealDelay(gap!, 900)).toBe(SEQUENCE_TRANSITION_MS)
    expect(second).toEqual({ index: 1, phase: 'item' })
    expect(sequenceRevealDelay(second!, 900)).toBe(900)
  })

  it('finishes immediately after the final item without a trailing gap', () => {
    expect(advanceSequenceRevealCursor({ index: 2, phase: 'item' }, 3)).toBeNull()
  })

  it('uses the same cursor transitions when adjacent values are equal', () => {
    const sequence = ['sun', 'sun']
    let cursor: SequenceRevealCursor | null = { index: 0, phase: 'item' }
    cursor = advanceSequenceRevealCursor(cursor, sequence.length)
    expect(cursor).toEqual({ index: 1, phase: 'transition' })
    cursor = advanceSequenceRevealCursor(cursor!, sequence.length)
    expect(cursor).toEqual({ index: 1, phase: 'item' })
  })
})

describe('buildSequenceAnswerSlots', () => {
  it('keeps empty slots numbered and marks each selected position independently', () => {
    expect(buildSequenceAnswerSlots(['sun', 'boat', 'shell'], ['sun', 'shell'])).toEqual([
      { index: 0, expected: 'sun', selected: 'sun', correct: true },
      { index: 1, expected: 'boat', selected: 'shell', correct: false },
      { index: 2, expected: 'shell', selected: null, correct: null },
    ])
  })

  it('handles repeated values by position rather than collapsing duplicates', () => {
    expect(buildSequenceAnswerSlots(['blue', 'blue'], ['blue', 'blue'])).toEqual([
      { index: 0, expected: 'blue', selected: 'blue', correct: true },
      { index: 1, expected: 'blue', selected: 'blue', correct: true },
    ])
  })
})

describe('sequence reveal scheduler', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('resumes an item with only its unelapsed reveal time', () => {
    vi.useFakeTimers()
    const cursors: SequenceRevealCursor[] = []
    const scheduler = createSequenceRevealScheduler({
      sequenceLength: 2,
      revealMs: 900,
      onCursor: (cursor) => cursors.push(cursor),
      onComplete: () => undefined,
    })

    scheduler.start({ index: 0, phase: 'item' })
    vi.advanceTimersByTime(400)
    scheduler.pause()
    vi.advanceTimersByTime(1000)
    expect(cursors).toEqual([{ index: 0, phase: 'item' }])

    scheduler.resume()
    vi.advanceTimersByTime(499)
    expect(cursors).toEqual([{ index: 0, phase: 'item' }])
    vi.advanceTimersByTime(1)
    expect(cursors).toEqual([
      { index: 0, phase: 'item' },
      { index: 1, phase: 'transition' },
    ])
  })

  it('resumes a transition with only its unelapsed gap time', () => {
    vi.useFakeTimers()
    const cursors: SequenceRevealCursor[] = []
    const scheduler = createSequenceRevealScheduler({
      sequenceLength: 2,
      revealMs: 900,
      onCursor: (cursor) => cursors.push(cursor),
      onComplete: () => undefined,
    })

    scheduler.start({ index: 0, phase: 'item' })
    vi.advanceTimersByTime(900)
    vi.advanceTimersByTime(200)
    scheduler.pause()
    vi.advanceTimersByTime(1000)
    expect(cursors).toEqual([
      { index: 0, phase: 'item' },
      { index: 1, phase: 'transition' },
    ])

    scheduler.resume()
    vi.advanceTimersByTime(299)
    expect(cursors).toHaveLength(2)
    vi.advanceTimersByTime(1)
    expect(cursors).toEqual([
      { index: 0, phase: 'item' },
      { index: 1, phase: 'transition' },
      { index: 1, phase: 'item' },
    ])
  })

  it('completes after the final item without scheduling a trailing transition', () => {
    vi.useFakeTimers()
    const cursors: SequenceRevealCursor[] = []
    let completed = 0
    const scheduler = createSequenceRevealScheduler({
      sequenceLength: 1,
      revealMs: 900,
      onCursor: (cursor) => cursors.push(cursor),
      onComplete: () => {
        completed += 1
      },
    })

    scheduler.start({ index: 0, phase: 'item' })
    vi.advanceTimersByTime(900)

    expect(cursors).toEqual([{ index: 0, phase: 'item' }])
    expect(completed).toBe(1)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does not let a cancelled timer advance a later round', () => {
    vi.useFakeTimers()
    const cursors: SequenceRevealCursor[] = []
    let completed = 0
    const scheduler = createSequenceRevealScheduler({
      sequenceLength: 2,
      revealMs: 900,
      onCursor: (cursor) => cursors.push(cursor),
      onComplete: () => {
        completed += 1
      },
    })

    scheduler.start({ index: 0, phase: 'item' })
    scheduler.cancel()
    vi.advanceTimersByTime(3000)

    expect(cursors).toEqual([{ index: 0, phase: 'item' }])
    expect(completed).toBe(0)
  })
})
