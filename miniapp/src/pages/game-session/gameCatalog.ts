import type { GameAudioKey } from './gameAudio'
import type { GameCode } from './gameTypes'

export type GameCatalogEntry = {
  source: GameCode
  code: GameCode
  introAudioKey: GameAudioKey
}

export const GAME_CATALOG: GameCatalogEntry[] = [
  {
    source: 'game-memory-color-sequence',
    code: 'game-memory-color-sequence',
    introAudioKey: 'color_intro',
  },
  {
    source: 'game-memory-pattern-sequence',
    code: 'game-memory-pattern-sequence',
    introAudioKey: 'pattern_intro',
  },
  {
    source: 'game-executive-inhibition',
    code: 'game-executive-inhibition',
    introAudioKey: 'inhibition_intro',
  },
  {
    source: 'game-executive-category-switch',
    code: 'game-executive-category-switch',
    introAudioKey: 'category_intro',
  },
  {
    source: 'game-audiovisual-sound-discrimination',
    code: 'game-audiovisual-sound-discrimination',
    introAudioKey: 'sound_intro',
  },
  {
    source: 'game-audiovisual-puzzle',
    code: 'game-audiovisual-puzzle',
    introAudioKey: 'puzzle_intro',
  },
]

export const GAME_CODE_BY_SOURCE: Record<string, GameCode> = Object.fromEntries(
  GAME_CATALOG.map((game) => [game.source, game.code])
) as Record<string, GameCode>

export function gameCodeForActionSource(source: string | null | undefined): GameCode | null {
  if (!source) return null
  return GAME_CODE_BY_SOURCE[source] ?? null
}
