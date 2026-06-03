import { describe, expect, it } from 'vitest'

import { createGameIntroSteps } from './gameIntro'

describe('createGameIntroSteps', () => {
  it('plays the game intro once before countdown and start', () => {
    expect(createGameIntroSteps('sound_intro')).toEqual([
      { key: 'sound_intro', minMs: 1200 },
      { key: 'count_3', minMs: 700 },
      { key: 'count_2', minMs: 700 },
      { key: 'count_1', minMs: 700 },
      { key: 'start', minMs: 700 },
    ])
  })
})
