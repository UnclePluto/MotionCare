import type { GameAudioKey } from './gameAudio'

export type GameIntroStep = {
  key: GameAudioKey
  minMs: number
}

export function createGameIntroSteps(introKey: GameAudioKey): GameIntroStep[] {
  return [
    { key: introKey, minMs: 1200 },
    { key: 'count_3', minMs: 700 },
    { key: 'count_2', minMs: 700 },
    { key: 'count_1', minMs: 700 },
    { key: 'start', minMs: 700 },
  ]
}
