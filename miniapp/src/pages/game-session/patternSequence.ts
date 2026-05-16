import type { GameDifficulty } from './gameTypes'

export type PatternTokenId = 'sun' | 'coconut' | 'boat' | 'lighthouse' | 'shell'

export type PatternToken = {
  id: PatternTokenId
  label: string
  imageSrc: string
  fallback: string
}

export type PatternSequenceRound = {
  patterns: PatternToken[]
  sequence: PatternTokenId[]
  revealMs: number
  inputTimeoutMs: number
}

const PATTERN_POOL: PatternToken[] = [
  { id: 'sun', label: '太阳', imageSrc: '/assets/images/game-session/pattern_sun.svg', fallback: '日' },
  { id: 'coconut', label: '椰子树', imageSrc: '/assets/images/game-session/pattern_coconut.svg', fallback: '椰' },
  { id: 'boat', label: '小船', imageSrc: '/assets/images/game-session/pattern_boat.svg', fallback: '船' },
  { id: 'lighthouse', label: '灯塔', imageSrc: '/assets/images/game-session/pattern_lighthouse.svg', fallback: '塔' },
  { id: 'shell', label: '贝壳', imageSrc: '/assets/images/game-session/pattern_shell.svg', fallback: '贝' },
]

const CONFIG: Record<
  GameDifficulty,
  { patternCount: number; minLength: number; maxLength: number; revealMs: number; inputTimeoutMs: number }
> = {
  简单: { patternCount: 3, minLength: 3, maxLength: 3, revealMs: 900, inputTimeoutMs: 8000 },
  中等: { patternCount: 4, minLength: 4, maxLength: 5, revealMs: 720, inputTimeoutMs: 6500 },
  困难: { patternCount: 5, minLength: 5, maxLength: 7, revealMs: 560, inputTimeoutMs: 5000 },
}

function pickIndex(length: number, random: () => number): number {
  const value = random()
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.9999999999999999) : 0
  return Math.floor(normalized * length)
}

export function createPatternSequenceRound(
  difficulty: GameDifficulty,
  random: () => number = Math.random
): PatternSequenceRound {
  const config = CONFIG[difficulty]
  const patterns = PATTERN_POOL.slice(0, config.patternCount)
  const length = config.minLength + pickIndex(config.maxLength - config.minLength + 1, random)
  const sequence = Array.from({ length }, () => patterns[pickIndex(patterns.length, random)].id)

  return {
    patterns,
    sequence,
    revealMs: config.revealMs,
    inputTimeoutMs: config.inputTimeoutMs,
  }
}

export function evaluatePatternSequenceAttempt(expected: string[], actual: string[]) {
  const correct = expected.length === actual.length && expected.every((token, index) => token === actual[index])
  return { correct, expected, actual }
}
