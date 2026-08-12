export type GameCode =
  | 'game-memory-color-sequence'
  | 'game-memory-pattern-sequence'
  | 'game-executive-inhibition'
  | 'game-executive-category-switch'
  | 'game-audiovisual-sound-discrimination'
  | 'game-audiovisual-puzzle'

export type GameKind = 'color' | 'pattern' | 'inhibition' | 'category' | 'sound' | 'puzzle'

export type GameIntroAudioKey =
  | 'color_intro'
  | 'pattern_intro'
  | 'inhibition_intro'
  | 'category_intro'
  | 'sound_intro'
  | 'puzzle_intro'

export type GameCatalogItem = {
  code: GameCode
  kind: GameKind
  name: string
  introAudioKey: GameIntroAudioKey
}

export const GAME_CATALOG: Record<GameCode, GameCatalogItem> = {
  'game-memory-color-sequence': {
    code: 'game-memory-color-sequence',
    kind: 'color',
    name: '颜色顺序记忆',
    introAudioKey: 'color_intro',
  },
  'game-memory-pattern-sequence': {
    code: 'game-memory-pattern-sequence',
    kind: 'pattern',
    name: '图案顺序记忆',
    introAudioKey: 'pattern_intro',
  },
  'game-executive-inhibition': {
    code: 'game-executive-inhibition',
    kind: 'inhibition',
    name: '反应抑制',
    introAudioKey: 'inhibition_intro',
  },
  'game-executive-category-switch': {
    code: 'game-executive-category-switch',
    kind: 'category',
    name: '分类切换',
    introAudioKey: 'category_intro',
  },
  'game-audiovisual-sound-discrimination': {
    code: 'game-audiovisual-sound-discrimination',
    kind: 'sound',
    name: '声音辨别',
    introAudioKey: 'sound_intro',
  },
  'game-audiovisual-puzzle': {
    code: 'game-audiovisual-puzzle',
    kind: 'puzzle',
    name: '拼图',
    introAudioKey: 'puzzle_intro',
  },
}

export const GAME_CODE_BY_SOURCE: Record<string, GameCode> = Object.fromEntries(
  Object.entries(GAME_CATALOG).map(([source, game]) => [source, game.code])
) as Record<string, GameCode>

export function gameCodeForActionSource(source: string | null | undefined): GameCode | null {
  if (!source) return null
  return GAME_CODE_BY_SOURCE[source] ?? null
}
