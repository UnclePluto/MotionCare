import { describe, expect, it, vi } from 'vitest'

import { cleanupAndCheckMotionTrainingStorage } from './storageGuard'

const MB = 1024 * 1024

describe('cleanupAndCheckMotionTrainingStorage', () => {
  it('waits for every deletion before relisting and returns ready at exactly 65MB free', async () => {
    let finishFirstRemoval!: () => void
    const listSavedFiles = vi.fn()
      .mockResolvedValueOnce([
        { filePath: 'wxfile://store/a.mp4', size: 20 * MB },
        { filePath: 'wxfile://store/b.mp4', size: 35 * MB }
      ])
      .mockResolvedValueOnce([{ filePath: 'wxfile://store/b.mp4', size: 35 * MB }])
    const run = cleanupAndCheckMotionTrainingStorage({
      hasPendingSession: () => false,
      listSavedFiles,
      removeSavedFile: (path) => path.endsWith('a.mp4')
        ? new Promise<void>((resolve) => { finishFirstRemoval = resolve })
        : Promise.reject(new Error('file is still occupied')),
      isActive: () => true
    })

    await vi.waitFor(() => expect(listSavedFiles).toHaveBeenCalledTimes(1))
    finishFirstRemoval()

    await expect(run).resolves.toEqual({
      kind: 'ready',
      usedBytes: 35 * MB,
      availableBytes: 65 * MB
    })
    expect(listSavedFiles).toHaveBeenCalledTimes(2)
  })

  it('short-circuits a pending session without accessing saved files', async () => {
    const listSavedFiles = vi.fn<() => Promise<[]>>()
    const removeSavedFile = vi.fn<() => Promise<void>>()

    await expect(cleanupAndCheckMotionTrainingStorage({
      hasPendingSession: () => true,
      listSavedFiles,
      removeSavedFile,
      isActive: () => true
    })).resolves.toEqual({ kind: 'pending_session' })

    expect(listSavedFiles).not.toHaveBeenCalled()
    expect(removeSavedFile).not.toHaveBeenCalled()
  })

  it('blocks when the confirmed free space is one byte below 65MB', async () => {
    const usedBytes = 35 * MB + 1

    await expect(cleanupAndCheckMotionTrainingStorage({
      hasPendingSession: () => false,
      listSavedFiles: vi.fn()
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([{ filePath: 'wxfile://store/remaining.mp4', size: usedBytes }]),
      removeSavedFile: () => Promise.resolve(),
      isActive: () => true
    })).resolves.toEqual({
      kind: 'blocked',
      usedBytes,
      availableBytes: 65 * MB - 1
    })
  })

  it('waits for other removals after one fails and calculates from the relisted files', async () => {
    let finishSecondRemoval!: () => void
    const listSavedFiles = vi.fn()
      .mockResolvedValueOnce([
        { filePath: 'wxfile://store/failed.mp4', size: 4 * MB },
        { filePath: 'wxfile://store/slow.mp4', size: 4 * MB }
      ])
      .mockResolvedValueOnce([{ filePath: 'wxfile://store/actual.mp4', size: 40 * MB }])
    const run = cleanupAndCheckMotionTrainingStorage({
      hasPendingSession: () => false,
      listSavedFiles,
      removeSavedFile: (path) => path.endsWith('failed.mp4')
        ? Promise.reject(new Error('removal failed'))
        : new Promise<void>((resolve) => { finishSecondRemoval = resolve }),
      isActive: () => true
    })

    await vi.waitFor(() => expect(listSavedFiles).toHaveBeenCalledTimes(1))
    expect(listSavedFiles).toHaveBeenCalledTimes(1)
    finishSecondRemoval()

    await expect(run).resolves.toEqual({
      kind: 'blocked',
      usedBytes: 40 * MB,
      availableBytes: 60 * MB
    })
    expect(listSavedFiles).toHaveBeenCalledTimes(2)
  })

  it('propagates the first saved-file listing failure unchanged', async () => {
    const failure = new Error('cannot list files')

    await expect(cleanupAndCheckMotionTrainingStorage({
      hasPendingSession: () => false,
      listSavedFiles: () => Promise.reject(failure),
      removeSavedFile: () => Promise.resolve(),
      isActive: () => true
    })).rejects.toBe(failure)
  })

  it('propagates the confirmation listing failure unchanged', async () => {
    const failure = new Error('cannot relist files')

    await expect(cleanupAndCheckMotionTrainingStorage({
      hasPendingSession: () => false,
      listSavedFiles: vi.fn()
        .mockResolvedValueOnce([])
        .mockRejectedValueOnce(failure),
      removeSavedFile: () => Promise.resolve(),
      isActive: () => true
    })).rejects.toBe(failure)
  })

  it('returns cancelled after every removal settles when the page becomes inactive', async () => {
    let finishRemoval!: () => void
    let active = true
    const listSavedFiles = vi.fn().mockResolvedValueOnce([
      { filePath: 'wxfile://store/a.mp4', size: MB }
    ])
    const run = cleanupAndCheckMotionTrainingStorage({
      hasPendingSession: () => false,
      listSavedFiles,
      removeSavedFile: () => new Promise<void>((resolve) => { finishRemoval = resolve }),
      isActive: () => active
    })

    await vi.waitFor(() => expect(listSavedFiles).toHaveBeenCalledTimes(1))
    active = false
    finishRemoval()

    await expect(run).resolves.toEqual({ kind: 'cancelled' })
    expect(listSavedFiles).toHaveBeenCalledTimes(1)
  })

  it('normalizes invalid sizes and clamps confirmed usage to saved-file capacity', async () => {
    await expect(cleanupAndCheckMotionTrainingStorage({
      hasPendingSession: () => false,
      listSavedFiles: vi.fn()
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([
          { filePath: 'wxfile://store/negative.mp4', size: -1 },
          { filePath: 'wxfile://store/nan.mp4', size: Number.NaN },
          { filePath: 'wxfile://store/infinite.mp4', size: Number.POSITIVE_INFINITY },
          { filePath: 'wxfile://store/large.mp4', size: 101 * MB }
        ]),
      removeSavedFile: () => Promise.resolve(),
      isActive: () => true
    })).resolves.toEqual({
      kind: 'blocked',
      usedBytes: 100 * MB,
      availableBytes: 0
    })
  })
})
