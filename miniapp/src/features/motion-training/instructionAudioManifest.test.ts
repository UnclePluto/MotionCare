import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { OFFICIAL_MOTION_SOURCE_KEYS } from './catalog'
import {
  getMotionInstructionAudioSrc,
  MOTION_INSTRUCTION_AUDIO_SRC,
} from './instructionAudioManifest'

describe('motion instruction audio manifest', () => {
  it('maps every official motion source key to one local m4a file', () => {
    expect(Object.keys(MOTION_INSTRUCTION_AUDIO_SRC)).toEqual([
      ...OFFICIAL_MOTION_SOURCE_KEYS,
    ])

    for (const sourceKey of OFFICIAL_MOTION_SOURCE_KEYS) {
      const src = getMotionInstructionAudioSrc(sourceKey)
      expect(src).toBe(
        `/features/motion-training/assets/audio/instructions/${sourceKey}.m4a`,
      )
      expect(existsSync(resolve(`src${src}`))).toBe(true)
    }
  })

  it('does not infer audio for unknown or malformed keys', () => {
    expect(getMotionInstructionAudioSrc('motion-resistance-row-extra')).toBeUndefined()
    expect(getMotionInstructionAudioSrc('坐姿划船')).toBeUndefined()
    expect(getMotionInstructionAudioSrc(undefined)).toBeUndefined()
  })
})
