import type { GameDifficulty } from './gameTypes'

export type ColorToken = 'blue' | 'green' | 'yellow' | 'red' | 'teal'

export type ColorSequenceRound = {
  colors: ColorToken[]
  sequence: ColorToken[]
  revealMs: number
  inputTimeoutMs: number
}

const COLOR_POOL: ColorToken[] = ['blue', 'green', 'yellow', 'red', 'teal']

const CONFIG: Record<
  GameDifficulty,
  { colorCount: number; minLength: number; maxLength: number; revealMs: number; inputTimeoutMs: number }
> = {
  简单: { colorCount: 3, minLength: 3, maxLength: 3, revealMs: 900, inputTimeoutMs: 8000 },
  中等: { colorCount: 4, minLength: 4, maxLength: 5, revealMs: 720, inputTimeoutMs: 6500 },
  困难: { colorCount: 5, minLength: 5, maxLength: 7, revealMs: 560, inputTimeoutMs: 5000 },
}

function pickIndex(length: number, random: () => number): number {
  const value = random()
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.9999999999999999) : 0
  return Math.floor(normalized * length)
}

export function createColorSequenceRound(difficulty: GameDifficulty, random: () => number = Math.random): ColorSequenceRound {
  const config = CONFIG[difficulty]
  const colors = COLOR_POOL.slice(0, config.colorCount)
  const length = config.minLength + pickIndex(config.maxLength - config.minLength + 1, random)
  const sequence = Array.from({ length }, () => colors[pickIndex(colors.length, random)])

  return {
    colors,
    sequence,
    revealMs: config.revealMs,
    inputTimeoutMs: config.inputTimeoutMs,
  }
}

export function evaluateColorSequenceAttempt(expected: ColorToken[], actual: ColorToken[]) {
  const correct = expected.length === actual.length && expected.every((token, index) => token === actual[index])
  return { correct, expected, actual }
}
