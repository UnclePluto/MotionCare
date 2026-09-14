import type { GameCode, GameDifficulty } from './gameTypes'

export type GameQuestionResultType = 'answered' | 'timeout' | 'interrupted'

export type GameQuestionSelectionStep = {
  step_index: number
  selected_value: string
  expected_value: string
  response_duration_ms: number
  is_correct: boolean
}

export type GameQuestionPayload = {
  capture_version?: 'active_response_v1' | 'active_response_v2'
  expected_step_count?: number | null
  selection_steps?: GameQuestionSelectionStep[]
  click_count?: number | null
  question_index: number
  game_code: GameCode
  difficulty: GameDifficulty
  response_duration_ms: number
  is_correct: boolean
  result_type: GameQuestionResultType
  swap_count: number | null
}

export type QuestionCapture = {
  begin: (gameCode: GameCode, difficulty: GameDifficulty) => void
  pause: () => void
  resume: () => void
  finish: (isCorrect: boolean, resultType: GameQuestionResultType) => GameQuestionPayload | null
  recordSelection: (selected: string, expected: string) => void
  recordClick: () => void
  recordSwap: () => void
  discard: () => void
  reset: () => void
  results: () => GameQuestionPayload[]
}

type CurrentQuestion = {
  gameCode: GameCode
  difficulty: GameDifficulty
  activeStartedAt: number | null
  elapsedMs: number
  swapCount: number
  clickCount: number
  expectedStepCount: number | null
  steps: GameQuestionSelectionStep[]
  lastStepElapsedMs: number
}

function copyResult(result: GameQuestionPayload): GameQuestionPayload {
  return { ...result, selection_steps: result.selection_steps?.map(step => ({ ...step })) }
}

export function createQuestionCapture(now: () => number): QuestionCapture {
  let currentQuestion: CurrentQuestion | null = null
  let lastClockValue: number | null = null
  let capturedResults: GameQuestionPayload[] = []

  function readClock(): number {
    const value = now()
    if (!Number.isFinite(value) || (lastClockValue !== null && value < lastClockValue)) {
      throw new Error('作答时钟无效')
    }
    lastClockValue = value
    return value
  }

  function pause(): void {
    if (currentQuestion === null || currentQuestion.activeStartedAt === null) return
    const current = readClock()
    currentQuestion.elapsedMs += current - currentQuestion.activeStartedAt
    currentQuestion.activeStartedAt = null
  }

  return {
    begin(gameCode, difficulty) {
      currentQuestion = {
        gameCode,
        difficulty,
        activeStartedAt: readClock(),
        elapsedMs: 0,
        swapCount: 0,
        clickCount: 0,
        expectedStepCount: gameCode === 'game-memory-color-sequence' || gameCode === 'game-memory-pattern-sequence'
          ? ({ '简单': 3, '中等': 4, '困难': 5 }[difficulty]) : null,
        steps: [],
        lastStepElapsedMs: 0,
      }
    },

    pause,

    resume() {
      if (currentQuestion === null || currentQuestion.activeStartedAt !== null) return
      currentQuestion.activeStartedAt = readClock()
    },

    finish(isCorrect, resultType) {
      if (currentQuestion === null) return null
      if (resultType === 'interrupted' && (currentQuestion.expectedStepCount === null
        || currentQuestion.steps.length === 0 || currentQuestion.steps.length >= currentQuestion.expectedStepCount)) {
        currentQuestion = null
        return null
      }
      pause()
      const result: GameQuestionPayload = {
        capture_version: 'active_response_v2',
        expected_step_count: currentQuestion.expectedStepCount,
        selection_steps: currentQuestion.steps,
        click_count: currentQuestion.gameCode === 'game-audiovisual-puzzle' ? currentQuestion.clickCount : null,
        question_index: capturedResults.length + 1,
        game_code: currentQuestion.gameCode,
        difficulty: currentQuestion.difficulty,
        response_duration_ms: Math.round(currentQuestion.elapsedMs),
        is_correct: resultType === 'interrupted' ? false : isCorrect,
        result_type: resultType,
        swap_count: currentQuestion.gameCode === 'game-audiovisual-puzzle'
          ? currentQuestion.swapCount
          : null,
      }
      capturedResults.push(result)
      currentQuestion = null
      return copyResult(result)
    },

    recordSelection(selected, expected) {
      if (!currentQuestion || currentQuestion.activeStartedAt === null || currentQuestion.expectedStepCount === null
        || currentQuestion.steps.length >= currentQuestion.expectedStepCount) return
      const elapsed = Math.round(currentQuestion.elapsedMs + readClock() - currentQuestion.activeStartedAt)
      currentQuestion.steps.push({
        step_index: currentQuestion.steps.length + 1,
        selected_value: selected,
        expected_value: expected,
        response_duration_ms: elapsed - currentQuestion.lastStepElapsedMs,
        is_correct: selected === expected,
      })
      currentQuestion.lastStepElapsedMs = elapsed
    },

    recordClick() {
      if (currentQuestion?.gameCode === 'game-audiovisual-puzzle' && currentQuestion.activeStartedAt !== null) {
        currentQuestion.clickCount += 1
      }
    },

    recordSwap() {
      if (currentQuestion !== null) currentQuestion.swapCount += 1
    },

    discard() {
      currentQuestion = null
    },

    reset() {
      currentQuestion = null
      capturedResults = []
      lastClockValue = null
    },

    results() {
      return capturedResults.map(copyResult)
    },
  }
}
