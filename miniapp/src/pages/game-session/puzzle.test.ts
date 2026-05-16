import { describe, expect, it } from 'vitest'

import { createPuzzleRound, evaluatePuzzleCompletion, swapPuzzleTiles } from './puzzle'

describe('createPuzzleRound', () => {
  it('creates a simple 2x2 round with four shuffled tiles and long preview', () => {
    const round = createPuzzleRound('简单', () => 0)

    expect(round.rows).toBe(2)
    expect(round.cols).toBe(2)
    expect(round.previewMs).toBe(3500)
    expect(round.tiles).toHaveLength(4)
    expect(evaluatePuzzleCompletion(round.tiles)).toBe(false)
  })

  it('creates a difficult 3x3 round with nine tiles and short preview', () => {
    const round = createPuzzleRound('困难', () => 0)

    expect(round.rows).toBe(3)
    expect(round.cols).toBe(3)
    expect(round.previewMs).toBe(2200)
    expect(round.tiles).toHaveLength(9)
  })
})

describe('swapPuzzleTiles', () => {
  it('swaps the first two tiles without mutating the input', () => {
    const round = createPuzzleRound('简单', () => 0)
    const firstTile = round.tiles[0]
    const secondTile = round.tiles[1]
    const swapped = swapPuzzleTiles(round.tiles, firstTile.id, secondTile.id)

    expect(swapped[0]).toBe(secondTile)
    expect(swapped[1]).toBe(firstTile)
    expect(round.tiles[0]).toBe(firstTile)
    expect(round.tiles[1]).toBe(secondTile)
  })
})

describe('evaluatePuzzleCompletion', () => {
  it('returns true for the correct tile order', () => {
    const round = createPuzzleRound('简单', () => 0)
    const completedTiles = [...round.tiles].sort((left, right) => left.correctIndex - right.correctIndex)

    expect(evaluatePuzzleCompletion(completedTiles)).toBe(true)
  })
})
