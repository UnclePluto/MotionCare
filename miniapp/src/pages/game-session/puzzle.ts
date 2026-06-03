import type { GameDifficulty } from './gameTypes'

export type PuzzleTile = {
  id: string
  correctIndex: number
}

export type PuzzleImageKey = 'beach' | 'garden' | 'lighthouse'

export type PuzzleRound = {
  imageKey: PuzzleImageKey
  imageSrc: string
  gridSize: {
    rows: number
    cols: number
  }
  rows: number
  cols: number
  tileCount: number
  previewMs: number
  tiles: PuzzleTile[]
  shuffledTiles: PuzzleTile[]
  solutionTiles: PuzzleTile[]
}

export type PuzzleTileImageStyle = {
  position: 'absolute'
  display: 'block'
  width: string
  height: string
  left: string
  top: string
}

export const PUZZLE_IMAGES = [
  { key: 'beach', src: '/pages/game-session/assets/images/game-session/puzzle_beach.png' },
  { key: 'garden', src: '/pages/game-session/assets/images/game-session/puzzle_garden.png' },
  { key: 'lighthouse', src: '/pages/game-session/assets/images/game-session/puzzle_lighthouse.png' },
] as const

const CONFIG: Record<GameDifficulty, { rows: number; cols: number; previewMs: number }> = {
  简单: { rows: 2, cols: 2, previewMs: 3500 },
  中等: { rows: 2, cols: 3, previewMs: 2800 },
  困难: { rows: 3, cols: 3, previewMs: 2200 },
}

function pickIndex(length: number, random: () => number): number {
  const value = random()
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.9999999999999999) : 0
  return Math.floor(normalized * length)
}

function createTiles(count: number): PuzzleTile[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `puzzle-tile-${index}`,
    correctIndex: index,
  }))
}

function shuffledTiles(count: number, random: () => number): PuzzleTile[] {
  const tiles = createTiles(count)

  if (tiles.length < 2) {
    return tiles
  }

  const result = [...tiles]

  for (let index = result.length - 1; index > 0; index -= 1) {
    const swapIndex = pickIndex(index + 1, random)
    const current = result[index]
    result[index] = result[swapIndex]
    result[swapIndex] = current
  }

  if (evaluatePuzzleCompletion(result)) {
    return swapPuzzleTiles(result, result[0].id, result[1].id)
  }

  return result
}

export function createPuzzleRound(difficulty: GameDifficulty, random: () => number = Math.random): PuzzleRound {
  const config = CONFIG[difficulty]
  const tileCount = config.rows * config.cols
  const image = PUZZLE_IMAGES[pickIndex(PUZZLE_IMAGES.length, random)]
  const solutionTiles = createTiles(tileCount)
  const initialTiles = shuffledTiles(tileCount, random)

  return {
    imageKey: image.key,
    imageSrc: image.src,
    gridSize: {
      rows: config.rows,
      cols: config.cols,
    },
    rows: config.rows,
    cols: config.cols,
    tileCount,
    previewMs: config.previewMs,
    tiles: initialTiles,
    shuffledTiles: initialTiles,
    solutionTiles,
  }
}

export function swapPuzzleTiles(tiles: PuzzleTile[], firstTileId: string, secondTileId: string): PuzzleTile[] {
  if (firstTileId === secondTileId) {
    return tiles
  }

  const firstIndex = tiles.findIndex((tile) => tile.id === firstTileId)
  const secondIndex = tiles.findIndex((tile) => tile.id === secondTileId)

  if (firstIndex < 0 || secondIndex < 0) {
    return tiles
  }

  const result = [...tiles]
  result[firstIndex] = tiles[secondIndex]
  result[secondIndex] = tiles[firstIndex]

  return result
}

export function evaluatePuzzleCompletion(tiles: ReadonlyArray<Pick<PuzzleTile, 'correctIndex'>>): boolean {
  return tiles.every((tile, index) => tile.correctIndex === index)
}

export function puzzleTileImageStyle(
  grid: Pick<PuzzleRound, 'rows' | 'cols'>,
  tile: Pick<PuzzleTile, 'correctIndex'>
): PuzzleTileImageStyle {
  const row = Math.floor(tile.correctIndex / grid.cols)
  const col = tile.correctIndex % grid.cols

  return {
    position: 'absolute',
    display: 'block',
    width: `${grid.cols * 100}%`,
    height: `${grid.rows * 100}%`,
    left: `-${col * 100}%`,
    top: `-${row * 100}%`,
  }
}
