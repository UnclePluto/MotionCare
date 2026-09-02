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
    },
    beginRender() {
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
      effectCleanups[index]?.()
      queuedEffects.push(() => {
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

const prescriptionHarness = vi.hoisted(() => ({ current: null as unknown }))
const audioHarness = vi.hoisted(() => ({
  playAudioSrc: vi.fn<(...args: unknown[]) => Promise<boolean>>(),
  playGameAudio: vi.fn(async () => undefined),
  stopActiveGameAudio: vi.fn(),
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
  isDemoSession: () => true,
}))

vi.mock('./retryUpload', () => ({
  postGameTrainingRecord: vi.fn(),
  savePendingGameUploadAfterActiveRetry: vi.fn(),
  startPendingGameUploadRetryLoop: vi.fn(),
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
  const render = () => {
    reactHarness.beginRender()
    let element = GameSessionPage() as ReactElement
    while (element && typeof element.type === 'function') element = element.type(element.props)
    reactHarness.runEffects()
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
    unmount() {
      reactHarness.cleanup()
    },
  }
}

type RenderedPage = ReturnType<typeof renderPage>

async function flushPromises(times = 8): Promise<void> {
  for (let index = 0; index < times; index += 1) await Promise.resolve()
}

async function renderGame(sourceKey: string, actionName: string): Promise<RenderedPage> {
  prescriptionHarness.current = prescriptionFor(sourceKey, actionName)
  const page = renderPage()
  taroHarness.showCallbacks.at(-1)?.()
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

function imageIn(node: unknown): ReactElement {
  const image = findAll(node, (item) => item.type === 'Image')[0]
  if (!image) throw new Error(`Image not found in: ${textContent(node)}`)
  return image
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve
  })
  return { promise, resolve }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-08-31T08:00:00+08:00'))
  vi.spyOn(Math, 'random').mockReturnValue(0)
  reactHarness.reset()
  taroHarness.reset()
  audioHarness.playAudioSrc.mockReset()
  audioHarness.playAudioSrc.mockResolvedValue(true)
  audioHarness.playGameAudio.mockClear()
  audioHarness.stopActiveGameAudio.mockClear()
})

afterEach(async () => {
  reactHarness.reset()
  vi.restoreAllMocks()
  vi.clearAllTimers()
  vi.useRealTimers()
})

describe('GameSessionPage 生命周期与反馈接线', () => {
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
    await vi.advanceTimersByTimeAsync(499)
    page.rerender()
    expect(textContent(findByClass(page.element, 'sequence-memory-progress'))).toContain('第 1 / 3 项')
    expect(textContent(page.element)).not.toContain('下一项')

    await vi.advanceTimersByTimeAsync(1)
    page.rerender()
    expect(textContent(page.element)).toContain('下一项')
    expect(textContent(findByClass(page.element, 'game-timer-value'))).toBe('00:01:00')

    await vi.advanceTimersByTimeAsync(100)
    page.rerender()
    expect(textContent(findByClass(page.element, 'game-timer-value'))).toBe('00:00:59')
    page.unmount()
  })

  it('后台挂起 sequence transition 并只恢复剩余的 300ms', async () => {
    const page = await renderGame('game-memory-color-sequence', '颜色顺序记忆')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(900)
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
    await vi.advanceTimersByTimeAsync(3700)
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

  it('声音图片在 preview 加载失败后立即回到稳定编号背面', async () => {
    const previewAudio = deferred<boolean>()
    audioHarness.playAudioSrc.mockReset()
    audioHarness.playAudioSrc.mockReturnValueOnce(previewAudio.promise).mockResolvedValue(true)
    const page = await renderGame('game-audiovisual-sound-discrimination', '声音辨别')
    await enterPlaying(page)
    page.rerender()

    const firstCard = soundCards(page.element)[0]
    expect(hasClass(firstCard, 'sound-card-preview')).toBe(true)
    const image = imageIn(firstCard)
    expect(typeof image.props.onError).toBe('function')
    image.props.onError?.()
    page.rerender()

    const failedCard = soundCards(page.element)[0]
    expect(hasClass(failedCard, 'sound-card-back')).toBe(true)
    expect(textContent(failedCard)).toContain('1')
    expect(findAll(failedCard, (item) => item.type === 'Image')).toHaveLength(0)
    previewAudio.resolve(true)
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
    expect(cards).toHaveLength(4)
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

  it('正确反馈阶段图片失败不揭示空白正面，并在新题清理失败与结果状态', async () => {
    const page = await renderGame('game-audiovisual-sound-discrimination', '声音辨别')
    await enterPlaying(page)
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises(20)
    page.rerender()
    expect(textContent(page.element)).toContain('请听目标声音，选择对应卡片')

    click(soundCards(page.element)[0])
    page.rerender()
    expect(hasClass(soundCards(page.element)[0], 'sound-card-correct')).toBe(true)
    expect(textContent(findByClass(page.element, 'game-feedback'))).toBe('很好')

    imageIn(soundCards(page.element)[0]).props.onError?.()
    page.rerender()
    expect(hasClass(soundCards(page.element)[0], 'sound-card-back')).toBe(true)
    expect(textContent(soundCards(page.element)[0])).toContain('1')
    expect(textContent(findByClass(page.element, 'game-feedback'))).toBe('很好')

    const nextRoundAudio = deferred<boolean>()
    audioHarness.playAudioSrc.mockReturnValueOnce(nextRoundAudio.promise)
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    page.rerender()
    const nextRoundFirstCard = soundCards(page.element)[0]
    expect(hasClass(nextRoundFirstCard, 'sound-card-preview')).toBe(true)
    expect(findAll(nextRoundFirstCard, (item) => item.type === 'Image')).toHaveLength(1)
    expect(findAll(page.element, (item) => hasClass(item, 'game-feedback'))).toHaveLength(0)
    nextRoundAudio.resolve(true)
    page.unmount()
  })
})
