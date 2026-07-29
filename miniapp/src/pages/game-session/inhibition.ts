import type { GameDifficulty } from './gameTypes'

export type InhibitionRound = {
  options: string[]
  correctIndex: number
  timeoutMs: number
}

const CONFIG: Record<GameDifficulty, { optionCount: number; timeoutMs: number }> = {
  简单: { optionCount: 4, timeoutMs: 7000 },
  中等: { optionCount: 6, timeoutMs: 5500 },
  困难: { optionCount: 9, timeoutMs: 4000 },
}

function pickIndex(length: number, random: () => number): number {
  const value = random()
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.9999999999999999) : 0
  return Math.floor(normalized * length)
}

export function createInhibitionRound(difficulty: GameDifficulty, random: () => number = Math.random): InhibitionRound {
  const config = CONFIG[difficulty]
  const baseDigit = String(pickIndex(8, random) + 1)
  const oddDigit = baseDigit === '9' ? '1' : String(Number(baseDigit) + 1)
  const correctIndex = pickIndex(config.optionCount, random)
  const options = Array.from({ length: config.optionCount }, (_value, index) =>
    index === correctIndex ? oddDigit : baseDigit
  )

  return {
    options,
    correctIndex,
    timeoutMs: config.timeoutMs,
  }
}

export function evaluateInhibitionAttempt(round: Pick<InhibitionRound, 'correctIndex'>, selectedIndex: number) {
  return {
    correct: selectedIndex === round.correctIndex,
    correctIndex: round.correctIndex,
    selectedIndex,
  }
}
