import type {
  SoundDiscriminationAudio,
  SoundDiscriminationAudioId,
  SoundDiscriminationCategory,
} from './gameAudio'
import type { GameDifficulty } from './gameTypes'

export type SoundCard = {
  id: string
  soundId: SoundDiscriminationAudioId
  label: string
  category: SoundDiscriminationCategory
  imageKey: SoundDiscriminationCategory
  imageSrc: string
  audioSrc: string
  previewed: boolean
}

export type SoundDiscriminationRound = {
  cards: SoundCard[]
  target: SoundCard
  previewComplete: boolean
  timeoutMs: number
}

export const CATEGORY_IMAGE_SRC: Record<SoundDiscriminationCategory, string> = {
  bird: '/assets/images/game-session/sound_bird.svg',
  train: '/assets/images/game-session/sound_train.svg',
  phone: '/assets/images/game-session/sound_phone.svg',
  laugh: '/assets/images/game-session/sound_laugh.svg',
  drum: '/assets/images/game-session/sound_drum.svg',
}

const CONFIG: Record<GameDifficulty, { pairCount: number; timeoutMs: number }> = {
  简单: { pairCount: 2, timeoutMs: 8000 },
  中等: { pairCount: 3, timeoutMs: 6500 },
  困难: { pairCount: 4, timeoutMs: 5000 },
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
    imageKey: source.imageKey,
    imageSrc: CATEGORY_IMAGE_SRC[source.imageKey],
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

  if (groups.length < config.pairCount) {
    throw new Error('声音辨别资源不足，无法生成当前难度题目')
  }

  const selectedGroups = shuffle(groups, random).slice(0, config.pairCount)
  const selectedSources = selectedGroups.flatMap((group) => shuffle(group, random).slice(0, 2))
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

export function evaluateSoundDiscriminationAttempt(round: SoundDiscriminationRound, selectedSoundId: string) {
  return {
    correct: selectedSoundId === round.target.soundId,
    correctSoundId: round.target.soundId,
    selectedSoundId,
  }
}
