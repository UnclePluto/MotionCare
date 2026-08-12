import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('演示会话', () => {
  beforeEach(() => vi.resetModules())

  it('只在当前模块实例中保持开启', async () => {
    const first = await import('./session')
    expect(first.DEMO_BINDING_CODE).toBe('8888')
    expect(first.isDemoSession()).toBe(false)
    first.startDemoSession()
    expect(first.isDemoSession()).toBe(true)

    vi.resetModules()
    const restarted = await import('./session')
    expect(restarted.isDemoSession()).toBe(false)
  })
})
