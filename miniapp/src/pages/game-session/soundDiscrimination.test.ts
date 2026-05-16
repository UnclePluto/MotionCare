import { describe, expect, it } from 'vitest'

import {
  createSoundDiscriminationRound,
  evaluateSoundDiscriminationAttempt,
  markCardPreviewed,
} from './soundDiscrimination'
import type { SoundDiscriminationAudio } from './gameAudio'

const SOURCES: SoundDiscriminationAudio[] = [
  {
    id: 'bird_1',
    label: '小鸟1',
    category: 'bird',
    imageKey: 'bird',
    src: '/assets/audio/sound-discrimination/bird_1.m4a',
  },
  {
    id: 'bird_2',
    label: '小鸟2',
    category: 'bird',
    imageKey: 'bird',
    src: '/assets/audio/sound-discrimination/bird_2.m4a',
  },
  {
    id: 'train_1',
    label: '火车汽笛声1',
    category: 'train',
    imageKey: 'train',
    src: '/assets/audio/sound-discrimination/train_1.m4a',
  },
  {
    id: 'train_2',
    label: '火车汽笛声2',
    category: 'train',
    imageKey: 'train',
    src: '/assets/audio/sound-discrimination/train_2.m4a',
  },
  {
    id: 'phone_1',
    label: '电话铃声1',
    category: 'phone',
    imageKey: 'phone',
    src: '/assets/audio/sound-discrimination/phone_1.m4a',
  },
  {
    id: 'phone_2',
    label: '电话铃声2',
    category: 'phone',
    imageKey: 'phone',
    src: '/assets/audio/sound-discrimination/phone_2.m4a',
  },
  {
    id: 'laugh_1',
    label: '笑声1',
    category: 'laugh',
    imageKey: 'laugh',
    src: '/assets/audio/sound-discrimination/laugh_1.m4a',
  },
  {
    id: 'laugh_2',
    label: '笑声2',
    category: 'laugh',
    imageKey: 'laugh',
    src: '/assets/audio/sound-discrimination/laugh_2.m4a',
  },
]

describe('createSoundDiscriminationRound', () => {
  it('creates a simple paired-confusion round with four cards and hidden preview state', () => {
    const round = createSoundDiscriminationRound('简单', SOURCES, () => 0)

    expect(round.cards.map((card) => card.soundId)).toEqual(['bird_1', 'bird_2', 'train_1', 'train_2'])
    expect(round.target.soundId).toBe('bird_1')
    expect(round.cards.filter((card) => card.category === 'bird')).toHaveLength(2)
    expect(round.cards.filter((card) => card.category === 'train')).toHaveLength(2)
    expect(round.cards.every((card) => card.previewed === false)).toBe(true)
    expect(round.previewComplete).toBe(false)
    expect(round.timeoutMs).toBe(8000)
  })

  it('keeps same-category variants on the same image while preserving distinct sound ids', () => {
    const round = createSoundDiscriminationRound('简单', SOURCES, () => 0)
    const birds = round.cards.filter((card) => card.category === 'bird')

    expect(new Set(birds.map((card) => card.imageSrc)).size).toBe(1)
    expect(birds.map((card) => card.soundId)).toEqual(['bird_1', 'bird_2'])
  })

  it('creates a difficult round with at least eight cards and target from cards', () => {
    const round = createSoundDiscriminationRound('困难', SOURCES, () => 0.4)

    expect(round.cards.length).toBeGreaterThanOrEqual(8)
    expect(round.cards.map((card) => card.soundId)).toContain(round.target.soundId)
    expect(round.timeoutMs).toBe(5000)
  })
})

describe('markCardPreviewed', () => {
  it('marks preview complete only after every card has been previewed', () => {
    const initialRound = createSoundDiscriminationRound('简单', SOURCES, () => 0)
    const round = initialRound.cards.reduce(
      (currentRound, card) => markCardPreviewed(currentRound, card.id),
      initialRound
    )

    expect(initialRound.previewComplete).toBe(false)
    expect(initialRound.cards.every((card) => card.previewed === false)).toBe(true)
    expect(round.cards.every((card) => card.previewed === true)).toBe(true)
    expect(round.previewComplete).toBe(true)
  })
})

describe('evaluateSoundDiscriminationAttempt', () => {
  const round = createSoundDiscriminationRound('简单', SOURCES, () => 0.25)

  it('requires an exact soundId match instead of category match', () => {
    expect(round.target.soundId).toBe('bird_2')
    expect(evaluateSoundDiscriminationAttempt(round, 'bird_2')).toEqual({
      correct: true,
      correctSoundId: 'bird_2',
      selectedSoundId: 'bird_2',
    })
    expect(evaluateSoundDiscriminationAttempt(round, 'bird_1')).toEqual({
      correct: false,
      correctSoundId: 'bird_2',
      selectedSoundId: 'bird_1',
    })
  })
})
