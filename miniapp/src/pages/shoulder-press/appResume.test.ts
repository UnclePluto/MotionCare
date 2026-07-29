import { describe, expect, it } from 'vitest'

import { shouldResumeShoulderPressUpload } from './appResume'
import type { ShoulderPressSession } from './session'

const session: ShoulderPressSession = {
  actionId: 42,
  videoId: 7,
  startedAt: 1,
  durationSeconds: 30,
  phase: 'recording',
  segments: [],
}

describe('肩部推举异常退出恢复', () => {
  it('应用重新启动到首页时直接恢复上传流程', () => {
    expect(shouldResumeShoulderPressUpload(session, 'pages/home/index')).toBe(true)
  })

  it('摄像页和上传页不重复重定向', () => {
    expect(shouldResumeShoulderPressUpload(session, 'pages/shoulder-press/camera')).toBe(false)
    expect(shouldResumeShoulderPressUpload(session, 'pages/shoulder-press/upload')).toBe(false)
  })
})
