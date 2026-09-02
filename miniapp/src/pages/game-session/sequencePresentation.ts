export const SEQUENCE_TRANSITION_MS = 500

export type SequenceRevealPhase = 'item' | 'transition'

export type SequenceRevealCursor = {
  index: number
  phase: SequenceRevealPhase
}

export type SequenceRevealScheduler = {
  start(cursor: SequenceRevealCursor): void
  pause(): void
  resume(): void
  cancel(): void
}

export type SequenceRevealSchedulerOptions = {
  sequenceLength: number
  revealMs: number
  onCursor: (cursor: SequenceRevealCursor) => void
  onComplete: () => void
}

export type SequenceAnswerSlot<T> = {
  index: number
  expected: T
  selected: T | null
  correct: boolean | null
}

export function buildSequenceAnswerSlots<T>(
  target: readonly T[],
  selected: readonly T[]
): SequenceAnswerSlot<T>[] {
  return target.map((expected, index) => {
    const selectedValue = index < selected.length ? selected[index] : null
    return {
      index,
      expected,
      selected: selectedValue,
      correct: selectedValue === null ? null : Object.is(expected, selectedValue),
    }
  })
}

export function sequenceRevealDelay(cursor: SequenceRevealCursor, revealMs: number): number {
  return cursor.phase === 'transition' ? SEQUENCE_TRANSITION_MS : revealMs
}

export function advanceSequenceRevealCursor(
  cursor: SequenceRevealCursor,
  sequenceLength: number
): SequenceRevealCursor | null {
  if (sequenceLength <= 0 || cursor.index < 0 || cursor.index >= sequenceLength) return null
  if (cursor.phase === 'item') {
    return cursor.index === sequenceLength - 1 ? null : { index: cursor.index + 1, phase: 'transition' }
  }
  return { index: cursor.index, phase: 'item' }
}

export function createSequenceRevealScheduler({
  sequenceLength,
  revealMs,
  onCursor,
  onComplete,
}: SequenceRevealSchedulerOptions): SequenceRevealScheduler {
  let cursor: SequenceRevealCursor | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let deadline: number | null = null
  let remainingMs: number | null = null
  let revision = 0

  function clearTimer() {
    if (timer) clearTimeout(timer)
    timer = null
    deadline = null
  }

  function schedule(durationMs: number) {
    if (!cursor) return
    const timerRevision = ++revision
    const delayMs = Math.max(0, durationMs)
    remainingMs = delayMs
    deadline = Date.now() + delayMs
    timer = setTimeout(() => {
      if (timerRevision !== revision) return
      timer = null
      deadline = null
      remainingMs = null
      if (!cursor) return

      const next = advanceSequenceRevealCursor(cursor, sequenceLength)
      if (!next) {
        cursor = null
        onComplete()
        return
      }

      cursor = next
      onCursor(next)
      schedule(sequenceRevealDelay(next, revealMs))
    }, delayMs)
  }

  return {
    start(nextCursor) {
      clearTimer()
      revision += 1
      cursor = nextCursor
      remainingMs = null
      onCursor(nextCursor)
      schedule(sequenceRevealDelay(nextCursor, revealMs))
    },
    pause() {
      if (!timer) return
      const activeDeadline = deadline
      clearTimer()
      revision += 1
      remainingMs = activeDeadline === null ? null : Math.max(0, activeDeadline - Date.now())
    },
    resume() {
      if (!cursor || timer) return
      schedule(remainingMs ?? sequenceRevealDelay(cursor, revealMs))
    },
    cancel() {
      clearTimer()
      revision += 1
      cursor = null
      remainingMs = null
    },
  }
}
