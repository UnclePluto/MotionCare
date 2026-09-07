import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { OFFICIAL_MOTION_SOURCE_KEYS } from './catalog'

const fetchManifest = vi.hoisted(() => vi.fn())
vi.mock('../../assets/signedAssetManifest', () => ({ fetchSignedAssetManifest: fetchManifest }))

const urls = {
  'motion-aerobic-high-knee': 'https://cdn.example.com/high-knee.m4a?e=1&token=test',
  'motion-balance-sit-stand': 'https://cdn.example.com/sit-stand.m4a?e=1&token=test',
  'motion-resistance-row': 'https://cdn.example.com/row.m4a?e=1&token=test',
  'motion-resistance-leg-kickback': 'https://cdn.example.com/leg-kickback.m4a?e=1&token=test',
  'motion-resistance-shoulder-press': 'https://cdn.example.com/shoulder-press.m4a?e=1&token=test',
}

describe('动作说明签名地址', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.stubEnv('TARO_APP_ASSET_BASE_URL', 'https://cdn.example.com/assets')
    fetchManifest.mockReset().mockResolvedValue({ urls })
  })

  afterEach(() => vi.unstubAllEnvs())

  it('导入和同步判断不会请求签名', async () => {
    const { hasMotionInstructionAudio } = await import('./instructionAudioManifest')
    expect(fetchManifest).not.toHaveBeenCalled()
    for (const key of OFFICIAL_MOTION_SOURCE_KEYS) expect(hasMotionInstructionAudio(key)).toBe(true)
    for (const key of [undefined, null, {}, '坐姿划船', 'motion-resistance-row-extra']) {
      expect(hasMotionInstructionAudio(key)).toBe(false)
    }
    expect(fetchManifest).not.toHaveBeenCalled()
  })

  it.each(OFFICIAL_MOTION_SOURCE_KEYS)('%s 返回清单中的签名地址', async (key) => {
    const { getMotionInstructionAudioSrc } = await import('./instructionAudioManifest')
    await expect(getMotionInstructionAudioSrc(key)).resolves.toBe(urls[key])
    expect(fetchManifest).toHaveBeenCalledOnce()
  })

  it('未知动作不发请求，返回 undefined', async () => {
    const { getMotionInstructionAudioSrc } = await import('./instructionAudioManifest')
    for (const key of [undefined, null, {}, '坐姿划船', 'motion-resistance-row-extra']) {
      await expect(getMotionInstructionAudioSrc(key)).resolves.toBeUndefined()
    }
    expect(fetchManifest).not.toHaveBeenCalled()
  })

  it('重试时传递强制刷新选项', async () => {
    const { getMotionInstructionAudioSrc } = await import('./instructionAudioManifest')
    await getMotionInstructionAudioSrc('motion-resistance-row', { forceRefresh: true })
    expect(fetchManifest).toHaveBeenCalledWith({ forceRefresh: true })
  })
})
