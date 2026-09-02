export type ChoiceOutcome<T> = {
  selected: T
  correct: boolean
}

export type ChoiceFeedbackState = 'idle' | 'correct' | 'wrong'

export function choiceFeedbackState<T>(
  option: T,
  outcome: ChoiceOutcome<T> | null
): ChoiceFeedbackState {
  if (!outcome || !Object.is(option, outcome.selected)) return 'idle'
  return outcome.correct ? 'correct' : 'wrong'
}
