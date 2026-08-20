import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { OFFICIAL_MOTION_SOURCE_KEYS } from '../features/motion-training/catalog'

const publicRequestMock = vi.hoisted(() => vi.fn())

vi.mock('../api/client', () => ({ publicRequest: publicRequestMock }))

const validResponse = {
  videos: OFFICIAL_MOTION_SOURCE_KEYS.map((sourceKey) => ({
    source_key: sourceKey,
    video_url: `https://signed.example.com/${sourceKey}.mp4`,
  }))
}

beforeEach(() => {
  vi.resetModules()
  vi.useFakeTimers()
  vi.setSystemTime(1_000)
  publicRequestMock.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('演示运动视频清单', () => {
  it('并发请求在 60 秒内复用同一 Promise 并返回恰好五个 HTTPS 地址', async () => {
    publicRequestMock.mockResolvedValue(validResponse)
    const { fetchDemoMotionVideoManifest } = await import('./motionVideoManifest')

    const first = fetchDemoMotionVideoManifest()
    const concurrent = fetchDemoMotionVideoManifest()
    expect(concurrent).toBe(first)

    await expect(first).resolves.toEqual(Object.fromEntries(
      OFFICIAL_MOTION_SOURCE_KEYS.map((sourceKey) => [
        sourceKey,
        `https://signed.example.com/${sourceKey}.mp4`,
      ])
    ))

    vi.setSystemTime(60_999)
    expect(fetchDemoMotionVideoManifest()).toBe(first)
    expect(publicRequestMock).toHaveBeenCalledTimes(1)
    expect(publicRequestMock).toHaveBeenCalledWith('/patient-app/demo-motion-videos/')
  })

  it('缓存满 60 秒后创建新请求', async () => {
    publicRequestMock.mockResolvedValue(validResponse)
    const { fetchDemoMotionVideoManifest } = await import('./motionVideoManifest')

    const first = fetchDemoMotionVideoManifest()
    await first
    vi.setSystemTime(61_000)
    const refreshed = fetchDemoMotionVideoManifest()

    expect(refreshed).not.toBe(first)
    await expect(refreshed).resolves.toEqual(await first)
    expect(publicRequestMock).toHaveBeenCalledTimes(2)
  })

  it('显式刷新会绕过仍有效的缓存', async () => {
    publicRequestMock.mockResolvedValue(validResponse)
    const { fetchDemoMotionVideoManifest } = await import('./motionVideoManifest')

    const first = fetchDemoMotionVideoManifest()
    await first
    const refreshed = fetchDemoMotionVideoManifest({ forceRefresh: true })

    expect(refreshed).not.toBe(first)
    await expect(refreshed).resolves.toEqual(await first)
    expect(publicRequestMock).toHaveBeenCalledTimes(2)
  })

  it('旧请求延迟失败不会清除较新的强制刷新缓存', async () => {
    let rejectOld!: (error: Error) => void
    const old = new Promise((_, reject) => { rejectOld = reject })
    publicRequestMock
      .mockReturnValueOnce(old)
      .mockResolvedValueOnce(validResponse)
    const { fetchDemoMotionVideoManifest } = await import('./motionVideoManifest')

    const first = fetchDemoMotionVideoManifest()
    const refreshed = fetchDemoMotionVideoManifest({ forceRefresh: true })
    await refreshed
    rejectOld(new Error('旧请求失败'))
    await expect(first).rejects.toThrow('旧请求失败')

    expect(fetchDemoMotionVideoManifest()).toBe(refreshed)
    expect(publicRequestMock).toHaveBeenCalledTimes(2)
  })

  it('请求失败后立即清空缓存并允许重试', async () => {
    publicRequestMock
      .mockRejectedValueOnce(new Error('演示视频暂时不可用'))
      .mockResolvedValueOnce(validResponse)
    const { fetchDemoMotionVideoManifest } = await import('./motionVideoManifest')

    await expect(fetchDemoMotionVideoManifest()).rejects.toThrow('演示视频暂时不可用')
    await expect(fetchDemoMotionVideoManifest()).resolves.toMatchObject({
      'motion-resistance-row': 'https://signed.example.com/motion-resistance-row.mp4',
    })
    expect(publicRequestMock).toHaveBeenCalledTimes(2)
  })

  it.each([
    ['缺少动作', { videos: validResponse.videos.slice(0, 4) }],
    ['重复 source key', { videos: [...validResponse.videos.slice(0, 4), validResponse.videos[0]] }],
    ['未知 source key', {
      videos: [...validResponse.videos.slice(0, 4), {
        source_key: 'motion-unknown',
        video_url: 'https://signed.example.com/unknown.mp4',
      }]
    }],
    ['非 HTTPS 地址', {
      videos: validResponse.videos.map((video, index) => (
        index === 0 ? { ...video, video_url: 'http://signed.example.com/video.mp4' } : video
      ))
    }],
    ['空地址', {
      videos: validResponse.videos.map((video, index) => (
        index === 0 ? { ...video, video_url: '   ' } : video
      ))
    }],
    ['畸形 HTTPS 地址', {
      videos: validResponse.videos.map((video, index) => (
        index === 0 ? { ...video, video_url: 'https://[invalid-host/video.mp4' } : video
      ))
    }],
    ['带凭据 HTTPS 地址', {
      videos: validResponse.videos.map((video, index) => (
        index === 0 ? { ...video, video_url: 'https://user:pass@signed.example.com/video.mp4' } : video
      ))
    }],
    ['错误响应形状', { videos: null }],
  ])('拒绝%s且不缓存无效响应', async (_caseName, response) => {
    publicRequestMock
      .mockResolvedValueOnce(response)
      .mockResolvedValueOnce(validResponse)
    const { fetchDemoMotionVideoManifest } = await import('./motionVideoManifest')

    await expect(fetchDemoMotionVideoManifest()).rejects.toThrow('演示视频暂时不可用，请稍后重试')
    await expect(fetchDemoMotionVideoManifest()).resolves.toMatchObject({
      'motion-resistance-row': 'https://signed.example.com/motion-resistance-row.mp4',
    })
    expect(publicRequestMock).toHaveBeenCalledTimes(2)
  })
})
