import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import GameSessionPage from './index'
import type { GameTrainingPayload } from './gameTypes'

type ReactElement = {
  type: string | ((props?: Record<string, unknown>) => ReactElement)
  props: Record<string, unknown> & {
    children?: unknown
    className?: string
    disabled?: boolean
    onClick?: () => unknown
    onKeyDown?: (event: { key: string; preventDefault: () => void }) => unknown
    onError?: () => unknown
  }
}

type HookEntry = unknown

const reactHarness = vi.hoisted(() => {
  let hookEntries: HookEntry[] = []
  let hookCursor = 0
  let queuedEffects: Array<() => unknown> = []
  let effectCleanups: Array<(() => unknown) | undefined> = []
  let mounted = false
  let stateWritesAfterCleanup = 0

  function depsChanged(previous: unknown, next: unknown[] | undefined): boolean {
    if (!Array.isArray(previous) || !next) return true
    return previous.length !== next.length || previous.some((value, index) => value !== next[index])
  }

  return {
    reset() {
      effectCleanups.forEach((cleanup) => cleanup?.())
      hookEntries = []
      hookCursor = 0
      queuedEffects = []
      effectCleanups = []
      mounted = false
      stateWritesAfterCleanup = 0
    },
    beginRender() {
      mounted = true
      hookCursor = 0
      queuedEffects = []
    },
    runEffects() {
      const effects = queuedEffects
      queuedEffects = []
      effects.forEach((effect) => effect())
    },
    cleanup() {
      effectCleanups.forEach((cleanup) => cleanup?.())
      effectCleanups = []
      mounted = false
    },
    stateWritesAfterCleanup() {
      return stateWritesAfterCleanup
    },
    useState(initialValue: unknown) {
      const index = hookCursor
      hookCursor += 1
      if (hookEntries[index] === undefined) {
        hookEntries[index] = typeof initialValue === 'function'
          ? (initialValue as () => unknown)()
          : initialValue
      }
      const setState = (nextValue: unknown) => {
        if (!mounted) {
          stateWritesAfterCleanup += 1
          return
        }
        hookEntries[index] = typeof nextValue === 'function'
          ? (nextValue as (current: unknown) => unknown)(hookEntries[index])
          : nextValue
      }
      return [hookEntries[index], setState]
    },
    useRef(initialValue: unknown) {
      const index = hookCursor
      hookCursor += 1
      if (hookEntries[index] === undefined) hookEntries[index] = { current: initialValue }
      return hookEntries[index]
    },
    useEffect(callback: () => unknown, deps?: unknown[]) {
      const index = hookCursor
      hookCursor += 1
      if (!depsChanged(hookEntries[index], deps)) return
      queuedEffects.push(() => {
        effectCleanups[index]?.()
        const cleanup = callback()
        effectCleanups[index] = typeof cleanup === 'function' ? cleanup : undefined
      })
      hookEntries[index] = deps ?? []
    },
  }
})

const taroHarness = vi.hoisted(() => {
  const showCallbacks: Array<() => unknown> = []
  const hideCallbacks: Array<() => unknown> = []
  const routerParams: Record<string, string> = { actionId: '101' }
  const taroMock = {
    getStorageSync: vi.fn(),
    setStorageSync: vi.fn(),
    removeStorageSync: vi.fn(),
    getImageInfo: vi.fn<(options: { src: string }) => Promise<{ path: string }>>(),
    redirectTo: vi.fn(),
    navigateBack: vi.fn(),
  }

  return {
    showCallbacks,
    hideCallbacks,
    routerParams,
    taroMock,
    reset() {
      showCallbacks.length = 0
      hideCallbacks.length = 0
      routerParams.actionId = '101'
      Object.values(taroMock).forEach((mock) => mock.mockClear())
    },
  }
})

const clockHarness = vi.hoisted(() => ({ offset: 0 }))
vi.mock('./capturePlatform', async (importOriginal) => ({
  ...await importOriginal<typeof import('./capturePlatform')>(),
  createCaptureNow: () => () => Date.now() + clockHarness.offset,
}))

const prescriptionHarness = vi.hoisted(() => ({ current: null as unknown, demo: true }))
const retryUploadHarness = vi.hoisted(() => ({
  postGameTrainingRecord: vi.fn(),
  clearPendingGameUpload: vi.fn(),
  savePendingGameUploadAfterActiveRetry: vi.fn(),
  savePendingGameUpload: vi.fn(),
  startPendingGameUploadRetryLoop: vi.fn(),
}))
const audioHarness = vi.hoisted(() => ({
  playAudioSrc: vi.fn<(...args: unknown[]) => Promise<boolean>>(),
  playGameAudio: vi.fn(async () => undefined),
  stopActiveGameAudio: vi.fn(),
}))
const signedAssetHarness = vi.hoisted(() => ({
  fetchSignedAssetManifest: vi.fn(async () => ({
    assetVersion: 'test', issuedAt: 0, expiresAt: 600,
    urls: new Proxy({}, { get: (_, key) => `https://cdn.example.com/signed/${String(key)}.webp?e=600&token=test` }),
  })),
}))

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    useEffect: reactHarness.useEffect,
    useMemo: (factory: () => unknown) => factory(),
    useRef: reactHarness.useRef,
    useState: reactHarness.useState,
  }
})

vi.mock('@tarojs/components', () => ({
  Button: 'Button',
  Image: 'Image',
  Input: 'Input',
  Picker: 'Picker',
  Text: 'Text',
  View: 'View',
}))

vi.mock('@tarojs/taro', () => ({
  default: taroHarness.taroMock,
  useRouter: () => ({ params: taroHarness.routerParams }),
  useDidShow: (callback: () => unknown) => taroHarness.showCallbacks.push(callback),
  useDidHide: (callback: () => unknown) => taroHarness.hideCallbacks.push(callback),
}))

vi.mock('../../demo/patientAppData', () => ({
  fetchCurrentPrescriptionData: vi.fn(async () => prescriptionHarness.current),
}))

vi.mock('../../demo/session', () => ({
  isDemoSession: () => prescriptionHarness.demo,
}))

vi.mock('./retryUpload', () => ({
  postGameTrainingRecord: retryUploadHarness.postGameTrainingRecord,
  clearPendingGameUpload: retryUploadHarness.clearPendingGameUpload,
  savePendingGameUploadAfterActiveRetry: retryUploadHarness.savePendingGameUploadAfterActiveRetry,
  savePendingGameUpload: retryUploadHarness.savePendingGameUpload,
  startPendingGameUploadRetryLoop: retryUploadHarness.startPendingGameUploadRetryLoop,
}))

vi.mock('./gameAudio', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./gameAudio')>()
  return {
    ...actual,
    isGameAudioMuted: () => false,
    playAudioSrc: audioHarness.playAudioSrc,
    playGameAudio: audioHarness.playGameAudio,
    playGameFeedback: (kind: 'correct' | 'wrong') => ({
      key: `${kind}-test`,
      text: kind === 'correct' ? '很好' : '没关系',
      src: `/${kind}.m4a`,
    }),
    setGameAudioMuted: vi.fn(),
    stopActiveGameAudio: audioHarness.stopActiveGameAudio,
  }
})

vi.mock('../../assets/signedAssetManifest', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../assets/signedAssetManifest')>(),
  fetchSignedAssetManifest: signedAssetHarness.fetchSignedAssetManifest,
}))

function prescriptionFor(sourceKey: string, actionName: string) {
  return {
    id: 1,
    version: 1,
    status: 'active',
    effective_at: '2026-08-31T00:00:00+08:00',
    week_start: '2026-08-31',
    week_end: '2026-09-06',
    actions: [{
      id: 101,
      action_library_item: 101,
      source_key: sourceKey,
      action_name: actionName,
      training_type: '游戏训练',
      internal_type: 'game',
      action_type: '益智游戏',
      action_instruction: '请按提示完成训练',
      video_url: '',
      has_ai_supervision: false,
      weekly_frequency: '1',
      duration_minutes: 1,
      weekly_target_count: 1,
      weekly_completed_count: 0,
      difficulty: '简单',
      notes: '',
      sort_order: 1,
      recent_record: null,
    }],
  }
}

function childrenOf(node: unknown): unknown[] {
  if (Array.isArray(node)) return node
  if (!node || typeof node !== 'object') return []
  const children = (node as ReactElement).props?.children
  if (children === undefined || children === null) return []
  return Array.isArray(children) ? children : [children]
}

function textContent(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  return childrenOf(node).map(textContent).join('')
}

function findAll(node: unknown, predicate: (element: ReactElement) => boolean): ReactElement[] {
  if (!node || typeof node !== 'object') return []
  const element = node as ReactElement
  const current = predicate(element) ? [element] : []
  return current.concat(childrenOf(element).flatMap((child) => findAll(child, predicate)))
}

function hasClass(element: ReactElement, className: string): boolean {
  return String(element.props.className ?? '').split(/\s+/).includes(className)
}

function findByClass(node: unknown, className: string): ReactElement {
  const element = findAll(node, (item) => hasClass(item, className))[0]
  if (!element) throw new Error(`Class not found: ${className}; rendered: ${textContent(node)}`)
  return element
}

function findButtonByText(node: unknown, text: string): ReactElement {
  const element = findAll(node, (item) => item.type === 'Button' && textContent(item).includes(text))[0]
  if (!element) throw new Error(`Button not found: ${text}; rendered: ${textContent(node)}`)
  return element
}

function click(element: ReactElement): void {
  if (typeof element.props.onClick === 'function') element.props.onClick()
}

function renderPage() {
  const render = (runEffects = true) => {
    reactHarness.beginRender()
    let element = GameSessionPage() as ReactElement
    while (element && typeof element.type === 'function') element = element.type(element.props)
    if (runEffects) reactHarness.runEffects()
    return element
  }
  let element = render()
  return {
    get element() {
      return element
    },
    rerender() {
      element = render()
      return element
    },
    rerenderWithoutEffects() {
      element = render(false)
      return element
    },
    unmount() {
      reactHarness.cleanup()
    },
  }
}

type RenderedPage = ReturnType<typeof renderPage>

async function flushPromises(times = 8): Promise<void> {
  for (let index = 0; index < times; index += 1) await Promise.resolve()
}

async function renderGame(sourceKey: string, actionName: string, difficulty = '简单'): Promise<RenderedPage> {
  const prescription = prescriptionFor(sourceKey, actionName)
  prescription.actions[0].difficulty = difficulty
  prescriptionHarness.current = prescription
  const page = renderPage()
  taroHarness.showCallbacks.at(-1)?.()
  await flushPromises()
  page.rerender()
  await flushPromises()
  page.rerender()
  return page
}

function chooseDifficulty(page: RenderedPage, level: string) {
  const option = findAll(page.element, (item) =>
    item.type === 'Button' && item.props['aria-label'] === level
  )[0]
  expect(option).toBeTruthy()
  click(option)
  page.rerender()
}

async function enterPlaying(page: RenderedPage): Promise<void> {
  click(findButtonByText(page.element, '开始游戏'))
  page.rerender()
  for (const durationMs of [1200, 700, 700, 700, 700]) {
    await vi.advanceTimersByTimeAsync(durationMs)
    await flushPromises()
  }
  page.rerender()
  expect(findButtonByText(page.element, '提前结束')).toBeTruthy()
}

async function hidePage(page: RenderedPage): Promise<void> {
  taroHarness.hideCallbacks.at(-1)?.()
  await flushPromises()
  page.rerender()
}

async function showPage(page: RenderedPage): Promise<void> {
  taroHarness.showCallbacks.at(-1)?.()
  await flushPromises()
  page.rerender()
}

function numberTiles(node: unknown): ReactElement[] {
  return findAll(node, (item) => item.type === 'Button' && hasClass(item, 'number-tile'))
}

function soundCards(node: unknown): ReactElement[] {
  return findAll(node, (item) => item.type === 'Button' && hasClass(item, 'sound-card'))
}

function puzzleTiles(node: unknown): ReactElement[] {
  return findAll(node, (item) => item.type === 'Button' && hasClass(item, 'puzzle-tile'))
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve
    reject = nextReject
  })
  return { promise, reject, resolve }
}

beforeEach(() => {
  clockHarness.offset = 0
  prescriptionHarness.demo = true
  vi.stubEnv('TARO_APP_ASSET_BASE_URL', 'https://cdn.example.com/assets')
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-08-31T08:00:00+08:00'))
  vi.spyOn(Math, 'random').mockReturnValue(0)
  reactHarness.reset()
  taroHarness.reset()
  taroHarness.taroMock.getImageInfo.mockReset()
  taroHarness.taroMock.getImageInfo.mockImplementation(async ({ src }) => ({
    path: `wxfile://game-images/${src.split('/').at(-1)}`,
  }))
  Object.values(retryUploadHarness).forEach((mock) => mock.mockReset())
  audioHarness.playAudioSrc.mockReset()
  audioHarness.playAudioSrc.mockResolvedValue(true)
  audioHarness.playGameAudio.mockClear()
  audioHarness.stopActiveGameAudio.mockClear()
  signedAssetHarness.fetchSignedAssetManifest.mockClear()
})

afterEach(async () => {
  reactHarness.reset()
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
  vi.clearAllTimers()
  vi.useRealTimers()
})

describe('GameSessionPage 训练图片准备门禁', () => {
  it('图片未全部准备完成时禁用开始游戏，且不启动计时或创建训练记录', async () => {
    const pendingImage = deferred<{ path: string }>()
    taroHarness.taroMock.getImageInfo.mockReturnValue(pendingImage.promise)
    const page = await renderGame('game-memory-pattern-sequence', '图案顺序记忆')
    chooseDifficulty(page, '困难')

    expect(textContent(page.element)).toContain('正在准备训练图片')
    const startButton = findButtonByText(page.element, '开始游戏')
    expect(startButton.props.disabled).toBe(true)
    click(startButton)
    await vi.advanceTimersByTimeAsync(5000)
    page.rerender()

    expect(textContent(page.element)).not.toContain('提前结束')
    expect(findAll(page.element, (item) => hasClass(item, 'game-timer-value'))).toHaveLength(0)
    expect(retryUploadHarness.postGameTrainingRecord).not.toHaveBeenCalled()
    page.unmount()
    pendingImage.resolve({ path: 'wxfile://game-images/late.webp' })
    await flushPromises()
  })

  it.each([
    ['game-memory-color-sequence', '颜色顺序记忆'],
    ['game-executive-inhibition', '反应抑制'],
  ])('%s 不依赖训练图片，可立即进入现有流程', async (sourceKey, actionName) => {
    const page = await renderGame(sourceKey, actionName)

    expect(findButtonByText(page.element, '开始游戏').props.disabled).toBe(false)
    expect(taroHarness.taroMock.getImageInfo).not.toHaveBeenCalled()
    page.unmount()
  })

  it.each([
    ['game-memory-pattern-sequence', '图案顺序记忆', '5/5', '100%'],
    ['game-audiovisual-puzzle', '图片拼图', '3/3', '100%'],
  ])('%s 全部图片成功后显示完成进度并允许开始', async (sourceKey, actionName, fraction, percent) => {
    const page = await renderGame(sourceKey, actionName)

    expect(textContent(page.element)).toContain('训练图片已准备完成')
    expect(textContent(page.element)).toContain(fraction)
    expect(textContent(page.element)).toContain(percent)
    expect(findButtonByText(page.element, '开始游戏').props.disabled).toBe(false)
    page.unmount()
  })

  it('图片就绪后等待 600 秒不重新预取也不提前出题', async () => {
    const page = await renderGame('game-memory-pattern-sequence', '图案顺序记忆')
    const downloads = taroHarness.taroMock.getImageInfo.mock.calls.length
    const manifests = signedAssetHarness.fetchSignedAssetManifest.mock.calls.length

    await vi.advanceTimersByTimeAsync(600_000)
    await flushPromises()
    page.rerender()

    expect(taroHarness.taroMock.getImageInfo).toHaveBeenCalledTimes(downloads)
    expect(signedAssetHarness.fetchSignedAssetManifest).toHaveBeenCalledTimes(manifests)
    expect(findButtonByText(page.element, '开始游戏').props.disabled).toBe(false)
    expect(findAll(page.element, (item) => hasClass(item, 'sequence-memory-image'))).toHaveLength(0)
    page.unmount()
  })

  it('隐藏期间签名返回不应启动图片下载', async () => {
    const manifest = await signedAssetHarness.fetchSignedAssetManifest()
    signedAssetHarness.fetchSignedAssetManifest.mockClear()
    const pendingManifest = deferred<typeof manifest>()
    signedAssetHarness.fetchSignedAssetManifest.mockReturnValueOnce(pendingManifest.promise)
    const page = await renderGame('game-memory-pattern-sequence', '图案顺序记忆')
    expect(taroHarness.taroMock.getImageInfo).not.toHaveBeenCalled()

    await hidePage(page)
    pendingManifest.resolve(manifest)
    await flushPromises(20)
    page.rerender()

    expect(taroHarness.taroMock.getImageInfo).not.toHaveBeenCalled()
    expect(textContent(page.element)).toContain('0/5')
    expect(findButtonByText(page.element, '开始游戏').props.disabled).toBe(true)
    page.unmount()
  })

  it('下载中隐藏后丢弃迟到结果且不继续下载或更新进度', async () => {
    const pendingImages = Array.from({ length: 3 }, () => deferred<{ path: string }>())
    pendingImages.forEach((image) => taroHarness.taroMock.getImageInfo.mockReturnValueOnce(image.promise))
    const page = await renderGame('game-memory-pattern-sequence', '图案顺序记忆')
    expect(taroHarness.taroMock.getImageInfo).toHaveBeenCalledTimes(3)

    await hidePage(page)
    pendingImages.forEach((image) => image.resolve({ path: 'wxfile://stale.webp' }))
    await flushPromises(20)
    page.rerender()

    expect(taroHarness.taroMock.getImageInfo).toHaveBeenCalledTimes(3)
    expect(textContent(page.element)).toContain('0/5')
    expect(findButtonByText(page.element, '开始游戏').props.disabled).toBe(true)
    expect(signedAssetHarness.fetchSignedAssetManifest).toHaveBeenCalledTimes(1)
    page.unmount()
  })

  it('重新显示后开启新代准备且旧下载不能覆盖新图片', async () => {
    const staleImages = Array.from({ length: 3 }, () => deferred<{ path: string }>())
    staleImages.forEach((image) => taroHarness.taroMock.getImageInfo.mockReturnValueOnce(image.promise))
    const page = await renderGame('game-memory-pattern-sequence', '图案顺序记忆')
    await hidePage(page)
    await showPage(page)
    await flushPromises(20)
    page.rerender()

    expect(textContent(page.element)).toContain('训练图片已准备完成')
    expect(textContent(page.element)).toContain('5/5')
    expect(findButtonByText(page.element, '开始游戏').props.disabled).toBe(false)
    expect(signedAssetHarness.fetchSignedAssetManifest).toHaveBeenCalledTimes(2)
    const downloads = taroHarness.taroMock.getImageInfo.mock.calls.length
    staleImages.forEach((image) => image.resolve({ path: 'wxfile://stale.webp' }))
    await flushPromises(20)
    page.rerender()
    expect(taroHarness.taroMock.getImageInfo).toHaveBeenCalledTimes(downloads)
    await enterPlaying(page)
    const images = findAll(page.element, (item) => hasClass(item, 'sequence-memory-image'))
    expect(images.length).toBeGreaterThan(0)
    expect(images.every((item) => String(item.props.src).startsWith('wxfile://game-images/'))).toBe(true)
    page.unmount()
  })

  it('就绪后隐藏再显示保留图片与本轮训练且不重新预取', async () => {
    const page = await renderGame('game-memory-pattern-sequence', '图案顺序记忆')
    const downloads = taroHarness.taroMock.getImageInfo.mock.calls.length
    const manifests = signedAssetHarness.fetchSignedAssetManifest.mock.calls.length
    await hidePage(page)
    await showPage(page)
    expect(findButtonByText(page.element, '开始游戏').props.disabled).toBe(false)
    expect(findAll(page.element, (item) => hasClass(item, 'sequence-memory-image'))).toHaveLength(0)
    await enterPlaying(page)
    const roundImages = findAll(page.element, (item) => hasClass(item, 'sequence-memory-image'))
      .map((item) => item.props.src)
    const randomCalls = vi.mocked(Math.random).mock.calls.length
    await hidePage(page)
    await vi.advanceTimersByTimeAsync(10_000)
    await showPage(page)

    expect(findButtonByText(page.element, '提前结束')).toBeTruthy()
    expect(findAll(page.element, (item) => hasClass(item, 'sequence-memory-image'))
      .map((item) => item.props.src)).toEqual(roundImages)
    expect(Math.random).toHaveBeenCalledTimes(randomCalls)
    expect(taroHarness.taroMock.getImageInfo).toHaveBeenCalledTimes(downloads)
    expect(signedAssetHarness.fetchSignedAssetManifest).toHaveBeenCalledTimes(manifests)
    page.unmount()
  })

  it('两次图片下载失败后显示重试和返回，手动重试使用新 generation', async () => {
    taroHarness.taroMock.getImageInfo.mockRejectedValue(new Error('CDN unavailable'))
    const page = await renderGame('game-memory-pattern-sequence', '图案顺序记忆')

    await flushPromises()
    page.rerender()
    expect(textContent(page.element)).toContain('训练图片加载失败')
    expect(findButtonByText(page.element, '重新加载')).toBeTruthy()
    expect(findButtonByText(page.element, '返回当前运动计划')).toBeTruthy()
    expect(findAll(page.element, (item) => item.type === 'Button')).toHaveLength(2)

    taroHarness.taroMock.getImageInfo.mockImplementation(async ({ src }) => ({
      path: `wxfile://game-images/${src.split('/').at(-1)}`,
    }))
    click(findButtonByText(page.element, '重新加载'))
    await flushPromises(20)
    page.rerender()
    expect(textContent(page.element)).toContain('训练图片已准备完成')
    expect(textContent(page.element)).toContain('5/5')

    page.unmount()
  })

  it('动作变化后旧图片回调不能覆盖新动作的准备结果', async () => {
    const firstPrescription = prescriptionFor('game-memory-pattern-sequence', '图案顺序记忆')
    const secondAction = {
      ...firstPrescription.actions[0],
      id: 102,
      action_library_item: 102,
      source_key: 'game-executive-category-switch',
      action_name: '分类切换',
    }
    prescriptionHarness.current = {
      ...firstPrescription,
      actions: [...firstPrescription.actions, secondAction],
    }
    const staleImages = Array.from({ length: 3 }, () => deferred<{ path: string }>())
    staleImages.forEach((image) => {
      taroHarness.taroMock.getImageInfo.mockImplementationOnce(() => image.promise)
    })
    const page = renderPage()
    taroHarness.showCallbacks.at(-1)?.()
    await flushPromises()
    page.rerender()
    page.rerender()
    await flushPromises(20)
    expect(taroHarness.taroMock.getImageInfo).toHaveBeenCalledTimes(3)

    taroHarness.routerParams.actionId = '102'
    page.rerender()
    await flushPromises(20)
    page.rerender()
    expect(textContent(page.element)).toContain('分类切换')
    expect(textContent(page.element)).toContain('训练图片已准备完成')

    staleImages.forEach((image, index) => {
      image.resolve({ path: `wxfile://game-images/stale-${index}.webp` })
    })
    await flushPromises(20)
    page.rerender()
    expect(textContent(page.element)).toContain('分类切换')
    expect(textContent(page.element)).toContain('训练图片已准备完成')
    page.unmount()
  })

  it('切换到同一游戏的另一动作时立即关闭旧 ready 门禁', async () => {
    const firstPrescription = prescriptionFor('game-memory-pattern-sequence', '图案顺序记忆 A')
    prescriptionHarness.current = {
      ...firstPrescription,
      actions: [
        ...firstPrescription.actions,
        {
          ...firstPrescription.actions[0],
          id: 102,
          action_library_item: 102,
          action_name: '图案顺序记忆 B',
        },
      ],
    }
    const page = renderPage()
    taroHarness.showCallbacks.at(-1)?.()
    await flushPromises(20)
    page.rerender()
    await flushPromises(20)
    page.rerender()
    expect(findButtonByText(page.element, '开始游戏').props.disabled).toBe(false)

    taroHarness.routerParams.actionId = '102'
    page.rerender()
    const startButton = findButtonByText(page.element, '开始游戏')
    expect(startButton.props.disabled).toBe(true)
    expect(textContent(page.element)).toContain('正在准备训练图片')
    expect(textContent(page.element)).toContain('已完成 0/5')
    expect(textContent(page.element)).not.toContain('训练图片已准备完成')
    expect(textContent(page.element)).not.toContain('100%')
    click(startButton)
    await vi.advanceTimersByTimeAsync(5000)
    page.rerender()
    expect(textContent(page.element)).not.toContain('提前结束')
    page.unmount()
  })

  it('重试开始后忽略旧题树第二个迟到的图片错误', async () => {
    const page = await renderGame('game-memory-pattern-sequence', '图案顺序记忆')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(3700)
    page.rerender()
    const oldImages = findAll(page.element, (item) => hasClass(item, 'game-card-image'))
    expect(oldImages.length).toBeGreaterThanOrEqual(2)
    const firstOldOnError = oldImages[0].props.onError
    const secondOldOnError = oldImages[1].props.onError
    expect(typeof firstOldOnError).toBe('function')
    expect(typeof secondOldOnError).toBe('function')

    firstOldOnError?.()
    page.rerender()
    expect(textContent(page.element)).toContain('训练图片加载失败')

    const retryImage = deferred<{ path: string }>()
    taroHarness.taroMock.getImageInfo.mockImplementation(() => retryImage.promise)
    click(findButtonByText(page.element, '重新加载'))
    page.rerender()
    expect(textContent(page.element)).toContain('正在准备训练图片')

    secondOldOnError?.()
    page.rerender()
    expect(textContent(page.element)).toContain('正在准备训练图片')
    expect(textContent(page.element)).not.toContain('训练图片加载失败')

    retryImage.resolve({ path: 'wxfile://game-images/retry.webp' })
    await flushPromises(30)
    page.rerender()
    expect(textContent(page.element)).toContain('训练图片已准备完成')
    expect(textContent(page.element)).toContain('5/5')
    page.unmount()
  })

  it('新动作准备完成后忽略旧动作题树迟到的图片错误', async () => {
    const firstPrescription = prescriptionFor('game-memory-pattern-sequence', '图案顺序记忆')
    prescriptionHarness.current = {
      ...firstPrescription,
      actions: [
        ...firstPrescription.actions,
        {
          ...firstPrescription.actions[0],
          id: 102,
          action_library_item: 102,
          source_key: 'game-executive-category-switch',
          action_name: '分类切换',
        },
      ],
    }
    const page = renderPage()
    taroHarness.showCallbacks.at(-1)?.()
    await flushPromises(20)
    page.rerender()
    await flushPromises(20)
    page.rerender()
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(3700)
    page.rerender()
    const oldImages = findAll(page.element, (item) => hasClass(item, 'game-card-image'))
    expect(oldImages.length).toBeGreaterThanOrEqual(2)
    const firstOldOnError = oldImages[0].props.onError
    const secondOldOnError = oldImages[1].props.onError

    firstOldOnError?.()
    page.rerender()
    expect(textContent(page.element)).toContain('训练图片加载失败')

    taroHarness.routerParams.actionId = '102'
    page.rerender()
    await flushPromises(20)
    page.rerender()
    expect(textContent(page.element)).toContain('分类切换')
    expect(textContent(page.element)).toContain('训练图片已准备完成')

    secondOldOnError?.()
    page.rerender()
    expect(textContent(page.element)).toContain('分类切换')
    expect(textContent(page.element)).toContain('训练图片已准备完成')
    expect(textContent(page.element)).not.toContain('训练图片加载失败')
    page.unmount()
  })

  it('新 action 已渲染但 effect 未执行时立即忽略旧图片错误', async () => {
    const firstPrescription = prescriptionFor('game-memory-pattern-sequence', '图案顺序记忆 A')
    prescriptionHarness.current = {
      ...firstPrescription,
      actions: [
        ...firstPrescription.actions,
        {
          ...firstPrescription.actions[0],
          id: 102,
          action_library_item: 102,
          action_name: '图案顺序记忆 B',
        },
      ],
    }
    const page = renderPage()
    taroHarness.showCallbacks.at(-1)?.()
    await flushPromises(20)
    page.rerender()
    await flushPromises(20)
    page.rerender()
    await enterPlaying(page)
    const staleOnError = findByClass(page.element, 'sequence-memory-image').props.onError
    expect(typeof staleOnError).toBe('function')

    click(findButtonByText(page.element, '提前结束'))
    page.rerender()
    expect(textContent(page.element)).toContain('训练结果')

    taroHarness.routerParams.actionId = '102'
    page.rerenderWithoutEffects()
    staleOnError?.()
    page.rerenderWithoutEffects()

    expect(textContent(page.element)).toContain('训练结果')
    expect(textContent(page.element)).not.toContain('训练图片加载失败')
    page.unmount()
  })

  it('页面卸载后图片迟到回调不再写入页面状态', async () => {
    const pendingImage = deferred<{ path: string }>()
    taroHarness.taroMock.getImageInfo.mockReturnValue(pendingImage.promise)
    const page = await renderGame('game-memory-pattern-sequence', '图案顺序记忆')

    page.unmount()
    pendingImage.resolve({ path: 'wxfile://game-images/late.webp' })
    await flushPromises(20)
    expect(reactHarness.stateWritesAfterCleanup()).toBe(0)
  })

  it.each([
    ['game-memory-pattern-sequence', '图案顺序记忆', 'sequence-memory-image'],
    ['game-executive-category-switch', '分类切换', 'category-image'],
    ['game-audiovisual-sound-discrimination', '声音辨别', 'sound-card-image'],
    ['game-audiovisual-puzzle', '图片拼图', 'puzzle-preview-image'],
  ])('%s 渲染图片失败后立即停止本题并进入可重试素材错误态', async (sourceKey, actionName, imageClass) => {
    const soundPreviewAudio = sourceKey === 'game-audiovisual-sound-discrimination'
      ? deferred<boolean>()
      : null
    if (soundPreviewAudio) audioHarness.playAudioSrc.mockReturnValueOnce(soundPreviewAudio.promise)
    const page = await renderGame(sourceKey, actionName)
    await enterPlaying(page)
    page.rerender()

    const image = findByClass(page.element, imageClass)
    expect(typeof image.props.onError).toBe('function')
    image.props.onError?.()
    page.rerender()
    expect(textContent(page.element)).toContain('训练图片加载失败')
    expect(findButtonByText(page.element, '重新加载')).toBeTruthy()
    expect(textContent(page.element)).not.toContain('提前结束')

    await vi.advanceTimersByTimeAsync(60_000)
    page.rerender()
    expect(textContent(page.element)).not.toContain('本次训练已完成')
    expect(retryUploadHarness.postGameTrainingRecord).not.toHaveBeenCalled()
    soundPreviewAudio?.resolve(true)
    page.unmount()
  })
})

describe('GameSessionPage 开始前自由选择难度', () => {
  const difficultyGames = [
    ['game-memory-color-sequence', '颜色顺序记忆'],
    ['game-memory-pattern-sequence', '图案顺序记忆'],
    ['game-executive-inhibition', '反应抑制'],
    ['game-executive-category-switch', '分类转换'],
    ['game-audiovisual-sound-discrimination', '声音辨别'],
    ['game-audiovisual-puzzle', '拼图'],
  ] as const
  const preparationCases = difficultyGames.flatMap(([code, name]) =>
    ['简单', '中等', '困难'].map((level) => [code, name, level] as const)
  )

  it('H5 三档支持 Tab，并用 Enter 或 Space 选择且阻止 Space 滚屏', async () => {
    vi.stubEnv('TARO_ENV', 'h5')
    const page = await renderGame('game-executive-inhibition', '反应抑制', '简单')
    let options = findAll(page.element, (item) => hasClass(item, 'difficulty-level-option'))
    expect(options.map((item) => item.props.tabIndex)).toEqual([0, 0, 0])
    expect(options.map((item) => item.props.role)).toEqual(['button', 'button', 'button'])

    const enterPreventDefault = vi.fn()
    options[1].props.onKeyDown?.({ key: 'Enter', preventDefault: enterPreventDefault })
    page.rerender()
    options = findAll(page.element, (item) => hasClass(item, 'difficulty-level-option'))
    expect(options.find((item) => item.props['aria-pressed'])?.props['aria-label']).toBe('中等')
    expect(enterPreventDefault).not.toHaveBeenCalled()

    const spacePreventDefault = vi.fn()
    options[2].props.onKeyDown?.({ key: ' ', preventDefault: spacePreventDefault })
    page.rerender()
    options = findAll(page.element, (item) => hasClass(item, 'difficulty-level-option'))
    expect(options.find((item) => item.props['aria-pressed'])?.props['aria-label']).toBe('困难')
    expect(spacePreventDefault).toHaveBeenCalledOnce()
    page.unmount()
    vi.unstubAllEnvs()
  })

  it.each(preparationCases)('%s默认%s相关准备状态：%s', async (code, name, level) => {
    const page = await renderGame(code, name, level)
    const options = findAll(page.element, (item) => hasClass(item, 'difficulty-level-option'))
    expect(options.map((item) => item.props['aria-label'])).toEqual(['简单', '中等', '困难'])
    expect(options.filter((item) => item.props['aria-pressed']).map((item) => item.props['aria-label'])).toEqual([level])
    expect(textContent(page.element)).toContain('仅用于本次训练')
    expect(textContent(page.element)).not.toContain('降低难度')
    page.unmount()
  })

  it.each([
    ['简单', '困难', 9],
    ['困难', '简单', 4],
    ['中等', '中等', 6],
  ])('处方%s可直接开始%s，记录空原因', async (prescribed, actual, count) => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-executive-inhibition', '反应抑制', prescribed)
    const options = findAll(page.element, (item) => hasClass(item, 'difficulty-level-option'))
    expect(options.map((item) => item.props['aria-label'])).toEqual(['简单', '中等', '困难'])
    chooseDifficulty(page, actual)
    expect(findAll(page.element, (item) => hasClass(item, 'difficulty-reason-option'))).toHaveLength(0)
    expect(findAll(page.element, (item) => item.type === 'Input')).toHaveLength(0)
    await enterPlaying(page)
    expect(numberTiles(page.element)).toHaveLength(count)
    expect(findAll(page.element, (item) => hasClass(item, 'difficulty-level-option'))).toHaveLength(0)
    click(findButtonByText(page.element, '提前结束'))
    await flushPromises()
    page.rerender()
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledWith(expect.objectContaining({
      form_data: expect.objectContaining({
        difficulty: actual,
        raw_detail: expect.objectContaining({
          prescribed_difficulty: prescribed,
          difficulty_adjusted: actual !== prescribed,
          difficulty_adjust_reason: '',
        }),
      }),
    }))
    page.unmount()
  })

  it('连续切换与重复点击使用最后档位，切回处方后不记调整', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-executive-inhibition', '反应抑制', '中等')
    for (const level of ['困难', '简单', '中等', '中等']) chooseDifficulty(page, level)
    await enterPlaying(page)
    expect(numberTiles(page.element)).toHaveLength(6)
    click(findButtonByText(page.element, '提前结束'))
    await flushPromises()
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledWith(expect.objectContaining({
      form_data: expect.objectContaining({
        difficulty: '中等',
        raw_detail: expect.objectContaining({ difficulty_adjusted: false, difficulty_adjust_reason: '' }),
      }),
    }))
    page.unmount()
  })

  it('退出重进恢复处方默认档位', async () => {
    const first = await renderGame('game-executive-inhibition', '反应抑制', '中等')
    chooseDifficulty(first, '困难')
    first.unmount()
    reactHarness.reset()
    taroHarness.reset()
    const second = await renderGame('game-executive-inhibition', '反应抑制', '中等')
    expect(findAll(second.element, (item) => hasClass(item, 'difficulty-level-option') && item.props['aria-pressed'])
      .map((item) => item.props['aria-label'])).toEqual(['中等'])
    second.unmount()
  })

  it('分类转换选择中等后保留题目文案与四个选项', async () => {
    const page = await renderGame('game-executive-category-switch', '分类转换', '困难')
    chooseDifficulty(page, '中等')
    await enterPlaying(page)
    expect(findAll(page.element, (item) => hasClass(item, 'category-option'))).toHaveLength(4)
    expect(textContent(page.element)).toContain('请判断彩图中的物体属于哪个类别，并选出正确的选项')
    page.unmount()
  })
})

describe('GameSessionPage 生命周期与反馈接线', () => {
  it.each([
    ['game-memory-pattern-sequence', '图案顺序记忆', 'sequence-memory-image', '/pattern_sun.'],
    ['game-executive-category-switch', '分类切换', 'category-image', '/category_pineapple.'],
    ['game-audiovisual-sound-discrimination', '声音辨别', 'sound-card-image', '/sound_'],
    ['game-audiovisual-puzzle', '图片拼图', 'puzzle-preview-image', '/puzzle_beach.'],
  ])('%s 页面只渲染 wxfile 临时图片路径', async (sourceKey, actionName, imageClass, assetMarker) => {
    const soundPreviewAudio = sourceKey === 'game-audiovisual-sound-discrimination'
      ? deferred<boolean>()
      : null
    if (soundPreviewAudio) audioHarness.playAudioSrc.mockReturnValueOnce(soundPreviewAudio.promise)
    const page = await renderGame(sourceKey, actionName)
    await enterPlaying(page)
    page.rerender()

    const imageSrc = String(findByClass(page.element, imageClass).props.src)
    expect(imageSrc).toMatch(/^wxfile:\/\/game-images\//)
    expect(imageSrc).toContain(assetMarker)
    expect(imageSrc).not.toMatch(/^https?:\/\//)
    soundPreviewAudio?.resolve(true)
    page.unmount()
  })

  it('后台挂起 item 与整场计时，并从各自剩余毫秒恢复', async () => {
    const page = await renderGame('game-memory-color-sequence', '颜色顺序记忆')
    await enterPlaying(page)

    expect(textContent(findByClass(page.element, 'sequence-memory-progress'))).toContain('第 1 / 3 项')
    expect(textContent(findByClass(page.element, 'game-timer-value'))).toBe('00:01:00')
    await vi.advanceTimersByTimeAsync(400)
    await hidePage(page)
    await vi.advanceTimersByTimeAsync(5000)

    expect(textContent(page.element)).toContain('训练已暂停')
    expect(textContent(findByClass(page.element, 'game-timer-value'))).toBe('00:01:00')

    await showPage(page)
    await vi.advanceTimersByTimeAsync(1599)
    page.rerender()
    expect(textContent(findByClass(page.element, 'sequence-memory-progress'))).toContain('第 1 / 3 项')
    expect(textContent(page.element)).not.toContain('下一项')

    await vi.advanceTimersByTimeAsync(1)
    page.rerender()
    expect(textContent(page.element)).toContain('下一项')
    expect(textContent(findByClass(page.element, 'game-timer-value'))).toBe('00:00:58')

    await vi.advanceTimersByTimeAsync(100)
    page.rerender()
    expect(textContent(findByClass(page.element, 'game-timer-value'))).toBe('00:00:58')
    page.unmount()
  })

  it('后台挂起 sequence transition 并只恢复剩余的 300ms', async () => {
    const page = await renderGame('game-memory-color-sequence', '颜色顺序记忆')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(2000)
    await vi.advanceTimersByTimeAsync(200)
    page.rerender()
    expect(textContent(page.element)).toContain('下一项')

    await hidePage(page)
    await vi.advanceTimersByTimeAsync(5000)
    await showPage(page)
    await vi.advanceTimersByTimeAsync(299)
    page.rerender()
    expect(textContent(page.element)).toContain('下一项')

    await vi.advanceTimersByTimeAsync(1)
    page.rerender()
    expect(textContent(page.element)).not.toContain('下一项')
    expect(textContent(findByClass(page.element, 'sequence-memory-progress'))).toContain('第 2 / 3 项')
    page.unmount()
  })

  it('后台挂起作答 timeout，并从剩余的 4500ms 继续', async () => {
    const page = await renderGame('game-executive-inhibition', '反应抑制')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(2500)
    await hidePage(page)
    await vi.advanceTimersByTimeAsync(10_000)
    await showPage(page)

    await vi.advanceTimersByTimeAsync(4499)
    page.rerender()
    expect(findAll(page.element, (item) => hasClass(item, 'game-feedback'))).toHaveLength(0)

    await vi.advanceTimersByTimeAsync(1)
    page.rerender()
    expect(textContent(findByClass(page.element, 'game-feedback'))).toBe('没关系')
    page.unmount()
  })

  it('后台挂起 settling 反馈并在剩余 600ms 后换题', async () => {
    const page = await renderGame('game-executive-inhibition', '反应抑制')
    await enterPlaying(page)
    click(numberTiles(page.element)[0])
    page.rerender()
    expect(hasClass(numberTiles(page.element)[0], 'choice-correct')).toBe(true)

    await vi.advanceTimersByTimeAsync(400)
    await hidePage(page)
    await vi.advanceTimersByTimeAsync(5000)
    await showPage(page)
    await vi.advanceTimersByTimeAsync(599)
    page.rerender()
    expect(hasClass(numberTiles(page.element)[0], 'choice-correct')).toBe(true)

    await vi.advanceTimersByTimeAsync(1)
    page.rerender()
    expect(numberTiles(page.element).every((tile) => !String(tile.props.className).includes('choice-'))).toBe(true)
    expect(findAll(page.element, (item) => hasClass(item, 'game-feedback'))).toHaveLength(0)
    page.unmount()
  })

  it('用户暂停不会被后台 show 自动继续，手动继续后保留 settling 剩余时间', async () => {
    const page = await renderGame('game-executive-inhibition', '反应抑制')
    await enterPlaying(page)
    click(numberTiles(page.element)[0])
    page.rerender()
    await vi.advanceTimersByTimeAsync(400)
    click(findButtonByText(page.element, '暂停'))
    page.rerender()

    await hidePage(page)
    await vi.advanceTimersByTimeAsync(5000)
    await showPage(page)
    expect(findButtonByText(page.element, '继续')).toBeTruthy()

    await vi.advanceTimersByTimeAsync(5000)
    page.rerender()
    expect(hasClass(numberTiles(page.element)[0], 'choice-correct')).toBe(true)

    click(findButtonByText(page.element, '继续'))
    page.rerender()
    await vi.advanceTimersByTimeAsync(599)
    page.rerender()
    expect(hasClass(numberTiles(page.element)[0], 'choice-correct')).toBe(true)

    await vi.advanceTimersByTimeAsync(1)
    page.rerender()
    expect(numberTiles(page.element).every((tile) => !String(tile.props.className).includes('choice-'))).toBe(true)
    page.unmount()
  })

  it('顺序题在 settling 暂停时保留已填写槽位与对错标记', async () => {
    const page = await renderGame('game-memory-color-sequence', '颜色顺序记忆')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(7000)
    page.rerender()
    const blueTile = findButtonByText(page.element, '蓝')
    click(blueTile)
    click(blueTile)
    click(blueTile)
    page.rerender()
    expect(findAll(page.element, (item) => hasClass(item, 'sequence-answer-slot'))).toHaveLength(3)
    expect(findAll(page.element, (item) => hasClass(item, 'sequence-result-mark'))).toHaveLength(3)

    await vi.advanceTimersByTimeAsync(400)
    click(findButtonByText(page.element, '暂停'))
    page.rerender()
    expect(findAll(page.element, (item) => hasClass(item, 'sequence-answer-slot'))).toHaveLength(3)
    expect(findAll(page.element, (item) => hasClass(item, 'sequence-result-mark'))).toHaveLength(3)
    expect(textContent(findByClass(page.element, 'game-feedback'))).toBe('很好')
    page.unmount()
  })

  it('选项结果固定展示 1000ms，并在新题清理 result class 与反馈', async () => {
    const page = await renderGame('game-executive-inhibition', '反应抑制')
    await enterPlaying(page)
    click(numberTiles(page.element)[0])
    page.rerender()
    expect(hasClass(numberTiles(page.element)[0], 'choice-correct')).toBe(true)

    await vi.advanceTimersByTimeAsync(999)
    page.rerender()
    expect(hasClass(numberTiles(page.element)[0], 'choice-correct')).toBe(true)

    await vi.advanceTimersByTimeAsync(1)
    page.rerender()
    expect(numberTiles(page.element).every((tile) => !String(tile.props.className).includes('choice-'))).toBe(true)
    expect(findAll(page.element, (item) => hasClass(item, 'game-feedback'))).toHaveLength(0)
    page.unmount()
  })

  it('声音卡默认直接渲染编号背面，只有当前试听卡渲染图片', async () => {
    const previewAudio = deferred<boolean>()
    audioHarness.playAudioSrc.mockReset()
    audioHarness.playAudioSrc.mockReturnValueOnce(previewAudio.promise).mockResolvedValue(true)
    const page = await renderGame('game-audiovisual-sound-discrimination', '声音辨别')
    await enterPlaying(page)
    page.rerender()

    const cards = soundCards(page.element)
    expect(cards).toHaveLength(3)
    expect(hasClass(cards[0], 'sound-card-preview')).toBe(true)
    expect(findAll(cards[0], (item) => item.type === 'Image')).toHaveLength(1)
    cards.slice(1).forEach((card, index) => {
      expect(hasClass(card, 'sound-card-back')).toBe(true)
      expect(textContent(card)).toBe(String(index + 2))
      expect(findAll(card, (item) => hasClass(item, 'sound-card-back-face'))).toHaveLength(1)
      expect(findAll(card, (item) => item.type === 'Image')).toHaveLength(0)
      expect(card.props.hoverClass).toBeUndefined()
    })

    previewAudio.resolve(true)
    page.unmount()
  })

  it('声音答错只保留编号背面和红框，并在卡片外提示错误', async () => {
    const page = await renderGame('game-audiovisual-sound-discrimination', '声音辨别')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises(20)
    page.rerender()

    click(soundCards(page.element)[1])
    page.rerender()
    const wrongCard = soundCards(page.element)[1]
    expect(hasClass(wrongCard, 'sound-card-wrong')).toBe(true)
    soundCards(page.element).forEach((card, index) => {
      expect(textContent(card)).toBe(String(index + 1))
      expect(findAll(card, (item) => item.type === 'Image')).toHaveLength(0)
    })
    expect(textContent(findByClass(page.element, 'game-feedback'))).toBe('没关系')
    page.unmount()
  })

  it('拼图交换后清除选中边框状态，且拼图块不使用通用倾斜按压类', async () => {
    const page = await renderGame('game-audiovisual-puzzle', '图片拼图')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(3500)
    page.rerender()

    const tiles = puzzleTiles(page.element)
    expect(tiles).toHaveLength(4)
    expect(tiles.every((tile) => tile.props.hoverClass === undefined)).toBe(true)
    click(tiles[0])
    page.rerender()
    expect(puzzleTiles(page.element).filter((tile) => hasClass(tile, 'selected'))).toHaveLength(1)

    click(puzzleTiles(page.element)[1])
    page.rerender()
    expect(puzzleTiles(page.element).filter((tile) => hasClass(tile, 'selected'))).toHaveLength(0)
    page.unmount()
  })

  it('后台中断声音 preview run 后回到同一张卡继续，而不是跳过当前卡', async () => {
    const firstAudio = deferred<boolean>()
    const resumedAudio = deferred<boolean>()
    audioHarness.playAudioSrc.mockReset()
    audioHarness.playAudioSrc
      .mockReturnValueOnce(firstAudio.promise)
      .mockReturnValueOnce(resumedAudio.promise)
      .mockResolvedValue(true)
    const page = await renderGame('game-audiovisual-sound-discrimination', '声音辨别')
    await enterPlaying(page)
    page.rerender()
    expect(hasClass(soundCards(page.element)[0], 'sound-card-preview')).toBe(true)

    await hidePage(page)
    await vi.advanceTimersByTimeAsync(5000)
    page.rerender()
    expect(soundCards(page.element).every((card) => !hasClass(card, 'sound-card-preview'))).toBe(true)

    await showPage(page)
    expect(hasClass(soundCards(page.element)[0], 'sound-card-preview')).toBe(true)
    expect(soundCards(page.element).slice(1).every((card) => !hasClass(card, 'sound-card-preview'))).toBe(true)
    firstAudio.resolve(true)
    resumedAudio.resolve(true)
    page.unmount()
  })

})

describe('GameSessionPage 规范逐题采集', () => {
  async function endAndRead(page: RenderedPage): Promise<GameTrainingPayload> {
    click(findButtonByText(page.element, '提前结束'))
    await flushPromises()
    page.rerender()
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledTimes(1)
    return retryUploadHarness.postGameTrainingRecord.mock.calls[0][0]
  }

  const cases = [
    ['game-memory-color-sequence', '颜色顺序记忆', 7000],
    ['game-memory-pattern-sequence', '图案顺序记忆', 7000],
    ['game-executive-inhibition', '反应抑制', 0],
    ['game-executive-category-switch', '分类转换', 0],
    ['game-audiovisual-sound-discrimination', '声音辨别', 540],
    ['game-audiovisual-puzzle', '拼图', 3500],
  ] as const

  function answer(page: RenderedPage, code: string) {
    if (code === 'game-memory-color-sequence' || code === 'game-memory-pattern-sequence') {
      const button = findButtonByText(page.element, code === 'game-memory-color-sequence' ? '蓝' : '太阳')
      click(button); click(button); click(button)
    } else if (code === 'game-executive-inhibition') {
      click(numberTiles(page.element)[0])
    } else if (code === 'game-executive-category-switch') {
      click(findButtonByText(page.element, '水果'))
    } else if (code === 'game-audiovisual-sound-discrimination') {
      click(soundCards(page.element)[0])
    } else {
      // 固定随机数0产生 [1,2,3,0]；同块点击不计交换，三次有效交换复原。
      click(puzzleTiles(page.element)[0]); page.rerender()
      click(puzzleTiles(page.element)[0]); page.rerender()
      for (const [left, right] of [[0, 3], [1, 3], [2, 3]]) {
        click(puzzleTiles(page.element)[left]); page.rerender()
        click(puzzleTiles(page.element)[right]); page.rerender()
      }
    }
    page.rerender()
  }

  it.each(cases)('%s 排除展示和8000ms暂停，记录1200+1300ms并在反馈中结束', async (code, name, previewMs) => {
    prescriptionHarness.demo = false
    const page = await renderGame(code, name)
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(previewMs)
    page.rerender()
    await vi.advanceTimersByTimeAsync(1200)
    click(findButtonByText(page.element, '暂停')); page.rerender()
    await vi.advanceTimersByTimeAsync(8000)
    click(findButtonByText(page.element, '继续')); page.rerender()
    await vi.advanceTimersByTimeAsync(1300)
    answer(page, code)
    await vi.advanceTimersByTimeAsync(400)
    const payload = await endAndRead(page)
    expect(payload.client_session_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(payload.question_results).toEqual([{
      capture_version: 'active_response_v2',
      expected_step_count: code.includes('sequence') ? 3 : null,
      selection_steps: code.includes('sequence') ? [2500, 0, 0].map((ms, i) => ({step_index: i + 1, selected_value: code.includes('color') ? 'blue' : 'sun', expected_value: code.includes('color') ? 'blue' : 'sun', response_duration_ms: ms, is_correct: true})) : [],
      click_count: code === 'game-audiovisual-puzzle' ? 8 : null,
      question_index: 1, game_code: code, difficulty: '简单', response_duration_ms: 2500,
      is_correct: true, result_type: 'answered', swap_count: code === 'game-audiovisual-puzzle' ? 3 : null,
    }])
    expect(payload.form_data.raw_detail).toMatchObject({ completed_units: 1, correct_units: 1, difficulty_adjust_reason: '' })
    expect(payload.form_data.raw_detail.rounds).toBeUndefined()
    page.unmount()
  })

  it('隐藏8000ms后按剩余时间超时，只输出一次7000ms错误判定', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-executive-inhibition', '反应抑制')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(1200)
    await hidePage(page)
    await vi.advanceTimersByTimeAsync(8000)
    await showPage(page)
    await vi.advanceTimersByTimeAsync(5800)
    page.rerender()
    click(numberTiles(page.element)[0])
    const payload = await endAndRead(page)
    expect(payload.question_results).toEqual([expect.objectContaining({response_duration_ms: 7000, is_correct: false, result_type: 'timeout'})])
    page.unmount()
  })

  it('整场使用单调时间补偿事件循环延迟，结束丢弃未判定题', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-executive-inhibition', '反应抑制')
    await enterPlaying(page)
    // 时钟前进2500ms但定时器尚未获调度，模拟事件循环堵塞。
    clockHarness.offset += 2500
    answer(page, 'game-executive-inhibition')
    await vi.advanceTimersByTimeAsync(1000)
    page.rerender()
    await vi.advanceTimersByTimeAsync(100)
    const payload = await endAndRead(page)
    expect(payload.question_results).toEqual([expect.objectContaining({response_duration_ms: 2500})])
    expect(payload.form_data.raw_detail.session_duration_seconds).toBe(3)
    page.unmount()
  })

  it('目标首次播放和重播禁选并排除音频耗时，重播不消耗剩余作答时间', async () => {
    prescriptionHarness.demo = false
    const initialTarget = deferred<boolean>()
    audioHarness.playAudioSrc.mockResolvedValueOnce(true).mockResolvedValueOnce(true).mockResolvedValueOnce(true).mockReturnValueOnce(initialTarget.promise)
    const page = await renderGame('game-audiovisual-sound-discrimination', '声音辨别')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(540)
    page.rerender()
    expect(soundCards(page.element).every(card => card.props.disabled)).toBe(true)
    click(soundCards(page.element)[0])
    await vi.advanceTimersByTimeAsync(5000)
    initialTarget.resolve(true); await flushPromises(); page.rerender()
    await vi.advanceTimersByTimeAsync(1200)
    const replay = deferred<boolean>()
    audioHarness.playAudioSrc.mockReturnValueOnce(replay.promise)
    click(findButtonByText(page.element, '重播目标声音')); page.rerender()
    expect(soundCards(page.element).every(card => card.props.disabled)).toBe(true)
    click(soundCards(page.element)[0])
    await vi.advanceTimersByTimeAsync(9000)
    replay.resolve(true); await flushPromises(); page.rerender()
    await vi.advanceTimersByTimeAsync(1300)
    answer(page, 'game-audiovisual-sound-discrimination')
    const payload = await endAndRead(page)
    expect(payload.question_results).toEqual([expect.objectContaining({response_duration_ms: 2500, result_type: 'answered'})])
    page.unmount()
  })

  it('重播失败保持禁选且不静默计时，成功重试保留剩余6800ms超时', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-audiovisual-sound-discrimination', '声音辨别')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(540)
    page.rerender()
    await vi.advanceTimersByTimeAsync(1200)
    audioHarness.playAudioSrc.mockRejectedValueOnce(new Error('播放失败'))
    click(findButtonByText(page.element, '重播目标声音'))
    await flushPromises(); page.rerender()
    expect(textContent(page.element)).toContain('目标声音播放异常')
    expect(soundCards(page.element).every(card => card.props.disabled)).toBe(true)
    await vi.advanceTimersByTimeAsync(9000)
    click(findButtonByText(page.element, '重播目标声音'))
    await flushPromises(); page.rerender()
    await vi.advanceTimersByTimeAsync(6799)
    page.rerender()
    expect(findAll(page.element, item => hasClass(item, 'game-feedback'))).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(1)
    page.rerender()
    const payload = await endAndRead(page)
    expect(payload.question_results).toEqual([expect.objectContaining({response_duration_ms: 8000, result_type: 'timeout', is_correct: false})])
    page.unmount()
  })

  it('隐藏重播后旧音频完成不能恢复新播放，且手动暂停优先于show', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-audiovisual-sound-discrimination', '声音辨别')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(540)
    page.rerender()
    await vi.advanceTimersByTimeAsync(1200)
    const oldReplay = deferred<boolean>()
    const newReplay = deferred<boolean>()
    audioHarness.playAudioSrc.mockReturnValueOnce(oldReplay.promise).mockReturnValueOnce(newReplay.promise)
    click(findButtonByText(page.element, '重播目标声音')); page.rerender()
    click(findButtonByText(page.element, '暂停')); page.rerender()
    await hidePage(page)
    await vi.advanceTimersByTimeAsync(8000)
    await showPage(page)
    expect(textContent(page.element)).toContain('训练已暂停')
    click(findButtonByText(page.element, '继续')); page.rerender()
    oldReplay.resolve(true); await flushPromises(); page.rerender()
    expect(soundCards(page.element).every(card => card.props.disabled)).toBe(true)
    click(soundCards(page.element)[0])
    await vi.advanceTimersByTimeAsync(3000)
    newReplay.resolve(true); await flushPromises(); page.rerender()
    await vi.advanceTimersByTimeAsync(1300)
    answer(page, 'game-audiovisual-sound-discrimination')
    const payload = await endAndRead(page)
    expect(payload.question_results).toEqual([expect.objectContaining({response_duration_ms: 2500})])
    page.unmount()
  })

  it.each(['结束', '卸载'])('目标音频迟到%s不新增判定或写页面状态', async operation => {
    prescriptionHarness.demo = false
    const audio = deferred<boolean>()
    audioHarness.playAudioSrc.mockResolvedValueOnce(true).mockResolvedValueOnce(true).mockResolvedValueOnce(true).mockReturnValueOnce(audio.promise)
    const page = await renderGame('game-audiovisual-sound-discrimination', '声音辨别')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(540)
    page.rerender()
    if (operation === '结束') {
      const payload = await endAndRead(page)
      expect(payload.question_results).toEqual([])
    }
    page.unmount()
    audio.resolve(true); await flushPromises()
    expect(reactHarness.stateWritesAfterCleanup()).toBe(0)
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledTimes(operation === '结束' ? 1 : 0)
  })

  it('第2000题判定后自动保存一次，不进入第2001题', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-executive-inhibition', '反应抑制')
    const prescription = prescriptionHarness.current as ReturnType<typeof prescriptionFor>
    prescription.actions[0].duration_minutes = 60
    page.rerender()
    await enterPlaying(page)
    for (let index = 0; index < 2000; index += 1) {
      click(numberTiles(page.element)[0]); page.rerender()
      if (index < 1999) {
        await vi.advanceTimersByTimeAsync(1000)
        page.rerender()
      }
    }
    await flushPromises(); page.rerender()
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledTimes(1)
    const payload = retryUploadHarness.postGameTrainingRecord.mock.calls[0][0] as GameTrainingPayload
    expect(payload.question_results).toHaveLength(2000)
    expect(payload.question_results?.at(-1)).toMatchObject({question_index: 2000, response_duration_ms: 0})
    expect(payload.form_data.raw_detail).toMatchObject({ended_by: 'timer', ended_early: true, completed_units: 2000, session_duration_seconds: 1999})
    expect(payload.status).toBe('partial')
    expect(payload.note).toBe('达到题数上限，训练自动结束')
    expect(textContent(page.element)).toContain('达到题数上限，训练自动结束')
    expect(textContent(page.element)).not.toContain('本次训练已完成')
    await vi.advanceTimersByTimeAsync(2000)
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledTimes(1)
    expect(numberTiles(page.element)).toHaveLength(0)
    page.unmount()
  })


  it('最终点击在tap音触发前结算题目毫秒', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-executive-inhibition', '反应抑制')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(2500)
    audioHarness.playGameAudio.mockImplementationOnce(async () => { clockHarness.offset += 500 })
    answer(page, 'game-executive-inhibition')
    const payload = await endAndRead(page)
    expect(payload.question_results).toEqual([expect.objectContaining({response_duration_ms: 2500})])
    page.unmount()
  })

  it('页面卸载后保留的点击回调不能写入反馈或触发媒体', async () => {
    const page = await renderGame('game-executive-inhibition', '反应抑制')
    await enterPlaying(page)
    const oldButton = numberTiles(page.element)[0]
    page.unmount()
    audioHarness.playGameAudio.mockClear()
    click(oldButton)
    expect(reactHarness.stateWritesAfterCleanup()).toBe(0)
    expect(audioHarness.playGameAudio).not.toHaveBeenCalled()
  })


  it('1999道亚毫秒题的舍入累计不超过整场秒数加1000ms容差', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-executive-inhibition', '反应抑制')
    const prescription = prescriptionHarness.current as ReturnType<typeof prescriptionFor>
    prescription.actions[0].duration_minutes = 60
    page.rerender()
    await enterPlaying(page)
    for (let index = 0; index < 1999; index += 1) {
      clockHarness.offset += 0.5001
      click(numberTiles(page.element)[0]); page.rerender()
      if (index < 1998) {
        await vi.advanceTimersByTimeAsync(1000)
        page.rerender()
      }
    }
    const payload = await endAndRead(page)
    expect(payload.question_results).toHaveLength(1999)
    const sum = payload.question_results!.reduce((total, question) => total + question.response_duration_ms, 0)
    expect(sum).toBe(1999)
    expect(sum).toBeLessThanOrEqual(payload.form_data.raw_detail.session_duration_seconds * 1000 + 1000)
    page.unmount()
  })

  it('拼图有效作答达到一小时安全结束，暂停不消耗剩余时间且不补造timeout行', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-audiovisual-puzzle', '拼图')
    const prescription = prescriptionHarness.current as ReturnType<typeof prescriptionFor>
    prescription.actions[0].duration_minutes = 120
    page.rerender()
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(3500)
    await vi.advanceTimersByTimeAsync(3599000)
    page.rerender()
    await hidePage(page)
    await vi.advanceTimersByTimeAsync(8000)
    await showPage(page)
    await vi.advanceTimersByTimeAsync(999)
    expect(retryUploadHarness.postGameTrainingRecord).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    await flushPromises(); page.rerender()
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledTimes(1)
    const payload = retryUploadHarness.postGameTrainingRecord.mock.calls[0][0] as GameTrainingPayload
    expect(payload.question_results).toEqual([])
    expect(payload.form_data.raw_detail).toMatchObject({ended_by: 'timer', ended_early: true})
    expect(payload.status).toBe('partial')
    expect(payload.note).toBe('达到单题时长上限，训练自动结束')
    expect(textContent(page.element)).toContain('达到单题时长上限，训练自动结束')
    expect(textContent(page.element)).not.toContain('本次训练已完成')
    expect(puzzleTiles(page.element)).toHaveLength(0)
    page.unmount()
  })


  it('拼图一小时后延迟定时器未执行时，点击也先安全结束', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-audiovisual-puzzle', '拼图')
    const prescription = prescriptionHarness.current as ReturnType<typeof prescriptionFor>
    prescription.actions[0].duration_minutes = 120
    page.rerender()
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(3500)
    page.rerender()
    clockHarness.offset += 3_600_001
    click(puzzleTiles(page.element)[0])
    await flushPromises(); page.rerender()
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledTimes(1)
    expect(retryUploadHarness.postGameTrainingRecord.mock.calls[0][0].question_results).toEqual([])
    expect(puzzleTiles(page.element)).toHaveLength(0)
    page.unmount()
  })

  it.each(['game-memory-color-sequence', 'game-memory-pattern-sequence'])('%s 逐步耗时排除后台暂停，错选后手动结束保留未完成', async code => {
    prescriptionHarness.demo = false
    const page = await renderGame(code, '顺序记忆')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(7000); page.rerender()
    await vi.advanceTimersByTimeAsync(1200)
    click(findButtonByText(page.element, code.includes('color') ? '绿' : '小船')); page.rerender()
    await hidePage(page)
    await vi.advanceTimersByTimeAsync(8000)
    expect(retryUploadHarness.savePendingGameUpload).not.toHaveBeenCalled()
    await showPage(page)
    await vi.advanceTimersByTimeAsync(1300)
    click(findButtonByText(page.element, code.includes('color') ? '蓝' : '太阳')); page.rerender()
    const payload = await endAndRead(page)
    expect(payload.question_results).toEqual([expect.objectContaining({
      result_type: 'interrupted', response_duration_ms: 2500, expected_step_count: 3,
      selection_steps: [expect.objectContaining({step_index: 1, response_duration_ms: 1200, is_correct: false}),
        expect.objectContaining({step_index: 2, response_duration_ms: 1300, is_correct: true})],
    })])
    expect(payload.form_data).toMatchObject({error_count: 0, accuracy_rate: 0, raw_detail: {completed_units: 0, correct_units: 0, recorded_question_count: 1}})
    page.unmount()
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledTimes(1)
  })

  it('离页同步缓存半题，卸载后不发请求不写状态，零步不补造题', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-memory-color-sequence', '顺序记忆')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(7000); page.rerender()
    await vi.advanceTimersByTimeAsync(250)
    click(findButtonByText(page.element, '蓝')); page.rerender()
    page.unmount()
    expect(retryUploadHarness.savePendingGameUpload).toHaveBeenCalledTimes(1)
    const payload = retryUploadHarness.savePendingGameUpload.mock.calls[0][1]
    expect(payload.question_results).toEqual([expect.objectContaining({result_type: 'interrupted', selection_steps: [expect.objectContaining({response_duration_ms: 250})]})])
    await vi.advanceTimersByTimeAsync(60000)
    expect(retryUploadHarness.postGameTrainingRecord).not.toHaveBeenCalled()
    expect(reactHarness.stateWritesAfterCleanup()).toBe(0)
  })

  it.each(['game-memory-color-sequence', 'game-memory-pattern-sequence'])('%s 超时保留错选，不与结束重复追加', async code => {
    prescriptionHarness.demo = false
    const page = await renderGame(code, '顺序记忆')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(7000); page.rerender()
    await vi.advanceTimersByTimeAsync(500)
    click(findButtonByText(page.element, code.includes('color') ? '绿' : '小船')); page.rerender()
    await vi.advanceTimersByTimeAsync(7500); page.rerender()
    const payload = await endAndRead(page)
    expect(payload.question_results).toEqual([expect.objectContaining({result_type: 'timeout', is_correct: false, response_duration_ms: 8000, selection_steps: [expect.objectContaining({is_correct: false, response_duration_ms: 500})]})])
    expect(payload.form_data).toMatchObject({error_count: 1, raw_detail: {completed_units: 1, recorded_question_count: 1}})
    page.unmount()
  })

  it.each([0, 1])('整场定时结束保留%s步半题，零步无行，重复结束无效', async steps => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-memory-color-sequence', '顺序记忆')
    const prescription = prescriptionHarness.current as ReturnType<typeof prescriptionFor>
    prescription.actions[0].duration_minutes = 0.2
    page.rerender()
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(7000); page.rerender()
    const staleEnd = findButtonByText(page.element, '提前结束')
    if (steps) { click(findButtonByText(page.element, '蓝')); page.rerender() }
    await vi.advanceTimersByTimeAsync(5000); page.rerender()
    click(staleEnd)
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledTimes(1)
    const payload = retryUploadHarness.postGameTrainingRecord.mock.calls[0][0]
    expect(payload.question_results).toHaveLength(steps)
    if (steps) expect(payload.question_results[0]).toMatchObject({result_type: 'interrupted', response_duration_ms: 5000})
    expect(payload.form_data.raw_detail).toMatchObject({ended_by: 'timer', completed_units: 0, recorded_question_count: steps})
    page.unmount()
  })

  it('卸载时直接上传尚未完成同步缓存同UUID且迟到失败不写状态', async () => {
    prescriptionHarness.demo = false
    const pending = deferred<void>()
    retryUploadHarness.postGameTrainingRecord.mockReturnValue(pending.promise)
    const page = await renderGame('game-executive-inhibition', '反应抑制')
    await enterPlaying(page)
    click(numberTiles(page.element)[0]); page.rerender()
    click(findButtonByText(page.element, '提前结束')); page.rerender()
    const payload = retryUploadHarness.postGameTrainingRecord.mock.calls[0][0]
    page.unmount()
    expect(retryUploadHarness.savePendingGameUpload).toHaveBeenCalledWith(taroHarness.taroMock, payload, expect.any(Number))
    pending.reject(Object.assign(new Error('断网'), {retryable: true}))
    await flushPromises()
    expect(reactHarness.stateWritesAfterCleanup()).toBe(0)
    expect(retryUploadHarness.savePendingGameUploadAfterActiveRetry).not.toHaveBeenCalled()
  })

  it('拼图预览无可点块，暂停/后台的旧点击不计数，取消同块仍计数', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-audiovisual-puzzle', '拼图')
    await enterPlaying(page)
    expect(puzzleTiles(page.element)).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(3500); page.rerender()
    const staleTile = puzzleTiles(page.element)[0]
    click(findButtonByText(page.element, '暂停')); page.rerender()
    click(staleTile)
    click(findButtonByText(page.element, '继续')); page.rerender()
    await hidePage(page); click(staleTile); await showPage(page)
    answer(page, 'game-audiovisual-puzzle')
    const payload = await endAndRead(page)
    expect(payload.question_results).toEqual([expect.objectContaining({click_count: 8, swap_count: 3})])
    page.unmount()
  })

  it('旧UUID待补传时新顺序半题卸载，两条都经真实缓存恢复且不弹提示', async () => {
    prescriptionHarness.demo = false
    const actual = await vi.importActual<typeof import('./retryUpload')>('./retryUpload')
    const store = new Map<string, unknown>()
    const storage = {
      getStorageSync: (key: string) => store.get(key),
      setStorageSync: (key: string, value: unknown) => { store.set(key, value) },
      removeStorageSync: (key: string) => { store.delete(key) },
    }
    const old: GameTrainingPayload = {client_session_id: 'old', prescription_action: 100, training_date: '2026-08-31', status: 'partial', actual_duration_minutes: 1, score: 0, note: '', form_data: {accuracy_rate: 0, error_count: 0, difficulty: '简单', raw_detail: {game_code: 'game-memory-color-sequence', ended_by: 'manual', ended_early: true, prescribed_difficulty: '简单', difficulty_adjusted: false, difficulty_adjust_reason: '', upload_mode: 'direct', retry_count: 0, total_retry_count: 0, session_duration_seconds: 1, suggested_duration_minutes: 1, completed_units: 0, correct_units: 0}}}
    actual.savePendingGameUpload(storage, old, Date.now())
    retryUploadHarness.savePendingGameUpload.mockImplementation((_taro, p, now) => actual.savePendingGameUpload(storage, p, now))
    const page = await renderGame('game-memory-color-sequence', '顺序记忆')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(7000); page.rerender()
    click(findButtonByText(page.element, '蓝')); page.rerender()
    page.unmount()
    expect(actual.loadPendingGameUpload(storage)?.payload).toEqual(old)
    actual.clearPendingGameUpload(storage, old)
    expect(actual.loadPendingGameUpload(storage)?.payload.question_results).toEqual([expect.objectContaining({result_type: 'interrupted', selection_steps: [expect.objectContaining({selected_value: 'blue'})]})])
    expect(actual.loadPendingGameUpload(storage)?.payload.client_session_id).not.toBe('old')
    await flushPromises()
    expect(reactHarness.stateWritesAfterCleanup()).toBe(0)
    expect(retryUploadHarness.postGameTrainingRecord).not.toHaveBeenCalled()
  })

  it('直接上传成功按本次UUID清理缓存', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-executive-inhibition', '反应抑制')
    await enterPlaying(page)
    const payload = await endAndRead(page)
    expect(retryUploadHarness.clearPendingGameUpload).toHaveBeenCalledWith(taroHarness.taroMock, payload)
    page.unmount()
  })

})
