import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import GameSessionPage from './index'

type ReactElement = {
  type: string | ((props?: Record<string, unknown>) => ReactElement)
  props: Record<string, unknown> & {
    children?: unknown
    className?: string
    disabled?: boolean
    onClick?: () => unknown
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

const prescriptionHarness = vi.hoisted(() => ({ current: null as unknown, demo: true }))
const retryUploadHarness = vi.hoisted(() => ({
  postGameTrainingRecord: vi.fn(),
  savePendingGameUploadAfterActiveRetry: vi.fn(),
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
  savePendingGameUploadAfterActiveRetry: retryUploadHarness.savePendingGameUploadAfterActiveRetry,
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

describe('GameSessionPage 开始前降低难度', () => {
  it('shows the prescribed rule and has no lower level when already simple', async () => {
    const page = await renderGame('game-memory-color-sequence', '颜色顺序记忆')
    expect(textContent(page.element)).toContain('记住 3 个颜色的顺序，每项展示 2 秒')
    expect(textContent(page.element)).toContain('当前已是最低难度')
    expect(findAll(page.element, (item) => item.type === 'Picker')).toHaveLength(0)
    expect(findAll(page.element, (item) => item.type === 'Button' && textContent(item) === '降低难度')).toHaveLength(0)
    page.unmount()
  })

  it('requires one reason before playing and uploads the actual level and selected reason', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-executive-inhibition', '反应抑制', '困难')
    expect(textContent(page.element)).toContain('从 9 个数字中选出不同的一个')
    click(findButtonByText(page.element, '降低难度'))
    page.rerender()
    const choices = findAll(page.element, (item) => item.type === 'Button' && hasClass(item, 'difficulty-level-option'))
    expect(choices.map(textContent)).toEqual(['简单', '中等'])
    click(choices[1])
    page.rerender()
    expect(textContent(page.element)).toContain('从 6 个数字中选出不同的一个')
    click(findButtonByText(page.element, '开始游戏'))
    page.rerender()
    expect(textContent(page.element)).toContain('请选择降低难度的原因')
    const reasons = findAll(page.element, (item) => item.type === 'Button' && hasClass(item, 'difficulty-reason-option'))
    expect(reasons.map(textContent)).toEqual(['切换速度问题', '选项个数问题', '思考时间问题', '其他'])
    click(reasons[0])
    page.rerender()
    click(findButtonByText(page.element, '思考时间问题'))
    page.rerender()
    expect(findAll(page.element, (item) => hasClass(item, 'difficulty-reason-option') && hasClass(item, 'is-selected'))).toHaveLength(1)
    await enterPlaying(page)
    expect(numberTiles(page.element)).toHaveLength(6)
    click(findButtonByText(page.element, '提前结束'))
    await flushPromises()
    page.rerender()
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledWith(expect.objectContaining({
      form_data: expect.objectContaining({
        difficulty: '中等',
        raw_detail: expect.objectContaining({ prescribed_difficulty: '困难', difficulty_adjusted: true, difficulty_adjust_reason: '思考时间问题' }),
      }),
    }))
    page.unmount()
  })

  it('restores the prescribed level and clears the adjustment reason', async () => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-executive-category-switch', '分类转换', '中等')
    click(findButtonByText(page.element, '降低难度'))
    page.rerender()
    const choices = findAll(page.element, (item) => hasClass(item, 'difficulty-level-option'))
    expect(choices.map(textContent)).toEqual(['简单'])
    click(choices[0])
    page.rerender()
    click(findButtonByText(page.element, '选项个数问题'))
    page.rerender()
    click(findButtonByText(page.element, '恢复指导老师设定'))
    page.rerender()
    expect(textContent(page.element)).toContain('判断物品类别，从 4 个选项中选择')
    expect(findAll(page.element, (item) => hasClass(item, 'difficulty-reason-option'))).toHaveLength(0)
    await enterPlaying(page)
    expect(findAll(page.element, (item) => hasClass(item, 'category-option'))).toHaveLength(4)
    expect(textContent(page.element)).toContain('请判断彩图中的物体属于哪个类别，并选出正确的选项')
    click(findButtonByText(page.element, '提前结束'))
    await flushPromises()
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledWith(expect.objectContaining({
      form_data: expect.objectContaining({ difficulty: '中等', raw_detail: expect.objectContaining({ difficulty_adjusted: false, difficulty_adjust_reason: '' }) }),
    }))
    page.unmount()
  })

  it.each([
    ['keep', '其他：今天比较疲劳'],
    ['switch', '思考时间问题'],
    ['switch-back', '其他'],
    ['restore', '其他'],
  ])('records optional other details and clears stale text: %s', async (change, expectedReason) => {
    prescriptionHarness.demo = false
    const page = await renderGame('game-executive-inhibition', '反应抑制', '中等')
    click(findButtonByText(page.element, '降低难度'))
    page.rerender()
    click(findAll(page.element, (item) => hasClass(item, 'difficulty-level-option'))[0])
    page.rerender()
    click(findButtonByText(page.element, '其他'))
    page.rerender()
    const input = findAll(page.element, (item) => item.type === 'Input')[0]
    const onInput = input.props.onInput as (event: { detail: { value: string } }) => void
    onInput({ detail: { value: '今天比较疲劳' } })
    page.rerender()
    if (change === 'switch' || change === 'switch-back') {
      click(findButtonByText(page.element, '思考时间问题'))
      page.rerender()
      expect(findAll(page.element, (item) => item.type === 'Input')).toHaveLength(0)
      if (change === 'switch-back') {
        click(findButtonByText(page.element, '其他'))
        page.rerender()
        expect(findAll(page.element, (item) => item.type === 'Input')[0].props.value).toBe('')
      }
    }
    if (change === 'restore') {
      click(findButtonByText(page.element, '恢复指导老师设定'))
      page.rerender()
      click(findButtonByText(page.element, '降低难度'))
      page.rerender()
      click(findAll(page.element, (item) => hasClass(item, 'difficulty-level-option'))[0])
      page.rerender()
      expect(findAll(page.element, (item) => hasClass(item, 'difficulty-reason-option') && hasClass(item, 'is-selected'))).toHaveLength(0)
      click(findButtonByText(page.element, '其他'))
      page.rerender()
      expect(findAll(page.element, (item) => item.type === 'Input')[0].props.value).toBe('')
    }
    await enterPlaying(page)
    click(findButtonByText(page.element, '提前结束'))
    await flushPromises()
    expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledWith(expect.objectContaining({
      form_data: expect.objectContaining({ raw_detail: expect.objectContaining({ difficulty_adjust_reason: expectedReason }) }),
    }))
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
