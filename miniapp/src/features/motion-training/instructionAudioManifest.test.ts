import { afterEach, describe, expect, it, vi } from 'vitest'

import { OFFICIAL_MOTION_SOURCE_KEYS } from './catalog'

async function loadInstructionAudioManifest() {
  vi.resetModules()
  vi.stubEnv('TARO_APP_ASSET_BASE_URL', 'https://cdn.example.com/assets')
  return import('./instructionAudioManifest')
}

describe('motion instruction audio manifest', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('maps every official motion source key to one immutable CDN m4a', async () => {
    const {
      getMotionInstructionAudioSrc,
      MOTION_INSTRUCTION_AUDIO_SRC,
    } = await loadInstructionAudioManifest()

    expect(Object.keys(MOTION_INSTRUCTION_AUDIO_SRC)).toEqual([
      ...OFFICIAL_MOTION_SOURCE_KEYS,
    ])

    for (const sourceKey of OFFICIAL_MOTION_SOURCE_KEYS) {
      expect(getMotionInstructionAudioSrc(sourceKey)).toMatch(
        new RegExp(
          `^https://cdn\\.example\\.com/assets/v-[a-f0-9]{12}/${sourceKey}\\.[a-f0-9]{12}\\.m4a$`,
        ),
      )
    }
  })

  it('does not infer audio for unknown or malformed keys', async () => {
    const { getMotionInstructionAudioSrc } = await loadInstructionAudioManifest()

    expect(getMotionInstructionAudioSrc('motion-resistance-row-extra')).toBeUndefined()
    expect(getMotionInstructionAudioSrc('坐姿划船')).toBeUndefined()
    expect(getMotionInstructionAudioSrc(undefined)).toBeUndefined()
  })
})
