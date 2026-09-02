# 运动动作说明预生成语音 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

执行记录（2026-09-02, Codex）：代码提交 `3cefec4` 已合并至 `main`；最终全量验证为 48 个测试文件、726 项测试通过，开发与生产微信构建成功。微信开发版 `7.0.3` 已通过 CLI 上传（AppID `wx095c9a6c41b60112`，描述“动作说明语音优化”），用户完成体验验收。

**Goal:** 在微信小程序统一运动动作说明页中，为 5 个正式动作增加已确认的小米 MiMo 本地语音、自动播放、手动重播和失败降级能力。

**Architecture:** 使用独立静态音频清单按 `source_key` 精确映射本地 M4A，并将现有 `motion-training/alertAudio.ts` 泛化为可配置超时的公共单实例播放器；原网络告警 API 保持不变并组合复用同一底层。页面只管理自动播放时机、可见状态和导航前停止，不接入后端或运行时 TTS，也不再新建第二套音频生命周期实现。

**Tech Stack:** Taro 4.2、React 18、TypeScript 5.4、Vitest 3、Sass、微信小程序静态 M4A、`Taro.createInnerAudioContext`

**Spec:** `docs/superpowers/specs/2026-09-01-motion-instruction-voice-design.md`

> 状态：implemented
> 日期：2026-09-01
> 范围：5 个正式运动动作说明的预生成语音资源、播放器和说明页交互。
> 关联：`docs/superpowers/specs/2026-09-01-motion-instruction-voice-design.md`
> 实施基线 commit：`09e6c2b`

## Global Constraints

- 只使用已经试听确认的小米 `mimo-v2.5-tts-voicedesign` 生成结果；不重新生成、不替换音色。
- 只覆盖 5 个正式 `source_key`：`motion-aerobic-high-knee`、`motion-balance-sit-stand`、`motion-resistance-row`、`motion-resistance-leg-kickback`、`motion-resistance-shoulder-press`。
- 语音是增强能力：文字始终可见，播放失败不得阻塞动作预览或训练。
- 不新增后端接口、在线 TTS、前端密钥、依赖包或医生端改动。
- 任意时刻最多一个动作说明音频实例；页面隐藏、卸载、进入预览或训练前停止播放。
- 播放器超时设为 `90_000ms`，覆盖当前最长约 54 秒的音频并保留网络无关的本地解码余量。
- `MIMO_API_KEY` 不得写入源码、测试、构建产物、文档或 Git 历史。
- 当前用户未授权 Git 提交；下列提交步骤只有在用户明确授权后才执行，默认跳过。
- 保留现有工作区和 worktree 中其他 AI 工具的改动，不修改 `.风格复制模式.swn`、`.impeccable/critique/` 或认知游戏变更。

## File Structure

### 新建

- `miniapp/src/features/motion-training/instructionAudioManifest.ts`：5 个正式 `source_key` 与本地 M4A 的唯一映射及查询函数。
- `miniapp/src/features/motion-training/instructionAudioManifest.test.ts`：验证完整映射、精确匹配和资源存在性。
- `miniapp/src/features/motion-training/assets/audio/instructions/*.m4a`：5 个已确认的小米 MiMo 语音文件。

### 修改

- `miniapp/src/features/motion-training/alertAudio.ts`：泛化现有播放器底层，保留网络告警公开 API，并支持动作说明的 90 秒超时。
- `miniapp/src/features/motion-training/alertAudio.test.ts`：在现有回归测试上增加公共播放器契约测试。
- `miniapp/src/pages/motion-training/index.tsx`：加载成功后自动播放一次，展示重播按钮和失败提示，导航及生命周期停止播放。
- `miniapp/src/pages/shoulder-press/pages.test.tsx`：在现有统一运动页集成测试中覆盖自动播放、重播、失败降级和停止行为。
- `miniapp/src/app.scss`：增加适老化语音按钮容器和错误提示样式。

---

### Task 1: 固化已确认音频并建立精确资源映射

**Files:**
- Create: `miniapp/src/features/motion-training/instructionAudioManifest.ts`
- Create: `miniapp/src/features/motion-training/instructionAudioManifest.test.ts`
- Create: `miniapp/src/features/motion-training/assets/audio/instructions/motion-aerobic-high-knee.m4a`
- Create: `miniapp/src/features/motion-training/assets/audio/instructions/motion-balance-sit-stand.m4a`
- Create: `miniapp/src/features/motion-training/assets/audio/instructions/motion-resistance-row.m4a`
- Create: `miniapp/src/features/motion-training/assets/audio/instructions/motion-resistance-leg-kickback.m4a`
- Create: `miniapp/src/features/motion-training/assets/audio/instructions/motion-resistance-shoulder-press.m4a`

**Interfaces:**
- Consumes: `MotionSourceKey` 与 `isOfficialMotionSourceKey(value)`，来自 `miniapp/src/features/motion-training/catalog.ts`。
- Produces: `MOTION_INSTRUCTION_AUDIO_SRC: Record<MotionSourceKey, string>`。
- Produces: `getMotionInstructionAudioSrc(sourceKey: unknown): string | undefined`。

- [x] **Step 1: 写资源映射失败测试**

新建 `instructionAudioManifest.test.ts`：

```ts
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { OFFICIAL_MOTION_SOURCE_KEYS } from './catalog'
import {
  getMotionInstructionAudioSrc,
  MOTION_INSTRUCTION_AUDIO_SRC,
} from './instructionAudioManifest'

describe('motion instruction audio manifest', () => {
  it('maps every official motion source key to one local m4a file', () => {
    expect(Object.keys(MOTION_INSTRUCTION_AUDIO_SRC)).toEqual([
      ...OFFICIAL_MOTION_SOURCE_KEYS,
    ])

    for (const sourceKey of OFFICIAL_MOTION_SOURCE_KEYS) {
      const src = getMotionInstructionAudioSrc(sourceKey)
      expect(src).toBe(
        `/features/motion-training/assets/audio/instructions/${sourceKey}.m4a`,
      )
      expect(existsSync(resolve(`src${src}`))).toBe(true)
    }
  })

  it('does not infer audio for unknown or malformed keys', () => {
    expect(getMotionInstructionAudioSrc('motion-resistance-row-extra')).toBeUndefined()
    expect(getMotionInstructionAudioSrc('坐姿划船')).toBeUndefined()
    expect(getMotionInstructionAudioSrc(undefined)).toBeUndefined()
  })
})
```

- [x] **Step 2: 运行测试并确认因模块不存在而失败**

Run:

```bash
cd miniapp
npx vitest run src/features/motion-training/instructionAudioManifest.test.ts
```

Expected: FAIL，错误包含 `Cannot find module './instructionAudioManifest'`。

- [x] **Step 3: 复制已确认的 5 个试听文件并校验字节一致**

从主 checkout 的已确认试听目录复制到当前实施 worktree：

```bash
mkdir -p miniapp/src/features/motion-training/assets/audio/instructions
cp /Users/nick/my_dev/workout/MotionCare/.superpowers/brainstorm/motion-instruction-voice-preview/01-high-knee.m4a miniapp/src/features/motion-training/assets/audio/instructions/motion-aerobic-high-knee.m4a
cp /Users/nick/my_dev/workout/MotionCare/.superpowers/brainstorm/motion-instruction-voice-preview/02-sit-stand.m4a miniapp/src/features/motion-training/assets/audio/instructions/motion-balance-sit-stand.m4a
cp /Users/nick/my_dev/workout/MotionCare/.superpowers/brainstorm/motion-instruction-voice-preview/03-seated-row.m4a miniapp/src/features/motion-training/assets/audio/instructions/motion-resistance-row.m4a
cp /Users/nick/my_dev/workout/MotionCare/.superpowers/brainstorm/motion-instruction-voice-preview/04-leg-kickback.m4a miniapp/src/features/motion-training/assets/audio/instructions/motion-resistance-leg-kickback.m4a
cp /Users/nick/my_dev/workout/MotionCare/.superpowers/brainstorm/motion-instruction-voice-preview/05-shoulder-press.m4a miniapp/src/features/motion-training/assets/audio/instructions/motion-resistance-shoulder-press.m4a
shasum -a 256 miniapp/src/features/motion-training/assets/audio/instructions/*.m4a
```

Expected hashes,按文件名字典序：

```text
d5650f7b5bee482aa32953e1f06e974cea6d97aa18bc007c5fbc7b5ec9302674  motion-aerobic-high-knee.m4a
b6e32e46d40466ded6a451aafab13dc3e6ca746e5dd53643055aa00168f66e24  motion-balance-sit-stand.m4a
725ea66457c3ff7fac511a7fc3713eb2848f45c6fc96c070029fbb70342882e1  motion-resistance-leg-kickback.m4a
4e47b657633bf1527d68d15d7c687626ccedaa1c27a9402ae258eee6aa7a64cf  motion-resistance-row.m4a
3fed2a4235efa9343b68fbcb30d453cfb763c63f8b145bc6308fad7773382809  motion-resistance-shoulder-press.m4a
```

- [x] **Step 4: 实现静态资源映射**

新建 `instructionAudioManifest.ts`：

```ts
import { isOfficialMotionSourceKey, type MotionSourceKey } from './catalog'

import './assets/audio/instructions/motion-aerobic-high-knee.m4a'
import './assets/audio/instructions/motion-balance-sit-stand.m4a'
import './assets/audio/instructions/motion-resistance-row.m4a'
import './assets/audio/instructions/motion-resistance-leg-kickback.m4a'
import './assets/audio/instructions/motion-resistance-shoulder-press.m4a'

export const MOTION_INSTRUCTION_AUDIO_SRC: Record<MotionSourceKey, string> = {
  'motion-aerobic-high-knee': '/features/motion-training/assets/audio/instructions/motion-aerobic-high-knee.m4a',
  'motion-balance-sit-stand': '/features/motion-training/assets/audio/instructions/motion-balance-sit-stand.m4a',
  'motion-resistance-row': '/features/motion-training/assets/audio/instructions/motion-resistance-row.m4a',
  'motion-resistance-leg-kickback': '/features/motion-training/assets/audio/instructions/motion-resistance-leg-kickback.m4a',
  'motion-resistance-shoulder-press': '/features/motion-training/assets/audio/instructions/motion-resistance-shoulder-press.m4a',
}

export function getMotionInstructionAudioSrc(sourceKey: unknown): string | undefined {
  return isOfficialMotionSourceKey(sourceKey)
    ? MOTION_INSTRUCTION_AUDIO_SRC[sourceKey]
    : undefined
}
```

- [x] **Step 5: 运行映射测试并确认通过**

Run:

```bash
cd miniapp
npx vitest run src/features/motion-training/instructionAudioManifest.test.ts
```

Expected: PASS，2 tests passed。

- [x] **Step 6: 仅在用户授权后提交本任务**

```bash
git add miniapp/src/features/motion-training/instructionAudioManifest.ts miniapp/src/features/motion-training/instructionAudioManifest.test.ts miniapp/src/features/motion-training/assets/audio/instructions
git commit -m "feat(小程序): 内置运动动作说明语音"
```

---

### Task 2: 泛化并复用现有运动告警播放器

**Files:**
- Modify: `miniapp/src/features/motion-training/alertAudio.ts`
- Modify: `miniapp/src/features/motion-training/alertAudio.test.ts`
- Verify: `miniapp/src/pages/shoulder-press/alertAudio.test.ts`

**Interfaces:**
- Produces: `MotionTrainingAudioPlayerOptions = { timeoutMs?: number }`。
- Produces: `MotionTrainingAudioPlayer`，包含 `play(src: string): Promise<boolean>`、`stop(): void`、`dispose(): void`。
- Produces: `createMotionTrainingAudioPlayer(options?: MotionTrainingAudioPlayerOptions): MotionTrainingAudioPlayer`。
- Preserves: `MotionTrainingAlertPlayer` 与 `createMotionTrainingAlertPlayer()` 的现有公开接口和行为。

- [x] **Step 1: 在现有告警测试中先写公共播放器失败测试**

在 `miniapp/src/features/motion-training/alertAudio.test.ts` 的 import 中增加 `createMotionTrainingAudioPlayer`，并追加：

```ts
it('reuses the player for an arbitrary local source with a configurable timeout', async () => {
  const { audio, callbacks } = audioContextHarness()
  taroMock.createInnerAudioContext.mockReturnValue(audio)
  const player = createMotionTrainingAudioPlayer({ timeoutMs: 90_000 })

  const playback = player.play('/features/motion-training/assets/audio/instructions/motion-resistance-row.m4a')

  expect(audio.src).toBe('/features/motion-training/assets/audio/instructions/motion-resistance-row.m4a')
  expect(audio.play).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(89_999)
  expect(audio.destroy).not.toHaveBeenCalled()
  callbacks.ended?.()
  await expect(playback).resolves.toBe(true)
  expect(audio.destroy).toHaveBeenCalledTimes(1)
  expect(vi.getTimerCount()).toBe(0)
})

it('exposes an idempotent stop for page lifecycle cleanup', async () => {
  const { audio } = audioContextHarness()
  taroMock.createInnerAudioContext.mockReturnValue(audio)
  const player = createMotionTrainingAudioPlayer({ timeoutMs: 90_000 })
  const playback = player.play('/features/motion-training/assets/audio/instructions/motion-resistance-row.m4a')

  player.stop()
  player.stop()

  await expect(playback).resolves.toBe(false)
  expect(audio.stop).toHaveBeenCalledTimes(1)
  expect(audio.destroy).toHaveBeenCalledTimes(1)
})
```

- [x] **Step 2: 运行测试并确认因公共工厂尚未导出而失败**

Run:

```bash
cd miniapp
npx vitest run src/features/motion-training/alertAudio.test.ts
```

Expected: FAIL，错误指出 `createMotionTrainingAudioPlayer` 不存在或不是函数；原有 11 项告警测试在新增测试之前保持通过。

- [x] **Step 3: 在原模块中抽取可配置的公共播放器**

在 `alertAudio.ts` 保留现有常量、文字、资源路径和告警类型，新增：

```ts
export type MotionTrainingAudioPlayerOptions = {
  timeoutMs?: number
}

export type MotionTrainingAudioPlayer = {
  play: (src: string) => Promise<boolean>
  stop: () => void
  dispose: () => void
}

export function createMotionTrainingAudioPlayer(
  options: MotionTrainingAudioPlayerOptions = {},
): MotionTrainingAudioPlayer
```

把当前 `createMotionTrainingAlertPlayer` 内已经验证的 `activePlayback`、`settled`、timer、`audio.stop()`、`audio.destroy()` 和同步回调防护移动到该公共工厂中；唯一参数差异是 `audio.src = src`，超时取 `options.timeoutMs ?? 15_000`。公共 `stop()` 与 `dispose()` 都调用同一个当前活动实例 `stop()`，所以重复调用安全。

随后用组合而不是复制实现告警包装器：

```ts
export function createMotionTrainingAlertPlayer(): MotionTrainingAlertPlayer {
  const player = createMotionTrainingAudioPlayer({ timeoutMs: 15_000 })
  return {
    play: (kind) => player.play(MOTION_TRAINING_ALERT_SRC[kind]),
    dispose: player.dispose,
  }
}
```

禁止复制第二份 `Taro.createInnerAudioContext` 状态机；`alertAudio.ts` 中只能有一个公共播放实现。

- [x] **Step 4: 运行公共与兼容性测试并确认通过**

Run:

```bash
cd miniapp
npx vitest run src/features/motion-training/alertAudio.test.ts src/pages/shoulder-press/alertAudio.test.ts
```

Expected: PASS；公共播放器新增测试通过，两个位置的原告警回归测试保持通过，证明既有公开接口未改变。

- [x] **Step 5: 仅在用户授权后提交本任务**

```bash
git add miniapp/src/features/motion-training/alertAudio.ts miniapp/src/features/motion-training/alertAudio.test.ts
git commit -m "refactor(小程序): 复用运动训练语音播放器"
```

---

### Task 3: 接入说明页自动播放、重播和失败降级

**Files:**
- Modify: `miniapp/src/pages/motion-training/index.tsx`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx`
- Modify: `miniapp/src/app.scss`

**Interfaces:**
- Consumes: `createMotionTrainingAudioPlayer({ timeoutMs: 90_000 })` 与 `MotionTrainingAudioPlayer`。
- Consumes: `getMotionInstructionAudioSrc(action.source_key)`，决定是否展示语音控制。
- Produces: 页面内部状态 `idle | playing | played`、非阻塞失败文案和导航前停止行为。

- [x] **Step 1: 在现有页面 harness 中加入播放器 mock**

在 `pages.test.tsx` 的 hoisted harness 区域加入：

```ts
const motionInstructionAudioHarness = vi.hoisted(() => ({
  play: vi.fn(async () => true),
  stop: vi.fn(),
  dispose: vi.fn(),
  getSrc: vi.fn((sourceKey: unknown) => (
    typeof sourceKey === 'string' && sourceKey.startsWith('motion-')
      ? `/features/motion-training/assets/audio/instructions/${sourceKey}.m4a`
      : undefined
  )),
}))
```

扩展文件中已经存在的 `../../features/motion-training/alertAudio` mock，在保留 `createMotionTrainingAlertPlayer` 和告警文字的同时增加公共工厂：

```ts
createMotionTrainingAudioPlayer: () => motionInstructionAudioHarness,
```

另增加资源映射 mock：

```ts
vi.mock('../../features/motion-training/instructionAudioManifest', () => ({
  getMotionInstructionAudioSrc: motionInstructionAudioHarness.getSrc,
}))
```

在现有 `beforeEach` 中恢复默认值：

```ts
motionInstructionAudioHarness.play.mockReset().mockResolvedValue(true)
motionInstructionAudioHarness.stop.mockReset()
motionInstructionAudioHarness.dispose.mockReset()
motionInstructionAudioHarness.getSrc.mockReset().mockImplementation((sourceKey: unknown) => (
  typeof sourceKey === 'string' && sourceKey.startsWith('motion-')
    ? `/features/motion-training/assets/audio/instructions/${sourceKey}.m4a`
    : undefined
))
```

- [x] **Step 2: 写页面行为失败测试**

在统一运动说明页现有测试附近增加：

```ts
it('自动播放一次并在完成后提供重新播放', async () => {
  const autoPlayback = deferred<boolean>()
  motionInstructionAudioHarness.play.mockReturnValueOnce(autoPlayback.promise)
  const page = renderPage(ShoulderPressGuidePage)
  await flushPromises()
  page.rerender()

  expect(motionInstructionAudioHarness.play).toHaveBeenCalledTimes(1)
  expect(motionInstructionAudioHarness.play).toHaveBeenCalledWith(
    '/features/motion-training/assets/audio/instructions/motion-resistance-shoulder-press.m4a',
  )
  expect(findButtonByText(page.element, '正在播放说明').props.disabled).toBe(true)

  autoPlayback.resolve(true)
  await flushPromises()
  page.rerender()
  clickButtonByText(page.element, '重新播放说明')

  expect(motionInstructionAudioHarness.play).toHaveBeenCalledTimes(2)
  page.rerender()
  expect(motionInstructionAudioHarness.play).toHaveBeenCalledTimes(2)
})

it('语音失败后保留文字、恢复重播并允许继续训练', async () => {
  motionInstructionAudioHarness.play.mockResolvedValueOnce(false)
  const page = renderPage(ShoulderPressGuidePage)
  await flushPromises()
  page.rerender()

  expect(textContent(page.element)).toContain('保持正面，缓慢推举。')
  expect(textContent(page.element)).toContain('语音播放失败，请阅读文字说明')
  expect(findButtonByText(page.element, '重新播放说明').props.disabled).not.toBe(true)

  clickButtonByText(page.element, '开始训练')
  expect(motionInstructionAudioHarness.stop).toHaveBeenCalled()
  expect(taroHarness.taroMock.navigateTo).toHaveBeenCalledWith({
    url: '/pages/motion-training/camera?actionId=42',
  })
})

it('进入预览、页面隐藏和卸载都会停止或销毁语音', async () => {
  const page = renderPage(ShoulderPressGuidePage)
  await flushPromises()
  page.rerender()

  clickButtonByText(page.element, '动作预览')
  expect(motionInstructionAudioHarness.stop).toHaveBeenCalledTimes(1)

  taroHarness.hideCallbacks[0]?.()
  expect(motionInstructionAudioHarness.stop).toHaveBeenCalledTimes(2)

  page.unmount()
  expect(motionInstructionAudioHarness.dispose).toHaveBeenCalledTimes(1)
})

it('无映射动作不播放也不展示语音按钮', async () => {
  motionInstructionAudioHarness.getSrc.mockReturnValue(undefined)
  const page = renderPage(ShoulderPressGuidePage)
  await flushPromises()
  page.rerender()

  expect(motionInstructionAudioHarness.play).not.toHaveBeenCalled()
  expect(textContent(page.element)).not.toContain('播放说明')
  expect(textContent(page.element)).not.toContain('语音播放失败')
})
```

把 `MOTION_ACTION_CASES` 的参数化说明页测试增强为逐项断言 `play(getMotionInstructionAudioSrc(actionCase.sourceKey))` 对应的精确本地路径，从而明确覆盖 5 个正式动作；另加一次 `page.rerender()` 并断言调用次数不增加，覆盖页面恢复或普通重渲染不重复自动播放。

- [x] **Step 3: 运行页面测试并确认失败原因是交互尚未接入**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/pages.test.tsx
```

Expected: FAIL，失败集中在找不到“正在播放说明/重新播放说明”、播放器未调用或导航前未停止。

- [x] **Step 4: 在说明页实现播放生命周期**

修改 `miniapp/src/pages/motion-training/index.tsx`：

1. 从 `@tarojs/taro` 引入 `useDidHide`；从 React 引入 `useCallback`、`useRef`。
2. 创建一次复用的 `MotionTrainingAudioPlayer`，并维护：

```ts
type InstructionAudioStatus = 'idle' | 'playing' | 'played'

const instructionPlayerRef = useRef<MotionTrainingAudioPlayer | null>(null)
const autoPlayedSourceKeyRef = useRef<string | null>(null)
const playbackAttemptRef = useRef(0)
const [instructionAudioStatus, setInstructionAudioStatus] = useState<InstructionAudioStatus>('idle')
const [instructionAudioError, setInstructionAudioError] = useState('')

if (!instructionPlayerRef.current) {
  instructionPlayerRef.current = createMotionTrainingAudioPlayer({ timeoutMs: 90_000 })
}
```

3. 实现稳定的 `playInstruction(sourceKey)`：先通过 `getMotionInstructionAudioSrc` 取得精确路径；无映射时直接返回。递增 `playbackAttemptRef`，清空旧错误并设为 `playing`；调用 `player.play(src)` 后，只有 attempt 仍是当前值时更新 UI。返回 `true` 设为 `played`；返回 `false` 设为 `played` 并显示“语音播放失败，请阅读文字说明”。页面主动停止前必须先递增 attempt，使停止导致的 `false` 结果失效，不显示错误。
4. 动作加载成功且 `getMotionInstructionAudioSrc(action.source_key)` 存在时，仅当 `autoPlayedSourceKeyRef.current !== action.source_key` 执行一次自动播放。
5. 动作 `source_key` 改变时先停止旧播放、递增 attempt、清理旧错误和状态，再为新 key 自动播放。
6. `useDidHide` 调用无 UI 更新的停止函数；卸载 cleanup 调用 `dispose()` 并使旧 Promise 失效。
7. “开始训练”和“动作预览”处理器先停止播放器，再执行原导航调用；停止异常不得阻断导航。

在动作说明文字后、底部主操作区前增加：

```tsx
{action && getMotionInstructionAudioSrc(action.source_key) ? (
  <View className='motion-training-instruction-audio-controls'>
    <Button
      className='secondary-button full-button motion-training-instruction-audio-button'
      disabled={instructionAudioStatus === 'playing'}
      onClick={() => void playInstruction(action.source_key)}
    >
      {instructionAudioStatus === 'playing'
        ? '正在播放说明'
        : instructionAudioStatus === 'played'
          ? '重新播放说明'
          : '播放动作说明'}
    </Button>
    {instructionAudioError ? (
      <Text className='motion-training-instruction-audio-error'>
        {instructionAudioError}
      </Text>
    ) : null}
  </View>
) : null}
```

- [x] **Step 5: 增加适老化样式**

在 `miniapp/src/app.scss` 的 `.motion-training-action-instruction` 附近增加：

```scss
.motion-training-instruction-audio-controls {
  margin-top: 18px;
}

.motion-training-instruction-audio-button {
  min-height: 72px;
  font-size: 24px;
  font-weight: 800;
}

.motion-training-instruction-audio-error {
  display: block;
  margin-top: 12px;
  color: #b42318;
  font-size: 22px;
  line-height: 1.5;
}
```

- [x] **Step 6: 运行页面及播放器相关测试并确认通过**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/pages.test.tsx src/features/motion-training/alertAudio.test.ts src/pages/shoulder-press/alertAudio.test.ts src/features/motion-training/instructionAudioManifest.test.ts
```

Expected: PASS，现有统一运动页面测试和新增语音测试全部通过。

- [x] **Step 7: 仅在用户授权后提交本任务**

```bash
git add miniapp/src/pages/motion-training/index.tsx miniapp/src/pages/shoulder-press/pages.test.tsx miniapp/src/app.scss
git commit -m "feat(小程序): 接入动作说明语音交互"
```

---

### Task 4: 完整验证、构建产物检查和人工验收

**Files:**
- Verify: `miniapp/src/features/motion-training/assets/audio/instructions/*.m4a`
- Verify: `miniapp/dist/`
- Update: `docs/superpowers/plans/2026-09-01-motion-instruction-voice.md`（只勾选实际完成步骤并追加执行记录）
- Update: `.superpowers/sdd/2026-09-01-motion-instruction-voice/progress.md`（若本轮 SDD 工作流已建立该账本）

**Interfaces:**
- Consumes: Tasks 1–3 的完整实现。
- Produces: 可复查的测试、构建、音频格式和人工交互证据。

- [x] **Step 1: 运行全部小程序测试**

Run:

```bash
cd miniapp
npm test
```

Expected: 所有 Vitest 测试通过；无未处理 Promise rejection、未清理 timer 或新增 warning。

- [x] **Step 2: 运行开发和生产构建**

Run:

```bash
cd miniapp
npm run build:weapp
npm run build:weapp:prod
```

Expected: 两次构建退出码均为 0；5 个 M4A 进入对应微信小程序构建产物，源码中没有 `MIMO_API_KEY`。

- [x] **Step 3: 校验音频编码、声道、采样率和时长**

Run:

```bash
for audio_file in miniapp/src/features/motion-training/assets/audio/instructions/*.m4a; do
  ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,sample_rate,channels:format=duration,size -of compact=p=0:nk=1 "$audio_file"
done
```

Expected:

- 5 个文件均为 `aac`、`24000Hz`、单声道。
- 时长分别约为 44.416、47.488、51.968、54.016、50.688 秒。
- 文件均可解析且大小非 0。

- [x] **Step 4: 检查密钥和资源引用边界**

Run:

```bash
rg -n "MIMO_API_KEY|api\.xiaomimimo\.com" miniapp/src miniapp/dist
rg -n "motion-(aerobic-high-knee|balance-sit-stand|resistance-row|resistance-leg-kickback|resistance-shoulder-press)\.m4a" miniapp/dist
```

Expected: 第一条无输出；第二条能确认 5 个本地资源被构建引用。若构建器重命名资源，则改用 `find miniapp/dist -type f -name '*.m4a'` 和文件哈希确认 5 个文件存在，而不是修改业务代码迎合文件名。

- [x] **Step 5: 在微信开发者工具或真机完成交互验收**

按 5 个正式动作逐项检查：

1. 首次进入说明页自动播放正确语音一次。
2. 播放中按钮显示“正在播放说明”且不可重复点击。
3. 播放结束后显示“重新播放说明”，点击后从头播放。
4. 普通重渲染、切后台再返回不重复自动播放。
5. 点击“动作预览”或“开始训练”后语音立即停止且导航成功。
6. 模拟静音、系统中断或播放器错误时，文字仍可读，出现“语音播放失败，请阅读文字说明”，训练入口保持可用。
7. 确认 5 段语音内容、音色和语速与已批准试听版一致。

- [x] **Step 6: 复查工作区边界和计划完成记录**

Run:

```bash
git status --short
git diff --check
git diff --stat 09e6c2b
```

Expected: 只包含本计划文件、已知认知游戏工作和本功能文件；没有 `.env`、临时 WAV、生成脚本、`.风格复制模式.swn` 或 `.impeccable/critique/` 被纳入本功能改动。

仅把已经有证据完成的 checkbox 改为 `[x]`，并在计划顶部追加实际执行记录；人工验收未完成时保持未勾选，不得把计划状态标记为 `implemented`。

- [x] **Step 7: 仅在用户授权后提交验证记录**

```bash
git add docs/superpowers/specs/2026-09-01-motion-instruction-voice-design.md docs/superpowers/plans/2026-09-01-motion-instruction-voice.md
git commit -m "docs(小程序): 记录运动说明语音落地结果"
```
