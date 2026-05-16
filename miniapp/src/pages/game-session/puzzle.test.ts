import { describe, expect, it } from 'vitest'

import { createPuzzleRound, evaluatePuzzleCompletion, swapPuzzleTiles } from './puzzle'

function randomSequence(values: number[]) {
  let index = 0
  return () => values[Math.min(index++, values.length - 1)]
}

describe('createPuzzleRound', () => {
  it('creates a simple 2x2 round with four shuffled tiles and long preview', () => {
    const round = createPuzzleRound('简单', randomSequence([0, 0, 0, 0]))

    expect(round.imageKey).toBe('beach')
    expect(round.imageSrc).toBe('/assets/images/game-session/puzzle_beach.svg')
    expect(round.gridSize).toEqual({ rows: 2, cols: 2 })
    expect(round.rows).toBe(2)
    expect(round.cols).toBe(2)
    expect(round.tileCount).toBe(4)
    expect(round.previewMs).toBe(3500)
    expect(round.tiles).toHaveLength(4)
    expect(round.shuffledTiles).toHaveLength(4)
    expect(evaluatePuzzleCompletion(round.tiles)).toBe(true)
    expect(evaluatePuzzleCompletion(round.shuffledTiles)).toBe(false)
  })

  it('creates a medium 2x3 round with six tiles and medium preview', () => {
    const round = createPuzzleRound('中等', randomSequence([0, 0, 0, 0, 0, 0]))

    expect(round.gridSize).toEqual({ rows: 2, cols: 3 })
    expect(round.rows).toBe(2)
    expect(round.cols).toBe(3)
    expect(round.tileCount).toBe(6)
    expect(round.previewMs).toBe(2800)
    expect(round.tiles).toHaveLength(6)
    expect(round.shuffledTiles).toHaveLength(6)
    expect(evaluatePuzzleCompletion(round.tiles)).toBe(true)
    expect(evaluatePuzzleCompletion(round.shuffledTiles)).toBe(false)
  })

  it('creates a difficult 3x3 round with nine tiles and short preview', () => {
    const round = createPuzzleRound('困难', randomSequence([0, 0, 0, 0, 0, 0, 0, 0, 0]))

    expect(round.gridSize).toEqual({ rows: 3, cols: 3 })
    expect(round.rows).toBe(3)
    expect(round.cols).toBe(3)
    expect(round.tileCount).toBe(9)
    expect(round.previewMs).toBe(2200)
    expect(round.tiles).toHaveLength(9)
    expect(round.shuffledTiles).toHaveLength(9)
  })

  it('uses random to select different images', () => {
    const beachRound = createPuzzleRound('简单', randomSequence([0, 0, 0, 0]))
    const lighthouseRound = createPuzzleRound('简单', randomSequence([0.99, 0, 0, 0]))

    expect(beachRound.imageKey).toBe('beach')
    expect(beachRound.imageSrc).toBe('/assets/images/game-session/puzzle_beach.svg')
    expect(lighthouseRound.imageKey).toBe('lighthouse')
    expect(lighthouseRound.imageSrc).toBe('/assets/images/game-session/puzzle_lighthouse.svg')
  })

  it('uses random to create different tile orders instead of a fixed first-pair swap', () => {
    const firstRound = createPuzzleRound('简单', randomSequence([0, 0, 0, 0]))
    const secondRound = createPuzzleRound('简单', randomSequence([0, 0.99, 0.99, 0.99]))
    const firstOrder = firstRound.shuffledTiles.map((tile) => tile.correctIndex)
    const secondOrder = secondRound.shuffledTiles.map((tile) => tile.correctIndex)

    expect(firstOrder).not.toEqual(secondOrder)
    expect(firstOrder).not.toEqual([1, 0, 2, 3])
    expect(secondOrder).not.toEqual([0, 1, 2, 3])
  })
})

describe('swapPuzzleTiles', () => {
  it('swaps the first two tiles without mutating the input', () => {
    const round = createPuzzleRound('简单', randomSequence([0, 0, 0, 0]))
    const firstTile = round.shuffledTiles[0]
    const secondTile = round.shuffledTiles[1]
    const swapped = swapPuzzleTiles(round.shuffledTiles, firstTile.id, secondTile.id)

    expect(swapped[0]).toBe(secondTile)
    expect(swapped[1]).toBe(firstTile)
    expect(round.shuffledTiles[0]).toBe(firstTile)
    expect(round.shuffledTiles[1]).toBe(secondTile)
  })

  it('returns the original array when swapping the same tile id', () => {
    const round = createPuzzleRound('简单', randomSequence([0, 0, 0, 0]))
    const tilesBefore = [...round.shuffledTiles]
    const swapped = swapPuzzleTiles(round.shuffledTiles, round.shuffledTiles[0].id, round.shuffledTiles[0].id)

    expect(swapped).toBe(round.shuffledTiles)
    expect(round.shuffledTiles).toEqual(tilesBefore)
  })

  it('returns the original array and does not mutate when either tile id is missing', () => {
    const round = createPuzzleRound('简单', randomSequence([0, 0, 0, 0]))
    const tilesBefore = [...round.shuffledTiles]
    const swapped = swapPuzzleTiles(round.shuffledTiles, round.shuffledTiles[0].id, 'missing-tile')

    expect(swapped).toBe(round.shuffledTiles)
    expect(round.shuffledTiles).toEqual(tilesBefore)
  })
})

describe('evaluatePuzzleCompletion', () => {
  it('returns true for the correct tile order', () => {
    const round = createPuzzleRound('简单', randomSequence([0, 0, 0, 0]))

    expect(evaluatePuzzleCompletion(round.tiles)).toBe(true)
  })
})
