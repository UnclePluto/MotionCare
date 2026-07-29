import { describe, expect, it, vi } from 'vitest'

import {
  advanceRecordingClock,
  classifyTimedOutSegment,
  finishCurrentSegment,
  initialRecordingState,
  rotateTimedOutSegment,
  shouldStartRecordingAfterSessionCreated,
  shouldWaitForAutomaticFinalSegment,
  waitForPendingPersistence,
  type RecordingState,
} from './recordingMachine'

describe('肩部推举连续录制状态机', () => {
  it('30 秒轮转先启动下一段再持久化上一段', async () => {
    const order: string[] = []
    const persist = vi.fn(async (sequenceIndex: number) => {
      order.push(`persist-${sequenceIndex}`)
    })

    const next = await rotateTimedOutSegment({
      state: { ...initialRecordingState(), phase: 'recording' },
      startNextRecording: () => order.push('start-next'),
      persistCompletedSegment: persist,
    })

    expect(order).toEqual(['start-next', 'persist-0'])
    expect(next.currentSequenceIndex).toBe(1)
    expect(next.phase).toBe('recording')
  })

  it('总计时跨分片连续累加且不受 30 秒限制', () => {
    let state: RecordingState = { ...initialRecordingState(), phase: 'recording' }
    for (let index = 0; index < 75; index += 1) state = advanceRecordingClock(state)
    expect(state.elapsedSeconds).toBe(75)
  })

  it.each(['manual', 'hidden'] as const)('%s 结束只保存当前段且不续录', async (reason) => {
    const startNext = vi.fn()
    const persist = vi.fn().mockResolvedValue(undefined)

    const next = await finishCurrentSegment({
      state: {
        ...initialRecordingState(),
        phase: 'recording',
        currentSequenceIndex: 2,
        elapsedSeconds: 70,
      },
      reason,
      startNextRecording: startNext,
      persistCompletedSegment: persist,
    })

    expect(startNext).not.toHaveBeenCalled()
    expect(persist).toHaveBeenCalledWith(2)
    expect(next.phase).toBe('finishing')
    expect(next.segmentCount).toBe(3)
  })

  it('页面隐藏后收到 timeoutCallback 时把当前段作为最后分片收尾', () => {
    expect(classifyTimedOutSegment({ finalizing: true, pageHidden: true })).toBe('finalize')
    expect(classifyTimedOutSegment({ finalizing: false, pageHidden: false })).toBe('rotate')
  })

  it('创建服务端会话期间页面隐藏时不再启动摄像头', () => {
    expect(shouldStartRecordingAfterSessionCreated(true)).toBe(false)
    expect(shouldStartRecordingAfterSessionCreated(false)).toBe(true)
  })

  it('页面隐藏时 stopRecord 失败仍等待系统返回最后分片', () => {
    expect(shouldWaitForAutomaticFinalSegment('hidden')).toBe(true)
    expect(shouldWaitForAutomaticFinalSegment('manual')).toBe(false)
  })

  it('等待分片持久化时吸收已记录的失败并继续收尾', async () => {
    await expect(waitForPendingPersistence([
      Promise.resolve(),
      Promise.reject(new Error('save failed')),
    ])).resolves.toBeUndefined()
  })
})
