import Taro from '@tarojs/taro'

import {
  gameImageRemoteUrl,
  type GameImageKey,
  type LoadedGameImagePathMap,
} from './gameImageAssets'

export type GameImageLoadProgress = {
  completed: number
  total: number
  percent: number
}

export type GameImageInfoGetter = (options: { src: string }) => Promise<{ path: string }>

export type GameImagePreloadOptions = {
  getImageInfo: GameImageInfoGetter
  isCurrent: () => boolean
  onProgress: (progress: GameImageLoadProgress) => void
  concurrency?: number
}

export class GameImagePreloadCancelledError extends Error {
  constructor() {
    super('游戏图片预取已取消')
    this.name = 'GameImagePreloadCancelledError'
  }
}

export function taroGetImageInfo({ src }: { src: string }): Promise<{ path: string }> {
  return Taro.getImageInfo({ src }).then((result) => ({ path: result.path }))
}

function assertCurrent(isCurrent: () => boolean) {
  if (!isCurrent()) throw new GameImagePreloadCancelledError()
}

function uniqueKeys(keys: readonly GameImageKey[]): GameImageKey[] {
  return [...new Set(keys)]
}

function progressFor(completed: number, total: number): GameImageLoadProgress {
  return {
    completed,
    total,
    percent: total === 0 ? 100 : Math.round((completed / total) * 100),
  }
}

export async function preloadGameImages(
  keys: readonly GameImageKey[],
  { getImageInfo, isCurrent, onProgress, concurrency = 3 }: GameImagePreloadOptions
): Promise<LoadedGameImagePathMap> {
  const requestedKeys = uniqueKeys(keys)
  const total = requestedKeys.length
  const loadedPaths: Partial<Record<GameImageKey, string>> = {}
  const workerCount = Math.max(1, Math.floor(concurrency))
  let completed = 0
  let nextIndex = 0
  let terminal = false
  let terminalError: unknown

  assertCurrent(isCurrent)
  onProgress(progressFor(0, total))

  async function worker() {
    while (!terminal) {
      assertCurrent(isCurrent)
      const key = requestedKeys[nextIndex]
      nextIndex += 1
      if (!key) return

      try {
        const { path } = await getImageInfo({ src: gameImageRemoteUrl(key) })
        assertCurrent(isCurrent)
        if (terminal) return

        loadedPaths[key] = path
        completed += 1
        onProgress(progressFor(completed, total))
      } catch (error) {
        if (!terminal) {
          terminal = true
          terminalError = isCurrent() ? error : new GameImagePreloadCancelledError()
        }
        throw terminalError
      }
    }
  }

  try {
    await Promise.all(Array.from({ length: Math.min(workerCount, total) }, () => worker()))
  } catch (error) {
    terminal = true
    if (!isCurrent()) {
      terminalError = new GameImagePreloadCancelledError()
      throw terminalError
    }
    if (terminalError === undefined) terminalError = error
    throw terminalError
  }

  assertCurrent(isCurrent)
  return loadedPaths
}
