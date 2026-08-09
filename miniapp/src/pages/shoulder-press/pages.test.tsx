import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  PENDING_SHOULDER_PRESS_SESSION_KEY,
  type PendingShoulderPressSession
} from './session'

type ReactElement = {
  type: string
  props: Record<string, unknown> & {
    children?: unknown
    onError?: () => unknown
    onTouchStart?: (event: { touches: Array<{ clientX: number; clientY: number }> }) => unknown
    onTouchEnd?: (event: { changedTouches: Array<{ clientX: number; clientY: number }> }) => unknown
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
      if (hookEntries[index] === undefined) {
        hookEntries[index] = { current: initialValue }
      }
      return hookEntries[index]
    },
    useEffect(callback: () => unknown, deps?: unknown[]) {
      const index = hookCursor
      hookCursor += 1
      if (depsChanged(hookEntries[index], deps)) {
        effectCleanups[index]?.()
        queuedEffects.push(() => {
          const cleanup = callback()
          effectCleanups[index] = typeof cleanup === 'function' ? cleanup : undefined
        })
        hookEntries[index] = deps ?? []
      }
    }
  }
})

const taroHarness = vi.hoisted(() => {
  const storage = new Map<string, unknown>()
  const showCallbacks: Array<() => unknown> = []
  const hideCallbacks: Array<() => unknown> = []
  const routerParams: Record<string, string> = { actionId: '42' }
  let currentRoute = 'pages/home/index'
  const unlinkMock = vi.fn((options) => options.success?.())
  const getSavedFileListMock = vi.fn((options) => options.success?.({ fileList: [] }))
  const removeSavedFileMock = vi.fn((options) => options.success?.())
  const taroMock = {
    getStorageSync: vi.fn((key: string) => storage.get(key)),
    setStorageSync: vi.fn((key: string, value: unknown) => storage.set(key, value)),
    removeStorageSync: vi.fn((key: string) => storage.delete(key)),
    getCurrentPages: vi.fn(() => [{ route: currentRoute }]),
    reLaunch: vi.fn(),
    navigateTo: vi.fn(),
    navigateBack: vi.fn(),
    redirectTo: vi.fn(),
    showModal: vi.fn(async () => ({ confirm: true, cancel: false })),
    setKeepScreenOn: vi.fn(() => Promise.resolve()),
    saveFile: vi.fn(),
    getVideoInfo: vi.fn(),
    getFileInfo: vi.fn(),
    compressVideo: vi.fn(),
    createCameraContext: vi.fn(() => ({
      startRecord: vi.fn((options) => options.success?.()),
      stopRecord: vi.fn((options) => options.success?.({ tempVideoPath: 'wxfile://temp/stop.mp4' }))
    })),
    createVideoContext: vi.fn(() => ({ play: vi.fn() })),
    createInnerAudioContext: vi.fn(),
    getFileSystemManager: vi.fn(() => ({
      getSavedFileList: getSavedFileListMock,
      removeSavedFile: removeSavedFileMock,
      unlink: unlinkMock
    }))
  }

  return {
    storage,
    showCallbacks,
    hideCallbacks,
    routerParams,
    taroMock,
    unlinkMock,
    getSavedFileListMock,
    removeSavedFileMock,
    reset() {
      storage.clear()
      showCallbacks.length = 0
      hideCallbacks.length = 0
      routerParams.actionId = '42'
      currentRoute = 'pages/home/index'
      Object.values(taroMock).forEach((value) => {
        if (typeof value === 'function' && 'mockClear' in value) value.mockClear()
      })
      unlinkMock.mockClear()
      getSavedFileListMock.mockClear()
      removeSavedFileMock.mockClear()
    },
    setCurrentRoute(route: string) {
      currentRoute = route
    }
  }
})

const alertPlayerHarness = vi.hoisted(() => ({
  play: vi.fn(async () => true),
  dispose: vi.fn()
}))

const requestMock = vi.hoisted(() => vi.fn())
const apiMocks = vi.hoisted(() => ({
  createVideoSession: vi.fn(),
  getVideoSessionStatus: vi.fn(),
  uploadVideoSegment: vi.fn(),
  finalizeVideoSession: vi.fn()
}))
const retryMocks = vi.hoisted(() => ({
  resetRetryWindowForLaunch: vi.fn(),
  startPendingGameUploadRetryLoop: vi.fn(),
  loadPendingGameUpload: vi.fn(),
  subscribePendingGameUploadRetryLoop: vi.fn(() => vi.fn()),
  tryUploadPendingGameRecord: vi.fn()
}))
const recorderHarness = vi.hoisted(() => {
  let nextStartPromise: Promise<void> | null = null
  let nextFinishError: Error | null = null
  const instances: Array<{
    start: ReturnType<typeof vi.fn>
    pause: ReturnType<typeof vi.fn>
    finish: ReturnType<typeof vi.fn>
    hasFailedSegment: ReturnType<typeof vi.fn>
    retryFailedSegment: ReturnType<typeof vi.fn>
    abandonFailedSegment: ReturnType<typeof vi.fn>
    options: {
      maxDurationMs?: number
      onMaxDuration?: (cutoffMs: number) => void
      onSegment: (path: string, durationMs: number) => Promise<void> | void
    }
  }> = []

  class MockShoulderPressRecorder {
    start = vi.fn(() => {
      const pending = nextStartPromise
      nextStartPromise = null
      return pending ?? Promise.resolve()
    })
    pause = vi.fn(async () => null)
    finish = vi.fn(async () => {
      const error = nextFinishError
      nextFinishError = null
      if (error) throw error
      return []
    })
    hasFailedSegment = vi.fn(() => false)
    retryFailedSegment = vi.fn(async () => null)
    abandonFailedSegment = vi.fn(() => null)
    options: {
      maxDurationMs?: number
      onMaxDuration?: (cutoffMs: number) => void
      onSegment: (path: string, durationMs: number) => Promise<void> | void
    }

    constructor(options: {
      maxDurationMs?: number
      onMaxDuration?: (cutoffMs: number) => void
      onSegment: (path: string, durationMs: number) => Promise<void> | void
    }) {
      this.options = options
      instances.push(this)
    }
  }

  return {
    instances,
    MockShoulderPressRecorder,
    reset() {
      instances.length = 0
      nextStartPromise = null
      nextFinishError = null
    },
    setNextStartPromise(promise: Promise<void>) {
      nextStartPromise = promise
    },
    setNextFinishError(error: Error) {
      nextFinishError = error
    }
  }
})

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    useEffect: reactHarness.useEffect,
    useRef: reactHarness.useRef,
    useState: reactHarness.useState
  }
})

vi.mock('@tarojs/components', () => ({
  Button: 'Button',
  Camera: 'Camera',
  Text: 'Text',
  Video: 'Video',
  View: 'View'
}))

vi.mock('@tarojs/taro', () => ({
  default: taroHarness.taroMock,
  useRouter: () => ({ params: taroHarness.routerParams }),
  useDidShow: (callback: () => unknown) => {
    taroHarness.showCallbacks.push(callback)
  },
  useDidHide: (callback: () => unknown) => {
    taroHarness.hideCallbacks.push(callback)
  }
}))

vi.mock('../../api/client', () => ({ request: requestMock }))
vi.mock('../game-session/retryUpload', () => retryMocks)
vi.mock('./api', () => apiMocks)
vi.mock('./recorder', () => ({ ShoulderPressRecorder: recorderHarness.MockShoulderPressRecorder }))
vi.mock('./alertAudio', () => ({
  createShoulderPressAlertPlayer: () => alertPlayerHarness,
  SHOULDER_PRESS_ALERT_TEXT: {
    pause: '网络较慢，训练已暂停，请保持页面打开，等待视频上传。',
    ready: '视频上传已恢复，可以继续训练。'
  }
}))

import App from '../../app'
import HomePage from '../home'
import PrescriptionPage from '../prescription'
import {
  clearCurrentPrescriptionCache,
  readCurrentPrescriptionCache,
  writeCurrentPrescriptionCache
} from '../prescription/cache'
import ShoulderPressCameraPage from './camera'
import ShoulderPressGuidePage from './index'
import ShoulderPressPreviewPage from './preview'
import { ShoulderPressTrainingOverlay } from './trainingOverlay'
import ShoulderPressUploadPage from './upload'

const PRESCRIPTION = {
  id: 1,
  version: 1,
  status: 'active',
  effective_at: '2026-07-10T00:00:00+08:00',
  week_start: '2026-07-06',
  week_end: '2026-07-12',
  actions: [{
    id: 42,
    action_library_item: 9,
    source_key: 'motion-resistance-shoulder-press',
    action_name: '肩部推举',
    training_type: '抗阻训练',
    internal_type: 'motion',
    action_type: '抗阻训练',
    action_instruction: '保持正面，缓慢推举。',
    video_url: 'https://cdn.example.com/demo.mp4',
    has_ai_supervision: true,
    weekly_frequency: '3',
    duration_minutes: 2,
    weekly_target_count: 3,
    weekly_completed_count: 0,
    difficulty: '简单',
    notes: '',
    sort_order: 1,
    recent_record: null
  }]
}

function pendingSession(segmentCount = 2) {
  return {
    clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
    videoId: 9,
    actionId: 42,
    trainingDate: '2026-07-11',
    expectedDurationSeconds: 120,
    actualDurationMs: 30_000 * segmentCount,
    finalized: false,
    createdAt: 1783692000000,
    trainingStartedAt: '2026-07-11T09:32:14+08:00',
    trainingEndedAt: '2026-07-11T09:41:27+08:00',
    segments: Array.from({ length: segmentCount }, (_, index) => ({
      index,
      compressionState: 'compressed' as const,
      savedFilePath: `wxfile://store/segment-${index}.mp4`,
      durationMs: 30_000,
      sizeBytes: 1024,
      uploadState: 'pending' as const
    }))
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
}

async function flushPromises(times = 8) {
  for (let index = 0; index < times; index += 1) {
    await Promise.resolve()
  }
}

function renderPage<T>(Component: (props?: T) => ReactElement, props?: T) {
  const render = () => {
    reactHarness.beginRender()
    const element = Component(props)
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
    }
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

function findButtonByText(node: unknown, text: string): ReactElement {
  const button = findAll(node, (element) => element.type === 'Button' && textContent(element).includes(text))[0]
  if (!button) throw new Error(`Button not found: ${text}; rendered: ${textContent(node)}`)
  return button
}

function clickButtonByText(node: unknown, text: string) {
  const onClick = findButtonByText(node, text).props.onClick
  if (typeof onClick === 'function') onClick()
}

function initializeCamera(node: unknown) {
  const onInitDone = findFirstByType(node, 'Camera').props.onInitDone
  if (typeof onInitDone === 'function') onInitDone()
}

function findFirstByType(node: unknown, type: string): ReactElement {
  const element = findAll(node, (item) => item.type === type)[0]
  if (!element) throw new Error(`Element not found: ${type}`)
  return element
}

function findTrainingOverlay(node: unknown): ReactElement {
  const overlay = findAll(node, (element) => (
    element.type === (ShoulderPressTrainingOverlay as unknown as string)
  ))[0]
  if (!overlay) throw new Error('Training overlay not found')
  return overlay
}

function saveStorageSession(session: unknown) {
  taroHarness.storage.set(PENDING_SHOULDER_PRESS_SESSION_KEY, session)
}

beforeEach(async () => {
  vi.useRealTimers()
  await flushPromises(50)
  vi.clearAllMocks()
  reactHarness.reset()
  taroHarness.reset()
  recorderHarness.reset()
  clearCurrentPrescriptionCache()
  requestMock.mockResolvedValue(PRESCRIPTION)
  retryMocks.loadPendingGameUpload.mockReturnValue(null)
  retryMocks.tryUploadPendingGameRecord.mockResolvedValue('idle')
  apiMocks.createVideoSession.mockResolvedValue({ video_id: 9, status: 'recording', uploaded_segments: [] })
  apiMocks.getVideoSessionStatus.mockResolvedValue({ video_id: 9, status: 'recording', uploaded_segments: [] })
  apiMocks.uploadVideoSegment.mockImplementation(async (input) => ({ index: input.index, sha256: `sha-${input.index}` }))
  apiMocks.finalizeVideoSession.mockResolvedValue({ video_id: 9, status: 'queued', assembly_job_id: 9 })
  taroHarness.taroMock.saveFile.mockImplementation(async ({ tempFilePath }) => ({
    savedFilePath: tempFilePath.includes('compressed')
      ? `wxfile://store/${tempFilePath.split('/').at(-1)}`
      : `wxfile://store/raw-${tempFilePath.split('/').at(-1)}`
  }))
  taroHarness.taroMock.getVideoInfo.mockImplementation(async ({ src }) => ({
    duration: 30,
    size: src.includes('compressed') ? 1024 : 2048,
    width: src.includes('compressed') ? 720 : 1080,
    height: src.includes('compressed') ? 1280 : 1920
  }))
  taroHarness.taroMock.getFileInfo.mockResolvedValue({ size: 19_876_543 })
  taroHarness.taroMock.compressVideo.mockImplementation(async ({ src }) => ({
    tempFilePath: `wxfile://temp/compressed-${src.split('/').at(-1)}`,
    size: 1024
  }))
})

afterEach(async () => {
  await flushPromises(50)
  taroHarness.storage.clear()
  vi.useRealTimers()
})

describe('shoulder press pages', () => {
  it('writes the home prescription response into the process cache', async () => {
    requestMock.mockResolvedValueOnce({
      patient: { name: '王阿姨' },
      project: { name: '康复研究' },
      current_prescription: PRESCRIPTION
    })

    renderPage(HomePage)
    await taroHarness.showCallbacks[0]()
    await flushPromises()

    expect(readCurrentPrescriptionCache()).toBe(PRESCRIPTION)
  })

  it('renders a cached prescription immediately while refreshing in the background', async () => {
    writeCurrentPrescriptionCache(PRESCRIPTION)
    const refresh = deferred<typeof PRESCRIPTION>()
    requestMock.mockReturnValueOnce(refresh.promise)

    const page = renderPage(PrescriptionPage)

    expect(textContent(page.element)).toContain('肩部推举')
    expect(textContent(page.element)).not.toContain('正在加载当前处方')

    await taroHarness.showCallbacks[0]()
    refresh.resolve({
      ...PRESCRIPTION,
      version: 2,
      actions: [{ ...PRESCRIPTION.actions[0], action_name: '肩部推举（更新）' }]
    })
    await flushPromises()
    page.rerender()

    expect(textContent(page.element)).toContain('肩部推举（更新）')
    expect(textContent(page.element)).toContain('当前处方 v2')
  })

  it('keeps cached actions visible when the background refresh fails', async () => {
    writeCurrentPrescriptionCache(PRESCRIPTION)
    requestMock.mockRejectedValueOnce(new Error('处方刷新失败'))

    const page = renderPage(PrescriptionPage)
    await taroHarness.showCallbacks[0]()
    await flushPromises()
    page.rerender()

    expect(textContent(page.element)).toContain('肩部推举')
    expect(textContent(page.element)).toContain('处方刷新失败')
    expect(textContent(page.element)).not.toContain('正在加载当前处方')
  })

  it('offers direct training and a separate muted looping preview', async () => {
    const guide = renderPage(ShoulderPressGuidePage)
    await flushPromises()
    guide.rerender()

    expect(findAll(guide.element, (element) => element.type === 'Video')).toHaveLength(0)
    expect(textContent(guide.element)).toContain('保持正面，缓慢推举。')
    findButtonByText(guide.element, '动作预览').props.onClick?.()
    expect(taroHarness.taroMock.navigateTo).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/preview?actionId=42'
    })

    findButtonByText(guide.element, '开始训练').props.onClick?.()

    expect(taroHarness.taroMock.navigateTo).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/camera?actionId=42'
    })

    reactHarness.reset()
    const preview = renderPage(ShoulderPressPreviewPage)
    await flushPromises()
    preview.rerender()
    const video = findFirstByType(preview.element, 'Video')
    expect(video.props).toMatchObject({
      src: 'https://cdn.example.com/demo.mp4',
      autoplay: true,
      loop: true,
      muted: true,
      controls: false
    })

    findButtonByText(preview.element, '关闭预览').props.onClick?.()
    expect(taroHarness.taroMock.navigateBack).toHaveBeenCalledTimes(1)
    findButtonByText(preview.element, '开始训练').props.onClick?.()
    expect(taroHarness.taroMock.redirectTo).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/camera?actionId=42'
    })
  })

  it('hides the preview entry when the action has no video url', async () => {
    requestMock.mockResolvedValueOnce({
      ...PRESCRIPTION,
      actions: [{ ...PRESCRIPTION.actions[0], video_url: null }]
    })
    const guide = renderPage(ShoulderPressGuidePage)
    await flushPromises()
    guide.rerender()

    expect(textContent(guide.element)).not.toContain('动作预览')
    expect(textContent(guide.element)).toContain('保持正面，缓慢推举。')
    expect(findButtonByText(guide.element, '开始训练')).toBeTruthy()
  })

  it('retries a failed preview without disabling training', async () => {
    const preview = renderPage(ShoulderPressPreviewPage)
    await flushPromises()
    preview.rerender()

    findFirstByType(preview.element, 'Video').props.onError?.()
    preview.rerender()

    expect(textContent(preview.element)).toContain('视频加载失败')
    expect(findButtonByText(preview.element, '开始训练')).toBeTruthy()
    clickButtonByText(preview.element, '重新加载')
    preview.rerender()

    expect(findFirstByType(preview.element, 'Video').props.src)
      .toBe('https://cdn.example.com/demo.mp4')
    expect(textContent(preview.element)).not.toContain('视频加载失败')
  })

  it('rejects a preview action that is no longer in the current prescription', async () => {
    requestMock.mockResolvedValueOnce({
      ...PRESCRIPTION,
      actions: [{ ...PRESCRIPTION.actions[0], source_key: 'motion-resistance-row' }]
    })
    const preview = renderPage(ShoulderPressPreviewPage)
    await flushPromises()
    preview.rerender()

    expect(findAll(preview.element, (element) => element.type === 'Video')).toHaveLength(0)
    expect(textContent(preview.element)).toContain('返回当前处方')
    expect(findButtonByText(preview.element, '返回当前处方')).toBeTruthy()
  })

  it('does not show the training timer before recording has started', () => {
    const overlay = renderPage(ShoulderPressTrainingOverlay, {
      videoUrl: 'https://cdn.example.com/demo.mp4',
      elapsedMs: 0,
      expectedDurationSeconds: 180,
      started: false
    })

    expect(findAll(overlay.element, (element) => (
      element.props.className === 'shoulder-training-timer'
    ))).toHaveLength(0)
    expect(findFirstByType(overlay.element, 'Video')).toBeTruthy()
  })

  it('disables native progress gestures on the swipeable training preview', () => {
    const overlay = renderPage(ShoulderPressTrainingOverlay, {
      videoUrl: 'https://cdn.example.com/demo.mp4',
      elapsedMs: 24_000,
      expectedDurationSeconds: 180,
      started: true
    })

    expect(findFirstByType(overlay.element, 'Video').props.enableProgressGesture).toBe(false)
  })

  it('keeps the timer fixed while the muted preview hides and restores', () => {
    const overlay = renderPage(ShoulderPressTrainingOverlay, {
      videoUrl: 'https://cdn.example.com/demo.mp4',
      elapsedMs: 24_000,
      expectedDurationSeconds: 180,
      started: true
    })

    expect(textContent(overlay.element)).toContain('已训练00:24')
    expect(textContent(overlay.element)).toContain('剩余02:36')
    const timerBefore = findAll(overlay.element, (element) => (
      element.props.className === 'shoulder-training-timer'
    ))[0]
    const preview = findFirstByType(overlay.element, 'Video')
    expect(preview.props).toMatchObject({ autoplay: true, loop: true, muted: true, controls: false })

    preview.props.onTouchStart?.({ touches: [{ clientX: 10, clientY: 10 }] })
    preview.props.onTouchEnd?.({ changedTouches: [{ clientX: 60, clientY: 12 }] })
    overlay.rerender()

    const hiddenPreview = findFirstByType(overlay.element, 'Video')
    expect(hiddenPreview.props.className).toContain('shoulder-training-preview-hidden')
    expect(hiddenPreview.props.onTouchStart).toBeUndefined()
    expect(hiddenPreview.props.onTouchEnd).toBeUndefined()
    expect(textContent(overlay.element)).toContain('向左滑恢复示范')
    const timerAfter = findAll(overlay.element, (element) => (
      element.props.className === 'shoulder-training-timer'
    ))[0]
    expect(timerAfter.props.className).toBe(timerBefore.props.className)

    const restore = findAll(overlay.element, (element) => (
      element.props.className === 'shoulder-training-preview-restore'
    ))[0]
    restore.props.onTouchStart?.({ touches: [{ clientX: 60, clientY: 12 }] })
    restore.props.onTouchEnd?.({ changedTouches: [{ clientX: 10, clientY: 10 }] })
    overlay.rerender()

    expect(findFirstByType(overlay.element, 'Video').props.className)
      .toBe('shoulder-training-preview')
    expect(textContent(overlay.element)).not.toContain('向左滑恢复示范')
  })

  it('degrades preview playback without changing timer content', () => {
    const overlay = renderPage(ShoulderPressTrainingOverlay, {
      videoUrl: 'https://cdn.example.com/demo.mp4',
      elapsedMs: 24_000,
      expectedDurationSeconds: 180,
      started: true
    })
    findFirstByType(overlay.element, 'Video').props.onError?.()
    overlay.rerender()

    expect(textContent(overlay.element)).toContain('示范视频暂时无法播放')
    expect(textContent(overlay.element)).toContain('已训练00:24')
    expect(textContent(overlay.element)).toContain('剩余02:36')
  })

  it('lets a failed preview slide away and restore without changing the timer', () => {
    const overlay = renderPage(ShoulderPressTrainingOverlay, {
      videoUrl: 'https://cdn.example.com/demo.mp4',
      elapsedMs: 24_000,
      expectedDurationSeconds: 180,
      started: true
    })
    findFirstByType(overlay.element, 'Video').props.onError?.()
    overlay.rerender()

    const errorPreview = findAll(overlay.element, (element) => (
      element.props.className === 'shoulder-training-preview-error'
    ))[0]
    errorPreview.props.onTouchStart?.({ touches: [{ clientX: 10, clientY: 10 }] })
    errorPreview.props.onTouchEnd?.({ changedTouches: [{ clientX: 60, clientY: 12 }] })
    overlay.rerender()

    const hiddenError = findAll(overlay.element, (element) => (
      String(element.props.className).includes('shoulder-training-preview-error')
    ))[0]
    expect(hiddenError.props.className).toContain('shoulder-training-preview-hidden')
    expect(hiddenError.props.onTouchStart).toBeUndefined()
    expect(hiddenError.props.onTouchEnd).toBeUndefined()
    expect(textContent(overlay.element)).toContain('向左滑恢复示范')
    expect(textContent(overlay.element)).toContain('已训练00:24')

    const restore = findAll(overlay.element, (element) => (
      element.props.className === 'shoulder-training-preview-restore'
    ))[0]
    restore.props.onTouchStart?.({ touches: [{ clientX: 60, clientY: 12 }] })
    restore.props.onTouchEnd?.({ changedTouches: [{ clientX: 10, clientY: 10 }] })
    overlay.rerender()

    expect(findAll(overlay.element, (element) => (
      element.props.className === 'shoulder-training-preview-error'
    ))).toHaveLength(1)
    expect(textContent(overlay.element)).not.toContain('向左滑恢复示范')
  })

  it('blocks first start until cleanup and the second storage listing finish at exactly 65MB free', async () => {
    vi.useFakeTimers()
    const before = deferred<Array<{ filePath: string; size: number }>>()
    const removed = deferred<void>()
    const after = deferred<Array<{ filePath: string; size: number }>>()
    taroHarness.getSavedFileListMock
      .mockImplementationOnce((options) => void before.promise.then((fileList) => options.success?.({ fileList })))
      .mockImplementationOnce((options) => void after.promise.then((fileList) => options.success?.({ fileList })))
    taroHarness.removeSavedFileMock
      .mockImplementationOnce((options) => void removed.promise.then(() => options.success?.()))
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()

    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    page.rerender()
    expect(textContent(page.element)).toContain('正在清理录像空间')
    expect(taroHarness.storage.has(PENDING_SHOULDER_PRESS_SESSION_KEY)).toBe(false)
    expect(recorderHarness.instances).toHaveLength(0)
    expect(vi.getTimerCount()).toBe(0)

    before.resolve([{ filePath: 'wxfile://store/old.mp4', size: 1 }])
    await flushPromises()
    expect(taroHarness.removeSavedFileMock).toHaveBeenCalledTimes(1)
    expect(recorderHarness.instances).toHaveLength(0)

    removed.resolve()
    await flushPromises()
    expect(taroHarness.getSavedFileListMock).toHaveBeenCalledTimes(2)
    expect(recorderHarness.instances).toHaveLength(0)

    after.resolve([{ filePath: 'wxfile://store/kept.mp4', size: 35 * 1024 * 1024 }])
    await flushPromises(20)
    expect(recorderHarness.instances[0].start).toHaveBeenCalledTimes(1)
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toHaveProperty(
      'trainingStartedAt'
    )
  })

  it('sends an existing local session straight to forced upload without file cleanup', async () => {
    saveStorageSession(pendingSession(1))

    renderPage(ShoulderPressCameraPage)
    await flushPromises()

    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/upload'
    })
    expect(taroHarness.getSavedFileListMock).not.toHaveBeenCalled()
    expect(taroHarness.removeSavedFileMock).not.toHaveBeenCalled()
  })

  it('blocks at one byte below 65MB free and returns to prescription without creating a session', async () => {
    taroHarness.getSavedFileListMock
      .mockImplementationOnce((options) => options.success?.({ fileList: [] }))
      .mockImplementationOnce((options) => options.success?.({
        fileList: [{
          filePath: 'wxfile://store/occupied.mp4',
          size: (35 * 1024 * 1024) + 1
        }]
      }))
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()

    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    page.rerender()

    expect(textContent(page.element)).toContain('录像空间不足，至少需要 65 MB 可用空间。')
    expect(findButtonByText(page.element, '重新清理')).toBeTruthy()
    expect(findButtonByText(page.element, '返回处方')).toBeTruthy()
    expect(taroHarness.storage.has(PENDING_SHOULDER_PRESS_SESSION_KEY)).toBe(false)
    expect(recorderHarness.instances).toHaveLength(0)

    clickButtonByText(page.element, '返回处方')
    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({
      url: '/pages/prescription/index'
    })
    expect(taroHarness.storage.has(PENDING_SHOULDER_PRESS_SESSION_KEY)).toBe(false)
  })

  it('runs one fresh preflight when retrying blocked storage', async () => {
    taroHarness.getSavedFileListMock
      .mockImplementationOnce((options) => options.success?.({ fileList: [] }))
      .mockImplementationOnce((options) => options.success?.({
        fileList: [{ filePath: 'wxfile://store/full.mp4', size: (35 * 1024 * 1024) + 1 }]
      }))
      .mockImplementationOnce((options) => options.success?.({ fileList: [] }))
      .mockImplementationOnce((options) => options.success?.({
        fileList: [{ filePath: 'wxfile://store/allowed.mp4', size: 35 * 1024 * 1024 }]
      }))
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    page.rerender()

    clickButtonByText(page.element, '重新清理')
    await flushPromises(20)

    expect(taroHarness.getSavedFileListMock).toHaveBeenCalledTimes(4)
    expect(recorderHarness.instances[0].start).toHaveBeenCalledTimes(1)
  })

  it('deduplicates repeated cleanup clicks and starts only once', async () => {
    const before = deferred<Array<{ filePath: string; size: number }>>()
    taroHarness.getSavedFileListMock
      .mockImplementationOnce((options) => void before.promise.then((fileList) => options.success?.({ fileList })))
      .mockImplementationOnce((options) => options.success?.({ fileList: [] }))
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()

    clickButtonByText(page.element, '开始训练')
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    expect(taroHarness.getSavedFileListMock).toHaveBeenCalledTimes(1)

    before.resolve([{ filePath: 'wxfile://store/old.mp4', size: 1024 }])
    await flushPromises(20)
    expect(taroHarness.getSavedFileListMock).toHaveBeenCalledTimes(2)
    expect(taroHarness.removeSavedFileMock).toHaveBeenCalledTimes(1)
    expect(recorderHarness.instances[0].start).toHaveBeenCalledTimes(1)
  })

  it('cancels an unresolved preflight after unmount without creating or starting anything', async () => {
    const before = deferred<Array<{ filePath: string; size: number }>>()
    taroHarness.getSavedFileListMock
      .mockImplementationOnce((options) => void before.promise.then((fileList) => options.success?.({ fileList })))
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    page.unmount()

    before.resolve([])
    await flushPromises(20)

    expect(taroHarness.removeSavedFileMock).not.toHaveBeenCalled()
    expect(taroHarness.storage.has(PENDING_SHOULDER_PRESS_SESSION_KEY)).toBe(false)
    expect(recorderHarness.instances).toHaveLength(0)
  })

  it('cancels an unresolved preflight after the page enters the background', async () => {
    const before = deferred<Array<{ filePath: string; size: number }>>()
    taroHarness.getSavedFileListMock
      .mockImplementationOnce((options) => void before.promise.then((fileList) => options.success?.({ fileList })))
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()

    await taroHarness.hideCallbacks[0]()
    before.resolve([])
    await flushPromises(20)

    expect(taroHarness.removeSavedFileMock).not.toHaveBeenCalled()
    expect(taroHarness.storage.has(PENDING_SHOULDER_PRESS_SESSION_KEY)).toBe(false)
    expect(recorderHarness.instances).toHaveLength(0)
  })

  it('does not persist a start time when the page hides while the recorder is starting', async () => {
    const starting = deferred<void>()
    recorderHarness.setNextStartPromise(starting.promise)
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises(20)

    expect(recorderHarness.instances[0].start).toHaveBeenCalledTimes(1)
    recorderHarness.instances[0].pause.mockImplementationOnce(async () => {
      await recorderHarness.instances[0].options.onSegment(
        'wxfile://temp/background-start.mp4',
        3_000
      )
      return null
    })
    await taroHarness.hideCallbacks[0]()
    starting.resolve()
    await flushPromises(20)

    expect(recorderHarness.instances[0].pause).toHaveBeenCalledTimes(1)
    expect(taroHarness.unlinkMock).toHaveBeenCalledWith(expect.objectContaining({
      filePath: 'wxfile://temp/background-start.mp4'
    }))
    expect(taroHarness.storage.has(PENDING_SHOULDER_PRESS_SESSION_KEY)).toBe(false)
  })

  it('pauses once at 65MB and only becomes manually resumable below 10MB', async () => {
    const upload0 = deferred<{ index: number; sha256: string }>()
    const upload1 = deferred<{ index: number; sha256: string }>()
    const upload2 = deferred<{ index: number; sha256: string }>()
    apiMocks.uploadVideoSegment
      .mockReturnValueOnce(upload0.promise)
      .mockReturnValueOnce(upload1.promise)
      .mockReturnValueOnce(upload2.promise)
    taroHarness.taroMock.getFileInfo
      .mockResolvedValueOnce({ size: 55 * 1024 * 1024 })
      .mockResolvedValueOnce({ size: 1 })
      .mockResolvedValueOnce({ size: (10 * 1024 * 1024) - 1 })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    const started = taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY) as PendingShoulderPressSession
    const recorder = recorderHarness.instances[0]

    await recorder.options.onSegment('wxfile://temp/0.mp4', 5_000)
    await recorder.options.onSegment('wxfile://temp/1.mp4', 5_000)
    await recorder.options.onSegment('wxfile://temp/2.mp4', 5_000)
    await flushPromises(20)
    page.rerender()

    expect(recorder.pause).toHaveBeenCalledTimes(1)
    expect(alertPlayerHarness.play).toHaveBeenCalledTimes(1)
    expect(alertPlayerHarness.play).toHaveBeenCalledWith('pause')
    expect(textContent(page.element)).toContain('网络较慢，训练已暂停，请保持页面打开，等待视频上传。')
    expect(apiMocks.uploadVideoSegment).toHaveBeenCalledTimes(1)

    upload0.resolve({ index: 0, sha256: 'sha-0' })
    await flushPromises(20)
    page.rerender()
    expect(textContent(page.element)).not.toContain('视频上传已恢复，可以继续训练。')
    expect(recorder.start).toHaveBeenCalledTimes(1)
    expect(apiMocks.uploadVideoSegment).toHaveBeenCalledTimes(2)

    upload1.resolve({ index: 1, sha256: 'sha-1' })
    await flushPromises(20)
    page.rerender()
    expect(textContent(page.element)).toContain('视频上传已恢复，可以继续训练。')
    expect(alertPlayerHarness.play).toHaveBeenCalledTimes(2)
    expect(alertPlayerHarness.play).toHaveBeenLastCalledWith('ready')
    expect(recorder.start).toHaveBeenCalledTimes(1)

    clickButtonByText(page.element, '继续训练')
    await flushPromises()
    expect(recorder.start).toHaveBeenCalledTimes(2)
    expect(taroHarness.getSavedFileListMock).toHaveBeenCalledTimes(2)
    expect((taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY) as PendingShoulderPressSession).clientSessionId)
      .toBe(started.clientSessionId)
    expect((taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY) as PendingShoulderPressSession).trainingStartedAt)
      .toBe(started.trainingStartedAt)

    upload2.resolve({ index: 2, sha256: 'sha-2' })
    await flushPromises(20)
  })

  it('stops both timers while buffer-paused and restarts them after manual continue', async () => {
    vi.useFakeTimers()
    const startAt = 1783692000000
    vi.setSystemTime(startAt)
    const upload = deferred<{ index: number; sha256: string }>()
    apiMocks.uploadVideoSegment.mockReturnValueOnce(upload.promise)
    taroHarness.taroMock.getVideoInfo.mockResolvedValueOnce({
      duration: 5,
      size: 65 * 1024 * 1024,
      width: 1080,
      height: 1920
    })
    taroHarness.taroMock.getFileInfo.mockResolvedValueOnce({ size: 65 * 1024 * 1024 })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(3_000)
    await recorderHarness.instances[0].options.onSegment('wxfile://temp/high.mp4', 5_000)
    await flushPromises(20)
    page.rerender()
    expect(findTrainingOverlay(page.element).props).toMatchObject({
      elapsedMs: 5_000,
      expectedDurationSeconds: 120
    })

    await vi.advanceTimersByTimeAsync(5_000)
    page.rerender()
    expect(findTrainingOverlay(page.element).props.elapsedMs).toBe(5_000)

    upload.resolve({ index: 0, sha256: 'sha-0' })
    await flushPromises(20)
    page.rerender()
    clickButtonByText(page.element, '继续训练')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2_000)
    page.rerender()
    expect(findTrainingOverlay(page.element).props.elapsedMs).toBe(7_000)
  })

  it('does not count or retry a server-confirmed segment when local deletion fails', async () => {
    taroHarness.unlinkMock.mockImplementationOnce((options) => options.fail?.({ errMsg: 'unlink failed' }))
    taroHarness.taroMock.getFileInfo.mockResolvedValueOnce({ size: 65 * 1024 * 1024 })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/confirmed.mp4', 5_000)
    await flushPromises(30)
    page.rerender()

    expect(taroHarness.unlinkMock).toHaveBeenCalledTimes(1)
    expect(apiMocks.uploadVideoSegment).toHaveBeenCalledTimes(1)
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(
      expect.objectContaining({
        segments: [expect.objectContaining({ uploadState: 'uploaded' })]
      })
    )
    expect(textContent(page.element)).toContain('视频上传已恢复，可以继续训练。')
  })

  it('deletes a local segment immediately when server session creation reports it uploaded', async () => {
    apiMocks.createVideoSession.mockResolvedValueOnce({
      video_id: 9,
      status: 'recording',
      uploaded_segments: [0]
    })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/server-known.mp4', 5_000)
    await flushPromises(30)

    expect(apiMocks.uploadVideoSegment).not.toHaveBeenCalled()
    expect(taroHarness.unlinkMock).toHaveBeenCalledWith(expect.objectContaining({
      filePath: 'wxfile://temp/server-known.mp4'
    }))
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(
      expect.objectContaining({
        segments: [expect.objectContaining({ uploadState: 'uploaded' })]
      })
    )
  })

  it('fails safe into buffer pause when local segment inspection fails', async () => {
    taroHarness.taroMock.getFileInfo.mockRejectedValueOnce(new Error('missing local file'))
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()

    await expect(
      recorderHarness.instances[0].options.onSegment('wxfile://temp/missing.mp4', 5_000)
    ).rejects.toThrow('missing local file')
    await flushPromises(20)
    page.rerender()

    expect(recorderHarness.instances[0].pause).toHaveBeenCalledTimes(1)
    expect(recorderHarness.instances[0].start).toHaveBeenCalledTimes(1)
    expect(textContent(page.element)).toContain('网络较慢，训练已暂停，请保持页面打开，等待视频上传。')
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toHaveProperty('trainingStartedAt')
  })

  it('persists an unreadable temporary segment and keeps the upload retry route available', async () => {
    taroHarness.taroMock.getFileInfo.mockRejectedValueOnce(new Error('missing local file info'))
    taroHarness.taroMock.getVideoInfo.mockResolvedValueOnce({
      duration: 5,
      size: 2048,
      width: 1080,
      height: 1920
    })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()

    await expect(
      recorderHarness.instances[0].options.onSegment('wxfile://temp/unknown-size.mp4', 5_000)
    ).rejects.toThrow('missing local file info')
    await flushPromises(20)
    page.rerender()

    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(
      expect.objectContaining({
        segments: [expect.objectContaining({
          compressionState: 'compression_failed',
          rawSavedFilePath: 'wxfile://temp/unknown-size.mp4',
          durationMs: 5_000
        })]
      })
    )
    expect(textContent(page.element)).toContain('网络较慢，训练已暂停，请保持页面打开，等待视频上传。')
    expect(findButtonByText(page.element, '结束训练')).toBeTruthy()

    clickButtonByText(page.element, '结束训练')
    await flushPromises(20)
    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/upload'
    })
  })

  it('fails safe into buffer pause when retry persistence cannot save the local segment', async () => {
    apiMocks.uploadVideoSegment.mockRejectedValueOnce(new Error('network unavailable'))
    taroHarness.taroMock.saveFile.mockRejectedValueOnce(new Error('storage full'))
    taroHarness.taroMock.getFileInfo.mockResolvedValueOnce({ size: 1024 })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/save-failed.mp4', 5_000)
    await flushPromises(30)
    page.rerender()

    expect(recorderHarness.instances[0].pause).toHaveBeenCalledTimes(1)
    expect(recorderHarness.instances[0].start).toHaveBeenCalledTimes(1)
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(
      expect.objectContaining({
        segments: [expect.objectContaining({
          savedFilePath: 'wxfile://temp/save-failed.mp4',
          localFileState: 'save_failed',
          uploadState: 'pending'
        })]
      })
    )
    expect(textContent(page.element)).toContain('网络较慢，训练已暂停，请保持页面打开，等待视频上传。')
  })

  it('keeps a small save-failed segment blocked until foreground retry uploads it', async () => {
    const retryUpload = deferred<{ index: number; sha256: string }>()
    apiMocks.uploadVideoSegment
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockReturnValueOnce(retryUpload.promise)
    taroHarness.taroMock.saveFile.mockRejectedValueOnce(new Error('storage full'))
    taroHarness.taroMock.getFileInfo.mockResolvedValueOnce({ size: 1024 })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/retry-on-show.mp4', 5_000)
    await flushPromises(30)
    page.rerender()
    expect(textContent(page.element)).toContain('网络较慢，训练已暂停，请保持页面打开，等待视频上传。')
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(
      expect.objectContaining({
        segments: [expect.objectContaining({
          savedFilePath: 'wxfile://temp/retry-on-show.mp4',
          localFileState: 'save_failed',
          uploadState: 'pending'
        })]
      })
    )

    await taroHarness.hideCallbacks[0]()
    await taroHarness.showCallbacks[0]()
    await flushPromises(20)
    page.rerender()

    const retryCallCount = apiMocks.uploadVideoSegment.mock.calls.length
    const textDuringRetry = textContent(page.element)

    retryUpload.resolve({ index: 0, sha256: 'sha-0' })
    await flushPromises(30)
    page.rerender()

    expect(retryCallCount).toBe(2)
    expect(textDuringRetry).toContain('网络较慢，训练已暂停，请保持页面打开，等待视频上传。')
    expect(textDuringRetry).not.toContain('视频上传已恢复，可以继续训练。')
    expect(textContent(page.element)).toContain('视频上传已恢复，可以继续训练。')
  })

  it('rechecks failed local state before continuing from buffer ready', async () => {
    const upload = deferred<{ index: number; sha256: string }>()
    apiMocks.uploadVideoSegment.mockReturnValueOnce(upload.promise)
    taroHarness.taroMock.getFileInfo.mockResolvedValueOnce({ size: 65 * 1024 * 1024 })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    await recorderHarness.instances[0].options.onSegment('wxfile://temp/late-failure.mp4', 5_000)
    await flushPromises(20)

    const pausedSession = taroHarness.storage.get(
      PENDING_SHOULDER_PRESS_SESSION_KEY
    ) as PendingShoulderPressSession
    saveStorageSession({
      ...pausedSession,
      segments: pausedSession.segments.map((segment) => ({
        ...segment,
        sizeBytes: 1024,
        localFileState: 'temporary' as const
      }))
    })
    await taroHarness.showCallbacks[0]()
    await flushPromises(20)
    page.rerender()
    expect(findButtonByText(page.element, '继续训练')).toBeTruthy()

    const readySession = taroHarness.storage.get(
      PENDING_SHOULDER_PRESS_SESSION_KEY
    ) as PendingShoulderPressSession
    saveStorageSession({
      ...readySession,
      segments: readySession.segments.map((segment) => ({
        ...segment,
        localFileState: 'save_failed' as const
      }))
    })
    clickButtonByText(page.element, '继续训练')
    await flushPromises(20)
    page.rerender()

    const startCallCount = recorderHarness.instances[0].start.mock.calls.length
    const textAfterContinue = textContent(page.element)

    upload.resolve({ index: 0, sha256: 'sha-0' })
    await flushPromises(20)

    expect(startCallCount).toBe(1)
    expect(textAfterContinue).toContain('网络较慢，训练已暂停，请保持页面打开，等待视频上传。')
  })

  it('recomputes a low buffer after background return without auto-resuming', async () => {
    const upload = deferred<{ index: number; sha256: string }>()
    apiMocks.uploadVideoSegment.mockReturnValueOnce(upload.promise)
    taroHarness.taroMock.getFileInfo.mockResolvedValueOnce({ size: 65 * 1024 * 1024 })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    await recorderHarness.instances[0].options.onSegment('wxfile://temp/background.mp4', 5_000)
    await flushPromises(20)
    await taroHarness.hideCallbacks[0]()
    await flushPromises()

    const stored = taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY) as PendingShoulderPressSession
    saveStorageSession({
      ...stored,
      segments: stored.segments.map((segment) => ({ ...segment, uploadState: 'uploaded' as const }))
    })
    await taroHarness.showCallbacks[0]()
    await flushPromises(20)
    page.rerender()

    expect(textContent(page.element)).toContain('视频上传已恢复，可以继续训练。')
    expect(recorderHarness.instances[0].start).toHaveBeenCalledTimes(1)

    upload.resolve({ index: 0, sha256: 'sha-0' })
    await flushPromises(20)
  })

  it('keeps buffer text and state when pause audio resolves false and ready audio rejects', async () => {
    const upload = deferred<{ index: number; sha256: string }>()
    apiMocks.uploadVideoSegment.mockReturnValueOnce(upload.promise)
    alertPlayerHarness.play
      .mockResolvedValueOnce(false)
      .mockRejectedValueOnce(new Error('audio unavailable'))
    taroHarness.taroMock.getFileInfo.mockResolvedValueOnce({ size: 65 * 1024 * 1024 })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    await recorderHarness.instances[0].options.onSegment('wxfile://temp/audio.mp4', 5_000)
    await flushPromises(20)
    page.rerender()
    expect(textContent(page.element)).toContain('网络较慢，训练已暂停，请保持页面打开，等待视频上传。')

    upload.resolve({ index: 0, sha256: 'sha-0' })
    await flushPromises(20)
    page.rerender()
    expect(textContent(page.element)).toContain('视频上传已恢复，可以继续训练。')
    expect(findButtonByText(page.element, '继续训练')).toBeTruthy()
  })

  it('keeps manual finish deduplicated while buffer-paused', async () => {
    const upload = deferred<{ index: number; sha256: string }>()
    apiMocks.uploadVideoSegment.mockReturnValueOnce(upload.promise)
    taroHarness.taroMock.getFileInfo.mockResolvedValueOnce({ size: 65 * 1024 * 1024 })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    await recorderHarness.instances[0].options.onSegment('wxfile://temp/finish-paused.mp4', 5_000)
    await flushPromises(20)
    page.rerender()

    clickButtonByText(page.element, '结束训练')
    clickButtonByText(page.element, '结束训练')
    await flushPromises(20)

    expect(taroHarness.taroMock.showModal).toHaveBeenCalledTimes(1)
    expect(recorderHarness.instances[0].finish).toHaveBeenCalledTimes(1)

    upload.resolve({ index: 0, sha256: 'sha-0' })
    await flushPromises(30)
  })

  it('renders the recording page as a fullscreen camera with overlay and fixed bottom action', async () => {
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()

    expect(page.element.props.className).toBe('training-camera-page')
    expect(findFirstByType(page.element, 'Camera').props.className).toBe('training-camera-fullscreen')
    expect(findAll(page.element, (element) => String(element.props.className ?? '').includes('page-hero')))
      .toHaveLength(0)
    expect(findAll(page.element, (element) => String(element.props.className ?? '').includes('recording-dashboard')))
      .toHaveLength(0)
    const overlay = findTrainingOverlay(page.element)
    expect(overlay.props).toMatchObject({
      started: false,
      videoUrl: 'https://cdn.example.com/demo.mp4',
      elapsedMs: 0,
      expectedDurationSeconds: 120
    })
    expect(findAll(page.element, (element) => element.props.className === 'training-camera-bottom-action'))
      .toHaveLength(1)
  })

  it('records with the low camera resolution and forty-minute safety boundary', async () => {
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()

    expect(findFirstByType(page.element, 'Camera').props.resolution).toBe('low')
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    expect(recorderHarness.instances[0].options.maxDurationMs).toBe(2_397_000)
  })

  it('completes recording and upload when the action has no preview video', async () => {
    requestMock.mockResolvedValueOnce({
      ...PRESCRIPTION,
      actions: [{ ...PRESCRIPTION.actions[0], video_url: null }]
    })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    await recorderHarness.instances[0].options.onSegment(
      'wxfile://temp/no-preview.mp4',
      30_000
    )
    await flushPromises()
    page.rerender()

    clickButtonByText(page.element, '结束训练')
    await flushPromises(20)

    expect(recorderHarness.instances[0].finish).toHaveBeenCalledTimes(1)
    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/upload'
    })
  })

  it('keeps the forced page until all segments and finalize succeed', async () => {
    saveStorageSession(pendingSession(2))
    const finalize = deferred<{ video_id: number; status: 'queued'; assembly_job_id: number }>()
    apiMocks.uploadVideoSegment
      .mockResolvedValueOnce({ index: 0, sha256: 'sha-0' })
      .mockResolvedValueOnce({ index: 1, sha256: 'sha-1' })
    apiMocks.finalizeVideoSession.mockReturnValueOnce(finalize.promise)

    renderPage(ShoulderPressUploadPage)
    await Promise.resolve()
    await taroHarness.showCallbacks[0]()
    await flushPromises()

    expect(apiMocks.uploadVideoSegment).toHaveBeenCalledTimes(2)
    expect(apiMocks.finalizeVideoSession).toHaveBeenCalledWith(
      expect.objectContaining({
        trainingEndedAt: '2026-07-11T09:41:27+08:00'
      })
    )
    expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()

    finalize.resolve({ video_id: 9, status: 'queued', assembly_job_id: 9 })
    await flushPromises()

    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({ url: '/pages/prescription/index' })
  })

  it('rejects a zero-segment recovery before file work or any video API call', async () => {
    saveStorageSession({
      ...pendingSession(0),
      videoId: undefined
    })

    const page = renderPage(ShoulderPressUploadPage)
    await taroHarness.showCallbacks[0]()
    await flushPromises()
    page.rerender()

    expect(taroHarness.taroMock.getFileInfo).not.toHaveBeenCalled()
    expect(apiMocks.createVideoSession).not.toHaveBeenCalled()
    expect(apiMocks.getVideoSessionStatus).not.toHaveBeenCalled()
    expect(apiMocks.uploadVideoSegment).not.toHaveBeenCalled()
    expect(apiMocks.finalizeVideoSession).not.toHaveBeenCalled()
    expect(textContent(page.element)).toContain('没有可上传的训练片段，请重新训练')
    expect(findButtonByText(page.element, '重新训练')).toBeTruthy()
  })

  it('pauses on page hide and requires a manual continue after returning', async () => {
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()

    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    const recorder = recorderHarness.instances[0]
    expect(recorder.start).toHaveBeenCalledTimes(1)

    await taroHarness.hideCallbacks[0]()
    await flushPromises()
    page.rerender()

    expect(recorder.pause).toHaveBeenCalledTimes(1)
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY))
      .not.toHaveProperty('trainingEndedAt')
    expect(textContent(page.element)).toContain('继续训练')
    expect(recorder.start).toHaveBeenCalledTimes(1)

    await taroHarness.showCallbacks[0]()
    findButtonByText(page.element, '继续训练').props.onClick?.()
    await flushPromises()

    expect(recorder.start).toHaveBeenCalledTimes(2)
  })

  it('auto finishes when the pause tail crosses the prescription duration', async () => {
    vi.useFakeTimers()
    const startAt = 1783692000000
    vi.setSystemTime(startAt)
    requestMock.mockResolvedValueOnce({
      ...PRESCRIPTION,
      actions: [{ ...PRESCRIPTION.actions[0], duration_minutes: 17 / 60 }]
    })
    taroHarness.taroMock.getVideoInfo
      .mockResolvedValueOnce({ duration: 15, size: 2048, width: 1080, height: 1920 })
      .mockResolvedValueOnce({ duration: 2.1, size: 2048, width: 1080, height: 1920 })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()

    const recorder = recorderHarness.instances[0]
    vi.setSystemTime(startAt + 15_000)
    await recorder.options.onSegment('wxfile://temp/segment-15s.mp4', 15_000)
    await flushPromises()
    recorder.pause.mockImplementationOnce(async () => {
      await recorder.options.onSegment('wxfile://temp/pause-tail.mp4', 2_100)
      return null
    })
    vi.setSystemTime(startAt + 17_100)
    await taroHarness.hideCallbacks[0]()
    await flushPromises(20)

    expect(taroHarness.taroMock.showModal).not.toHaveBeenCalled()
    expect(recorder.finish).toHaveBeenCalledTimes(1)
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toMatchObject({
      actualDurationMs: 17_100,
      trainingEndedAt: expect.any(String),
      segments: [{ durationMs: 15_000 }, { durationMs: 2_100 }]
    })
    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/upload'
    })
  })

  it('persists start only after recorder start succeeds and keeps it on resume', async () => {
    const timezoneOffset = vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-06T01:32:14Z'))
    const page = renderPage(ShoulderPressCameraPage)
    try {
      await flushPromises()
      page.rerender()
      findFirstByType(page.element, 'Camera').props.onInitDone?.()
      page.rerender()

      findButtonByText(page.element, '开始训练').props.onClick?.()
      await flushPromises()
      const started = taroHarness.storage.get(
        PENDING_SHOULDER_PRESS_SESSION_KEY
      ) as PendingShoulderPressSession | undefined
      expect(started).toBeDefined()
      expect(started?.trainingStartedAt).toBe('2026-08-06T09:32:14+08:00')

      await taroHarness.hideCallbacks[0]()
      await flushPromises()
      page.rerender()
      vi.setSystemTime(new Date('2026-08-06T01:35:00Z'))
      findButtonByText(page.element, '继续训练').props.onClick?.()
      await flushPromises()
      const resumed = taroHarness.storage.get(
        PENDING_SHOULDER_PRESS_SESSION_KEY
      ) as PendingShoulderPressSession | undefined
      expect(resumed?.trainingStartedAt).toBe(started?.trainingStartedAt)
    } finally {
      page.unmount()
      timezoneOffset.mockRestore()
    }
  })

  it('does not persist start when recorder start fails', async () => {
    const timezoneOffset = vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-06T01:32:14Z'))
    const page = renderPage(ShoulderPressCameraPage)
    try {
      await flushPromises()
      page.rerender()
      findFirstByType(page.element, 'Camera').props.onInitDone?.()
      page.rerender()

      const start = deferred<void>()
      recorderHarness.setNextStartPromise(start.promise)
      findButtonByText(page.element, '开始训练').props.onClick?.()
      start.reject(new Error('camera failed'))
      await flushPromises()

      expect(
        (taroHarness.storage.get(
          PENDING_SHOULDER_PRESS_SESSION_KEY
        ) as PendingShoulderPressSession | undefined)?.trainingStartedAt
      ).toBeUndefined()
    } finally {
      page.unmount()
      timezoneOffset.mockRestore()
    }
  })

  it('keeps the first start and recording controls when persistence and compensating stop both fail', async () => {
    const timezoneOffset = vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
    vi.useFakeTimers()
    const firstStartMs = new Date('2026-08-06T01:32:14Z').valueOf()
    vi.setSystemTime(firstStartMs)
    const page = renderPage(ShoulderPressCameraPage)
    try {
      await flushPromises()
      page.rerender()
      findFirstByType(page.element, 'Camera').props.onInitDone?.()
      page.rerender()

      taroHarness.taroMock.setStorageSync.mockImplementationOnce(() => {
        throw new Error('本地写入失败')
      })
      recorderHarness.setNextFinishError(new Error('录像停止失败，请稍后重试'))
      findButtonByText(page.element, '开始训练').props.onClick?.()
      await flushPromises()
      page.rerender()
      const recorder = recorderHarness.instances[0]

      expect(recorder.finish).toHaveBeenCalledTimes(1)
      expect(findTrainingOverlay(page.element).props.started).toBe(true)
      expect(findButtonByText(page.element, '结束训练')).toBeTruthy()

      vi.setSystemTime(new Date('2026-08-06T01:35:00Z'))
      await recorder.options.onSegment('wxfile://temp/retained-start.mp4', 15_000)
      await flushPromises()

      expect(
        (taroHarness.storage.get(
          PENDING_SHOULDER_PRESS_SESSION_KEY
        ) as PendingShoulderPressSession | undefined)?.trainingStartedAt
      ).toBe('2026-08-06T09:32:14+08:00')
    } finally {
      page.unmount()
      timezoneOffset.mockRestore()
    }
  })

  it('returns to a retryable non-recording state when compensating stop succeeds', async () => {
    const timezoneOffset = vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-06T01:32:14Z'))
    const page = renderPage(ShoulderPressCameraPage)
    try {
      await flushPromises()
      page.rerender()
      findFirstByType(page.element, 'Camera').props.onInitDone?.()
      page.rerender()

      taroHarness.taroMock.setStorageSync.mockImplementationOnce(() => {
        throw new Error('本地写入失败')
      })
      findButtonByText(page.element, '开始训练').props.onClick?.()
      await flushPromises()
      page.rerender()

      const recorder = recorderHarness.instances[0]
      expect(recorder.finish).toHaveBeenCalledTimes(1)
      expect(findButtonByText(page.element, '开始训练')).toBeTruthy()

      vi.setSystemTime(new Date('2026-08-06T01:35:00Z'))
      findButtonByText(page.element, '开始训练').props.onClick?.()
      await flushPromises()

      expect(recorder.start).toHaveBeenCalledTimes(2)
      expect(
        (taroHarness.storage.get(
          PENDING_SHOULDER_PRESS_SESSION_KEY
        ) as PendingShoulderPressSession | undefined)?.trainingStartedAt
      ).toBe('2026-08-06T09:32:14+08:00')
    } finally {
      page.unmount()
      timezoneOffset.mockRestore()
    }
  })

  it('allows an early manual finish only after confirmation', async () => {
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    page.rerender()

    const finishButton = findButtonByText(page.element, '结束训练')
    expect(finishButton.props.disabled).toBe(false)
    clickButtonByText(page.element, '结束训练')
    await flushPromises()

    expect(taroHarness.taroMock.showModal).toHaveBeenCalledWith(expect.objectContaining({
      title: '结束训练？',
      confirmText: '结束训练'
    }))
    expect(recorderHarness.instances[0].finish).toHaveBeenCalledTimes(1)
  })

  it('continues recording when the patient cancels manual finish', async () => {
    taroHarness.taroMock.showModal.mockResolvedValueOnce({ confirm: false, cancel: true })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    page.rerender()

    clickButtonByText(page.element, '结束训练')
    await flushPromises()

    expect(recorderHarness.instances[0].finish).not.toHaveBeenCalled()
    expect(findTrainingOverlay(page.element).props.started).toBe(true)
  })

  it('keeps recording and reports a non-blocking error when finish confirmation fails', async () => {
    taroHarness.taroMock.showModal.mockRejectedValueOnce(new Error('modal unavailable'))
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()
    page.rerender()

    clickButtonByText(page.element, '结束训练')
    await flushPromises()
    page.rerender()

    expect(recorderHarness.instances[0].finish).not.toHaveBeenCalled()
    expect(textContent(page.element)).toContain('结束确认失败，请继续训练或稍后重试')
    expect(findTrainingOverlay(page.element).props.started).toBe(true)
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY))
      .not.toHaveProperty('trainingEndedAt')

    clickButtonByText(page.element, '结束训练')
    await flushPromises()

    expect(taroHarness.taroMock.showModal).toHaveBeenCalledTimes(2)
    expect(recorderHarness.instances[0].finish).toHaveBeenCalledTimes(1)
  })

  it('does not stop recording while the manual finish confirmation is pending', async () => {
    const confirmation = deferred<{ confirm: boolean; cancel: boolean }>()
    taroHarness.taroMock.showModal.mockReturnValueOnce(confirmation.promise)
    const page = renderPage(ShoulderPressCameraPage)
    try {
      await flushPromises()
      page.rerender()
      initializeCamera(page.element)
      page.rerender()
      clickButtonByText(page.element, '开始训练')
      await flushPromises()
      page.rerender()

      clickButtonByText(page.element, '结束训练')
      await flushPromises()

      expect(taroHarness.taroMock.showModal).toHaveBeenCalledTimes(1)
      expect(recorderHarness.instances[0].finish).not.toHaveBeenCalled()
    } finally {
      confirmation.resolve({ confirm: false, cancel: true })
      await flushPromises()
      page.unmount()
    }
  })

  it('ignores a stale confirmation after automatic finish has completed', async () => {
    vi.useFakeTimers()
    const startAt = 1783692000000
    vi.setSystemTime(startAt)
    const confirmation = deferred<{ confirm: boolean; cancel: boolean }>()
    taroHarness.taroMock.showModal.mockReturnValueOnce(confirmation.promise)
    requestMock.mockResolvedValueOnce({
      ...PRESCRIPTION,
      actions: [{ ...PRESCRIPTION.actions[0], duration_minutes: 1 / 60 }]
    })
    const page = renderPage(ShoulderPressCameraPage)
    try {
      await flushPromises()
      page.rerender()
      initializeCamera(page.element)
      page.rerender()
      clickButtonByText(page.element, '开始训练')
      await flushPromises()
      await recorderHarness.instances[0].options.onSegment('wxfile://temp/automatic-finish.mp4', 1_000)
      await flushPromises()
      page.rerender()

      clickButtonByText(page.element, '结束训练')
      await flushPromises()
      expect(recorderHarness.instances[0].finish).not.toHaveBeenCalled()

      await vi.advanceTimersByTimeAsync(1_100)
      await flushPromises(20)
      expect(recorderHarness.instances[0].finish).toHaveBeenCalledTimes(1)
      expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledTimes(1)

      confirmation.resolve({ confirm: true, cancel: false })
      await flushPromises(20)

      expect(recorderHarness.instances[0].finish).toHaveBeenCalledTimes(1)
      expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledTimes(1)
    } finally {
      page.unmount()
    }
  })

  it('persists end before recorder finalization and upload work', async () => {
    const timezoneOffset = vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
    vi.useFakeTimers()
    const startAt = new Date('2026-08-06T01:32:14Z').valueOf()
    vi.setSystemTime(startAt)
    const finish = deferred<unknown[]>()
    const page = renderPage(ShoulderPressCameraPage)
    try {
      await flushPromises()
      page.rerender()
      findFirstByType(page.element, 'Camera').props.onInitDone?.()
      page.rerender()
      findButtonByText(page.element, '开始训练').props.onClick?.()
      await flushPromises()

      recorderHarness.instances[0].finish.mockReturnValueOnce(finish.promise)
      vi.setSystemTime(new Date('2026-08-06T01:41:27Z'))
      page.rerender()
      findButtonByText(page.element, '结束训练').props.onClick?.()
      await flushPromises()

      expect(recorderHarness.instances[0].finish).toHaveBeenCalledTimes(1)
      expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()
      const ended = taroHarness.storage.get(
        PENDING_SHOULDER_PRESS_SESSION_KEY
      ) as PendingShoulderPressSession | undefined
      expect(ended).toBeDefined()
      expect(ended?.trainingEndedAt).toBe('2026-08-06T09:41:27+08:00')
    } finally {
      finish.resolve([])
      await flushPromises()
      page.unmount()
      timezoneOffset.mockRestore()
    }
  })

  it('still stops and enters upload when the optional end timestamp cannot be persisted', async () => {
    const timezoneOffset = vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
    vi.useFakeTimers()
    const startAt = new Date('2026-08-06T01:32:14Z').valueOf()
    vi.setSystemTime(startAt)
    const page = renderPage(ShoulderPressCameraPage)
    try {
      await flushPromises()
      page.rerender()
      findFirstByType(page.element, 'Camera').props.onInitDone?.()
      page.rerender()
      findButtonByText(page.element, '开始训练').props.onClick?.()
      await flushPromises()

      await recorderHarness.instances[0].options.onSegment(
        'wxfile://temp/completed-before-end-write.mp4',
        30_000
      )
      await flushPromises(20)
      vi.setSystemTime(startAt + 120_000)
      page.rerender()
      taroHarness.taroMock.setStorageSync.mockImplementationOnce(() => {
        throw new Error('结束时间写入失败')
      })

      findButtonByText(page.element, '结束训练').props.onClick?.()
      await flushPromises(20)

      expect(recorderHarness.instances[0].finish).toHaveBeenCalledTimes(1)
      expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({
        url: '/pages/shoulder-press/upload'
      })
      expect(
        taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)
      ).not.toHaveProperty('trainingEndedAt')
    } finally {
      page.unmount()
      timezoneOffset.mockRestore()
    }
  })

  it('persists the recorder cutoff even when automatic completion runs later', async () => {
    const timezoneOffset = vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-06T01:32:14Z'))
    const page = renderPage(ShoulderPressCameraPage)
    try {
      await flushPromises()
      page.rerender()
      findFirstByType(page.element, 'Camera').props.onInitDone?.()
      page.rerender()
      findButtonByText(page.element, '开始训练').props.onClick?.()
      await flushPromises()

      const cutoffMs = new Date('2026-08-06T02:12:11Z').valueOf()
      vi.setSystemTime(new Date('2026-08-06T02:20:00Z'))
      recorderHarness.instances[0].options.onMaxDuration?.(cutoffMs)
      await flushPromises()

      expect(
        (taroHarness.storage.get(
          PENDING_SHOULDER_PRESS_SESSION_KEY
        ) as PendingShoulderPressSession | undefined)?.trainingEndedAt
      ).toBe('2026-08-06T10:12:11+08:00')
    } finally {
      page.unmount()
      timezoneOffset.mockRestore()
    }
  })

  it('keeps the screen awake only while shoulder-press recording is active', async () => {
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()

    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    expect(taroHarness.taroMock.setKeepScreenOn).toHaveBeenLastCalledWith({
      keepScreenOn: true
    })

    await taroHarness.hideCallbacks[0]()
    await flushPromises()
    page.rerender()

    expect(taroHarness.taroMock.setKeepScreenOn).toHaveBeenLastCalledWith({
      keepScreenOn: false
    })

    await taroHarness.showCallbacks[0]()
    findButtonByText(page.element, '继续训练').props.onClick?.()
    await flushPromises()
    expect(taroHarness.taroMock.setKeepScreenOn).toHaveBeenLastCalledWith({
      keepScreenOn: true
    })

    page.unmount()
    expect(taroHarness.taroMock.setKeepScreenOn).toHaveBeenLastCalledWith({
      keepScreenOn: false
    })
  })

  it('queues page-hide pause until an asynchronous start command settles', async () => {
    const start = deferred<void>()
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()

    recorderHarness.setNextStartPromise(start.promise)
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises(20)
    expect(recorderHarness.instances[0].start).toHaveBeenCalledTimes(1)
    await taroHarness.hideCallbacks[0]()
    start.resolve()
    await flushPromises()
    page.rerender()

    expect(recorderHarness.instances[0].pause).toHaveBeenCalledTimes(1)
    expect(textContent(page.element)).toContain('开始训练')
    expect(taroHarness.storage.has(PENDING_SHOULDER_PRESS_SESSION_KEY)).toBe(false)

    await taroHarness.showCallbacks[0]()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises(20)
    expect(recorderHarness.instances[0].start).toHaveBeenCalledTimes(2)
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toHaveProperty(
      'trainingStartedAt'
    )
  })

  it('uploads a raw camera segment without compression or persistent save', async () => {
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()
    const started = taroHarness.storage.get(
      PENDING_SHOULDER_PRESS_SESSION_KEY
    ) as PendingShoulderPressSession

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/raw.mp4', 15_000)
    await flushPromises(20)

    expect(taroHarness.taroMock.getVideoInfo).toHaveBeenCalledWith({ src: 'wxfile://temp/raw.mp4' })
    expect(taroHarness.taroMock.getFileInfo).toHaveBeenCalledWith({ filePath: 'wxfile://temp/raw.mp4' })
    expect(taroHarness.taroMock.saveFile).not.toHaveBeenCalled()
    expect(taroHarness.taroMock.compressVideo).not.toHaveBeenCalled()
    expect(taroHarness.taroMock.setStorageSync).toHaveBeenCalledWith(
      PENDING_SHOULDER_PRESS_SESSION_KEY,
      expect.objectContaining({
        segments: [expect.objectContaining({
          compressionState: 'compressed',
          savedFilePath: 'wxfile://temp/raw.mp4',
          sizeBytes: 19_876_543,
          localFileState: 'temporary'
        })]
      })
    )
    expect(apiMocks.uploadVideoSegment).toHaveBeenCalledWith(expect.objectContaining({
      filePath: 'wxfile://temp/raw.mp4',
      sizeBytes: 19_876_543
    }))
    expect(apiMocks.createVideoSession).toHaveBeenCalledWith(expect.objectContaining({
      trainingStartedAt: started.trainingStartedAt
    }))
    expect(taroHarness.unlinkMock).toHaveBeenCalledWith(expect.objectContaining({
      filePath: 'wxfile://temp/raw.mp4'
    }))
  })

  it('persists only the failed raw upload segment for retry', async () => {
    apiMocks.uploadVideoSegment.mockRejectedValueOnce(new Error('网络不可用'))
    taroHarness.taroMock.saveFile.mockResolvedValueOnce({
      savedFilePath: 'wxfile://store/failed-raw.mp4'
    })

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/failed-raw.mp4', 15_000)
    await flushPromises(20)

    expect(taroHarness.taroMock.saveFile).toHaveBeenCalledTimes(1)
    expect(taroHarness.taroMock.saveFile).toHaveBeenCalledWith({
      tempFilePath: 'wxfile://temp/failed-raw.mp4'
    })
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(
      expect.objectContaining({
        segments: [expect.objectContaining({
          savedFilePath: 'wxfile://store/failed-raw.mp4',
          localFileState: 'saved',
          uploadState: 'pending'
        })]
      })
    )
  })

  it('uploads a cold-start raw manifest without compression before creating the server session', async () => {
    saveStorageSession({
      ...pendingSession(1),
      videoId: undefined,
      segments: [{
        index: 0,
        compressionState: 'compression_failed',
        rawSavedFilePath: 'wxfile://store/cold-raw.mp4',
        durationMs: 30_000,
        compressionError: '上次压缩失败'
      }]
    })

    renderPage(ShoulderPressUploadPage)
    await taroHarness.showCallbacks[0]()
    await flushPromises(30)

    expect(taroHarness.taroMock.getFileInfo).toHaveBeenCalledWith({
      filePath: 'wxfile://store/cold-raw.mp4'
    })
    expect(taroHarness.taroMock.compressVideo).not.toHaveBeenCalled()
    expect(apiMocks.uploadVideoSegment).toHaveBeenCalledWith(expect.objectContaining({
      filePath: 'wxfile://store/cold-raw.mp4'
    }))
    expect(apiMocks.createVideoSession).toHaveBeenCalledWith(expect.objectContaining({
      trainingStartedAt: '2026-07-11T09:32:14+08:00'
    }))
  })

  it('reuses persisted training timestamps when retrying the upload page', async () => {
    saveStorageSession(pendingSession(1))
    apiMocks.finalizeVideoSession
      .mockRejectedValueOnce(new Error('网络不可用'))
      .mockResolvedValueOnce({ video_id: 9, status: 'queued', assembly_job_id: 9 })

    const page = renderPage(ShoulderPressUploadPage)
    await taroHarness.showCallbacks[0]()
    await flushPromises()
    page.rerender()

    findButtonByText(page.element, '重试上传').props.onClick?.()
    await flushPromises()

    expect(apiMocks.finalizeVideoSession.mock.calls).toHaveLength(2)
    expect(apiMocks.finalizeVideoSession.mock.calls.map(([input]) => (
      input.trainingEndedAt
    ))).toEqual([
      '2026-07-11T09:41:27+08:00',
      '2026-07-11T09:41:27+08:00'
    ])
  })

  it('uses the recorder duration when iOS reports zero duration for a closed segment', async () => {
    taroHarness.taroMock.getVideoInfo.mockResolvedValueOnce({ duration: 0, size: 1 })

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    await recorderHarness.instances[0].options.onSegment(
      'wxfile://temp/zero-duration.mp4',
      30_000
    )

    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(
      expect.objectContaining({
        actualDurationMs: 30_000,
        segments: [
          expect.objectContaining({
            durationMs: 30_000
          })
        ]
      })
    )
  })

  it('does not let a late segment save overwrite a newer client session manifest', async () => {
    const fileInfo = deferred<{ size: number }>()
    taroHarness.taroMock.getFileInfo.mockReturnValueOnce(fileInfo.promise)

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    const segmentPromise = recorderHarness.instances[0].options.onSegment('wxfile://temp/old.mp4', 30_000)
    await flushPromises()
    expect(taroHarness.taroMock.getFileInfo).toHaveBeenCalledWith({ filePath: 'wxfile://temp/old.mp4' })

    const newerSession = {
      ...pendingSession(1),
      clientSessionId: '9cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      segments: [{
        index: 0,
        savedFilePath: 'wxfile://store/newer-segment-0.mp4',
        durationMs: 30_000,
        sizeBytes: 1024,
        uploadState: 'pending' as const
      }]
    }
    saveStorageSession(newerSession)

    fileInfo.resolve({ size: 1024 })
    await segmentPromise
    await flushPromises()

    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(newerSession)
    expect(apiMocks.createVideoSession).not.toHaveBeenCalled()
    expect(apiMocks.uploadVideoSegment).not.toHaveBeenCalled()
  })

  it('does not resurrect a cleared manifest after the old page unmounts while saveFile is pending', async () => {
    const fileInfo = deferred<{ size: number }>()
    taroHarness.taroMock.getFileInfo.mockReturnValueOnce(fileInfo.promise)

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    const segmentPromise = recorderHarness.instances[0].options.onSegment('wxfile://temp/old-cleared.mp4', 30_000)
    await flushPromises()
    page.unmount()
    taroHarness.storage.delete(PENDING_SHOULDER_PRESS_SESSION_KEY)

    fileInfo.resolve({ size: 1024 })
    await segmentPromise
    await flushPromises()

    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toBeUndefined()
    expect(apiMocks.createVideoSession).not.toHaveBeenCalled()
    expect(apiMocks.uploadVideoSegment).not.toHaveBeenCalled()
    expect(taroHarness.unlinkMock).toHaveBeenCalledWith(
      expect.objectContaining({ filePath: 'wxfile://temp/old-cleared.mp4' })
    )
  })

  it('allows the active page to create the first manifest and append a later segment for the same client session', async () => {
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/owned-0.mp4', 30_000)
    await flushPromises()
    const firstSaved = taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY) as ReturnType<typeof pendingSession>

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/owned-1.mp4', 30_000)
    await flushPromises()
    const secondSaved = taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY) as ReturnType<typeof pendingSession>

    expect(firstSaved.clientSessionId).toBe(secondSaved.clientSessionId)
    expect(secondSaved.segments.map((segment) => segment.savedFilePath)).toEqual([
      'wxfile://temp/owned-0.mp4',
      'wxfile://temp/owned-1.mp4'
    ])
    expect(apiMocks.uploadVideoSegment.mock.calls.map(([input]) => input.index)).toEqual([0, 1])
  })

  it('runs one background segment upload at a time while recording', async () => {
    const upload0 = deferred<{ index: number; sha256: string }>()
    apiMocks.uploadVideoSegment
      .mockReturnValueOnce(upload0.promise)
      .mockResolvedValueOnce({ index: 1, sha256: 'sha-1' })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    const recorder = recorderHarness.instances[0]
    await recorder.options.onSegment('wxfile://temp/0.mp4', 30_000)
    await recorder.options.onSegment('wxfile://temp/1.mp4', 30_000)
    await flushPromises()

    expect(apiMocks.uploadVideoSegment.mock.calls.map(([input]) => input.index)).toEqual([0])
    expect(apiMocks.finalizeVideoSession).not.toHaveBeenCalled()

    upload0.resolve({ index: 0, sha256: 'sha-0' })
    await flushPromises()

    expect(apiMocks.uploadVideoSegment.mock.calls.map(([input]) => input.index)).toEqual([0, 1])
    await flushPromises(20)
  })

  it('serializes concurrent onSegment saves so delayed first save cannot overwrite segment indexes', async () => {
    const firstInfo = deferred<{ size: number }>()
    const events: string[] = []
    let firstInfoPending = true
    taroHarness.taroMock.getFileInfo.mockImplementation(async (input) => {
      events.push(`info-start:${input.filePath}`)
      if (firstInfoPending && input.filePath === 'wxfile://temp/0.mp4') {
        firstInfoPending = false
        const result = await firstInfo.promise
        events.push(`info-done:${input.filePath}`)
        return result
      }
      events.push(`info-done:${input.filePath}`)
      return { size: 2048 }
    })

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    const recorder = recorderHarness.instances[0]
    const first = recorder.options.onSegment('wxfile://temp/0.mp4', 30_000)
    const second = recorder.options.onSegment('wxfile://temp/1.mp4', 30_000)
    await flushPromises()

    expect(events).toEqual(['info-start:wxfile://temp/0.mp4'])

    firstInfo.resolve({ size: 1024 })
    await Promise.all([first, second])
    await flushPromises()

    const saved = taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY) as ReturnType<typeof pendingSession>
    expect(events).toEqual([
      'info-start:wxfile://temp/0.mp4',
      'info-done:wxfile://temp/0.mp4',
      'info-start:wxfile://temp/1.mp4',
      'info-done:wxfile://temp/1.mp4'
    ])
    expect(saved.segments.map((segment) => segment.index)).toEqual([0, 1])
    expect(saved.segments.map((segment) => segment.savedFilePath)).toEqual([
      'wxfile://temp/0.mp4',
      'wxfile://temp/1.mp4'
    ])
    await flushPromises(20)
  })

  it('waits for the current background segment upload before finish relaunches the forced page', async () => {
    vi.useFakeTimers()
    const startAt = 1783692000000
    vi.setSystemTime(startAt)
    const upload = deferred<{ index: number; sha256: string }>()
    const events: string[] = []
    requestMock.mockResolvedValueOnce({
      ...PRESCRIPTION,
      actions: [{ ...PRESCRIPTION.actions[0], duration_minutes: 0.5 }]
    })
    apiMocks.uploadVideoSegment.mockImplementationOnce((input) => {
      events.push(`upload:${input.index}`)
      return upload.promise
    })

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/0.mp4', 30_000)
    await flushPromises()
    vi.setSystemTime(startAt + 30_000)
    page.rerender()
    expect(events).toEqual(['upload:0'])

    findButtonByText(page.element, '结束训练').props.onClick?.()
    await flushPromises()

    try {
      expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()
    } finally {
      upload.resolve({ index: 0, sha256: 'sha-0' })
      await flushPromises(30)
    }

    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({ url: '/pages/shoulder-press/upload' })
    expect(taroHarness.taroMock.setKeepScreenOn).toHaveBeenLastCalledWith({
      keepScreenOn: false
    })
  })

  it('does not let a late old background upload rewrite the manifest after forced finalize clears it', async () => {
    const oldUpload = deferred<{ index: number; sha256: string }>()
    const events: string[] = []
    apiMocks.uploadVideoSegment.mockImplementation((input) => {
      events.push(`upload:${input.index}:${events.length}`)
      if (events.length === 1) return oldUpload.promise
      return Promise.resolve({ index: input.index, sha256: `sha-${input.index}` })
    })

    const trainingPage = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    trainingPage.rerender()
    findFirstByType(trainingPage.element, 'Camera').props.onInitDone?.()
    trainingPage.rerender()
    findButtonByText(trainingPage.element, '开始训练').props.onClick?.()
    await flushPromises()
    await recorderHarness.instances[0].options.onSegment('wxfile://temp/0.mp4', 30_000)
    await flushPromises()
    expect(events).toEqual(['upload:0:0'])

    reactHarness.reset()
    taroHarness.showCallbacks.length = 0
    renderPage(ShoulderPressUploadPage)
    await taroHarness.showCallbacks[0]()
    await flushPromises()

    expect(events).toEqual(['upload:0:0', 'upload:0:1'])
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toBeUndefined()

    oldUpload.resolve({ index: 0, sha256: 'old-sha-0' })
    await flushPromises()

    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toBeUndefined()
  })

  it('redirects on app cold start before ordinary retry work when a manifest is pending', async () => {
    saveStorageSession(pendingSession(1))

    renderPage(App, { children: null })
    await taroHarness.showCallbacks[0]()
    await flushPromises()

    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({ url: '/pages/shoulder-press/upload' })
    expect(retryMocks.resetRetryWindowForLaunch).not.toHaveBeenCalled()
    expect(retryMocks.startPendingGameUploadRetryLoop).not.toHaveBeenCalled()
  })

  it('keeps the active camera session on app foreground after page-hide pause', async () => {
    taroHarness.setCurrentRoute('pages/shoulder-press/camera')
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    initializeCamera(page.element)
    page.rerender()
    clickButtonByText(page.element, '开始训练')
    await flushPromises()

    await taroHarness.hideCallbacks[0]()
    await flushPromises()
    page.rerender()
    expect(textContent(page.element)).toContain('继续训练')
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY))
      .not.toHaveProperty('trainingEndedAt')

    renderPage(App, { children: null })
    await taroHarness.showCallbacks[0]()
    await flushPromises()

    expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()
    expect(retryMocks.resetRetryWindowForLaunch).not.toHaveBeenCalled()
    expect(retryMocks.startPendingGameUploadRetryLoop).not.toHaveBeenCalled()

    page.rerender()
    clickButtonByText(page.element, '继续训练')
    await flushPromises()
    expect(recorderHarness.instances[0].start).toHaveBeenCalledTimes(2)
  })

  it('still sends a cold residual session from camera bootstrap to forced upload', async () => {
    saveStorageSession(pendingSession(1))
    taroHarness.setCurrentRoute('pages/shoulder-press/camera')

    renderPage(ShoulderPressCameraPage)
    await flushPromises()

    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/upload'
    })
    expect(requestMock).not.toHaveBeenCalled()
  })

  it('does not relaunch the forced upload page when app show already happens on that route', async () => {
    saveStorageSession(pendingSession(1))
    taroHarness.setCurrentRoute('pages/shoulder-press/upload')

    renderPage(App, { children: null })
    await taroHarness.showCallbacks[0]()
    await flushPromises()

    expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()
    expect(retryMocks.resetRetryWindowForLaunch).not.toHaveBeenCalled()
    expect(retryMocks.startPendingGameUploadRetryLoop).not.toHaveBeenCalled()
  })

  it('does not pause on page hide while finish is already in flight', async () => {
    vi.useFakeTimers()
    const startAt = 1783692000000
    vi.setSystemTime(startAt)
    const finish = deferred<unknown[]>()
    requestMock.mockResolvedValueOnce({
      ...PRESCRIPTION,
      actions: [{ ...PRESCRIPTION.actions[0], duration_minutes: 0.5 }]
    })

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()
    await recorderHarness.instances[0].options.onSegment('wxfile://temp/0.mp4', 30_000)
    await flushPromises()
    vi.setSystemTime(startAt + 30_000)
    page.rerender()

    recorderHarness.instances[0].finish.mockReturnValueOnce(finish.promise)
    findButtonByText(page.element, '结束训练').props.onClick?.()
    await flushPromises()
    await taroHarness.hideCallbacks[0]()
    await flushPromises()

    try {
      expect(recorderHarness.instances[0].finish).toHaveBeenCalledTimes(1)
      expect(recorderHarness.instances[0].pause).not.toHaveBeenCalled()
    } finally {
      finish.resolve([])
      await flushPromises()
    }
  })

  it('does not double count saved segment duration against the continuous recording anchor', async () => {
    vi.useFakeTimers()
    const startAt = 1783692000000
    vi.setSystemTime(startAt)
    requestMock.mockResolvedValueOnce({
      ...PRESCRIPTION,
      actions: [{ ...PRESCRIPTION.actions[0], duration_minutes: 1.5 }]
    })

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/0.mp4', 30_000)
    vi.setSystemTime(startAt + 60_000)
    await flushPromises()
    page.rerender()

    expect(findTrainingOverlay(page.element).props.elapsedMs).toBe(60_000)
    expect(findButtonByText(page.element, '结束训练').props.disabled).toBe(false)

    vi.setSystemTime(startAt + 90_000)
    page.rerender()

    expect(findButtonByText(page.element, '结束训练').props.disabled).toBe(false)
  })

  it('counts resume duration from the saved base after hide pause without gating manual finish', async () => {
    vi.useFakeTimers()
    const startAt = 1783692000000
    vi.setSystemTime(startAt)
    requestMock.mockResolvedValueOnce({
      ...PRESCRIPTION,
      actions: [{ ...PRESCRIPTION.actions[0], duration_minutes: 1 }]
    })

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/0.mp4', 30_000)
    await flushPromises()
    vi.setSystemTime(startAt + 35_000)
    await taroHarness.hideCallbacks[0]()
    await flushPromises()
    page.rerender()

    expect(textContent(page.element)).toContain('继续训练')

    vi.setSystemTime(startAt + 40_000)
    await taroHarness.showCallbacks[0]()
    findButtonByText(page.element, '继续训练').props.onClick?.()
    await flushPromises()

    vi.setSystemTime(startAt + 60_000)
    page.rerender()

    expect(findTrainingOverlay(page.element).props.elapsedMs).toBe(50_000)
    expect(findButtonByText(page.element, '结束训练').props.disabled).toBe(false)

    vi.setSystemTime(startAt + 70_000)
    page.rerender()

    expect(findTrainingOverlay(page.element).props.elapsedMs).toBe(60_000)
    expect(findButtonByText(page.element, '结束训练').props.disabled).toBe(false)
  })

  it('auto finishes once at the prescription duration without a confirmation', async () => {
    vi.useFakeTimers()
    const startAt = 1783692000000
    vi.setSystemTime(startAt)
    requestMock.mockResolvedValueOnce({
      ...PRESCRIPTION,
      actions: [{ ...PRESCRIPTION.actions[0], duration_minutes: 1 / 60 }]
    })

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()
    page.rerender()

    await vi.advanceTimersByTimeAsync(1_100)
    await flushPromises()

    expect(taroHarness.taroMock.showModal).not.toHaveBeenCalled()
    expect(recorderHarness.instances[0].finish).toHaveBeenCalledTimes(1)
  })

  it('stops at the safe boundary before 2400 seconds after automatic segment splits', async () => {
    vi.useFakeTimers()
    const startAt = 1783692000000
    vi.setSystemTime(startAt)
    requestMock.mockResolvedValueOnce({
      ...PRESCRIPTION,
      actions: [{ ...PRESCRIPTION.actions[0], duration_minutes: 45 }]
    })

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()
    page.rerender()

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/0.mp4', 30_000)
    await flushPromises()
    expect(apiMocks.createVideoSession).toHaveBeenCalledWith(
      expect.objectContaining({ expectedDurationSeconds: 2400 })
    )
    expect(recorderHarness.instances[0].options.maxDurationMs).toBe(2_397_000)

    vi.setSystemTime(startAt + 2_370_000)
    vi.advanceTimersByTime(1000)
    await flushPromises()

    expect(recorderHarness.instances[0].finish).not.toHaveBeenCalled()
    expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()

    vi.setSystemTime(startAt + 2_397_000)
    vi.advanceTimersByTime(1000)
    await flushPromises()

    expect(recorderHarness.instances[0].finish).toHaveBeenCalledTimes(1)
  })

  it('fails closed above 2400000ms and only enters forced upload after tail retry succeeds', async () => {
    vi.useFakeTimers()
    const startAt = 1783692000000
    vi.setSystemTime(startAt)
    requestMock.mockResolvedValueOnce({
      ...PRESCRIPTION,
      actions: [{ ...PRESCRIPTION.actions[0], duration_minutes: 45 }]
    })
    taroHarness.taroMock.getVideoInfo.mockImplementation(async ({ src }) => ({
      duration: src.includes('first-2370') ? 2370 : src.includes('final') ? 30.001 : 30,
      size: src.includes('compressed') ? 1 : 2,
      width: src.includes('compressed') ? 720 : 1080,
      height: src.includes('compressed') ? 1280 : 1920
    }))

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()
    const recorder = recorderHarness.instances[0]

    await recorder.options.onSegment('wxfile://temp/first-2370.mp4', 2_370_000)
    await expect(
      recorder.options.onSegment('wxfile://temp/final.mp4', 30_001)
    ).rejects.toThrow('录像总时长超过限制')
    recorder.hasFailedSegment.mockReturnValue(true)
    recorder.finish.mockRejectedValue(new Error('录像总时长超过限制，请重新录制'))
    vi.setSystemTime(startAt + 2_397_000)
    recorder.options.onMaxDuration?.(startAt + 2_397_000)
    await flushPromises()
    page.rerender()

    expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()
    expect(findButtonByText(page.element, '重试保存尾段')).toBeTruthy()
    expect(findButtonByText(page.element, '重新训练')).toBeTruthy()
    expect(taroHarness.unlinkMock.mock.calls.map(([options]) => options.filePath)).toEqual([
      'wxfile://temp/first-2370.mp4'
    ])

    vi.advanceTimersByTime(2_000)
    await flushPromises()
    expect(recorder.finish).toHaveBeenCalledTimes(1)

    taroHarness.taroMock.getVideoInfo.mockImplementation(async ({ src }) => ({
      duration: src.includes('first-2370') ? 2370 : src.includes('final') ? 27 : 30,
      size: src.includes('compressed') ? 1 : 2,
      width: src.includes('compressed') ? 720 : 1080,
      height: src.includes('compressed') ? 1280 : 1920
    }))
    recorder.retryFailedSegment.mockImplementationOnce(async () => {
      await recorder.options.onSegment('wxfile://temp/final.mp4', 27_000)
      recorder.hasFailedSegment.mockReturnValue(false)
      return { savedFilePath: 'wxfile://temp/final.mp4', durationMs: 27_000 }
    })
    await findButtonByText(page.element, '重试保存尾段').props.onClick?.()
    await flushPromises(20)

    expect(taroHarness.taroMock.compressVideo).not.toHaveBeenCalled()
    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/upload'
    })
  })

  it('fails closed when the raw segment size cannot be read', async () => {
    taroHarness.taroMock.getFileInfo.mockRejectedValue({
      errMsg: 'getFileInfo:fail tempFilePath file not exist'
    })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()
    await expect(
      recorderHarness.instances[0].options.onSegment('wxfile://temp/missing-size.mp4', 15_000)
    ).rejects.toThrow('getFileInfo:fail tempFilePath file not exist')
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(
      expect.objectContaining({
        segments: [expect.objectContaining({
          compressionState: 'compression_failed',
          rawSavedFilePath: 'wxfile://temp/missing-size.mp4',
          compressionError: expect.stringContaining('getFileInfo:fail tempFilePath file not exist')
        })],
        trainingStartedAt: expect.stringMatching(
          /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$/
        )
      })
    )
  })

  it('keeps the temporary path when failed-upload persistence exceeds WeChat storage', async () => {
    apiMocks.uploadVideoSegment.mockRejectedValueOnce(new Error('网络不可用'))
    taroHarness.taroMock.saveFile.mockResolvedValueOnce({
      errMsg: 'saveFile:fail the maximum size of the file storage limit is exceeded'
    })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    await recorderHarness.instances[0].options.onSegment(
      'wxfile://temp/storage-fallback.mp4',
      30_000
    )
    await flushPromises()

    expect(taroHarness.taroMock.getVideoInfo).toHaveBeenCalledWith({
      src: 'wxfile://temp/storage-fallback.mp4'
    })
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(
      expect.objectContaining({
        segments: [
          expect.objectContaining({
            compressionState: 'compressed',
            savedFilePath: 'wxfile://temp/storage-fallback.mp4',
            localFileState: 'save_failed',
            uploadState: 'pending'
          })
        ]
      })
    )
  })

  it('shows the native file errMsg when the temp recording is unreadable', async () => {
    taroHarness.taroMock.getFileInfo.mockRejectedValue({
      errMsg: 'getFileInfo:fail tempFilePath file not exist'
    })
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    await expect(
      recorderHarness.instances[0].options.onSegment(
        'wxfile://temp/missing.mp4',
        30_000
      )
    ).rejects.toThrow('getFileInfo:fail tempFilePath file not exist')
    page.rerender()

    expect(textContent(page.element)).toContain(
      'getFileInfo:fail tempFilePath file not exist'
    )
  })

  it('blocks the home page entry and redirects to forced upload when a shoulder press manifest is pending', async () => {
    saveStorageSession(pendingSession(1))

    renderPage(HomePage)
    await taroHarness.showCallbacks[0]()
    await flushPromises()

    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({ url: '/pages/shoulder-press/upload' })
    expect(requestMock).not.toHaveBeenCalledWith('/patient-app/home/')
    expect(retryMocks.tryUploadPendingGameRecord).not.toHaveBeenCalled()
  })

  it('tells patients failed uploads keep the local video before retry or retraining', async () => {
    saveStorageSession(pendingSession(1))
    apiMocks.finalizeVideoSession.mockResolvedValueOnce({ video_id: 9, status: 'failed', assembly_job_id: 9 })

    const page = renderPage(ShoulderPressUploadPage)
    await taroHarness.showCallbacks[0]()
    await flushPromises()
    page.rerender()

    expect(textContent(page.element)).toContain('本地视频仍保留')
  })

  it('best-effort deletes every saved segment before clearing a retrained manifest', async () => {
    saveStorageSession(pendingSession(2))
    apiMocks.finalizeVideoSession.mockResolvedValueOnce({
      video_id: 9,
      status: 'failed',
      assembly_job_id: 9
    })
    taroHarness.unlinkMock
      .mockImplementationOnce((options) => options.fail?.({ errMsg: 'unlink failed' }))
      .mockImplementationOnce((options) => options.success?.())

    const page = renderPage(ShoulderPressUploadPage)
    await taroHarness.showCallbacks[0]()
    await flushPromises()
    page.rerender()
    await findButtonByText(page.element, '重新训练').props.onClick?.()
    await flushPromises()

    expect(taroHarness.unlinkMock.mock.calls.map(([options]) => options.filePath)).toEqual([
      'wxfile://store/segment-0.mp4',
      'wxfile://store/segment-1.mp4'
    ])
    expect(taroHarness.storage.has(PENDING_SHOULDER_PRESS_SESSION_KEY)).toBe(false)
    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/index?actionId=42'
    })
  })

  it('uses the shoulder press dedicated route from the home continue action', async () => {
    requestMock.mockResolvedValueOnce({
      patient: { name: '王阿姨' },
      project: { name: '康复研究' },
      current_prescription: PRESCRIPTION
    })

    const page = renderPage(HomePage)
    await taroHarness.showCallbacks[0]()
    await flushPromises()
    page.rerender()

    clickButtonByText(page.element, '继续训练')

    expect(taroHarness.taroMock.navigateTo).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/index?actionId=42'
    })
  })
})
