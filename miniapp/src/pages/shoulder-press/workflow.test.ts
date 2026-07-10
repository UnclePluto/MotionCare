import { describe, expect, it, vi } from 'vitest'

import {
  appendPendingSegment,
  createPendingShoulderPressSession,
  type PendingShoulderPressSession
} from './session'
import {
  runPendingSegmentUploads,
  runShoulderPressUploadWorkflow,
  shoulderPressUploadErrorMessage
} from './workflow'

const NOW = 1783692000000

function baseSession(): PendingShoulderPressSession {
  return [
    { savedFilePath: 'wxfile://store/segment-0.mp4', durationSeconds: 30, sizeKb: 1000 },
    { savedFilePath: 'wxfile://store/segment-1.mp4', durationSeconds: 31, sizeKb: 1001 },
    { savedFilePath: 'wxfile://store/segment-2.mp4', durationSeconds: 32, sizeKb: 1002 }
  ].reduce((session, segment) => appendPendingSegment(session, segment), createPendingShoulderPressSession({
    actionId: 42,
    expectedDurationSeconds: 180,
    trainingDate: '2026-07-11',
    clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
    createdAt: NOW
  }))
}

function dependencies() {
  const saved: PendingShoulderPressSession[] = []
  const deleted: string[] = []
  const eventLog: string[] = []
  const deps = {
    createVideoSession: vi.fn().mockResolvedValue({ video_id: 9, status: 'created' }),
    getVideoSessionStatus: vi.fn().mockResolvedValue({ video_id: 9, status: 'created', uploaded_segments: [] }),
    uploadVideoSegment: vi.fn().mockImplementation(async ({ index }) => ({
      index,
      sha256: `sha-${index}`
    })),
    finalizeVideoSession: vi.fn().mockResolvedValue({
      video_id: 9,
      status: 'assembling',
      assembly_job_id: 'job-1'
    }),
    saveSession: vi.fn((session: PendingShoulderPressSession) => {
      saved.push(JSON.parse(JSON.stringify(session)) as PendingShoulderPressSession)
      for (const segment of session.segments) {
        if (segment.uploadState === 'uploaded' && segment.sha256) {
          eventLog.push(`save:uploaded:${segment.index}:${segment.sha256}`)
        }
      }
    }),
    deleteSavedFile: vi.fn(async (path: string) => {
      deleted.push(path)
      eventLog.push(`delete:${path}`)
    })
  }
  return { deps, saved, deleted, eventLog }
}

async function flushPromises(times = 6) {
  for (let index = 0; index < times; index += 1) {
    await Promise.resolve()
  }
}

describe('shoulder press pending segment upload workflow', () => {
  it('keeps clear Chinese business errors and hides unsafe transport details', () => {
    expect(shoulderPressUploadErrorMessage(new Error('处方已更新，请重新进入')))
      .toBe('处方已更新，请重新进入')
    expect(shoulderPressUploadErrorMessage(new Error('Failed to fetch Authorization: Bearer secret')))
      .toBe('上传失败，请检查网络后重试')
  })

  it('creates the video session, uploads one segment at a time, persists uploaded sha before delete, then finalizes', async () => {
    const { deps, saved, deleted, eventLog } = dependencies()
    const events: Array<{ index: number; state: string; progress?: number }> = []

    const result = await runPendingSegmentUploads(baseSession(), deps, (event) => events.push(event))

    expect(deps.createVideoSession).toHaveBeenCalledWith({
      actionId: 42,
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      trainingDate: '2026-07-11',
      expectedDurationSeconds: 180
    })
    expect(deps.uploadVideoSegment.mock.calls.map(([input]) => input.index)).toEqual([0, 1, 2])
    expect(deps.finalizeVideoSession).toHaveBeenCalledWith({
      videoId: 9,
      segmentCount: 3,
      actualDurationSeconds: 93,
      note: ''
    })
    expect(result.finalized).toBe(true)
    expect(events).toContainEqual({ phase: 'upload', index: 0, state: 'uploaded', progress: 100 })

    const firstDeleteIndex = saved.findIndex((session) => (
      session.segments[0].uploadState === 'uploaded' && session.segments[0].sha256 === 'sha-0'
    ))
    expect(firstDeleteIndex).toBeGreaterThanOrEqual(0)
    expect(deleted[0]).toBe('wxfile://store/segment-0.mp4')
    expect(eventLog.indexOf('save:uploaded:0:sha-0'))
      .toBeLessThan(eventLog.indexOf('delete:wxfile://store/segment-0.mp4'))
  })

  it('skips server-confirmed indexes during cold recovery and continues with the first local pending segment', async () => {
    const { deps } = dependencies()
    deps.getVideoSessionStatus.mockResolvedValueOnce({
      video_id: 9,
      status: 'created',
      uploaded_segments: [0]
    })

    await runPendingSegmentUploads({ ...baseSession(), videoId: 9 }, deps, vi.fn())

    expect(deps.createVideoSession).not.toHaveBeenCalled()
    expect(deps.uploadVideoSegment.mock.calls.map(([input]) => input.index)).toEqual([1, 2])
  })

  it.each([
    [[99], '越界'],
    [[1], '非前缀'],
    [[0, 0], '重复']
  ])('stops and persists lastError when remote uploaded_segments are %s (%s)', async (uploadedSegments) => {
    const { deps, saved } = dependencies()
    deps.getVideoSessionStatus.mockResolvedValueOnce({
      video_id: 9,
      status: 'created',
      uploaded_segments: uploadedSegments
    })

    await expect(runPendingSegmentUploads({ ...baseSession(), videoId: 9 }, deps, vi.fn()))
      .rejects.toThrow('服务端分段状态不一致，请重新上传')

    expect(deps.uploadVideoSegment).not.toHaveBeenCalled()
    expect(deps.finalizeVideoSession).not.toHaveBeenCalled()
    expect(saved.at(-1)?.lastError).toBe('服务端分段状态不一致，请重新上传')
  })

  it('never starts the next upload promise until the current segment has resolved', async () => {
    const { deps } = dependencies()
    const pendingResolvers: Array<(value: { index: number; sha256: string }) => void> = []
    deps.uploadVideoSegment.mockImplementation(({ index }) => (
      new Promise((resolve) => {
        pendingResolvers.push(resolve)
      }).then(() => ({ index, sha256: `sha-${index}` }))
    ))

    const running = runPendingSegmentUploads(baseSession(), deps, vi.fn())
    await flushPromises()

    expect(deps.uploadVideoSegment.mock.calls.map(([input]) => input.index)).toEqual([0])
    pendingResolvers[0]({ index: 0, sha256: 'sha-0' })
    await flushPromises()
    expect(deps.uploadVideoSegment.mock.calls.map(([input]) => input.index)).toEqual([0, 1])
    pendingResolvers[1]({ index: 1, sha256: 'sha-1' })
    await flushPromises()
    expect(deps.uploadVideoSegment.mock.calls.map(([input]) => input.index)).toEqual([0, 1, 2])
    pendingResolvers[2]({ index: 2, sha256: 'sha-2' })

    await expect(running).resolves.toMatchObject({ finalized: true })
  })

  it('stops at the current segment on failure and leaves current plus later segments pending', async () => {
    const { deps, saved } = dependencies()
    deps.uploadVideoSegment
      .mockResolvedValueOnce({ index: 0, sha256: 'sha-0' })
      .mockRejectedValueOnce(new Error('网络不可用'))

    await expect(runPendingSegmentUploads(baseSession(), deps, vi.fn())).rejects.toThrow('网络不可用')

    expect(deps.uploadVideoSegment.mock.calls.map(([input]) => input.index)).toEqual([0, 1])
    expect(saved.at(-1)?.segments.map((segment) => segment.uploadState)).toEqual(['uploaded', 'pending', 'pending'])
    expect(saved.at(-1)?.lastError).toBe('网络不可用')
    expect(deps.finalizeVideoSession).not.toHaveBeenCalled()
  })

  it('does not roll an uploaded segment back to pending when best-effort local deletion fails', async () => {
    const { deps, saved } = dependencies()
    deps.deleteSavedFile.mockRejectedValueOnce(new Error('remove failed'))

    const result = await runPendingSegmentUploads(baseSession(), deps, vi.fn())

    expect(result.segments[0]).toMatchObject({
      uploadState: 'uploaded',
      sha256: 'sha-0'
    })
    expect(saved.find((session) => (
      session.segments[0].uploadState === 'pending' && session.segments[0].sha256 === 'sha-0'
    ))).toBeUndefined()
  })

  it('bridges the legacy upload page through a single-segment pending session with real metadata', async () => {
    const initial = baseSession()
    const singleSegmentPending = {
      ...initial,
      actualDurationMs: initial.segments[0].durationMs,
      segments: [initial.segments[0]],
      durationSeconds: 30,
      tempFilePath: initial.segments[0].savedFilePath,
      sizeBytes: initial.segments[0].sizeBytes
    }
    const saved: PendingShoulderPressSession[] = []
    const deps = {
      createIntent: vi.fn().mockResolvedValue({ video_id: 77, status: 'created' }),
      getVideoSessionStatus: vi.fn().mockResolvedValue({ video_id: 77, status: 'created', uploaded_segments: [] }),
      uploadVideoSegment: vi.fn().mockResolvedValue({ index: 0, sha256: 'sha-real' }),
      finalizeVideoSession: vi.fn().mockResolvedValue({ video_id: 77, status: 'assembling' }),
      savePending: vi.fn((session: PendingShoulderPressSession) => {
        saved.push(JSON.parse(JSON.stringify(session)) as PendingShoulderPressSession)
      }),
      deleteSavedFile: vi.fn(async () => undefined),
      uploadVideo: vi.fn(async () => {
        throw new Error('legacy uploadVideo should not be used')
      }),
      completeUpload: vi.fn(async () => {
        throw new Error('legacy completeUpload should not be used')
      })
    }

    const result = await runShoulderPressUploadWorkflow(singleSegmentPending, deps, vi.fn())

    expect(deps.createIntent).toHaveBeenCalledWith({
      actionId: 42,
      sizeBytes: 1024000,
      durationSeconds: 30,
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      trainingDate: '2026-07-11'
    })
    expect(deps.uploadVideoSegment).toHaveBeenCalledWith(expect.objectContaining({
      videoId: 77,
      index: 0,
      filePath: 'wxfile://store/segment-0.mp4',
      durationMs: 30000,
      sizeBytes: 1024000
    }))
    expect(deps.finalizeVideoSession).toHaveBeenCalledWith({
      videoId: 77,
      segmentCount: 1,
      actualDurationSeconds: 30,
      note: ''
    })
    expect(deps.uploadVideo).not.toHaveBeenCalled()
    expect(deps.completeUpload).not.toHaveBeenCalled()
    expect(result).toMatchObject({
      videoId: 77,
      finalized: true,
      hash: 'sha-real'
    })
    expect(saved.at(-1)).toMatchObject({ videoId: 77, finalized: true })
  })
})
