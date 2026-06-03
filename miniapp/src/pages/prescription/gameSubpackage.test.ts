import { describe, expect, it, vi } from 'vitest'

import {
  GAME_SESSION_SUBPACKAGE_NAME,
  gameSessionUrl,
  loadGameSessionSubpackage,
  type WechatSubpackageRuntime,
} from './gameSubpackage'

describe('game subpackage loader', () => {
  it('builds the game session URL with action id', () => {
    expect(GAME_SESSION_SUBPACKAGE_NAME).toBe('pages/game-session')
    expect(gameSessionUrl(42)).toBe('/pages/game-session/index?actionId=42')
  })

  it('resolves after loading the game subpackage and reports progress', async () => {
    let successCallback: (() => void) | undefined
    let progressCallback: ((event: { progress: number }) => void) | undefined
    const runtime: WechatSubpackageRuntime = {
      loadSubpackage: vi.fn((options) => {
        successCallback = options.success
        return {
          onProgressUpdate: vi.fn((listener) => {
            progressCallback = listener
          }),
        }
      }),
    }
    const progress: number[] = []

    const loading = loadGameSessionSubpackage((event) => progress.push(event.progress), runtime)
    progressCallback?.({ progress: 38.7 })
    successCallback?.()

    await expect(loading).resolves.toBe('loaded')
    expect(runtime.loadSubpackage).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'pages/game-session' })
    )
    expect(progress).toEqual([39, 100])
  })

  it('falls back when the runtime does not expose loadSubpackage', async () => {
    const progress: number[] = []

    await expect(loadGameSessionSubpackage((event) => progress.push(event.progress), {})).resolves.toBe(
      'unsupported'
    )

    expect(progress).toEqual([100])
  })

  it('rejects with a clear message when subpackage loading fails', async () => {
    let failCallback: ((error: { errMsg?: string }) => void) | undefined
    const runtime: WechatSubpackageRuntime = {
      loadSubpackage: vi.fn((options) => {
        failCallback = options.fail
        return {}
      }),
    }

    const loading = loadGameSessionSubpackage(() => undefined, runtime)
    failCallback?.({ errMsg: 'loadSubpackage: fail network' })

    await expect(loading).rejects.toThrow('loadSubpackage: fail network')
  })
})
