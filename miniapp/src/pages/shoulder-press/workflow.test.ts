import { describe, expect, it, vi } from 'vitest'
import { QiniuUploadError } from './api'
import type { PendingShoulderPressUpload } from './session'
import { runShoulderPressUploadWorkflow, shoulderPressUploadErrorMessage } from './workflow'

vi.mock('@tarojs/taro', () => ({ default: {} }))

const NOW = 1783692000000

function basePending(): PendingShoulderPressUpload {
  return {
    actionId: 42,
    tempFilePath: 'wxfile://video.mp4',
    durationSeconds: 120,
    sizeBytes: 2048,
    createdAt: NOW
  }
}

function intentPending(overrides: Partial<PendingShoulderPressUpload> = {}): PendingShoulderPressUpload {
  return {
    ...basePending(),
    videoId: 7,
    key: 'training-videos/7/video.mp4',
    uploadToken: 'token-7',
    uploadHost: 'https://upload.qiniup.com',
    expiresAt: NOW + 60_000,
    ...overrides
  }
}

function dependencies() {
  const saved: PendingShoulderPressUpload[] = []
  return {
    saved,
    deps: {
      now: () => NOW,
      createIntent: vi.fn().mockResolvedValue({
        video_id: 8,
        bucket: 'motioncare-training',
        key: 'training-videos/8/video.mp4',
        upload_token: 'token-8',
        upload_host: 'https://upload.qiniup.com',
        expires_at: new Date(NOW + 60_000).toISOString()
      }),
      uploadVideo: vi.fn().mockImplementation(async ({ key, onProgress }) => {
        onProgress?.(47)
        return { key, hash: `hash-for-${key}` }
      }),
      completeUpload: vi.fn().mockResolvedValue({ video_id: 8, status: 'attached' }),
      savePending: vi.fn((pending: PendingShoulderPressUpload) => saved.push({ ...pending }))
    }
  }
}

describe('shoulder press recoverable upload workflow', () => {
  it('keeps clear Chinese business errors and hides unsafe transport details', () => {
    expect(shoulderPressUploadErrorMessage(new Error('处方已更新，请重新进入')))
      .toBe('处方已更新，请重新进入')
    expect(shoulderPressUploadErrorMessage(new Error('Failed to fetch')))
      .toBe('上传失败，请检查网络后重试')
    expect(shoulderPressUploadErrorMessage(new Error('request failed with secret-token')))
      .toBe('上传失败，请检查网络后重试')
  })

  it('persists intent and hash before completing and reports all phases', async () => {
    const { saved, deps } = dependencies()
    const events: Array<{ phase: string; progress: number }> = []

    await runShoulderPressUploadWorkflow(basePending(), deps, (event) => events.push(event))

    expect(saved).toEqual(expect.arrayContaining([
      expect.objectContaining({
        videoId: 8,
        key: 'training-videos/8/video.mp4',
        uploadToken: 'token-8',
        uploadHost: 'https://upload.qiniup.com',
        expiresAt: NOW + 60_000
      }),
      expect.objectContaining({
        videoId: 8,
        key: 'training-videos/8/video.mp4',
        hash: 'hash-for-training-videos/8/video.mp4'
      })
    ]))
    expect(events).toEqual(expect.arrayContaining([
      { phase: 'credential', progress: 0 },
      { phase: 'credential', progress: 100 },
      { phase: 'upload', progress: 47 },
      { phase: 'complete', progress: 100 }
    ]))
  })

  it('reuses an unexpired intent instead of requesting another one', async () => {
    const { deps } = dependencies()

    await runShoulderPressUploadWorkflow(intentPending(), deps, vi.fn())

    expect(deps.createIntent).not.toHaveBeenCalled()
    expect(deps.uploadVideo).toHaveBeenCalledWith(expect.objectContaining({
      key: 'training-videos/7/video.mp4',
      uploadToken: 'token-7'
    }))
  })

  it('skips both credential request and kodo upload after hash was persisted', async () => {
    const { deps } = dependencies()
    const pending = intentPending({ hash: 'persisted-hash' })

    await runShoulderPressUploadWorkflow(pending, deps, vi.fn())

    expect(deps.createIntent).not.toHaveBeenCalled()
    expect(deps.uploadVideo).not.toHaveBeenCalled()
    expect(deps.completeUpload).toHaveBeenCalledWith({
      videoId: 7,
      key: 'training-videos/7/video.mp4',
      hash: 'persisted-hash',
      trainingDate: expect.any(String),
      actualDurationMinutes: 2,
      note: ''
    })
  })

  it('keeps the same video id, key, and hash when complete fails and is retried', async () => {
    const { saved, deps } = dependencies()
    deps.completeUpload.mockRejectedValueOnce(new Error('保存训练记录失败'))

    await expect(runShoulderPressUploadWorkflow(intentPending(), deps, vi.fn())).rejects.toThrow('保存训练记录失败')
    const recovered = saved.at(-1)
    expect(recovered).toEqual(expect.objectContaining({
      videoId: 7,
      key: 'training-videos/7/video.mp4',
      hash: 'hash-for-training-videos/7/video.mp4'
    }))

    await runShoulderPressUploadWorkflow(recovered!, deps, vi.fn())

    expect(deps.uploadVideo).toHaveBeenCalledTimes(1)
    expect(deps.completeUpload).toHaveBeenLastCalledWith(expect.objectContaining({
      videoId: 7,
      key: 'training-videos/7/video.mp4',
      hash: 'hash-for-training-videos/7/video.mp4'
    }))
  })

  it('clears an expired intent before requesting a replacement', async () => {
    const { saved, deps } = dependencies()

    await runShoulderPressUploadWorkflow(intentPending({ expiresAt: NOW }), deps, vi.fn())

    expect(saved[0]).not.toHaveProperty('videoId')
    expect(saved[0]).not.toHaveProperty('key')
    expect(deps.createIntent).toHaveBeenCalledTimes(1)
    expect(deps.uploadVideo).toHaveBeenCalledWith(expect.objectContaining({
      key: 'training-videos/8/video.mp4',
      uploadToken: 'token-8'
    }))
  })

  it('keeps a still-valid intent after an ordinary upload failure', async () => {
    const { saved, deps } = dependencies()
    deps.uploadVideo.mockRejectedValueOnce(new Error('网络不可用'))

    await expect(runShoulderPressUploadWorkflow(intentPending(), deps, vi.fn())).rejects.toThrow('网络不可用')

    expect(deps.createIntent).not.toHaveBeenCalled()
    expect(saved.at(-1)).toEqual(expect.objectContaining({
      videoId: 7,
      key: 'training-videos/7/video.mp4',
      uploadToken: 'token-7'
    }))
  })

  it('replaces an intent only when qiniu explicitly reports token expiry', async () => {
    const { deps } = dependencies()
    deps.uploadVideo
      .mockRejectedValueOnce(new QiniuUploadError('token_expired'))
      .mockImplementationOnce(async ({ key }) => ({ key, hash: 'replacement-hash' }))

    await runShoulderPressUploadWorkflow(intentPending(), deps, vi.fn())

    expect(deps.createIntent).toHaveBeenCalledTimes(1)
    expect(deps.uploadVideo).toHaveBeenCalledTimes(2)
    expect(deps.completeUpload).toHaveBeenCalledWith(expect.objectContaining({
      videoId: 8,
      key: 'training-videos/8/video.mp4',
      hash: 'replacement-hash'
    }))
  })

  it('does not persist a partial intent returned by the credential endpoint', async () => {
    const { saved, deps } = dependencies()
    deps.createIntent.mockResolvedValueOnce({
      video_id: 8,
      bucket: 'motioncare-training',
      key: 'training-videos/8/video.mp4',
      upload_token: 'token-8',
      upload_host: '',
      expires_at: new Date(NOW + 60_000).toISOString()
    })

    await expect(runShoulderPressUploadWorkflow(basePending(), deps, vi.fn()))
      .rejects.toThrow('上传凭证信息不完整，请重试')

    expect(saved.at(-1)).not.toHaveProperty('videoId')
    expect(saved.at(-1)).not.toHaveProperty('uploadToken')
  })
})
