import { expect, it } from 'vitest'
import { createSegmentTrace } from './segmentTrace'
import type { PendingMotionTrainingSession } from './session'

it('exports cleanup backlog and safe native errors without paths or credentials', () => {
  const trace = createSegmentTrace(() => 1000)
  trace.mark('cleanup_failure', 7, { errCode: 130001, errMsg: 'unlink:fail permission denied wxfile://private?token=secret' })
  const session: PendingMotionTrainingSession = { clientSessionId: 'private-session', actionId: 1, trainingDate: '2026-09-25', expectedDurationSeconds: 1200, actualDurationMs: 494000, createdAt: 0, finalized: false,
    segments: [{ index: 7, compressionState: 'compressed', savedFilePath: 'wxfile://private', durationMs: 60000, sizeBytes: 6500000, uploadState: 'uploaded', localFileState: 'temporary' }] }
  const output = trace.export(session, 'buffer_paused')
  const data = JSON.parse(output)
  expect(data.snapshot.pendingLocalBytes).toBe(6500000)
  expect(data.snapshot.uploadedUncleanedBytes).toBe(6500000)
  expect(data.snapshot.segments[0].localFileDeleted).toBe(false)
  expect(data.events[0]).toMatchObject({ event: 'cleanup_failure', segment: 7, code: 130001, reason: 'permission' })
  expect(output).not.toMatch(/wxfile|secret|private-session/)
})

it('bounds the diagnostic journal during repeated cleanup retries', () => {
  const trace = createSegmentTrace()
  for (let index = 0; index < 1000; index++) trace.mark('cleanup_call', index)
  expect(JSON.parse(trace.export(null, 'recording')).events).toHaveLength(400)
})
