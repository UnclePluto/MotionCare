# 肩部推举全屏录像与存储保护实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 状态：approved
> 日期：2026-08-09
> 范围：微信小程序肩部推举全屏录像、启动前清理、5 秒分段、65MB/10MB 缓冲保护与本地语音告警。
> 关联：`docs/superpowers/specs/2026-08-09-wechat-shoulder-press-fullscreen-storage-guard-design.md`
> 实施基线 commit：`1514455`

**Goal:** 把肩部推举录像页改为真正的全屏画中画训练界面，并通过启动前文件清理、5 秒直传分段和 65MB/10MB 高低水位保护，避免微信 `saveFile` 配额导致录像失败。

**Architecture:** 新增独立的存储预检器、缓冲水位纯状态机和肩部推举告警播放器；录像器只负责把常规分段边界从 15 秒改为 5 秒。录像页协调预检、录像、后台单并发上传、正倒计时和全屏覆盖层；后端仅提高有界分段数量上限，不新增模型或接口。

**Tech Stack:** Taro 4、React 18、TypeScript、Vitest、微信 `CameraContext` / `FileSystemManager` / `InnerAudioContext`、Django 5、DRF、pytest。

## Global Constraints

- 只修改微信小程序肩部推举、对应分段上限与测试；不修改患者 H5、医生端或其它训练动作。
- 录像页使用全屏相机，左侧正倒计时、右侧可收起示范视频、底部固定结束按钮。
- 有待上传肩部推举会话时绝不清理其文件，必须进入现有补传流程。
- 无待上传会话时，开始训练前清理本小程序全部历史 `saveFile` 文件，并等待删除与复核完成。
- 微信持久化文件总额度按 100MB 计算；清理后可用额度不足 65MB 时硬拦截。
- 正式录像每 5 秒产生一个分段；上传继续保持单并发，服务端确认后立即尽力清理本地文件。
- 待上传本地分段达到或超过 65MB 时，在分段边界自动暂停；严格低于 10MB 后才允许患者手动继续。
- 暂停和恢复各使用一条小程序包内本地语音；语音失败只能降级文字，不能改变业务状态。
- 缓冲暂停、页面后台和患者手动暂停期间不增加有效录像时长。
- 正常开始时间仍只在正式录像器启动成功后写入；清理与空间检查不得创建训练会话或时间戳。
- 不恢复客户端视频压缩，不保证整段训练完全离线保存。
- 后端分段上限固定为 600，必须接受 480 段并拒绝第 601 段或 `segment_count=601`。
- 所有提交描述使用中文，不合并、不推送、不发布，直到自动化和微信开发者工具/iOS/Android 人工门禁完成。

---

## 文件结构与职责

| 文件 | 职责 |
| --- | --- |
| `miniapp/src/pages/shoulder-press/storageGuard.ts` | 清理历史保存文件、复核剩余占用、计算 65MB 启动门槛 |
| `miniapp/src/pages/shoulder-press/storageGuard.test.ts` | 存储预检、删除等待、竞态和边界测试 |
| `miniapp/src/pages/shoulder-press/bufferGuard.ts` | 计算待上传本地字节与 65MB/10MB 状态转换 |
| `miniapp/src/pages/shoulder-press/bufferGuard.test.ts` | 高低水位、精确边界、服务端确认排除测试 |
| `miniapp/src/pages/shoulder-press/recorder.ts` | 5 秒常规分段和既有有效尾段语义 |
| `miniapp/src/pages/shoulder-press/recorder.test.ts` | 5 秒连续分段、结束/暂停尾段与去重测试 |
| `miniapp/src/pages/shoulder-press/alertAudio.ts` | 本地暂停/恢复语音的播放、停止与销毁 |
| `miniapp/src/pages/shoulder-press/alertAudio.test.ts` | 播放一次、替换播放、失败降级和销毁测试 |
| `miniapp/src/pages/shoulder-press/assets/audio/*.m4a` | 两条离线告警语音 |
| `miniapp/src/pages/shoulder-press/camera.tsx` | 协调存储预检、缓冲状态、上传、计时和全屏页面 |
| `miniapp/src/pages/shoulder-press/camera.config.ts` | 自定义导航与禁止滚动 |
| `miniapp/src/pages/shoulder-press/pages.test.tsx` | 页面交互、全屏结构、清理、暂停恢复与语音集成回归 |
| `miniapp/src/app.scss` | 全屏相机、安全区域、覆盖层、缓冲暂停和空间不足样式 |
| `backend/config/settings.py` | 将单次训练最大分段数默认值提高到 600 |
| `deploy/docker-compose.prod.yml` | 显式传入 `TRAINING_VIDEO_MAX_SEGMENTS` |
| `deploy/env.production.example` | 记录生产分段上限变量默认值 600 |
| `backend/apps/patient_app/tests/test_patient_app_video_api.py` | 480/600/601 分段边界与 finalize 回归 |

---

### Task 1: 启动前历史文件清理与 65MB 空间门槛

**Files:**
- Create: `miniapp/src/pages/shoulder-press/storageGuard.ts`
- Create: `miniapp/src/pages/shoulder-press/storageGuard.test.ts`

**Interfaces:**
- Consumes: 调用方提供 `hasPendingSession()`、Promise 风格的 `listSavedFiles()` / `removeSavedFile()` 与页面存活检查 `isActive()`。
- Produces:

```ts
export const WECHAT_SAVED_FILE_CAPACITY_BYTES = 100 * 1024 * 1024
export const SHOULDER_PRESS_START_REQUIRED_FREE_BYTES = 65 * 1024 * 1024

export type ShoulderPressSavedFile = {
  filePath: string
  size: number
  createTime?: number
}

export type ShoulderPressStorageGuardResult =
  | { kind: 'pending_session' }
  | { kind: 'cancelled' }
  | { kind: 'ready'; usedBytes: number; availableBytes: number }
  | { kind: 'blocked'; usedBytes: number; availableBytes: number }

export async function cleanupAndCheckShoulderPressStorage(input: {
  hasPendingSession: () => boolean
  listSavedFiles: () => Promise<ShoulderPressSavedFile[]>
  removeSavedFile: (filePath: string) => Promise<void>
  isActive: () => boolean
}): Promise<ShoulderPressStorageGuardResult>
```

- [ ] **Step 1: 写入失败的存储预检测试**

```ts
it('waits for every deletion before relisting and returns ready at exactly 65MB free', async () => {
  let finishFirstRemoval!: () => void
  const listSavedFiles = vi.fn()
    .mockResolvedValueOnce([
      { filePath: 'wxfile://store/a.mp4', size: 20 * MB },
      { filePath: 'wxfile://store/b.mp4', size: 35 * MB }
    ])
    .mockResolvedValueOnce([{ filePath: 'wxfile://store/b.mp4', size: 35 * MB }])
  const run = cleanupAndCheckShoulderPressStorage({
    hasPendingSession: () => false,
    listSavedFiles,
    removeSavedFile: (path) => path.endsWith('a.mp4')
      ? new Promise<void>((resolve) => { finishFirstRemoval = resolve })
      : Promise.reject(new Error('file is still occupied')),
    isActive: () => true
  })

  expect(listSavedFiles).toHaveBeenCalledTimes(1)
  expect(listSavedFiles).toHaveBeenCalledTimes(1)
  finishFirstRemoval()

  await expect(run).resolves.toEqual({
    kind: 'ready',
    usedBytes: 35 * MB,
    availableBytes: 65 * MB
  })
  expect(listSavedFiles).toHaveBeenCalledTimes(2)
})
```

同一测试文件必须再用完整 Arrange/Act/Assert 覆盖：

- `hasPendingSession()` 返回 `true` 时结果为 `pending_session`，且列表、删除方法均为 0 次调用；
- 复核后占用 `35MB + 1 byte` 时结果为 `blocked`，可用字节精确等于 `65MB - 1 byte`；
- 一个删除 Promise reject 时仍等待其它删除结束，并以第二次列表而不是删除回调结果计算空间；
- 第一次或第二次列表 reject 时，主 Promise 原样 reject，绝不返回 `ready`；
- 删除尚未结束时把 `isActive()` 改为 `false`，全部删除 settled 后返回 `cancelled`，且不启动录像侧效果；
- `size` 为负数、`NaN` 或 `Infinity` 时按 0 计，累计超过 100MB 时钳制为 100MB，确保可用空间处于
  `0..100MB`。

- [ ] **Step 2: 运行目标测试，确认新模块尚不存在**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/storageGuard.test.ts
```

Expected: FAIL，提示无法解析 `./storageGuard`。

- [ ] **Step 3: 实现最小存储预检器**

核心实现必须先短路待上传会话，再等待 `Promise.allSettled`，最后重新读取文件清单：

```ts
const normalizedSize = (value: number) => (
  Number.isFinite(value) && value > 0 ? Math.floor(value) : 0
)

function usedSavedBytes(files: ShoulderPressSavedFile[]): number {
  return Math.min(
    WECHAT_SAVED_FILE_CAPACITY_BYTES,
    files.reduce((total, file) => total + normalizedSize(file.size), 0)
  )
}

export async function cleanupAndCheckShoulderPressStorage(
  input: StorageGuardInput
): Promise<ShoulderPressStorageGuardResult> {
  if (input.hasPendingSession()) return { kind: 'pending_session' }
  const before = await input.listSavedFiles()
  if (!input.isActive()) return { kind: 'cancelled' }
  await Promise.allSettled(before.map((file) => input.removeSavedFile(file.filePath)))
  if (!input.isActive()) return { kind: 'cancelled' }
  const after = await input.listSavedFiles()
  if (!input.isActive()) return { kind: 'cancelled' }
  const usedBytes = usedSavedBytes(after)
  const availableBytes = WECHAT_SAVED_FILE_CAPACITY_BYTES - usedBytes
  return {
    kind: availableBytes >= SHOULDER_PRESS_START_REQUIRED_FREE_BYTES ? 'ready' : 'blocked',
    usedBytes,
    availableBytes
  }
}
```

文件列表读取失败必须向调用方抛出，由页面转换为安全中文错误；不能把失败当成空列表。

- [ ] **Step 4: 运行测试并检查类型**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/storageGuard.test.ts
npx tsc --noEmit --pretty false
```

Expected: 存储预检测试全部 PASS；TypeScript 不得比实施基线新增错误。

- [ ] **Step 5: 提交存储预检器**

```bash
git add miniapp/src/pages/shoulder-press/storageGuard.ts miniapp/src/pages/shoulder-press/storageGuard.test.ts
git commit -m "feat(miniapp): 增加肩部推举录像空间预检"
```

---

### Task 2: 5 秒录像分段与 65MB/10MB 缓冲状态机

**Files:**
- Create: `miniapp/src/pages/shoulder-press/bufferGuard.ts`
- Create: `miniapp/src/pages/shoulder-press/bufferGuard.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/recorder.ts`
- Modify: `miniapp/src/pages/shoulder-press/recorder.test.ts`

**Interfaces:**
- Consumes: `PendingShoulderPressSegment[]`、当前缓冲状态和实际分段字节数。
- Produces:

```ts
export const SHOULDER_PRESS_SEGMENT_DURATION_MS = 5_000
export const SHOULDER_PRESS_BUFFER_HIGH_BYTES = 65 * 1024 * 1024
export const SHOULDER_PRESS_BUFFER_LOW_BYTES = 10 * 1024 * 1024

export type ShoulderPressBufferState = 'recording' | 'buffer_paused' | 'buffer_ready'
export type ShoulderPressBufferTransition = {
  state: ShoulderPressBufferState
  alert: 'pause' | 'ready' | null
}

export function pendingShoulderPressLocalBytes(
  segments: PendingShoulderPressSegment[]
): number

export function nextShoulderPressBufferTransition(input: {
  state: ShoulderPressBufferState
  pendingBytes: number
}): ShoulderPressBufferTransition

export function canResumeShoulderPressFromBuffer(pendingBytes: number): boolean
```

- [ ] **Step 1: 写入失败的缓冲边界和 5 秒录像测试**

```ts
it('counts only segments that still depend on a local file', () => {
  expect(pendingShoulderPressLocalBytes([
    compressedSegment({ sizeBytes: 7 * MB, uploadState: 'pending' }),
    compressedSegment({ sizeBytes: 8 * MB, uploadState: 'uploading' }),
    compressedSegment({ sizeBytes: 9 * MB, uploadState: 'uploaded', sha256: 'ok' })
  ])).toBe(15 * MB)
})

it('pauses once at 65MB and becomes ready only below 10MB', () => {
  expect(nextShoulderPressBufferTransition({ state: 'recording', pendingBytes: 65 * MB }))
    .toEqual({ state: 'buffer_paused', alert: 'pause' })
  expect(nextShoulderPressBufferTransition({ state: 'buffer_paused', pendingBytes: 10 * MB }))
    .toEqual({ state: 'buffer_paused', alert: null })
  expect(nextShoulderPressBufferTransition({ state: 'buffer_paused', pendingBytes: 10 * MB - 1 }))
    .toEqual({ state: 'buffer_ready', alert: 'ready' })
  expect(nextShoulderPressBufferTransition({ state: 'buffer_ready', pendingBytes: 0 }))
    .toEqual({ state: 'buffer_ready', alert: null })
})

it('treats a legacy local segment with unknown size as unsafe', () => {
  expect(pendingShoulderPressLocalBytes([
    {
      index: 0,
      compressionState: 'pending_compression',
      rawSavedFilePath: 'wxfile://store/legacy.mp4',
      durationMs: 5_000
    }
  ])).toBe(Number.POSITIVE_INFINITY)
})
```

在 `recorder.test.ts` 把常规超时测试改为精确验证：

```ts
expect(camera.startRecord).toHaveBeenNthCalledWith(
  1,
  expect.objectContaining({ timeout: 5 })
)
expect(camera.startRecord).toHaveBeenNthCalledWith(
  2,
  expect.objectContaining({ timeout: 5 })
)
expect(onSegment).toHaveBeenNthCalledWith(1, 'wxfile://temp/segment-0.mp4', 5_000)
```

还必须保留并调整暂停/结束尾段、相机最大时长、重复 timeout callback 和失败分段重试测试。

- [ ] **Step 2: 运行目标测试，确认 15 秒旧行为导致失败**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/bufferGuard.test.ts src/pages/shoulder-press/recorder.test.ts
```

Expected: 新模块不存在，且 recorder 仍请求 `timeout: 15`。

- [ ] **Step 3: 实现缓冲纯函数并把分段常量改为 5 秒**

`pendingShoulderPressLocalBytes` 只对 `compressionState === 'compressed'` 且
`uploadState !== 'uploaded'` 的分段累加合法正字节；已上传段不计入。任一 legacy 段没有可信
`sizeBytes`，函数必须返回 `Number.POSITIVE_INFINITY`，使页面保持暂停并转入现有 legacy
恢复/补传流程；不得把未知大小当作 0。

状态转换必须使用严格边界：

```ts
if (state === 'recording' && pendingBytes >= HIGH) {
  return { state: 'buffer_paused', alert: 'pause' }
}
if (state === 'buffer_paused' && pendingBytes < LOW) {
  return { state: 'buffer_ready', alert: 'ready' }
}
return { state, alert: null }
```

在 `recorder.ts` 导出并使用 `SHOULDER_PRESS_SEGMENT_DURATION_MS = 5_000`，替换旧
`TIMEOUT_SEGMENT_MS = 15_000`。不要修改 `MIN_PAUSE_SEGMENT_MS = 2_000`、最大录像时长或尾段去重。

- [ ] **Step 4: 运行目标与肩部推举状态回归**

Run:

```bash
cd miniapp
npx vitest run \
  src/pages/shoulder-press/bufferGuard.test.ts \
  src/pages/shoulder-press/recorder.test.ts \
  src/pages/shoulder-press/session.test.ts \
  src/pages/shoulder-press/workflow.test.ts
```

Expected: 全部 PASS，且没有测试继续把常规分段写死为 15 秒。

- [ ] **Step 5: 提交分段与缓冲状态机**

```bash
git add \
  miniapp/src/pages/shoulder-press/bufferGuard.ts \
  miniapp/src/pages/shoulder-press/bufferGuard.test.ts \
  miniapp/src/pages/shoulder-press/recorder.ts \
  miniapp/src/pages/shoulder-press/recorder.test.ts
git commit -m "feat(miniapp): 改为五秒录像分段与缓冲保护"
```

---

### Task 3: 本地暂停与恢复语音

**Files:**
- Create: `miniapp/src/pages/shoulder-press/alertAudio.ts`
- Create: `miniapp/src/pages/shoulder-press/alertAudio.test.ts`
- Create: `miniapp/src/pages/shoulder-press/assets/audio/network_slow_paused.m4a`
- Create: `miniapp/src/pages/shoulder-press/assets/audio/upload_recovered.m4a`

**Interfaces:**
- Consumes: Taro `createInnerAudioContext()`。
- Produces:

```ts
export type ShoulderPressAlertKind = 'pause' | 'ready'

export const SHOULDER_PRESS_ALERT_TEXT: Record<ShoulderPressAlertKind, string>
export const SHOULDER_PRESS_ALERT_SRC: Record<ShoulderPressAlertKind, string>

export type ShoulderPressAlertPlayer = {
  play: (kind: ShoulderPressAlertKind) => Promise<boolean>
  dispose: () => void
}

export function createShoulderPressAlertPlayer(): ShoulderPressAlertPlayer
```

- [ ] **Step 1: 写入失败的播放器生命周期测试**

```ts
it('stops the previous alert before playing the next one', async () => {
  const first = audioContextHarness()
  const second = audioContextHarness()
  taroMock.createInnerAudioContext.mockReturnValueOnce(first.audio).mockReturnValueOnce(second.audio)
  const player = createShoulderPressAlertPlayer()

  void player.play('pause')
  void player.play('ready')

  expect(first.audio.stop).toHaveBeenCalledTimes(1)
  expect(second.audio.src).toBe(SHOULDER_PRESS_ALERT_SRC.ready)
  expect(second.audio.play).toHaveBeenCalledTimes(1)
})
```

还要覆盖：暂停/恢复文案完全一致、播放成功 resolve `true`、`onError` resolve `false`、构造异常
resolve `false`、`dispose()` 停止并销毁、迟到回调不重复 resolve。

- [ ] **Step 2: 运行测试，确认播放器尚不存在**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/alertAudio.test.ts
```

Expected: FAIL，提示无法解析 `./alertAudio`。

- [ ] **Step 3: 实现播放器并生成两条本地音频**

播放器复用 `miniapp/src/pages/game-session/gameAudio.ts` 已验证的 `InnerAudioContext`
生命周期模式，但不得读取游戏静音偏好；
本次患者安全告警始终尝试播放。超时固定 15 秒，所有失败都 resolve `false`。

在 macOS 生成中文本地音频并转换为 AAC/M4A：

```bash
mkdir -p miniapp/src/pages/shoulder-press/assets/audio
say -v Tingting "网络较慢，训练已暂停，请保持页面打开，等待视频上传。" \
  -o /tmp/motioncare-network-slow-paused.aiff
afconvert -f m4af -d aac /tmp/motioncare-network-slow-paused.aiff \
  miniapp/src/pages/shoulder-press/assets/audio/network_slow_paused.m4a
say -v Tingting "视频上传已恢复，可以继续训练。" \
  -o /tmp/motioncare-upload-recovered.aiff
afconvert -f m4af -d aac /tmp/motioncare-upload-recovered.aiff \
  miniapp/src/pages/shoulder-press/assets/audio/upload_recovered.m4a
```

检查文件非空、编码为 AAC，试听确认没有截字、静音或爆音：

```bash
ffprobe -v error -show_entries format=duration:stream=codec_name \
  miniapp/src/pages/shoulder-press/assets/audio/network_slow_paused.m4a
ffprobe -v error -show_entries format=duration:stream=codec_name \
  miniapp/src/pages/shoulder-press/assets/audio/upload_recovered.m4a
```

- [ ] **Step 4: 运行播放器测试和微信开发构建**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/alertAudio.test.ts
npm run build:weapp
```

Expected: 测试 PASS；构建产物包含两条 `.m4a` 且构建成功。

- [ ] **Step 5: 提交本地语音**

```bash
git add \
  miniapp/src/pages/shoulder-press/alertAudio.ts \
  miniapp/src/pages/shoulder-press/alertAudio.test.ts \
  miniapp/src/pages/shoulder-press/assets/audio/network_slow_paused.m4a \
  miniapp/src/pages/shoulder-press/assets/audio/upload_recovered.m4a
git commit -m "feat(miniapp): 增加录像缓冲语音告警"
```

---

### Task 4: 全屏录像页集成清理、缓冲暂停与语音

**Files:**
- Modify: `miniapp/src/pages/shoulder-press/camera.tsx`
- Modify: `miniapp/src/pages/shoulder-press/camera.config.ts`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx`
- Modify: `miniapp/src/app.scss`

**Interfaces:**
- Consumes:
  - `cleanupAndCheckShoulderPressStorage(...)` from Task 1；
  - `pendingShoulderPressLocalBytes(...)`、`nextShoulderPressBufferTransition(...)`、
    `canResumeShoulderPressFromBuffer(...)` from Task 2；
  - `createShoulderPressAlertPlayer()` from Task 3；
  - 现有 `ShoulderPressTrainingOverlay`、录像器、会话与后台单并发上传。
- Produces: 全屏录像页面，以及 `preflight | ready | recording | buffer_paused | buffer_ready` 的页面协调行为。

- [ ] **Step 1: 扩展 Taro 测试 harness 并写入失败的页面测试**

在 `pages.test.tsx` 的 Taro mock 中加入：

```ts
getFileSystemManager: vi.fn(() => ({
  getSavedFileList: vi.fn(),
  removeSavedFile: vi.fn(),
  unlink: vi.fn()
})),
createInnerAudioContext: vi.fn()
```

新增页面测试时，每条都要通过现有页面 harness 执行真实点击、Promise 推进和重渲染，并完成
下列精确断言：

- 点击首次开始后显示阻塞清理态；删除和第二次列表未完成时，`createPendingSession`、
  `camera.startRecord` 和计时器都是 0 次；精确 65MB 可用时各启动 1 次；
- 已有待上传会话时直接 `reLaunch` 到上传页，文件列表和删除都是 0 次；
- 可用空间为 `65MB - 1 byte` 时显示固定中文拦截文案，不创建会话、不开始录像；
- 空间不足态同时显示“重新清理”和“返回处方”；前者重新执行唯一预检任务，
  后者不创建会话并回到处方页；
- 清理期间连续点击两次，文件列表/删除/正式启动仍各只执行一组；
- 页面卸载后再 resolve 清理 Promise，不设状态、不创建会话、不启动录像；
- 上传未确认的本地分段在分段边界达到 65MB 时，`pauseTraining` 只执行 1 次，
  暂停语音只播放 1 次；
- `buffer_paused` 时上传 worker 继续执行；10MB 时仍不可继续，`10MB - 1 byte`
  时变为 `buffer_ready`、恢复语音只播放 1 次，且不自动调用 `camera.startRecord`；
- 服务端确认某分段后，立即调用既有本地文件删除路径；即使删除失败，该分段也不再计入
  `pendingBytes`、不重新上传；
- 65MB 前发生 `saveFile` 或本地文件失败时，当前有效分段和会话保留，页面进入
  `buffer_paused`，不再启动下一段；
- 点击“继续训练”后只恢复录像，不再清理、不新建会话、不覆盖首次
  `trainingStartedAt`；
- 缓冲暂停期间推进假时钟，正计时与倒计时数字不变；继续后再推进才增加；
- 缓冲暂停后进入后台再回到前台，根据最新会话重算缓存，即使已低于 10MB
  也只进入 `buffer_ready`，不自动恢复录像；
- 语音 Promise resolve `false` 或 reject 时，对应中文文字仍可见，缓冲状态不回退；
- 缓冲暂停时“结束训练”仍可点击，且复用已有结束去重锁；
- 根节点是 `training-camera-page`，Camera 使用 `training-camera-fullscreen`，旧 `page-hero` /
  `recording-dashboard` 不存在；覆盖层完整收到
  `started/videoUrl/elapsedMs/expectedDurationSeconds`，底部主按钮位于独立固定容器。

全屏结构测试至少断言：根节点为 `training-camera-page`、Camera 使用
`training-camera-fullscreen`、旧 `page-hero` / `recording-dashboard` 不存在、覆盖层仍收到
`started/videoUrl/elapsedMs/expectedDurationSeconds`、底部主按钮位于独立固定容器。

- [ ] **Step 2: 运行页面测试，确认旧布局与缺少预检导致失败**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/pages.test.tsx
```

Expected: 新增用例 FAIL；旧页面仍渲染 hero、卡片和滚动录像框。

- [ ] **Step 3: 接入 Promise 风格文件系统适配器**

在 `camera.tsx` 内只保留薄适配，不把遍历逻辑写回页面：

```ts
const fs = Taro.getFileSystemManager()
const listSavedFiles = () => new Promise<ShoulderPressSavedFile[]>((resolve, reject) => {
  fs.getSavedFileList({
    success: (result) => resolve(result.fileList ?? []),
    fail: reject
  })
})
const removeSavedFile = (filePath: string) => new Promise<void>((resolve, reject) => {
  fs.removeSavedFile({ filePath, success: () => resolve(), fail: reject })
})
```

将入口显式分成 `prepareAndStartTraining()` 和 `resumeTrainingAfterBufferReady()`。前者取得
页面级互斥锁并调用预检；仅 `kind === 'ready'` 时才调用共享的底层录像启动函数。
`pending_session` 进入强制上传页，`blocked` 显示 MB 文案，`cancelled` 静默结束。
列表读取异常统一显示“无法检查录像空间，请重试”，不得透传原始英文错误。

- [ ] **Step 4: 接入缓冲高低水位和语音代次**

每次会话更新后根据最新分段计算 `pendingBytes`，并调用纯状态函数。发生
`recording -> buffer_paused` 时：

1. 先让当前 5 秒分段完成；
2. 复用现有 `pauseTraining()`，不新增第二套停止录像锁；
3. 保持后台上传运行；
4. 设置缓冲暂停文字并播放 `pause`。

发生 `buffer_paused -> buffer_ready` 时播放 `ready` 并展示“继续训练”；只有患者点击且
`canResumeShoulderPressFromBuffer(latestPendingBytes)` 为真时才调用
`resumeTrainingAfterBufferReady()`。该函数只复用底层录像启动分支，不能再次清理、创建新会话或
覆盖首次开始时间。

实际 `saveFile`/本地文件异常必须把页面推进 `buffer_paused`，保留已知分段和重试入口；不要仅
显示错误后继续产生新分段。

- [ ] **Step 5: 改为全屏组件树和自定义导航**

`camera.config.ts`：

```ts
export default definePageConfig({
  navigationStyle: 'custom',
  disableScroll: true
})
```

页面核心结构固定为：

```tsx
<View className='training-camera-page'>
  <Camera className='training-camera-fullscreen' {...cameraProps} />
  <View className='training-camera-safe-top'>
    <View className='training-camera-back' onClick={handleBack}>‹</View>
  </View>
  <ShoulderPressTrainingOverlay {...overlayProps} />
  {preflightMessage ? <View className='training-preflight-overlay'>...</View> : null}
  {bufferMessage ? <View className='training-buffer-banner'>...</View> : null}
  <View className='training-camera-bottom-action'>
    <Button>{primaryActionText}</Button>
    {bufferPaused ? <Button onClick={requestManualFinishTraining}>结束训练</Button> : null}
  </View>
</View>
```

删除录像页旧 hero、说明、媒体标签、dashboard 和页面外进度文案。上传数字可作为不抢占画中画的
紧凑状态条保留。SCSS 必须使用 `env(safe-area-inset-top)` / `env(safe-area-inset-bottom)`，Camera
和遮罩固定 `inset: 0`；覆盖层仍遵守微信 Camera/Video 同层渲染约束。

- [ ] **Step 6: 运行肩部推举页面与全量小程序验证**

Run:

```bash
cd miniapp
npx vitest run \
  src/pages/shoulder-press/pages.test.tsx \
  src/pages/shoulder-press/storageGuard.test.ts \
  src/pages/shoulder-press/bufferGuard.test.ts \
  src/pages/shoulder-press/alertAudio.test.ts \
  src/pages/shoulder-press/recorder.test.ts
npm test
npm run build:weapp
TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api npm run build:weapp:prod
npx tsc --noEmit --pretty false
npx eslint src --ext .ts,.tsx
npx stylelint "src/**/*.scss"
```

Expected: 目标测试和全量测试 PASS；开发/生产构建 PASS；TypeScript、ESLint、Stylelint 相对实施
基线零新增错误。仓库既有静态错误必须报告准确数量，不能误称全绿。

- [ ] **Step 7: 提交全屏录像页集成**

```bash
git add \
  miniapp/src/pages/shoulder-press/camera.tsx \
  miniapp/src/pages/shoulder-press/camera.config.ts \
  miniapp/src/pages/shoulder-press/pages.test.tsx \
  miniapp/src/app.scss
git commit -m "feat(miniapp): 集成全屏录像与缓存暂停恢复"
```

---

### Task 5: 后端 600 段边界与大量短分段回归

**Files:**
- Modify: `backend/config/settings.py`
- Modify: `deploy/docker-compose.prod.yml`
- Modify: `deploy/env.production.example`
- Modify: `backend/apps/patient_app/tests/test_patient_app_video_api.py`
- Modify: `backend/apps/training/tests/test_video_tasks.py`

**Interfaces:**
- Consumes: 现有分段上传/finalize API、`TrainingVideoSegment`、`VideoAssemblyJob` 和后台合并任务。
- Produces: `TRAINING_VIDEO_MAX_SEGMENTS=600` 的显式生产边界；480 个连续 5 秒分段可 finalize，601 被拒绝。

- [ ] **Step 1: 写入失败的 480/600/601 边界测试**

在 `test_patient_app_video_api.py` 使用 `bulk_create` 避免 480 次 HTTP 上传：

```py
@pytest.mark.django_db
def test_finalize_accepts_480_five_second_segments(
    project_patient, doctor, active_prescription, settings, tmp_path,
    django_capture_on_commit_callbacks,
):
    settings.TRAINING_VIDEO_MAX_SEGMENTS = 600
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    video = TrainingVideo.objects.get(pk=session.data['video_id'])
    rows = []
    for index in range(480):
        path = segment_path(video, index)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x')
        rows.append(TrainingVideoSegment(
            training_video=video,
            index=index,
            duration_ms=5_000,
            size_bytes=1,
            sha256=f'{index:064x}',
            relative_path=path.relative_to(tmp_path).as_posix(),
            status=TrainingVideoSegment.Status.UPLOADED,
            uploaded_at=timezone.now(),
        ))
    TrainingVideoSegment.objects.bulk_create(rows)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            _finalize_url(video),
            _finalize_payload(segment_count=480, actual_duration_seconds=2400),
            format='json',
        )

    assert response.status_code == 202
    assert VideoAssemblyJob.objects.filter(training_video=video).count() == 1
```

先抽取上述代码为本测试文件内的 `_bulk_create_uploaded_segments(video, root, count, duration_ms)`
助手，480 和 600 两个用例共用。再增加下列精确断言：

- 未覆盖环境变量时 `settings.TRAINING_VIDEO_MAX_SEGMENTS == 600`；
- 创建 600 个连续已上传分段后，`segment_count=600` 返回 202 并仅创建 1 个
  `VideoAssemblyJob`；
- `segment_count=601` 返回 400，错误文案含“分段”，且不创建 job；
- 上传 `index=600` 返回 400，`_staged_segment_path(..., 600)` 不存在，
  `_assert_no_partial_files(tmp_path)` 通过。

在 `test_video_tasks.py` 把现有 `_pending_job(...)` 扩展为可选 `segment_count` 和每段时长，
为 480 段写入有序的一字节 staging 文件和数据库行。在新测试中：

- 设置 `expected_segment_count=uploaded_segment_count=480`、`actual_duration_seconds=2400`；
- mock `assemble_video` 返回 `_assembly_result(video, duration=2400)`，mock
  `upload_and_publish_local_video` 和两个 cleanup task；
- 调用 `process_video_assembly_job(job.id)` 后断言 `assemble_video` 的第一个位置参数是按
  `000000.mp4..000479.mp4` 排序的 480 个路径；
- 断言 `TrainingRecord.objects.count() == 1`、记录时长为 40 分钟且 job 成功；
- 再次调用同一 job 仍只有 1 条记录且不再拼接/上传。

该测试不运行真实 FFmpeg、ffprobe 或七牛请求。

- [ ] **Step 2: 运行测试，确认默认 200 段上限导致失败**

Run:

```bash
cd backend
pytest \
  apps/patient_app/tests/test_patient_app_video_api.py \
  apps/training/tests/test_video_tasks.py -q
```

Expected: 480 段 finalize 被现有 200 上限拒绝，或默认值断言失败。

- [ ] **Step 3: 把配置边界提高到 600 并显式传入生产容器**

`backend/config/settings.py`：

```py
TRAINING_VIDEO_MAX_SEGMENTS = int(
    os.getenv("TRAINING_VIDEO_MAX_SEGMENTS", "600")
)
```

`deploy/docker-compose.prod.yml` 的后端共享环境：

```yaml
TRAINING_VIDEO_MAX_SEGMENTS: ${TRAINING_VIDEO_MAX_SEGMENTS:-600}
```

`deploy/env.production.example`：

```dotenv
TRAINING_VIDEO_MAX_SEGMENTS=600
```

不要取消 `index >= max`、总数量和 finalize 数量的现有后端防护。

- [ ] **Step 4: 运行后端目标、全量与迁移检查**

Run:

```bash
cd backend
pytest \
  apps/patient_app/tests/test_patient_app_video_api.py \
  apps/training/tests/test_video_tasks.py -q
pytest -q
python manage.py makemigrations --check --dry-run
```

Expected: 全部 PASS；无新 migration。

- [ ] **Step 5: 提交后端短分段边界**

```bash
git add \
  backend/config/settings.py \
  deploy/docker-compose.prod.yml \
  deploy/env.production.example \
  backend/apps/patient_app/tests/test_patient_app_video_api.py \
  backend/apps/training/tests/test_video_tasks.py
git commit -m "fix(training): 支持肩部推举大量短分段"
```

---

### Task 6: 最终验证、人工门禁与文档收口

**Files:**
- Modify: `docs/superpowers/plans/2026-08-09-wechat-shoulder-press-fullscreen-storage-guard.md`
- Modify after all gates pass: `docs/superpowers/specs/2026-08-09-wechat-shoulder-press-fullscreen-storage-guard-design.md`

**Interfaces:**
- Consumes: Task 1–5 的全部实现与测试。
- Produces: 可供合并决策的验证证据；人工门禁未完成时保持 `implementing`，不得发布。

- [ ] **Step 1: 运行最终自动化验证**

Run:

```bash
cd miniapp
npm test
npm run build:weapp
TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api npm run build:weapp:prod
npx tsc --noEmit --pretty false
npx eslint src --ext .ts,.tsx
npx stylelint "src/**/*.scss"

cd ../backend
pytest -q
python manage.py makemigrations --check --dry-run

cd ..
git diff --check
git status --short
```

Expected: 测试、两种微信构建、后端测试、迁移检查和 diff check 通过；静态检查若仍有既有错误，
必须与实施基线规范化对比并证明零新增。

- [ ] **Step 2: 微信开发者工具验收**

- [ ] 页面是全屏相机，不再出现 hero、说明卡、dashboard 或滚动条。
- [ ] 开始训练先显示清理等待，完成前不创建训练会话、不启动计时。
- [ ] 左侧正倒计时、右侧循环示范视频和底部结束按钮同屏。
- [ ] 每约 5 秒产生分段，上传计数连续增加，画中画与计时不重置。
- [ ] 清理失败/空间不足使用中文安全文案并可重试。

- [ ] **Step 3: iOS 与 Android 真机验收**

- [ ] iOS：Camera/Video 同层无黑屏或层级倒置，安全区域不遮挡返回、计时、画中画和底部按钮。
- [ ] Android：相同行为在至少一台真机通过，并覆盖不同屏幕比例。
- [ ] 慢网/断网：待上传缓存达到 65MB 后在分段边界暂停，只播放一次暂停语音。
- [ ] 上传恢复：缓存严格低于 10MB 后只播放一次恢复语音，不自动录像，点击继续后计时续算。
- [ ] 语音失败/手机静音：文字告警仍清晰，上传和状态转换不受影响。
- [ ] 提前结束、处方倒计时自动结束、进入后台暂停和恢复均不产生重复训练记录。
- [ ] 10 分钟训练可完成约 120 个分段的上传、服务器合并和七牛发布。

- [ ] **Step 4: 更新执行记录和状态**

每个 Task 完成后在本计划顶部追加：

```text
执行记录（2026-08-09, codex）：Task N 已落地于 commit <short-sha>。
```

仅在所有人工门禁通过后：

- 把本计划和关联设计状态改为 `implemented`；
- 记录微信开发版/体验版版本号、测试设备和结果；
- 执行 `superpowers:verification-before-completion`；
- 再执行 `superpowers:finishing-a-development-branch`，向用户提供合并选择。

- [ ] **Step 5: 提交验证收口文档**

```bash
git add \
  docs/superpowers/plans/2026-08-09-wechat-shoulder-press-fullscreen-storage-guard.md \
  docs/superpowers/specs/2026-08-09-wechat-shoulder-press-fullscreen-storage-guard-design.md
git commit -m "docs(miniapp): 记录全屏录像与存储保护验收结果"
```
