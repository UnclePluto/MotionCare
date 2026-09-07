import Taro from '@tarojs/taro'

import {
  fetchSignedAssetManifest,
  mayRefreshSignedAssets,
  SignedAssetManifestError,
} from '../../assets/signedAssetManifest'
import { gameImageRemoteUrl, type GameImageKey, type LoadedGameImagePathMap } from './gameImageAssets'

export type GameImageLoadProgress = { completed: number; total: number; percent: number }
export type GameImageInfoGetter = (options: { src: string }) => Promise<{ path: string }>
export type GameImagePreloadOptions = {
  getImageInfo: GameImageInfoGetter
  loadSignedManifest?: typeof fetchSignedAssetManifest
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

function progressFor(completed: number, total: number): GameImageLoadProgress {
  return { completed, total, percent: total === 0 ? 100 : Math.round((completed / total) * 100) }
}

export async function preloadGameImages(
  keys: readonly GameImageKey[],
  {
    getImageInfo,
    loadSignedManifest = fetchSignedAssetManifest,
    isCurrent,
    onProgress,
    concurrency = 3,
  }: GameImagePreloadOptions,
): Promise<LoadedGameImagePathMap> {
  const requestedKeys = [...new Set(keys)]
  const total = requestedKeys.length
  const loadedPaths: Partial<Record<GameImageKey, string>> = {}
  const workerCount = Math.max(1, Math.floor(concurrency))

  assertCurrent(isCurrent)
  onProgress(progressFor(0, total))
  if (total === 0) return loadedPaths

  for (let attempt = 0; attempt < 2; attempt += 1) {
    assertCurrent(isCurrent)
    let manifest
    try {
      manifest = attempt === 0
        ? await loadSignedManifest()
        : await loadSignedManifest({ forceRefresh: true })
      assertCurrent(isCurrent)
    } catch (error) {
      if (!isCurrent() || error instanceof GameImagePreloadCancelledError) {
        throw new GameImagePreloadCancelledError()
      }
      if (attempt === 0 && mayRefreshSignedAssets(error)) continue
      throw new SignedAssetManifestError(false)
    }

    const remaining = requestedKeys.filter((key) => loadedPaths[key] === undefined)
    let nextIndex = 0
    let terminal = false
    let terminalError: unknown

    async function worker() {
      while (!terminal) {
        assertCurrent(isCurrent)
        const key = remaining[nextIndex]
        nextIndex += 1
        if (!key) return
        try {
          const { path } = await getImageInfo({ src: gameImageRemoteUrl(key, manifest) })
          assertCurrent(isCurrent)
          if (terminal) return
          loadedPaths[key] = path
          onProgress(progressFor(Object.keys(loadedPaths).length, total))
        } catch (error) {
          if (!terminal) {
            terminal = true
            terminalError = isCurrent() ? error : new GameImagePreloadCancelledError()
          }
        }
      }
    }

    await Promise.allSettled(Array.from(
      { length: Math.min(workerCount, remaining.length) },
      () => worker(),
    ))
    if (!isCurrent() || terminalError instanceof GameImagePreloadCancelledError) {
      throw new GameImagePreloadCancelledError()
    }
    if (terminal) {
      if (attempt === 0) continue
      throw new SignedAssetManifestError(false)
    }
    assertCurrent(isCurrent)
    return loadedPaths
  }

  throw new SignedAssetManifestError(false)
}
