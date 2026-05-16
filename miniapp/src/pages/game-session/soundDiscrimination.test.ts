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

const THREE_VARIANT_SOURCES: SoundDiscriminationAudio[] = [
  ...SOURCES.slice(0, 2),
  {
    id: 'bird_3',
    label: '小鸟3',
    category: 'bird',
    imageKey: 'bird',
    src: '/assets/audio/sound-discrimination/bird_3.m4a',
  },
  ...SOURCES.slice(4, 6),
  {
    id: 'phone_3',
    label: '电话铃声3',
    category: 'phone',
    imageKey: 'phone',
    src: '/assets/audio/sound-discrimination/phone_3.m4a',
  },
]

function randomSequence(values: number[]) {
  let index = 0
  return () => values[Math.min(index++, values.length - 1)]
}

describe('createSoundDiscriminationRound', () => {
  it('creates a simple paired-confusion round with four cards and hidden preview state', () => {
    const round = createSoundDiscriminationRound('简单', SOURCES, () => 0)
    const categoryCounts = round.cards.reduce<Record<string, number>>((counts, card) => {
      counts[card.category] = (counts[card.category] ?? 0) + 1
      return counts
    }, {})

    expect(round.cards).toHaveLength(4)
    expect(Object.values(categoryCounts)).toEqual([2, 2])
    expect(round.cards.map((card) => card.soundId)).toContain(round.target.soundId)
    expect(round.cards.every((card) => card.previewed === false)).toBe(true)
    expect(round.previewComplete).toBe(false)
    expect(round.timeoutMs).toBe(8000)
  })

  it('keeps same-category variants on the same image while preserving distinct sound ids', () => {
    const round = createSoundDiscriminationRound('简单', SOURCES.slice(0, 4), () => 0)
    const birds = round.cards.filter((card) => card.category === 'bird')

    expect(new Set(birds.map((card) => card.imageSrc)).size).toBe(1)
    expect(new Set(birds.map((card) => card.soundId))).toEqual(new Set(['bird_1', 'bird_2']))
  })

  it('creates paired categories from shuffled source input', () => {
    const shuffledSources = [SOURCES[4], SOURCES[0], SOURCES[2], SOURCES[5], SOURCES[1], SOURCES[3]]
    const round = createSoundDiscriminationRound('简单', shuffledSources, randomSequence([0.7, 0.1, 0.9, 0.2, 0.4]))
    const selectedCategories = [...new Set(round.cards.map((card) => card.category))]

    expect(selectedCategories).toHaveLength(2)
    selectedCategories.forEach((category) => {
      expect(round.cards.filter((card) => card.category === category)).toHaveLength(2)
    })
  })

  it('can select the third variant from a category instead of always taking the first two', () => {
    const round = createSoundDiscriminationRound('简单', THREE_VARIANT_SOURCES, () => 0)

    expect(round.cards.map((card) => card.soundId)).toContain('bird_3')
    expect(round.cards.map((card) => card.soundId)).toContain('phone_3')
  })

  it('shuffles card order with injected random', () => {
    const firstRound = createSoundDiscriminationRound('简单', SOURCES, () => 0)
    const secondRound = createSoundDiscriminationRound('简单', SOURCES, () => 0.99)

    expect(firstRound.cards.map((card) => card.soundId)).not.toEqual(secondRound.cards.map((card) => card.soundId))
  })

  it('creates a difficult round with at least eight cards and target from cards', () => {
    const round = createSoundDiscriminationRound('困难', SOURCES, () => 0.4)

    expect(round.cards.length).toBeGreaterThanOrEqual(8)
    expect(round.cards.map((card) => card.soundId)).toContain(round.target.soundId)
    expect(round.timeoutMs).toBe(5000)
  })

  it('throws when there are not enough valid groups for the difficulty', () => {
    expect(() => createSoundDiscriminationRound('困难', SOURCES.slice(0, 6), () => 0)).toThrow(
      '声音辨别资源不足，无法生成当前难度题目'
    )
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

  it('is idempotent when previewing the same card more than once', () => {
    const initialRound = createSoundDiscriminationRound('简单', SOURCES, () => 0)
    const cardId = initialRound.cards[0].id
    const previewedOnce = markCardPreviewed(initialRound, cardId)
    const previewedTwice = markCardPreviewed(previewedOnce, cardId)

    expect(previewedTwice).toEqual(previewedOnce)
  })
})

describe('evaluateSoundDiscriminationAttempt', () => {
  const baseRound = createSoundDiscriminationRound('简单', SOURCES.slice(0, 4), () => 0)
  const birdTarget = baseRound.cards.find((card) => card.soundId === 'bird_2')
  const round = {
    ...baseRound,
    target: birdTarget ?? baseRound.target,
  }

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
