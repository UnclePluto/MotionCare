# 微信小程序肩部推举动作预览与录像画中画 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在微信小程序肩部推举流程中增加独立静音循环预览页，并在录像页提供左侧固定计时、右侧可滑动隐藏的示范视频，以及按处方时长自动结束的统一完成流程。

**Architecture:** 保留现有 `ActionLibraryItem -> PrescriptionAction -> TrainingVideo` 与分段上传链路，只在肩部推举页面层增加一个预览路由、一个独立画中画组件和少量纯状态函数。录像页继续作为摄像、分段与上传协调者；预览播放失败和画中画状态不得进入上传会话，手动结束与自动结束统一进入现有幂等结束函数。

**Tech Stack:** Taro 4.2.0、React 18、TypeScript 5.4、微信小程序基础库 3.16.0、Vitest 3、SCSS、现有 Django 当前处方 API 与训练视频分段 API。

## Global Constraints

- 一期只处理 `source_key = motion-resistance-shoulder-press`，其它运动、游戏、Web/H5 患者端不变。
- 示范视频只读取当前处方动作的 `video_url`；不新增后端字段、接口、七牛上传管理或签名刷新能力。
- `video_url` 必须是小程序可直接播放的稳定 HTTPS 七牛 CDN 地址；缺失或播放失败不能阻塞直接训练。
- 独立预览页与录像画中画都必须 `autoplay`、`loop`、`muted`，不提供声音开关。
- 录像页左上侧计时固定，右上侧示范视频向右滑隐藏、向左滑恢复；计时、录像和上传状态不随其变化。
- 倒计时使用会话已有 `expectedDurationSeconds`；有效录像时长达到该值后自动结束。
- 患者可提前结束，必须二次确认；手动、自动和 40 分钟安全截止只允许执行一次结束流程。
- 保留 15 秒低分辨率原始分段、后台单并发上传、尾段失败恢复、强制上传页和固定健康观察窗口。
- 正常手动或自动结束尽力保存手机端 `training_ended_at`；意外退出仍允许缺失，且该字段不参与健康图表查询。
- 微信原生 `Camera` 与 `Video` 同层渲染必须在微信开发者工具、iOS 和 Android 真机验收。

---

## File Map

| 文件 | 职责 |
| --- | --- |
| `miniapp/src/app.config.ts` | 注册新的肩部推举预览页面 |
| `miniapp/src/pages/shoulder-press/index.tsx` | 动作介绍与“开始训练 / 动作预览”双入口 |
| `miniapp/src/pages/shoulder-press/preview.tsx` | 独立静音循环预览及关闭/开始导航 |
| `miniapp/src/pages/shoulder-press/preview.config.ts` | 预览页导航栏配置 |
| `miniapp/src/pages/shoulder-press/session.ts` | 构造预览页地址，继续复用相机与上传地址 |
| `miniapp/src/pages/shoulder-press/pageState.ts` | 倒计时、按处方时长自动结束、画中画滑动的纯状态规则 |
| `miniapp/src/pages/shoulder-press/trainingOverlay.tsx` | 左侧固定计时与右侧示范视频画中画 |
| `miniapp/src/pages/shoulder-press/camera.tsx` | 集成画中画、提前结束确认和统一结束流程 |
| `miniapp/src/app.scss` | 介绍页双按钮、预览页和录像覆盖层样式 |
| `miniapp/src/pages/shoulder-press/session.test.ts` | 路由构造测试 |
| `miniapp/src/pages/shoulder-press/pageState.test.ts` | 倒计时、自动结束和手势纯函数测试 |
| `miniapp/src/pages/shoulder-press/pages.test.tsx` | 页面导航、视频属性、异常降级与录像结束集成测试 |

---

### Task 1: 动作介绍双入口与独立预览页

**Files:**
- Create: `miniapp/src/pages/shoulder-press/preview.tsx`
- Create: `miniapp/src/pages/shoulder-press/preview.config.ts`
- Modify: `miniapp/src/app.config.ts`
- Modify: `miniapp/src/pages/shoulder-press/index.tsx`
- Modify: `miniapp/src/pages/shoulder-press/session.ts`
- Modify: `miniapp/src/app.scss`
- Test: `miniapp/src/pages/shoulder-press/session.test.ts`
- Test: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Consumes: `resolveShoulderPressAction(prescription, actionId)`、`buildShoulderPressCameraUrl(actionId)`、`CurrentPrescription.actions[].video_url`。
- Produces: `buildShoulderPressPreviewUrl(actionId: number): string`；页面路由 `/pages/shoulder-press/preview?actionId=<id>`；默认导出的 `ShoulderPressPreviewPage`。

- [ ] **Step 1: 写入失败的路由与页面行为测试**

在 `session.test.ts` 的地址构造用例中加入：

```ts
expect(buildShoulderPressPreviewUrl(42)).toBe(
  '/pages/shoulder-press/preview?actionId=42'
)
```

在 `pages.test.tsx` 的 Taro mock 中增加：

```ts
navigateBack: vi.fn(),
redirectTo: vi.fn(),
```

导入预览页，并用现有 `renderPage`、`findAll`、`findButtonByText` 辅助函数增加以下测试：

```ts
it('offers direct training and a separate muted looping preview', async () => {
  const guide = renderPage(ShoulderPressGuidePage)
  await flushPromises()
  guide.rerender()

  expect(findAll(guide.element, (element) => element.type === 'Video')).toHaveLength(0)
  findButtonByText(guide.element, '动作预览').props.onClick?.()
  expect(taroHarness.taroMock.navigateTo).toHaveBeenCalledWith({
    url: '/pages/shoulder-press/preview?actionId=42'
  })

  findButtonByText(guide.element, '开始训练').props.onClick?.()
  expect(taroHarness.taroMock.navigateTo).toHaveBeenCalledWith({
    url: '/pages/shoulder-press/camera?actionId=42'
  })

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
  expect(findButtonByText(guide.element, '开始训练')).toBeTruthy()
})
```

- [ ] **Step 2: 运行目标测试，确认因缺少路由和预览页而失败**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/pages.test.tsx
```

Expected: FAIL，至少包含 `buildShoulderPressPreviewUrl is not a function` 或找不到“动作预览”。

- [ ] **Step 3: 实现地址、双入口和预览页**

在 `session.ts` 与 `app.config.ts` 增加：

```ts
export function buildShoulderPressPreviewUrl(actionId: number): string {
  return `/pages/shoulder-press/preview?actionId=${encodeURIComponent(String(actionId))}`
}
```

```ts
'pages/shoulder-press/preview',
```

把动作介绍页内嵌 `Video` 和 `videoError` 状态移除，动作有效时渲染：

```tsx
<View className='button-row shoulder-guide-actions'>
  <Button
    className='primary-button'
    onClick={() => Taro.navigateTo({ url: buildShoulderPressCameraUrl(actionId) })}
  >
    开始训练
  </Button>
  {action.video_url ? (
    <Button
      className='secondary-button'
      onClick={() => Taro.navigateTo({ url: buildShoulderPressPreviewUrl(actionId) })}
    >
      动作预览
    </Button>
  ) : null}
</View>
```

创建 `preview.tsx`。页面状态为 `action`、`loaded`、`error`、`videoError` 和 `retryKey`，并使用
以下启动逻辑校验待上传会话、路由参数与当前处方：

```tsx
useEffect(() => {
  let cancelled = false
  async function bootstrap() {
    const redirected = await reLaunchPendingShoulderPressUploadIfNeeded(Taro)
    if (cancelled || redirected) return
    if (!Number.isInteger(actionId) || actionId <= 0) {
      setError('训练动作无效，请返回当前处方重新进入')
      setLoaded(true)
      return
    }
    try {
      const prescription = await request<CurrentPrescription>('/patient-app/current-prescription/')
      if (cancelled) return
      const currentAction = resolveShoulderPressAction(prescription, actionId)
      if (!currentAction?.video_url) {
        setError('当前动作暂无可播放的示范视频，请返回当前处方')
      } else {
        setAction(currentAction)
      }
    } catch (loadError) {
      if (!cancelled) {
        setError(loadError instanceof Error ? loadError.message : '动作预览加载失败，请稍后重试')
      }
    } finally {
      if (!cancelled) setLoaded(true)
    }
  }
  void bootstrap()
  return () => { cancelled = true }
}, [actionId])
```

渲染结构必须为：

```tsx
<View className='page shoulder-preview-page'>
  <View className='shoulder-preview-media'>
    {action?.video_url && !videoError ? (
      <Video
        key={retryKey}
        className='shoulder-preview-video'
        src={action.video_url}
        autoplay
        loop
        muted
        controls={false}
        objectFit='contain'
        onError={() => setVideoError(true)}
      />
    ) : null}
    {videoError ? (
      <View className='shoulder-preview-error'>
        <Text>视频加载失败</Text>
        <Button
          className='secondary-button'
          onClick={() => {
            setVideoError(false)
            setRetryKey((value) => value + 1)
          }}
        >
          重新加载
        </Button>
      </View>
    ) : null}
  </View>
  {error ? <Text className='error'>{error}</Text> : null}
  {action?.video_url ? (
    <View className='button-row shoulder-preview-actions'>
      <Button className='secondary-button' onClick={() => Taro.navigateBack()}>
        关闭预览
      </Button>
      <Button
        className='primary-button'
        onClick={() => Taro.redirectTo({ url: buildShoulderPressCameraUrl(actionId) })}
      >
        开始训练
      </Button>
    </View>
  ) : (
    <Button
      className='secondary-button full-button'
      onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
    >
      返回当前处方
    </Button>
  )}
</View>
```

`preview.config.ts` 使用：

```ts
export default definePageConfig({
  navigationBarTitleText: '动作预览'
})
```

在 `app.scss` 增加介绍双按钮和预览页竖屏视频样式，确保底部按钮不覆盖安全区域：

```scss
.shoulder-guide-actions,
.shoulder-preview-actions {
  position: sticky;
  bottom: 0;
  z-index: 5;
  padding-bottom: calc(16px + env(safe-area-inset-bottom));
  background: $mc-panel-strong;
}

.shoulder-preview-video {
  width: 100%;
  height: 68vh;
  border-radius: 12px;
  background: #101418;
}
```

- [ ] **Step 4: 运行目标测试和开发构建**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/pages.test.tsx
npm run build:weapp
```

Expected: 两个测试文件全部 PASS，微信小程序开发构建成功且新页面进入 `dist/app.json`。

- [ ] **Step 5: 提交独立预览流程**

```bash
git add miniapp/src/app.config.ts miniapp/src/app.scss \
  miniapp/src/pages/shoulder-press/index.tsx \
  miniapp/src/pages/shoulder-press/preview.tsx \
  miniapp/src/pages/shoulder-press/preview.config.ts \
  miniapp/src/pages/shoulder-press/session.ts \
  miniapp/src/pages/shoulder-press/session.test.ts \
  miniapp/src/pages/shoulder-press/pages.test.tsx
git commit -m "feat(miniapp): 增加肩部推举独立动作预览"
```

---

### Task 2: 倒计时、自动结束与滑动纯状态规则

**Files:**
- Modify: `miniapp/src/pages/shoulder-press/pageState.ts`
- Test: `miniapp/src/pages/shoulder-press/pageState.test.ts`

**Interfaces:**
- Consumes: `SHOULDER_PRESS_RECORDING_STOP_MS = 2_397_000` 与会话的 `expectedDurationSeconds`。
- Produces: `remainingShoulderPressSeconds(actualDurationMs, expectedDurationSeconds): number`；`shouldAutoFinishShoulderPressTraining({ actualDurationMs, expectedDurationSeconds }): boolean`；`nextShoulderPressPreviewVisibility(input): 'visible' | 'hidden'`。

- [ ] **Step 1: 写入倒计时、处方时长和手势失败测试**

在 `pageState.test.ts` 增加：

```ts
it('computes a clamped prescription countdown from effective recording time', () => {
  expect(remainingShoulderPressSeconds(0, 120)).toBe(120)
  expect(remainingShoulderPressSeconds(30_001, 120)).toBe(90)
  expect(remainingShoulderPressSeconds(120_000, 120)).toBe(0)
  expect(remainingShoulderPressSeconds(150_000, 120)).toBe(0)
})

it('auto finishes at the prescription duration and retains the camera safety stop', () => {
  expect(shouldAutoFinishShoulderPressTraining({
    actualDurationMs: 119_999,
    expectedDurationSeconds: 120
  })).toBe(false)
  expect(shouldAutoFinishShoulderPressTraining({
    actualDurationMs: 120_000,
    expectedDurationSeconds: 120
  })).toBe(true)
  expect(shouldAutoFinishShoulderPressTraining({
    actualDurationMs: SHOULDER_PRESS_RECORDING_STOP_MS,
    expectedDurationSeconds: 2400
  })).toBe(true)
})

it('only changes preview visibility for a dominant horizontal swipe', () => {
  expect(nextShoulderPressPreviewVisibility({
    visibility: 'visible', deltaX: 45, deltaY: 5
  })).toBe('hidden')
  expect(nextShoulderPressPreviewVisibility({
    visibility: 'hidden', deltaX: -45, deltaY: 5
  })).toBe('visible')
  expect(nextShoulderPressPreviewVisibility({
    visibility: 'visible', deltaX: 20, deltaY: 0
  })).toBe('visible')
  expect(nextShoulderPressPreviewVisibility({
    visibility: 'visible', deltaX: 45, deltaY: 60
  })).toBe('visible')
})
```

- [ ] **Step 2: 运行目标测试，确认新接口尚不存在或旧自动结束语义不符**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/pageState.test.ts
```

Expected: FAIL，原因是缺少倒计时/手势函数，且现有自动结束函数只判断 40 分钟安全截止。

- [ ] **Step 3: 实现最小纯状态函数**

在 `pageState.ts` 中替换旧自动结束签名并加入：

```ts
export type ShoulderPressPreviewVisibility = 'visible' | 'hidden'

export function remainingShoulderPressSeconds(
  actualDurationMs: number,
  expectedDurationSeconds: number
): number {
  const elapsedSeconds = Math.max(0, Math.floor(actualDurationMs / 1000))
  const expectedSeconds = Math.max(1, Math.round(expectedDurationSeconds))
  return Math.max(0, expectedSeconds - elapsedSeconds)
}

export function shouldAutoFinishShoulderPressTraining(input: {
  actualDurationMs: number
  expectedDurationSeconds: number
}): boolean {
  if (!Number.isFinite(input.actualDurationMs)) return false
  const expectedMs = Math.max(1, Math.round(input.expectedDurationSeconds)) * 1000
  return input.actualDurationMs >= expectedMs ||
    input.actualDurationMs >= SHOULDER_PRESS_RECORDING_STOP_MS
}

export function nextShoulderPressPreviewVisibility(input: {
  visibility: ShoulderPressPreviewVisibility
  deltaX: number
  deltaY: number
  threshold?: number
}): ShoulderPressPreviewVisibility {
  const threshold = input.threshold ?? 40
  if (Math.abs(input.deltaX) < threshold || Math.abs(input.deltaX) <= Math.abs(input.deltaY)) {
    return input.visibility
  }
  if (input.visibility === 'visible' && input.deltaX > 0) return 'hidden'
  if (input.visibility === 'hidden' && input.deltaX < 0) return 'visible'
  return input.visibility
}
```

更新旧的 `shouldAutoFinishShoulderPressTraining` 测试调用为对象参数，保留 40 分钟安全边界断言。

- [ ] **Step 4: 运行纯状态测试**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/pageState.test.ts
```

Expected: PASS。

- [ ] **Step 5: 提交纯状态规则**

```bash
git add miniapp/src/pages/shoulder-press/pageState.ts \
  miniapp/src/pages/shoulder-press/pageState.test.ts
git commit -m "feat(miniapp): 增加肩部推举倒计时与画中画手势规则"
```

---

### Task 3: 录像页固定计时与可收起示范视频

**Files:**
- Create: `miniapp/src/pages/shoulder-press/trainingOverlay.tsx`
- Modify: `miniapp/src/pages/shoulder-press/camera.tsx`
- Modify: `miniapp/src/app.scss`
- Test: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Consumes: `nextShoulderPressPreviewVisibility()`、`remainingShoulderPressSeconds()`、当前动作 `video_url`、录像页 `elapsedMs` 和 `expectedDurationSeconds`。
- Produces: `ShoulderPressTrainingOverlay(props)`，其中 props 为 `{ videoUrl: string | null; elapsedMs: number; expectedDurationSeconds: number }`；组件内部独占 `visible/hidden` 与播放失败状态。

- [ ] **Step 1: 写入画中画渲染、固定计时、滑动和失败降级测试**

在 `pages.test.tsx` 导入 `ShoulderPressTrainingOverlay`，增加按现有 harness 直接渲染组件的测试：

```ts
it('keeps the timer fixed while the muted preview hides and restores', () => {
  const overlay = renderPage(ShoulderPressTrainingOverlay, {
    videoUrl: 'https://cdn.example.com/demo.mp4',
    elapsedMs: 24_000,
    expectedDurationSeconds: 180
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

  expect(findAll(overlay.element, (element) => element.type === 'Video')).toHaveLength(0)
  expect(textContent(overlay.element)).toContain('向左滑恢复示范')
  const timerAfter = findAll(overlay.element, (element) => (
    element.props.className === 'shoulder-training-timer'
  ))[0]
  expect(timerAfter.props.className).toBe(timerBefore.props.className)
})

it('degrades preview playback without changing timer content', () => {
  const overlay = renderPage(ShoulderPressTrainingOverlay, {
    videoUrl: 'https://cdn.example.com/demo.mp4',
    elapsedMs: 24_000,
    expectedDurationSeconds: 180
  })
  findFirstByType(overlay.element, 'Video').props.onError?.()
  overlay.rerender()

  expect(textContent(overlay.element)).toContain('示范视频暂时无法播放')
  expect(textContent(overlay.element)).toContain('已训练00:24')
  expect(textContent(overlay.element)).toContain('剩余02:36')
})
```

- [ ] **Step 2: 运行页面测试，确认组件不存在**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/pages.test.tsx
```

Expected: FAIL，原因是无法导入 `trainingOverlay.tsx`。

- [ ] **Step 3: 实现画中画组件并嵌入相机容器**

`trainingOverlay.tsx` 必须维护触摸起点与组件本地显示状态，核心接口和行为为：

```tsx
type TouchPoint = { clientX: number; clientY: number }

export type ShoulderPressTrainingOverlayProps = {
  videoUrl: string | null
  elapsedMs: number
  expectedDurationSeconds: number
}

export function ShoulderPressTrainingOverlay(props: ShoulderPressTrainingOverlayProps) {
  const [visibility, setVisibility] = useState<ShoulderPressPreviewVisibility>('visible')
  const [videoError, setVideoError] = useState(false)
  const touchStartRef = useRef<TouchPoint | null>(null)
  const remainingSeconds = remainingShoulderPressSeconds(
    props.elapsedMs,
    props.expectedDurationSeconds
  )

  const finishSwipe = (point: TouchPoint) => {
    const start = touchStartRef.current
    touchStartRef.current = null
    if (!start) return
    setVisibility((current) => nextShoulderPressPreviewVisibility({
      visibility: current,
      deltaX: point.clientX - start.clientX,
      deltaY: point.clientY - start.clientY
    }))
  }

  return (
    <View className='shoulder-training-overlay'>
      <View className='shoulder-training-timer'>
        <View><Text>已训练</Text><Text>{formatShoulderPressTimer(props.elapsedMs)}</Text></View>
        <View><Text>剩余</Text><Text>{formatShoulderPressTimer(remainingSeconds * 1000)}</Text></View>
      </View>
      {props.videoUrl && visibility === 'visible' && !videoError ? (
        <Video
          className='shoulder-training-preview'
          src={props.videoUrl}
          autoplay
          loop
          muted
          controls={false}
          objectFit='contain'
          onError={() => setVideoError(true)}
          onTouchStart={(event) => {
            const point = event.touches[0]
            if (point) touchStartRef.current = point
          }}
          onTouchEnd={(event) => {
            const point = event.changedTouches[0]
            if (point) finishSwipe(point)
          }}
        />
      ) : null}
      {props.videoUrl && visibility === 'hidden' ? (
        <View
          className='shoulder-training-preview-restore'
          onTouchStart={(event) => {
            const point = event.touches[0]
            if (point) touchStartRef.current = point
          }}
          onTouchEnd={(event) => {
            const point = event.changedTouches[0]
            if (point) finishSwipe(point)
          }}
        >
          <Text>←</Text><Text>向左滑恢复示范</Text>
        </View>
      ) : null}
      {videoError && visibility === 'visible' ? (
        <View
          className='shoulder-training-preview-error'
          onTouchStart={(event) => {
            const point = event.touches[0]
            if (point) touchStartRef.current = point
          }}
          onTouchEnd={(event) => {
            const point = event.changedTouches[0]
            if (point) finishSwipe(point)
          }}
        >
          <Text>示范视频暂时无法播放</Text>
        </View>
      ) : null}
    </View>
  )
}
```

在 `camera.tsx` 中把组件放在 `Camera` 后、同一个 `.camera-training-frame` 内：

```tsx
<View className='camera-training-frame'>
  <Camera
    className='camera-preview'
    devicePosition='front'
    resolution='low'
    flash='off'
    mode='normal'
    onInitDone={() => setCameraReady(true)}
    onError={() => {
      setCameraReady(false)
      setError('请开启摄像头权限，摄像头可用后才能开始录像')
    }}
  />
  <ShoulderPressTrainingOverlay
    videoUrl={action?.video_url ?? null}
    elapsedMs={elapsedMs}
    expectedDurationSeconds={session?.expectedDurationSeconds ?? 1}
  />
</View>
```

在 `app.scss` 明确相机容器为相对定位，计时绝对固定左侧，示范绝对固定右侧；隐藏类只能改变示范：

```scss
.camera-training-frame { position: relative; }
.shoulder-training-overlay { position: absolute; inset: 0; pointer-events: none; }
.shoulder-training-timer { position: absolute; top: 24px; left: 24px; z-index: 4; }
.shoulder-training-preview { position: absolute; top: 24px; right: 24px; z-index: 4; width: 210px; height: 300px; pointer-events: auto; }
.shoulder-training-preview-restore { position: absolute; top: 72px; right: 0; z-index: 4; pointer-events: auto; }
.shoulder-training-preview-error { position: absolute; top: 24px; right: 24px; z-index: 4; width: 210px; min-height: 120px; pointer-events: auto; }
```

同时加入以下视觉规则；隐藏态不得覆盖 `.shoulder-training-timer` 的 `left`、`top` 或 transform：

```scss
.shoulder-training-timer,
.shoulder-training-preview-error {
  padding: 16px;
  border-radius: 12px;
  color: #ffffff;
  background: rgba(16, 20, 24, 0.76);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.24);
}

.shoulder-training-preview,
.shoulder-training-preview-error {
  transition: transform 180ms ease, opacity 180ms ease;
}

.shoulder-training-preview-restore {
  display: flex;
  width: 54px;
  min-height: 150px;
  align-items: center;
  justify-content: center;
  border-radius: 16px 0 0 16px;
  color: $mc-primary;
  background: rgba(255, 255, 255, 0.94);
  writing-mode: vertical-rl;
}
```

- [ ] **Step 4: 运行页面测试、TypeScript 与微信开发构建**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/pages.test.tsx
npx tsc --noEmit
npm run build:weapp
```

Expected: PASS；构建产物同时包含 `camera` 和 `video` 原生组件，不出现类型或编译错误。

- [ ] **Step 5: 提交录像画中画**

```bash
git add miniapp/src/app.scss \
  miniapp/src/pages/shoulder-press/camera.tsx \
  miniapp/src/pages/shoulder-press/trainingOverlay.tsx \
  miniapp/src/pages/shoulder-press/pages.test.tsx
git commit -m "feat(miniapp): 增加肩部推举录像画中画"
```

---

### Task 4: 提前结束确认与按处方时长自动完成

**Files:**
- Modify: `miniapp/src/pages/shoulder-press/camera.tsx`
- Modify: `miniapp/src/pages/shoulder-press/pageState.ts`
- Test: `miniapp/src/pages/shoulder-press/pages.test.tsx`
- Test: `miniapp/src/pages/shoulder-press/pageState.test.ts`

**Interfaces:**
- Consumes: Task 2 的 `remainingShoulderPressSeconds()` 和对象参数版 `shouldAutoFinishShoulderPressTraining()`；现有结束函数、`finishInFlightRef`、`markShoulderPressTrainingEnded()` 与强制上传路由。
- Produces: `finishTraining(endedAtMs?: number): Promise<void>` 与 `requestManualFinishTraining(): Promise<void>`；录像中或暂停后只要已经有 `trainingStartedAt`，即可请求提前结束。

- [ ] **Step 1: 写入提前结束确认、取消与自动结束失败测试**

在 Taro mock 中加入默认确认行为：

```ts
showModal: vi.fn(async () => ({ confirm: true, cancel: false })),
```

在 `pages.test.tsx` 增加：

```ts
it('allows an early manual finish only after confirmation', async () => {
  const page = renderPage(ShoulderPressCameraPage)
  await flushPromises()
  page.rerender()
  findFirstByType(page.element, 'Camera').props.onInitDone?.()
  page.rerender()
  findButtonByText(page.element, '开始训练').props.onClick?.()
  await flushPromises()
  page.rerender()

  findButtonByText(page.element, '结束训练').props.onClick?.()
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
  findFirstByType(page.element, 'Camera').props.onInitDone?.()
  page.rerender()
  findButtonByText(page.element, '开始训练').props.onClick?.()
  await flushPromises()
  page.rerender()

  findButtonByText(page.element, '结束训练').props.onClick?.()
  await flushPromises()

  expect(recorderHarness.instances[0].finish).not.toHaveBeenCalled()
  expect(textContent(page.element)).toContain('正在录像')
})
```

把处方测试动作时长改为可控值或建立 1 秒处方夹具，再增加自动结束断言：

```ts
it('auto finishes once at the prescription duration without a confirmation', async () => {
  vi.useFakeTimers()
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

  await vi.advanceTimersByTimeAsync(1_100)
  await flushPromises()

  expect(taroHarness.taroMock.showModal).not.toHaveBeenCalled()
  expect(recorderHarness.instances[0].finish).toHaveBeenCalledTimes(1)
})
```

- [ ] **Step 2: 运行页面测试，确认旧完成门槛和旧自动结束条件导致失败**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/pages.test.tsx src/pages/shoulder-press/pageState.test.ts
```

Expected: FAIL；“完成训练”仍在处方时长前禁用，且自动结束仍只在 40 分钟触发。

- [ ] **Step 3: 统一手动、处方倒计时与安全截止的结束入口**

在 `camera.tsx` 增加：

```ts
async function requestManualFinishTraining() {
  if (finishInFlightRef.current || commandInFlightRef.current || finishPromptInFlightRef.current) return
  finishPromptInFlightRef.current = true
  try {
    const result = await Taro.showModal({
      title: '结束训练？',
      content: '确认结束本次肩部推举训练吗？',
      confirmText: '结束训练',
      confirmColor: '#ff4d4f',
      cancelText: '继续训练'
    })
    if (!result.confirm) return
    await finishTraining()
  } finally {
    finishPromptInFlightRef.current = false
  }
}
```

在其它命令 ref 旁增加 `const finishPromptInFlightRef = useRef(false)`。删除
`canCompleteShoulderPressTraining` 的导入、实现和旧测试；把结束函数签名改为
`async function finishTraining(endedAtMs = Date.now())`，删除其中“未达到处方时长不能完成”的
判断。`finishInFlightRef` 继续作为真正停止、落盘和跳转的唯一互斥保护。录像态和暂停态按钮
统一为：

```tsx
<Button
  className='primary-button full-button shoulder-finish-button'
  loading={processing}
  disabled={processing || !session?.trainingStartedAt}
  onClick={() => void requestManualFinishTraining()}
>
  结束训练
</Button>
```

倒计时使用 Task 2 的函数：

```ts
const remainingSeconds = remainingShoulderPressSeconds(
  elapsedMs,
  session?.expectedDurationSeconds ?? 1
)
```

每秒刷新时改为：

```ts
if (shouldAutoFinishShoulderPressTraining({
  actualDurationMs: elapsedMs,
  expectedDurationSeconds: sessionRef.current?.expectedDurationSeconds ?? 1
})) {
  void finishTraining()
}
```

保留录像器 `onMaxDuration` 和 hard-stop timer，但把带截止时间的调用改为
`finishTraining(cutoffMs)`，其它安全截止调用改为 `finishTraining()`；三路并发由
`finishInFlightRef` 去重。正常自动结束继续在 `finishTraining` 最前面调用现有
`markShoulderPressTrainingEnded(currentSession, endedAtMs)`，写入失败仍不得阻止上传。

- [ ] **Step 4: 运行肩部推举目标测试和完整小程序验证**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/pageState.test.ts \
  src/pages/shoulder-press/session.test.ts \
  src/pages/shoulder-press/pages.test.tsx \
  src/pages/shoulder-press/recorder.test.ts \
  src/pages/shoulder-press/workflow.test.ts
npm test
npx tsc --noEmit
npx eslint src --ext .ts,.tsx
npx stylelint "src/**/*.scss"
npm run build:weapp
npm run build:weapp:prod
git diff --check
```

Expected: 所有测试 PASS；TypeScript、ESLint、Stylelint、开发构建和生产构建成功；无空白错误。

- [ ] **Step 5: 提交统一结束流程**

```bash
git add miniapp/src/pages/shoulder-press/camera.tsx \
  miniapp/src/pages/shoulder-press/pageState.ts \
  miniapp/src/pages/shoulder-press/pageState.test.ts \
  miniapp/src/pages/shoulder-press/pages.test.tsx
git commit -m "feat(miniapp): 按处方时长结束肩部推举录像"
```

---

## Final Manual Acceptance Gate

自动化和构建通过后，在合并或发布开发版前完成以下微信环境验证；未完成时不得宣称真机功能
已经验收：

- [ ] 微信开发者工具：介绍页双入口、预览页关闭/开始导航、静音循环播放均正常。
- [ ] 微信开发者工具：录像启动后左侧正计时/倒计时更新，右侧示范画中画显示。
- [ ] iOS 真机：前置摄像头与示范视频同层显示，右滑隐藏、左滑恢复，计时不移动。
- [ ] Android 真机：前置摄像头与示范视频同层显示，右滑隐藏、左滑恢复，计时不移动。
- [ ] 真机：提前结束弹确认；取消后继续，确认后只生成一条训练会话并进入上传。
- [ ] 真机：处方倒计时归零自动结束，不弹确认，尾段与后台上传完成后进入强制上传页。
- [ ] 真机：七牛 CDN 地址可范围播放；断网或示范视频失败不阻塞录像和训练上传。
- [ ] 真机：小程序进入后台自动暂停，返回并继续后正计时与倒计时从有效录像时长续算。

真机验收结果应追加到本计划顶部的执行记录。全部通过后，把关联设计状态从 `approved` 更新为
`implemented`；如需上传微信开发版或发布线上，必须另行取得用户明确授权。
