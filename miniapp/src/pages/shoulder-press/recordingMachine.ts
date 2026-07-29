export type RecordingState = {
  phase: 'idle' | 'countdown' | 'recording' | 'finishing'
  currentSequenceIndex: number
  elapsedSeconds: number
  segmentCount: number
}

export function initialRecordingState(): RecordingState {
  return {
    phase: 'idle',
    currentSequenceIndex: 0,
    elapsedSeconds: 0,
    segmentCount: 0,
  }
}

export function advanceRecordingClock(state: RecordingState): RecordingState {
  if (state.phase !== 'recording') return state
  return { ...state, elapsedSeconds: state.elapsedSeconds + 1 }
}

export function classifyTimedOutSegment(input: {
  finalizing: boolean
  pageHidden: boolean
}): 'rotate' | 'finalize' {
  return input.finalizing || input.pageHidden ? 'finalize' : 'rotate'
}

export function shouldStartRecordingAfterSessionCreated(pageHidden: boolean): boolean {
  return !pageHidden
}

export function shouldWaitForAutomaticFinalSegment(
  reason: 'manual' | 'hidden',
): boolean {
  return reason === 'hidden'
}

export async function waitForPendingPersistence(promises: Promise<void>[]): Promise<void> {
  await Promise.allSettled(promises)
}

export async function rotateTimedOutSegment(input: {
  state: RecordingState
  startNextRecording: () => void
  persistCompletedSegment: (sequenceIndex: number) => Promise<void>
}): Promise<RecordingState> {
  const completedSequence = input.state.currentSequenceIndex
  input.startNextRecording()
  await input.persistCompletedSegment(completedSequence)
  return {
    ...input.state,
    phase: 'recording',
    currentSequenceIndex: completedSequence + 1,
    segmentCount: completedSequence + 1,
  }
}

export async function finishCurrentSegment(input: {
  state: RecordingState
  reason: 'manual' | 'hidden'
  startNextRecording: () => void
  persistCompletedSegment: (sequenceIndex: number) => Promise<void>
}): Promise<RecordingState> {
  await input.persistCompletedSegment(input.state.currentSequenceIndex)
  return {
    ...input.state,
    phase: 'finishing',
    segmentCount: input.state.currentSequenceIndex + 1,
  }
}
