import { describe, expect, it, vi } from 'vitest'

import {
  buildShoulderPressCameraUrl,
  loadShoulderPressSession,
  PENDING_SHOULDER_PRESS_SESSION_KEY,
  saveShoulderPressSession,
} from './session'

describe('肩部推举本地会话', () => {
  it('动作讲解页进入独立摄像训练页', () => {
    expect(buildShoulderPressCameraUrl(42)).toBe('/pages/shoulder-press/camera?actionId=42')
  })

  it('保存并恢复带分片队列的服务端会话', () => {
    const store = new Map<string, unknown>()
    const storage = {
      getStorageSync: vi.fn((key: string) => store.get(key)),
      setStorageSync: vi.fn((key: string, value: unknown) => store.set(key, value)),
    }
    saveShoulderPressSession(storage, {
      actionId: 42,
      videoId: 7,
      startedAt: 1,
      durationSeconds: 30,
      phase: 'recording',
      segments: [{
        sequenceIndex: 0,
        savedFilePath: 'wxfile://saved-0.mp4',
        durationSeconds: 30,
        sizeBytes: 100,
        status: 'pending',
        retryCount: 0,
      }],
    })

    expect(storage.setStorageSync).toHaveBeenCalledWith(
      PENDING_SHOULDER_PRESS_SESSION_KEY,
      expect.objectContaining({ videoId: 7 }),
    )
    expect(loadShoulderPressSession(storage)?.segments[0].sequenceIndex).toBe(0)
  })
})
