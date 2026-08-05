import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PENDING_SHOULDER_PRESS_SESSION_KEY } from './session'

type ReactElement = {
  type: string
  props: Record<string, unknown> & { children?: unknown }
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
  const taroMock = {
    getStorageSync: vi.fn((key: string) => storage.get(key)),
    setStorageSync: vi.fn((key: string, value: unknown) => storage.set(key, value)),
    removeStorageSync: vi.fn((key: string) => storage.delete(key)),
    getCurrentPages: vi.fn(() => [{ route: currentRoute }]),
    reLaunch: vi.fn(),
    navigateTo: vi.fn(),
    setKeepScreenOn: vi.fn(() => Promise.resolve()),
    saveFile: vi.fn(),
    getVideoInfo: vi.fn(),
    compressVideo: vi.fn(),
    createCameraContext: vi.fn(() => ({
      startRecord: vi.fn((options) => options.success?.()),
      stopRecord: vi.fn((options) => options.success?.({ tempVideoPath: 'wxfile://temp/stop.mp4' }))
    })),
    createVideoContext: vi.fn(() => ({ play: vi.fn() })),
    getFileSystemManager: vi.fn(() => ({ unlink: unlinkMock }))
  }

  return {
    storage,
    showCallbacks,
    hideCallbacks,
    routerParams,
    taroMock,
    unlinkMock,
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
    },
    setCurrentRoute(route: string) {
      currentRoute = route
    }
  }
})

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
  const instances: Array<{
    start: ReturnType<typeof vi.fn>
    pause: ReturnType<typeof vi.fn>
    finish: ReturnType<typeof vi.fn>
    hasFailedSegment: ReturnType<typeof vi.fn>
    retryFailedSegment: ReturnType<typeof vi.fn>
    abandonFailedSegment: ReturnType<typeof vi.fn>
    options: {
      maxDurationMs?: number
      onMaxDuration?: () => void
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
    finish = vi.fn(async () => [])
    hasFailedSegment = vi.fn(() => false)
    retryFailedSegment = vi.fn(async () => null)
    abandonFailedSegment = vi.fn(() => null)
    options: {
      maxDurationMs?: number
      onMaxDuration?: () => void
      onSegment: (path: string, durationMs: number) => Promise<void> | void
    }

    constructor(options: {
      maxDurationMs?: number
      onMaxDuration?: () => void
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
    },
    setNextStartPromise(promise: Promise<void>) {
      nextStartPromise = promise
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

import App from '../../app'
import HomePage from '../home'
import ShoulderPressCameraPage from './camera'
import ShoulderPressGuidePage from './index'
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

function findFirstByType(node: unknown, type: string): ReactElement {
  const element = findAll(node, (item) => item.type === type)[0]
  if (!element) throw new Error(`Element not found: ${type}`)
  return element
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
  it('separates the example video from the native camera recording page', async () => {
    const page = renderPage(ShoulderPressGuidePage)
    await flushPromises()
    page.rerender()

    expect(findAll(page.element, (element) => element.type === 'Video')).toHaveLength(1)
    expect(findAll(page.element, (element) => element.type === 'Camera')).toHaveLength(0)

    findButtonByText(page.element, '进入摄像训练').props.onClick?.()

    expect(taroHarness.taroMock.navigateTo).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/camera?actionId=42'
    })
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
    expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()

    finalize.resolve({ video_id: 9, status: 'queued', assembly_job_id: 9 })
    await flushPromises()

    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({ url: '/pages/prescription/index' })
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
    expect(textContent(page.element)).toContain('继续训练')
    expect(recorder.start).toHaveBeenCalledTimes(1)

    findButtonByText(page.element, '继续训练').props.onClick?.()
    await flushPromises()

    expect(recorder.start).toHaveBeenCalledTimes(2)
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
    await taroHarness.hideCallbacks[0]()
    start.resolve()
    await flushPromises()
    page.rerender()

    expect(recorderHarness.instances[0].pause).toHaveBeenCalledTimes(1)
    expect(textContent(page.element)).toContain('继续训练')
  })

  it('persists pending compression after raw save and uploads only the persisted compressed file', async () => {
    const saveFile = deferred<{ savedFilePath: string }>()
    taroHarness.taroMock.saveFile.mockReturnValueOnce(saveFile.promise)
    const compression = deferred<{ tempFilePath: string; size: number }>()
    taroHarness.taroMock.compressVideo.mockReturnValueOnce(compression.promise)

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    const segmentPromise = recorderHarness.instances[0].options.onSegment('wxfile://temp/raw.mp4', 30_000)
    await flushPromises()
    expect(taroHarness.taroMock.setStorageSync).not.toHaveBeenCalled()

    saveFile.resolve({ savedFilePath: 'wxfile://store/segment-0.mp4' })
    await flushPromises()

    expect(taroHarness.taroMock.getVideoInfo).toHaveBeenCalledWith({ src: 'wxfile://store/segment-0.mp4' })
    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(
      expect.objectContaining({
        segments: [expect.objectContaining({
          compressionState: 'pending_compression',
          rawSavedFilePath: 'wxfile://store/segment-0.mp4'
        })]
      })
    )
    expect(apiMocks.createVideoSession).not.toHaveBeenCalled()

    compression.resolve({
      tempFilePath: 'wxfile://temp/compressed-segment-0.mp4',
      size: 1024
    })
    await segmentPromise
    await flushPromises(20)

    expect(taroHarness.taroMock.compressVideo).toHaveBeenCalledWith({
      src: 'wxfile://store/segment-0.mp4',
      bitrate: 2000,
      fps: 24,
      resolution: 2 / 3
    })
    expect(taroHarness.taroMock.setStorageSync).toHaveBeenCalledWith(
      PENDING_SHOULDER_PRESS_SESSION_KEY,
      expect.objectContaining({
        segments: [expect.objectContaining({
          compressionState: 'compressed',
          savedFilePath: 'wxfile://store/compressed-segment-0.mp4',
          sizeBytes: 1_048_576
        })]
      })
    )
    expect(apiMocks.uploadVideoSegment).toHaveBeenCalledWith(expect.objectContaining({
      filePath: 'wxfile://store/compressed-segment-0.mp4',
      sizeBytes: 1_048_576
    }))
    expect(taroHarness.unlinkMock).toHaveBeenCalledWith(expect.objectContaining({
      filePath: 'wxfile://store/segment-0.mp4'
    }))
    expect(taroHarness.unlinkMock).toHaveBeenCalledWith(expect.objectContaining({
      filePath: 'wxfile://store/compressed-segment-0.mp4'
    }))
  })

  it('keeps the iOS temporary raw path when saveFile fails and still compresses it', async () => {
    taroHarness.taroMock.saveFile.mockRejectedValueOnce(new Error('saveFile:fail temp path'))

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    await recorderHarness.instances[0].options.onSegment('wxfile://temp/ios-raw.mp4', 30_000)
    await flushPromises()

    expect(taroHarness.taroMock.compressVideo).toHaveBeenCalledWith(expect.objectContaining({
      src: 'wxfile://temp/ios-raw.mp4'
    }))
    expect(apiMocks.uploadVideoSegment).toHaveBeenCalledWith(expect.objectContaining({
      filePath: expect.stringContaining('compressed-ios-raw.mp4')
    }))
  })

  it('keeps the raw segment retryable and never uploads when compression fails', async () => {
    taroHarness.taroMock.compressVideo.mockRejectedValueOnce(new Error('compressVideo:fail'))

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    await expect(recorderHarness.instances[0].options.onSegment(
      'wxfile://temp/compression-failed.mp4',
      30_000
    )).rejects.toThrow('录像压缩失败，可重试')
    page.rerender()

    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(
      expect.objectContaining({
        segments: [expect.objectContaining({
          compressionState: 'compression_failed',
          rawSavedFilePath: expect.stringContaining('compression-failed.mp4')
        })]
      })
    )
    expect(apiMocks.createVideoSession).not.toHaveBeenCalled()
    expect(apiMocks.uploadVideoSegment).not.toHaveBeenCalled()
    expect(textContent(page.element)).toContain('录像压缩失败，可重试')
  })

  it('compresses a cold-start raw manifest before creating the server upload session', async () => {
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

    expect(taroHarness.taroMock.compressVideo).toHaveBeenCalledWith(expect.objectContaining({
      src: 'wxfile://store/cold-raw.mp4'
    }))
    expect(taroHarness.taroMock.compressVideo.mock.invocationCallOrder[0])
      .toBeLessThan(apiMocks.createVideoSession.mock.invocationCallOrder[0])
    expect(apiMocks.uploadVideoSegment).toHaveBeenCalledWith(expect.objectContaining({
      filePath: expect.stringContaining('compressed-cold-raw.mp4')
    }))
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
    const videoInfo = deferred<{ duration: number; size: number }>()
    taroHarness.taroMock.getVideoInfo.mockReturnValueOnce(videoInfo.promise)

    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()

    const segmentPromise = recorderHarness.instances[0].options.onSegment('wxfile://temp/old.mp4', 30_000)
    await flushPromises()
    expect(taroHarness.taroMock.saveFile).toHaveBeenCalledWith({ tempFilePath: 'wxfile://temp/old.mp4' })

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

    videoInfo.resolve({ duration: 30, size: 1 })
    await segmentPromise
    await flushPromises()

    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(newerSession)
    expect(apiMocks.createVideoSession).not.toHaveBeenCalled()
    expect(apiMocks.uploadVideoSegment).not.toHaveBeenCalled()
  })

  it('does not resurrect a cleared manifest after the old page unmounts while saveFile is pending', async () => {
    const saveFile = deferred<{ savedFilePath: string }>()
    taroHarness.taroMock.saveFile.mockReturnValueOnce(saveFile.promise)

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

    saveFile.resolve({ savedFilePath: 'wxfile://store/orphaned-old.mp4' })
    await segmentPromise
    await flushPromises()

    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toBeUndefined()
    expect(apiMocks.createVideoSession).not.toHaveBeenCalled()
    expect(apiMocks.uploadVideoSegment).not.toHaveBeenCalled()
    expect(taroHarness.unlinkMock).toHaveBeenCalledWith(
      expect.objectContaining({ filePath: 'wxfile://store/orphaned-old.mp4' })
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
      'wxfile://store/compressed-raw-owned-0.mp4',
      'wxfile://store/compressed-raw-owned-1.mp4'
    ])
    expect(apiMocks.uploadVideoSegment.mock.calls.map(([input]) => input.index)).toEqual([0, 1])
  })

  it('runs one background segment upload at a time while recording', async () => {
    const upload0 = deferred<{ index: number; sha256: string }>()
    apiMocks.uploadVideoSegment
      .mockReturnValueOnce(upload0.promise)
      .mockResolvedValueOnce({ index: 1, sha256: 'sha-1' })
    taroHarness.taroMock.saveFile
      .mockResolvedValueOnce({ savedFilePath: 'wxfile://store/segment-0.mp4' })
      .mockResolvedValueOnce({ savedFilePath: 'wxfile://store/segment-1.mp4' })

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
    const firstSave = deferred<{ savedFilePath: string }>()
    const events: string[] = []
    let firstRawPending = true
    taroHarness.taroMock.saveFile.mockImplementation(async (input) => {
      events.push(`save-start:${input.tempFilePath}`)
      if (firstRawPending && input.tempFilePath === 'wxfile://temp/0.mp4') {
        firstRawPending = false
        const result = await firstSave.promise
        events.push(`save-done:${result.savedFilePath}`)
        return result
      }
      const savedFilePath = input.tempFilePath.includes('compressed')
        ? `wxfile://store/${input.tempFilePath.split('/').at(-1)}`
        : `wxfile://store/raw-${input.tempFilePath.split('/').at(-1)}`
      events.push(`save-done:${savedFilePath}`)
      return { savedFilePath }
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

    expect(events).toEqual(['save-start:wxfile://temp/0.mp4'])

    firstSave.resolve({ savedFilePath: 'wxfile://store/segment-0.mp4' })
    await Promise.all([first, second])
    await flushPromises()

    const saved = taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY) as ReturnType<typeof pendingSession>
    expect(events).toEqual([
      'save-start:wxfile://temp/0.mp4',
      'save-done:wxfile://store/segment-0.mp4',
      'save-start:wxfile://temp/compressed-segment-0.mp4',
      'save-done:wxfile://store/compressed-segment-0.mp4',
      'save-start:wxfile://temp/1.mp4',
      'save-done:wxfile://store/raw-1.mp4',
      'save-start:wxfile://temp/compressed-raw-1.mp4',
      'save-done:wxfile://store/compressed-raw-1.mp4'
    ])
    expect(saved.segments.map((segment) => segment.index)).toEqual([0, 1])
    expect(saved.segments.map((segment) => segment.savedFilePath)).toEqual([
      'wxfile://store/compressed-segment-0.mp4',
      'wxfile://store/compressed-raw-1.mp4'
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

    findButtonByText(page.element, '完成训练').props.onClick?.()
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
    findButtonByText(page.element, '完成训练').props.onClick?.()
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

    expect(textContent(page.element)).toContain('还需约 30 秒')
    expect(findButtonByText(page.element, '完成训练').props.disabled).toBe(true)

    vi.setSystemTime(startAt + 90_000)
    page.rerender()

    expect(findButtonByText(page.element, '完成训练').props.disabled).toBe(false)
  })

  it('counts resume duration from the saved base after hide pause before enabling completion', async () => {
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
    findButtonByText(page.element, '继续训练').props.onClick?.()
    await flushPromises()

    vi.setSystemTime(startAt + 60_000)
    page.rerender()

    expect(textContent(page.element)).toContain('00:50')
    expect(textContent(page.element)).toContain('还需约 10 秒')
    expect(findButtonByText(page.element, '完成训练').props.disabled).toBe(true)

    vi.setSystemTime(startAt + 70_000)
    page.rerender()

    expect(textContent(page.element)).toContain('01:00')
    expect(findButtonByText(page.element, '完成训练').props.disabled).toBe(false)
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
    taroHarness.taroMock.saveFile
      .mockResolvedValueOnce({ savedFilePath: 'wxfile://store/first-2370.mp4' })
      .mockResolvedValueOnce({ savedFilePath: 'wxfile://store/final-30.mp4' })
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
    recorder.options.onMaxDuration?.()
    await flushPromises()
    page.rerender()

    expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()
    expect(findButtonByText(page.element, '重试保存尾段')).toBeTruthy()
    expect(findButtonByText(page.element, '重新训练')).toBeTruthy()
    expect(taroHarness.unlinkMock.mock.calls.map(([options]) => options.filePath)).toEqual([
      'wxfile://store/first-2370.mp4',
      'wxfile://store/final-30.mp4'
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

    expect(taroHarness.taroMock.saveFile).toHaveBeenCalled()
    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/upload'
    })
  })

  it('keeps the original temp path when persistence and temp inspection both fail', async () => {
    taroHarness.taroMock.saveFile.mockRejectedValueOnce(new Error('saveFile failed'))
    taroHarness.taroMock.getVideoInfo.mockRejectedValue(new Error('getVideoInfo failed'))
    const page = renderPage(ShoulderPressCameraPage)
    await flushPromises()
    page.rerender()
    findFirstByType(page.element, 'Camera').props.onInitDone?.()
    page.rerender()
    findButtonByText(page.element, '开始训练').props.onClick?.()
    await flushPromises()
    const recorder = recorderHarness.instances[0]

    await expect(
      recorder.options.onSegment('wxfile://temp/final-save-failed.mp4', 30_000)
    ).rejects.toThrow('录像压缩失败，可重试')
    recorder.hasFailedSegment.mockReturnValue(true)
    recorder.abandonFailedSegment.mockReturnValue({
      savedFilePath: 'wxfile://temp/final-save-failed.mp4',
      durationMs: 30_000
    })
    recorder.finish.mockRejectedValue(new Error('getVideoInfo failed'))
    recorder.options.onMaxDuration?.()
    await flushPromises()
    page.rerender()

    expect(taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY)).toEqual(
      expect.objectContaining({
        segments: [expect.objectContaining({
          compressionState: 'compression_failed',
          rawSavedFilePath: 'wxfile://temp/final-save-failed.mp4'
        })]
      })
    )
    await findButtonByText(page.element, '重新训练').props.onClick?.()
    await flushPromises()

    expect(recorder.abandonFailedSegment).toHaveBeenCalledTimes(1)
    expect(taroHarness.unlinkMock).toHaveBeenCalledWith(expect.objectContaining({
      filePath: 'wxfile://temp/final-save-failed.mp4'
    }))
    expect(taroHarness.taroMock.reLaunch).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/index?actionId=42'
    })
  })

  it('falls back to the camera temp path when saveFile cannot persist a segment', async () => {
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
            savedFilePath: expect.stringContaining('compressed-storage-fallback.mp4')
          })
        ]
      })
    )
  })

  it('shows the native media errMsg when the temp recording is also unreadable', async () => {
    taroHarness.taroMock.saveFile.mockResolvedValueOnce({
      errMsg: 'saveFile:fail the maximum size of the file storage limit is exceeded'
    })
    taroHarness.taroMock.getVideoInfo.mockRejectedValue({
      errMsg: 'getVideoInfo:fail tempFilePath file not exist'
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
    ).rejects.toThrow('getVideoInfo:fail tempFilePath file not exist')
    page.rerender()

    expect(textContent(page.element)).toContain(
      'getVideoInfo:fail tempFilePath file not exist'
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

    findButtonByText(page.element, '继续训练').props.onClick?.()

    expect(taroHarness.taroMock.navigateTo).toHaveBeenCalledWith({
      url: '/pages/shoulder-press/index?actionId=42'
    })
  })
})
