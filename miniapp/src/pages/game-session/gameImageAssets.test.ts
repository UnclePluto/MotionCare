import { afterEach, describe, expect, it, vi } from 'vitest'

import { GAME_IMAGE_ASSET_PATHS } from './gameImageAssetManifest.generated'
import {
  gameImageRemoteUrl,
  loadedGameImagePath,
  requiredGameImageKeys,
  type GameImageKey,
  type LoadedGameImagePathMap,
} from './gameImageAssets'

const PATTERN_KEYS = [
  'pattern_sun',
  'pattern_coconut',
  'pattern_boat',
  'pattern_lighthouse',
  'pattern_shell',
] as const

const CATEGORY_KEYS = [
  'category_pineapple',
  'category_bird',
  'category_train',
  'category_drum',
  'category_phone',
] as const

const SOUND_KEYS = [
  'sound_bird',
  'sound_train',
  'sound_phone',
  'sound_laugh',
  'sound_drum',
] as const

const PUZZLE_KEYS = [
  'puzzle_beach',
  'puzzle_garden',
  'puzzle_lighthouse',
] as const

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('requiredGameImageKeys', () => {
  it('returns the exact image set required by each image-based game', () => {
    expect(requiredGameImageKeys('game-memory-pattern-sequence')).toEqual(PATTERN_KEYS)
    expect(requiredGameImageKeys('game-executive-category-switch')).toEqual(CATEGORY_KEYS)
    expect(requiredGameImageKeys('game-audiovisual-sound-discrimination')).toEqual(SOUND_KEYS)
    expect(requiredGameImageKeys('game-audiovisual-puzzle')).toEqual(PUZZLE_KEYS)
  })

  it('returns no image keys for the two image-free games', () => {
    expect(requiredGameImageKeys('game-memory-color-sequence')).toEqual([])
    expect(requiredGameImageKeys('game-executive-inhibition')).toEqual([])
  })

  it('returns no image keys for empty or unknown game codes', () => {
    expect(requiredGameImageKeys(null)).toEqual([])
    expect(requiredGameImageKeys('' as never)).toEqual([])
    expect(requiredGameImageKeys('game-unknown' as never)).toEqual([])
  })

  it('covers the generated 18-key manifest exactly without duplicate requirements', () => {
    const requiredKeys = [
      ...requiredGameImageKeys('game-memory-pattern-sequence'),
      ...requiredGameImageKeys('game-executive-category-switch'),
      ...requiredGameImageKeys('game-audiovisual-sound-discrimination'),
      ...requiredGameImageKeys('game-audiovisual-puzzle'),
    ]

    expect(requiredKeys).toHaveLength(18)
    expect(new Set(requiredKeys).size).toBe(18)
    expect([...requiredKeys].sort()).toEqual(Object.keys(GAME_IMAGE_ASSET_PATHS).sort())
  })

  it('uses a gameplay prefix and a stable snake-case identifier for every key', () => {
    const keys = Object.keys(GAME_IMAGE_ASSET_PATHS) as GameImageKey[]

    expect(keys.every((key) => /^(pattern|category|sound|puzzle)_[a-z]+$/.test(key))).toBe(true)
  })
})

describe('game image paths', () => {
  it('builds the remote URL through the generated manifest path', () => {
    vi.stubEnv('TARO_APP_ASSET_BASE_URL', 'https://cdn.example.com/assets/')

    expect(gameImageRemoteUrl('pattern_sun')).toBe(
      'https://cdn.example.com/assets/v-3aafe09211fd/pattern_sun.e27f9237d484.webp'
    )
  })

  it('reads one prepared game subset without requiring all 18 keys', () => {
    const paths: LoadedGameImagePathMap = {
      puzzle_beach: 'wxfile://game-images/puzzle_beach.webp',
    }

    expect(loadedGameImagePath(paths, 'puzzle_beach')).toBe('wxfile://game-images/puzzle_beach.webp')
  })

  it('throws when the requested key is missing from the prepared subset', () => {
    const paths: LoadedGameImagePathMap = {
      puzzle_beach: 'wxfile://game-images/puzzle_beach.webp',
    }

    expect(() => loadedGameImagePath(paths, 'puzzle_garden')).toThrow(
      '游戏图片尚未准备完成：puzzle_garden'
    )
  })
})
