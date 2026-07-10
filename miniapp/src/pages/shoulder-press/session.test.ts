import { describe, expect, it, vi } from 'vitest'

import {
  PENDING_SHOULDER_PRESS_UPLOAD_KEY,
  buildPendingShoulderPressUpload,
  buildShoulderPressSessionUrl,
  buildShoulderPressUploadUrl,
  clearPendingShoulderPressUpload,
  loadPendingShoulderPressUpload,
  savePendingShoulderPressUpload
} from './session'

function memoryStorage() {
  const store = new Map<string, unknown>()
  return {
    getStorageSync: vi.fn((key: string) => store.get(key)),
    setStorageSync: vi.fn((key: string, value: unknown) => store.set(key, value)),
    removeStorageSync: vi.fn((key: string) => store.delete(key))
  }
}

describe('shoulder press session helpers', () => {
  it('builds session and upload urls', () => {
    expect(buildShoulderPressSessionUrl(42)).toBe('/pages/shoulder-press/index?actionId=42')
    expect(buildShoulderPressUploadUrl()).toBe('/pages/shoulder-press/upload')
  })

  it('builds pending state from getVideoInfo metadata', () => {
    expect(buildPendingShoulderPressUpload({
      actionId: 42,
      tempFilePath: 'wxfile://video.mp4',
      videoInfo: { duration: 119.6, size: 2048 },
      createdAt: 1783692000000
    })).toEqual({
      actionId: 42,
      tempFilePath: 'wxfile://video.mp4',
      durationSeconds: 120,
      sizeBytes: 2048,
      createdAt: 1783692000000
    })
  })

  it('rejects an unusable temporary path or invalid video metadata', () => {
    expect(() => buildPendingShoulderPressUpload({
      actionId: 42,
      tempFilePath: '   ',
      videoInfo: { duration: 20, size: 2048 },
      createdAt: 1783692000000
    })).toThrow('录像文件路径无效')
    expect(() => buildPendingShoulderPressUpload({
      actionId: 42,
      tempFilePath: 'wxfile://video.mp4',
      videoInfo: { duration: 0, size: 2048 },
      createdAt: 1783692000000
    })).toThrow('录像时长无效')
  })

  it('stores and restores all successful upload stages', () => {
    const storage = memoryStorage()
    const pending = {
      actionId: 42,
      tempFilePath: 'wxfile://video.mp4',
      durationSeconds: 120,
      sizeBytes: 2048,
      createdAt: 1783692000000,
      videoId: 7,
      key: 'training-videos/7/video.mp4',
      uploadToken: 'token',
      uploadHost: 'https://upload.qiniup.com',
      expiresAt: 1783695600000,
      hash: 'qiniu-hash'
    }

    savePendingShoulderPressUpload(storage, pending)

    expect(storage.setStorageSync).toHaveBeenCalledWith(PENDING_SHOULDER_PRESS_UPLOAD_KEY, pending)
    expect(loadPendingShoulderPressUpload(storage)).toEqual(pending)
  })

  it('drops malformed diagnostic data while restoring a complete upload stage', () => {
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_SHOULDER_PRESS_UPLOAD_KEY, {
      actionId: 42,
      tempFilePath: 'wxfile://video.mp4',
      durationSeconds: 120,
      sizeBytes: 2048,
      createdAt: 1783692000000,
      videoId: 7,
      key: 'training-videos/7/video.mp4',
      uploadToken: 'token',
      uploadHost: 'https://upload.qiniup.com',
      expiresAt: 1783695600000,
      hash: 'qiniu-hash',
      lastError: 42
    })

    expect(loadPendingShoulderPressUpload(storage)).toEqual(expect.objectContaining({
      videoId: 7,
      hash: 'qiniu-hash'
    }))
    expect(loadPendingShoulderPressUpload(storage)).not.toHaveProperty('lastError')
  })

  it('recovers a valid recording by discarding a partial upload intent', () => {
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_SHOULDER_PRESS_UPLOAD_KEY, {
      actionId: 42,
      tempFilePath: 'wxfile://video.mp4',
      durationSeconds: 120,
      sizeBytes: 2048,
      createdAt: 1783692000000,
      videoId: 7,
      key: 'training-videos/7/video.mp4'
    })
    expect(loadPendingShoulderPressUpload(storage)).toEqual({
      actionId: 42,
      tempFilePath: 'wxfile://video.mp4',
      durationSeconds: 120,
      sizeBytes: 2048,
      createdAt: 1783692000000
    })
  })

  it('treats damaged base recording data as invalid', () => {
    const storage = memoryStorage()

    storage.setStorageSync(PENDING_SHOULDER_PRESS_UPLOAD_KEY, { actionId: '42' })
    expect(loadPendingShoulderPressUpload(storage)).toBeNull()
  })

  it('clears pending upload only through the named storage key', () => {
    const storage = memoryStorage()

    clearPendingShoulderPressUpload(storage)

    expect(storage.removeStorageSync).toHaveBeenCalledWith(PENDING_SHOULDER_PRESS_UPLOAD_KEY)
  })
})
