import type { SignedAssetManifest } from '../../assets/signedAssetManifest'
import type { GameCode } from './gameTypes'
import { type GeneratedGameImageKey } from './gameImageAssetManifest.generated'

export type GameImageKey = GeneratedGameImageKey

export type LoadedGameImagePathMap = Readonly<Partial<Record<GameImageKey, string>>>

const EMPTY_IMAGE_KEYS: readonly GameImageKey[] = []

const REQUIRED_IMAGE_KEYS: Readonly<Partial<Record<GameCode, readonly GameImageKey[]>>> = {
  'game-memory-pattern-sequence': [
    'pattern_sun',
    'pattern_coconut',
    'pattern_boat',
    'pattern_lighthouse',
    'pattern_shell',
  ],
  'game-executive-category-switch': [
    'category_pineapple',
    'category_bird',
    'category_train',
    'category_drum',
    'category_phone',
  ],
  'game-audiovisual-sound-discrimination': [
    'sound_bird',
    'sound_train',
    'sound_phone',
    'sound_laugh',
    'sound_drum',
  ],
  'game-audiovisual-puzzle': [
    'puzzle_beach',
    'puzzle_garden',
    'puzzle_lighthouse',
  ],
}

export function requiredGameImageKeys(gameCode: GameCode | null): readonly GameImageKey[] {
  if (!gameCode) return EMPTY_IMAGE_KEYS
  return REQUIRED_IMAGE_KEYS[gameCode] ?? EMPTY_IMAGE_KEYS
}

export function gameImageRemoteUrl(key: GameImageKey, manifest: SignedAssetManifest): string {
  return manifest.urls[key]
}

export function loadedGameImagePath(paths: LoadedGameImagePathMap, key: GameImageKey): string {
  const path = paths[key]
  if (!path) throw new Error(`游戏图片尚未准备完成：${key}`)
  return path
}
