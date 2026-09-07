import type {
  SoundDiscriminationAudio,
  SoundDiscriminationAudioId,
  SoundDiscriminationCategory,
} from './gameAudio'
import type { GameDifficulty } from './gameTypes'
import type { GameImageKey } from './gameImageAssets'

export type SoundCard = {
  id: string
  soundId: SoundDiscriminationAudioId
  label: string
  category: SoundDiscriminationCategory
  imageKey: GameImageKey
  audioSrc: string
  previewed: boolean
}

export type SoundDiscriminationRound = {
  cards: SoundCard[]
  target: SoundCard
  previewComplete: boolean
  timeoutMs: number
}

export type SoundAttemptOutcome = {
  selectedCardId: string
  correct: boolean
}

export type SoundCardVisualState = 'back' | 'preview' | 'correct' | 'wrong'

export const SOUND_CARD_RETURN_MS = 180

export type SoundCardPreviewReturnOptions = {
  previewPlayed: boolean
  isRunCurrent: () => boolean
  clearPreviewingCard: () => void
  waitForReturn: (ms: number) => Promise<void>
  onPreviewPlaybackFailure: () => void
}

export type SoundPreviewAfterShowOptions = {
  sessionIsPlaying: boolean
  isSoundGame: boolean
  soundPhase: 'preview' | 'choose'
  hasActiveRound: boolean
  previewInFlight: boolean
  startPreview: () => void
}

const SOUND_IMAGE_KEY: Record<SoundDiscriminationCategory, GameImageKey> = {
  bird: 'sound_bird',
  train: 'sound_train',
  phone: 'sound_phone',
  laugh: 'sound_laugh',
  drum: 'sound_drum',
}

const CONFIG: Record<GameDifficulty, { optionCount: number; timeoutMs: number }> = {
  简单: { optionCount: 3, timeoutMs: 8000 },
  中等: { optionCount: 4, timeoutMs: 6500 },
  困难: { optionCount: 5, timeoutMs: 5000 },
}

function pickIndex(length: number, random: () => number): number {
  const value = random()
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.9999999999999999) : 0
  return Math.floor(normalized * length)
}

function shuffle<T>(items: T[], random: () => number): T[] {
  const result = [...items]

  for (let index = result.length - 1; index > 0; index -= 1) {
    const swapIndex = pickIndex(index + 1, random)
    const current = result[index]
    result[index] = result[swapIndex]
    result[swapIndex] = current
  }

  return result
}

export function groupedByCategory(sources: SoundDiscriminationAudio[]): SoundDiscriminationAudio[][] {
  const groups = new Map<SoundDiscriminationCategory, SoundDiscriminationAudio[]>()

  sources.forEach((source) => {
    const existing = groups.get(source.category) ?? []
    existing.push(source)
    groups.set(source.category, existing)
  })

  return Array.from(groups.values()).filter((group) => group.length >= 2)
}

function toCard(source: SoundDiscriminationAudio): SoundCard {
  return {
    id: `sound-card-${source.id}`,
    soundId: source.id,
    label: source.label,
    category: source.category,
    imageKey: SOUND_IMAGE_KEY[source.imageKey],
    audioSrc: source.src,
    previewed: false,
  }
}

export function createSoundDiscriminationRound(
  difficulty: GameDifficulty,
  sources: SoundDiscriminationAudio[],
  random: () => number = Math.random
): SoundDiscriminationRound {
  const config = CONFIG[difficulty]
  const groups = groupedByCategory(sources)
  const groupCount = Math.ceil(config.optionCount / 2)

  if (groups.length < groupCount) {
    throw new Error('声音辨别资源不足，无法生成当前难度题目')
  }

  const selectedGroups = shuffle(groups, random).slice(0, groupCount)
  // 奇数张保留成对干扰声，最后一类只取一张，然后打乱卡片位置。
  const selectedSources = selectedGroups.flatMap((group) => shuffle(group, random).slice(0, 2)).slice(0, config.optionCount)
  const cards = shuffle(selectedSources.map(toCard), random)

  return {
    cards,
    target: cards[pickIndex(cards.length, random)],
    previewComplete: false,
    timeoutMs: config.timeoutMs,
  }
}

export function markCardPreviewed(round: SoundDiscriminationRound, cardId: string): SoundDiscriminationRound {
  const cards = round.cards.map((card) => (card.id === cardId ? { ...card, previewed: true } : card))

  return {
    ...round,
    cards,
    previewComplete: cards.every((card) => card.previewed),
  }
}

export function nextSoundPreviewCard(round: SoundDiscriminationRound): SoundCard | null {
  return round.cards.find((card) => !card.previewed) ?? null
}

export function evaluateSoundDiscriminationAttempt(round: SoundDiscriminationRound, selectedSoundId: string) {
  return {
    correct: selectedSoundId === round.target.soundId,
    correctSoundId: round.target.soundId,
    selectedSoundId,
  }
}

export function soundCardVisualState(
  cardId: string,
  previewingCardId: string | null,
  outcome: SoundAttemptOutcome | null
): SoundCardVisualState {
  if (previewingCardId === cardId) return 'preview'
  if (outcome?.selectedCardId !== cardId) return 'back'
  return outcome.correct ? 'correct' : 'wrong'
}

export async function finishSoundCardPreview({
  previewPlayed,
  isRunCurrent,
  clearPreviewingCard,
  waitForReturn,
  onPreviewPlaybackFailure,
}: SoundCardPreviewReturnOptions): Promise<boolean> {
  if (!isRunCurrent()) return false
  clearPreviewingCard()
  await waitForReturn(SOUND_CARD_RETURN_MS)
  if (!isRunCurrent()) return false
  if (!previewPlayed) onPreviewPlaybackFailure()
  return true
}

export function resumeSoundPreviewAfterShow({
  sessionIsPlaying,
  isSoundGame,
  soundPhase,
  hasActiveRound,
  previewInFlight,
  startPreview,
}: SoundPreviewAfterShowOptions): boolean {
  if (!sessionIsPlaying || !isSoundGame || soundPhase !== 'preview' || !hasActiveRound || previewInFlight) {
    return false
  }
  startPreview()
  return true
}
