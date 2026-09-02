# 微信小程序认知游戏大图展示与选择反馈 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

执行记录（2026-09-02, Codex）：代码提交 `a8dec36` 已合并至 `main`；48 个测试文件、726 项测试通过，开发与生产微信构建成功，用户完成体验验收。

**Goal:** 为六款认知游戏实现按玩法分型的大图记忆展示、500ms 项间提示、具体选择反馈、声音翻牌结果和分类规则收口，同时保持现有计分与上传链路不变。

**Architecture:** 新建纯函数模块承载顺序展示游标、槽位反馈与通用单选反馈，避免继续把可测试状态规则堆入 65KB 的 `index.tsx`。页面继续负责回合生命周期、计时器、音频与渲染；颜色/图案共享顺序状态机，声音使用独立卡片视觉状态，数字/分类共享单选反馈，拼图只增强现有 `selectedPuzzleTileId` 样式。

**Tech Stack:** Taro 4.2、React 18、TypeScript 5.4、Sass、Vitest 3、微信小程序。

**Spec:** `docs/superpowers/specs/2026-08-31-cognitive-game-ui-scale-and-feedback-design.md`

> 状态：implemented
> 日期：2026-08-31
> 范围：六款认知游戏患者端 UI、前端回合状态与分类出题规则；不改后端和上传协议。
> 关联：`docs/superpowers/specs/2026-08-31-cognitive-game-ui-scale-and-feedback-design.md`

## Global Constraints

- 顺序项原有 `revealMs` 完整保留；只在相邻项之间额外增加固定 `500ms` 过渡。
- 顺序作答不允许撤销；单步反馈不改变完整序列判分。
- 声音卡正面只显示放大图片，不显示类别、编号或小字。
- 声音答对时翻开所选卡；答错时保持背面并显示红色选框，不揭示正确卡。
- 拼图只增强第一块选中效果，第二块交换后清除；不增加逐块对错。
- 分类出题禁用 `scene`；颜色固定映射为菠萝=黄色、小鸟=蓝色、火车=蓝色、鼓=红色、电话=蓝色。
- 每题结果固定保留 `1000ms`。
- 不修改六款游戏编码、难度档位、评分公式、逐题数据结构、后端接口、上传或补传。
- 关键状态必须使用图标或文字辅助，不能只依赖红绿颜色。
- 必须保留并验证 `prefers-reduced-motion` 静态兜底。
- 所有 Git 提交信息使用中文；每个任务只提交该任务明确列出的文件。

---

## 文件结构与职责

- `miniapp/src/pages/game-session/sequencePresentation.ts`：顺序记忆展示游标、阶段时长和作答槽位纯函数；不访问 React、Taro 或计时器。
- `miniapp/src/pages/game-session/sequencePresentation.test.ts`：覆盖 500ms 项间过渡、结束条件、相同连续项与逐槽位正确性。
- `miniapp/src/pages/game-session/choiceFeedback.ts`：数字和分类单选结果到 `idle/correct/wrong` 视觉状态的通用纯函数。
- `miniapp/src/pages/game-session/choiceFeedback.test.ts`：覆盖数字索引与字符串选项反馈。
- `miniapp/src/pages/game-session/soundDiscrimination.ts`：保留声音出题/判定，并新增卡片视觉状态纯函数。
- `miniapp/src/pages/game-session/soundDiscrimination.test.ts`：覆盖试听、答对翻开、答错不翻开和状态清理语义。
- `miniapp/src/pages/game-session/categorySwitch.ts`：禁用 `scene` 出题并固定现有五张图片的颜色元数据。
- `miniapp/src/pages/game-session/categorySwitch.test.ts`：覆盖所有难度不生成 `scene` 及颜色映射。
- `miniapp/src/pages/game-session/index.tsx`：接线回合状态、计时器、暂停恢复、音频翻牌和六款游戏渲染。
- `miniapp/src/app.scss`：大舞台、500ms 过渡、槽位标记、声音卡结果、单选结果与拼图选中样式。
- `docs/superpowers/specs/2026-08-31-cognitive-game-ui-scale-and-feedback-design.md`：实施完成后更新状态与基线提交。
- `docs/superpowers/plans/2026-08-31-cognitive-game-ui-scale-and-feedback.md`：逐任务勾选和记录实施提交。
- `docs/superpowers/README.md`、`specs/patient-rehab-system/changelog.md`：实施完成后的索引与追加式变更记录。

---

### Task 1: 建立顺序展示状态机

**Files:**
- Create: `miniapp/src/pages/game-session/sequencePresentation.ts`
- Create: `miniapp/src/pages/game-session/sequencePresentation.test.ts`

**Interfaces:**
- Consumes: 序列长度和现有回合 `revealMs`。
- Produces: `SEQUENCE_TRANSITION_MS`、`SequenceRevealCursor`、`sequenceRevealDelay(cursor, revealMs)`、`advanceSequenceRevealCursor(cursor, sequenceLength)`。

- [x] **Step 1: 写 500ms 过渡和结束条件失败测试**

创建 `sequencePresentation.test.ts`：

```ts
import { describe, expect, it } from 'vitest'

import {
  SEQUENCE_TRANSITION_MS,
  advanceSequenceRevealCursor,
  sequenceRevealDelay,
  type SequenceRevealCursor,
} from './sequencePresentation'

describe('sequence reveal cursor', () => {
  it('inserts a 500ms transition only between items', () => {
    const first: SequenceRevealCursor = { index: 0, phase: 'item' }
    const gap = advanceSequenceRevealCursor(first, 3)
    const second = gap ? advanceSequenceRevealCursor(gap, 3) : null

    expect(gap).toEqual({ index: 1, phase: 'transition' })
    expect(sequenceRevealDelay(gap!, 900)).toBe(SEQUENCE_TRANSITION_MS)
    expect(second).toEqual({ index: 1, phase: 'item' })
    expect(sequenceRevealDelay(second!, 900)).toBe(900)
  })

  it('finishes immediately after the final item without a trailing gap', () => {
    expect(advanceSequenceRevealCursor({ index: 2, phase: 'item' }, 3)).toBeNull()
  })

  it('uses the same cursor transitions when adjacent values are equal', () => {
    const sequence = ['sun', 'sun']
    let cursor: SequenceRevealCursor | null = { index: 0, phase: 'item' }
    cursor = advanceSequenceRevealCursor(cursor, sequence.length)
    expect(cursor).toEqual({ index: 1, phase: 'transition' })
    cursor = advanceSequenceRevealCursor(cursor!, sequence.length)
    expect(cursor).toEqual({ index: 1, phase: 'item' })
  })
})
```

- [x] **Step 2: 运行测试确认模块尚不存在**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/sequencePresentation.test.ts
```

Expected: FAIL，提示无法解析 `./sequencePresentation`。

- [x] **Step 3: 实现最小顺序游标纯函数**

创建 `sequencePresentation.ts`：

```ts
export const SEQUENCE_TRANSITION_MS = 500

export type SequenceRevealPhase = 'item' | 'transition'

export type SequenceRevealCursor = {
  index: number
  phase: SequenceRevealPhase
}

export function sequenceRevealDelay(cursor: SequenceRevealCursor, revealMs: number): number {
  return cursor.phase === 'transition' ? SEQUENCE_TRANSITION_MS : revealMs
}

export function advanceSequenceRevealCursor(
  cursor: SequenceRevealCursor,
  sequenceLength: number
): SequenceRevealCursor | null {
  if (sequenceLength <= 0 || cursor.index < 0 || cursor.index >= sequenceLength) return null
  if (cursor.phase === 'item') {
    return cursor.index === sequenceLength - 1 ? null : { index: cursor.index + 1, phase: 'transition' }
  }
  return { index: cursor.index, phase: 'item' }
}
```

- [x] **Step 4: 运行顺序状态机测试**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/sequencePresentation.test.ts
```

Expected: 3 个测试全部 PASS。

- [x] **Step 5: 提交顺序状态机**

```bash
git add miniapp/src/pages/game-session/sequencePresentation.ts miniapp/src/pages/game-session/sequencePresentation.test.ts
git commit -m "feat(小游戏): 建立顺序展示状态机"
```

---

### Task 2: 接线颜色与图案大舞台、暂停恢复和作答槽位

**Files:**
- Modify: `miniapp/src/pages/game-session/sequencePresentation.ts`
- Modify: `miniapp/src/pages/game-session/sequencePresentation.test.ts`
- Modify: `miniapp/src/pages/game-session/index.tsx:9-59, 142-205, 240-330, 476-520, 551-642, 896-938, 952-1015, 1285-1330, 1375-1418`
- Modify: `miniapp/src/app.scss:915-1082, 1216-1224`

**Interfaces:**
- Consumes: Task 1 的 `SequenceRevealCursor`、`sequenceRevealDelay`、`advanceSequenceRevealCursor`；现有 `ColorSequenceRound.revealMs`、`PatternSequenceRound.revealMs` 和 `revealTimerRemainingMsRef`。
- Produces: `SequenceAnswerSlot<T>`、`buildSequenceAnswerSlots(target, selected)`；页面共享状态 `sequenceRevealCursor`；样式类 `sequence-memory-stage`、`sequence-transition-cue`、`sequence-answer-slot`、`sequence-result-mark`。

- [x] **Step 1: 写逐槽位结果失败测试**

向 `sequencePresentation.test.ts` 增加：

```ts
import { buildSequenceAnswerSlots } from './sequencePresentation'

describe('buildSequenceAnswerSlots', () => {
  it('keeps empty slots numbered and marks each selected position independently', () => {
    expect(buildSequenceAnswerSlots(['sun', 'boat', 'shell'], ['sun', 'shell'])).toEqual([
      { index: 0, expected: 'sun', selected: 'sun', correct: true },
      { index: 1, expected: 'boat', selected: 'shell', correct: false },
      { index: 2, expected: 'shell', selected: null, correct: null },
    ])
  })

  it('handles repeated values by position rather than collapsing duplicates', () => {
    expect(buildSequenceAnswerSlots(['blue', 'blue'], ['blue', 'blue'])).toEqual([
      { index: 0, expected: 'blue', selected: 'blue', correct: true },
      { index: 1, expected: 'blue', selected: 'blue', correct: true },
    ])
  })
})
```

- [x] **Step 2: 运行测试确认缺少槽位函数**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/sequencePresentation.test.ts
```

Expected: FAIL，提示 `buildSequenceAnswerSlots` 未导出。

- [x] **Step 3: 实现通用槽位纯函数**

在 `sequencePresentation.ts` 增加：

```ts
export type SequenceAnswerSlot<T> = {
  index: number
  expected: T
  selected: T | null
  correct: boolean | null
}

export function buildSequenceAnswerSlots<T>(
  target: readonly T[],
  selected: readonly T[]
): SequenceAnswerSlot<T>[] {
  return target.map((expected, index) => {
    const selectedValue = index < selected.length ? selected[index] : null
    return {
      index,
      expected,
      selected: selectedValue,
      correct: selectedValue === null ? null : Object.is(expected, selectedValue),
    }
  })
}
```

- [x] **Step 4: 运行槽位测试确认通过**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/sequencePresentation.test.ts
```

Expected: 5 个测试全部 PASS。

- [x] **Step 5: 将页面总时长定时器改为逐阶段调度**

在 `index.tsx` 导入 Task 1/2 接口，新增共享 state/ref：

```ts
const [sequenceRevealCursor, setSequenceRevealCursor] = useState<SequenceRevealCursor | null>(null)
const sequenceRevealCursorRef = useRef<SequenceRevealCursor | null>(null)

function setSequenceCursor(cursor: SequenceRevealCursor | null) {
  sequenceRevealCursorRef.current = cursor
  setSequenceRevealCursor(cursor)
}
```

删除 `colorRevealDurationMs()` 和 `patternRevealDurationMs()` 的“序列长度 × revealMs”总时长算法。用一个共享调度器代替两个一次性 timer：

```ts
function startSequenceRevealTimer(
  kind: 'color' | 'pattern',
  sequenceLength: number,
  revealMs: number,
  durationMs?: number
) {
  if (revealTimerRef.current) clearTimeout(revealTimerRef.current)
  const cursor = sequenceRevealCursorRef.current
  if (!cursor) return

  const nextDuration = Math.max(0, durationMs ?? sequenceRevealDelay(cursor, revealMs))
  revealTimerDeadlineRef.current = Date.now() + nextDuration
  revealTimerRemainingMsRef.current = nextDuration
  revealTimerRef.current = setTimeout(() => {
    revealTimerRef.current = null
    revealTimerDeadlineRef.current = null
    revealTimerRemainingMsRef.current = null
    if (phaseRef.current !== 'playing') return

    const current = sequenceRevealCursorRef.current
    if (!current) return
    const next = advanceSequenceRevealCursor(current, sequenceLength)
    if (next) {
      setSequenceCursor(next)
      startSequenceRevealTimer(kind, sequenceLength, revealMs)
      return
    }

    setSequenceCursor(null)
    if (kind === 'color') setColorRevealing(false)
    if (kind === 'pattern') setPatternRevealing(false)
    roundStartedAtRef.current = Date.now()
    const timeoutMs = kind === 'color'
      ? activeColorRoundRef.current?.inputTimeoutMs
      : activePatternRoundRef.current?.inputTimeoutMs
    if (timeoutMs) startRoundTimeout(timeoutMs)
  }, nextDuration)
}
```

`startColorRound()` 和 `startPatternRound()` 在设置 `*Revealing(true)` 前调用 `setSequenceCursor({ index: 0, phase: 'item' })`，随后使用各自序列长度和 `revealMs` 启动调度。进入其他游戏、新题、结束或卸载时调用 `setSequenceCursor(null)`。

- [x] **Step 6: 对齐暂停与恢复**

保留现有 `pauseRevealTimer()` 对剩余毫秒的计算；恢复颜色/图案时使用当前 cursor 和剩余时间：

```ts
if (gameCodeRef.current === 'game-memory-color-sequence' && colorRevealing && activeColorRound) {
  startSequenceRevealTimer(
    'color',
    activeColorRound.sequence.length,
    activeColorRound.revealMs,
    revealTimerRemainingMsRef.current ?? undefined
  )
  return
}
```

图案分支使用同样参数。恢复期间不重设 cursor，确保暂停发生在 `transition` 时仍完成剩余的 500ms。

- [x] **Step 7: 重写颜色和图案记忆渲染**

记忆阶段渲染一个大舞台：

```tsx
{sequenceRevealCursor ? (
  <View className='sequence-memory-wrap'>
    <Text className='sequence-memory-progress'>
      第 {sequenceRevealCursor.index + 1} / {activeColorRound.sequence.length} 项
    </Text>
    <View className='sequence-memory-stage'>
      {sequenceRevealCursor.phase === 'transition' ? (
        <Text className='sequence-transition-cue'>下一项</Text>
      ) : (
        <View className={`sequence-memory-color color-${activeColorRound.sequence[sequenceRevealCursor.index]}`}>
          <Text>{COLOR_LABEL[activeColorRound.sequence[sequenceRevealCursor.index]]}</Text>
        </View>
      )}
    </View>
  </View>
) : (
  <View className='sequence-answer-grid'>
    {buildSequenceAnswerSlots(activeColorRound.sequence, activeColorInput).map((slot) => (
      <View
        key={slot.index}
        className={`sequence-answer-slot ${slot.selected === null ? '' : `color-${slot.selected}`}`}
      >
        {slot.selected === null ? <Text>{slot.index + 1}</Text> : <Text>{COLOR_LABEL[slot.selected]}</Text>}
        {slot.correct !== null ? (
          <Text className={`sequence-result-mark ${slot.correct ? 'correct' : 'wrong'}`}>
            {slot.correct ? '✓' : '✕'}
          </Text>
        ) : null}
      </View>
    ))}
  </View>
)}
```

图案分支把 target/selected 都转换为稳定 `id`，再通过 `activePatternRound.patterns` 找回图片和名称；不得用对象引用比较正确性。具体映射如下：

```tsx
const patternSlots = buildSequenceAnswerSlots(
  activePatternRound.sequence.map((pattern) => pattern.id),
  activePatternInput
)

{patternSlots.map((slot) => {
  const selectedPattern = slot.selected === null
    ? null
    : activePatternRound.patterns.find((pattern) => pattern.id === slot.selected) ?? null
  return (
    <View key={slot.index} className='sequence-answer-slot'>
      {selectedPattern ? (
        <Image className='sequence-answer-image' src={selectedPattern.imageSrc} mode='aspectFit' />
      ) : (
        <Text>{slot.index + 1}</Text>
      )}
      {slot.correct !== null ? (
        <Text className={`sequence-result-mark ${slot.correct ? 'correct' : 'wrong'}`}>
          {slot.correct ? '✓' : '✕'}
        </Text>
      ) : null}
    </View>
  )
})}
```

图案记忆阶段在共享舞台里读取当前项，正面只展示一张大图：

```tsx
const currentPattern = activePatternRound.sequence[sequenceRevealCursor.index]

<View className='sequence-memory-stage'>
  {sequenceRevealCursor.phase === 'transition' ? (
    <Text className='sequence-transition-cue'>下一项</Text>
  ) : (
    <Image className='sequence-memory-image' src={currentPattern.imageSrc} mode='aspectFit' />
  )}
</View>
```

- [x] **Step 8: 实现大舞台和槽位样式**

在 `.game-session-page` 内新增实际样式值：

```scss
.sequence-memory-stage {
  display: flex;
  height: 34vh;
  min-height: 220px;
  max-height: 360px;
  align-items: center;
  justify-content: center;
  margin: 14px 0 22px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
}

.sequence-memory-progress {
  display: block;
  color: $mc-muted;
  text-align: center;
  font-size: 24px;
  font-weight: 800;
}

.sequence-memory-color,
.sequence-memory-image {
  width: 320px;
  max-width: 72vw;
  height: 28vh;
  min-height: 180px;
  max-height: 320px;
  border-radius: 18px;
}

.sequence-memory-color {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 34px;
  font-weight: 900;
}

.sequence-memory-image {
  display: block;
}

.sequence-transition-cue {
  color: $mc-primary;
  font-size: 38px;
  font-weight: 900;
}

.sequence-answer-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 12px 0 22px;
}

.sequence-answer-slot {
  position: relative;
  display: flex;
  overflow: hidden;
  min-height: 112px;
  align-items: center;
  justify-content: center;
  border: 2px dashed rgba(7, 152, 178, 0.48);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.88);
}

.sequence-answer-image {
  display: block;
  width: 100%;
  height: 112px;
}

.sequence-result-mark {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-size: 52px;
  font-weight: 900;
}

.sequence-result-mark.correct {
  background: rgba(31, 141, 99, 0.72);
}

.sequence-result-mark.wrong {
  background: rgba(177, 63, 49, 0.76);
}
```

图片和名称在 overlay 下仍可辨认。向 `prefers-reduced-motion` 列表加入新舞台和 marker，取消淡入/缩放但保留 500ms 静态空档。

- [x] **Step 9: 运行定向测试和小程序构建**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/sequencePresentation.test.ts src/pages/game-session/colorSequence.test.ts src/pages/game-session/patternSequence.test.ts
cd miniapp && npm run build:weapp
```

Expected: 测试全部 PASS；构建成功且无 TypeScript 错误。

- [x] **Step 10: 提交顺序记忆 UI**

```bash
git add miniapp/src/pages/game-session/sequencePresentation.ts miniapp/src/pages/game-session/sequencePresentation.test.ts miniapp/src/pages/game-session/index.tsx miniapp/src/app.scss
git commit -m "feat(小游戏): 放大顺序记忆并增加逐项反馈"
```

---

### Task 3: 实现声音卡试听翻回与答题结果

**Files:**
- Modify: `miniapp/src/pages/game-session/soundDiscrimination.ts`
- Modify: `miniapp/src/pages/game-session/soundDiscrimination.test.ts`
- Modify: `miniapp/src/pages/game-session/index.tsx:45-59, 167-185, 678-712, 1036-1094, 1118-1132, 1452-1501`
- Modify: `miniapp/src/app.scss:1021-1052, 1101-1135, 1197-1207, 1216-1224`

**Interfaces:**
- Consumes: 现有 `SoundCard.id`、`soundPreviewingCardId` 和 `evaluateSoundDiscriminationAttempt()`。
- Produces: `SoundAttemptOutcome`、`SoundCardVisualState`、`soundCardVisualState(cardId, previewingCardId, outcome)`；页面 state `soundAttemptOutcome`。

- [x] **Step 1: 写声音卡视觉状态失败测试**

向 `soundDiscrimination.test.ts` 增加导入和测试：

```ts
import { soundCardVisualState, type SoundAttemptOutcome } from './soundDiscrimination'

describe('soundCardVisualState', () => {
  const correct: SoundAttemptOutcome = { selectedCardId: 'card-2', correct: true }
  const wrong: SoundAttemptOutcome = { selectedCardId: 'card-2', correct: false }

  it('shows only the actively previewing card face', () => {
    expect(soundCardVisualState('card-2', 'card-2', null)).toBe('preview')
    expect(soundCardVisualState('card-1', 'card-2', null)).toBe('back')
  })

  it('reveals a correct choice but keeps a wrong choice on its back', () => {
    expect(soundCardVisualState('card-2', null, correct)).toBe('correct')
    expect(soundCardVisualState('card-2', null, wrong)).toBe('wrong')
    expect(soundCardVisualState('card-1', null, wrong)).toBe('back')
  })

  it('gives preview priority while audio is active', () => {
    expect(soundCardVisualState('card-2', 'card-2', wrong)).toBe('preview')
  })
})
```

- [x] **Step 2: 运行测试确认缺少声音视觉函数**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/soundDiscrimination.test.ts
```

Expected: FAIL，提示新类型或函数未导出。

- [x] **Step 3: 实现声音卡视觉状态纯函数**

在 `soundDiscrimination.ts` 增加：

```ts
export type SoundAttemptOutcome = {
  selectedCardId: string
  correct: boolean
}

export type SoundCardVisualState = 'back' | 'preview' | 'correct' | 'wrong'

export function soundCardVisualState(
  cardId: string,
  previewingCardId: string | null,
  outcome: SoundAttemptOutcome | null
): SoundCardVisualState {
  if (previewingCardId === cardId) return 'preview'
  if (outcome?.selectedCardId !== cardId) return 'back'
  return outcome.correct ? 'correct' : 'wrong'
}
```

- [x] **Step 4: 运行声音纯函数测试**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/soundDiscrimination.test.ts
```

Expected: 全部 PASS。

- [x] **Step 5: 接线声音答题结果与清理**

在 `index.tsx` 增加：

```ts
const [soundAttemptOutcome, setSoundAttemptOutcome] = useState<SoundAttemptOutcome | null>(null)
```

`startSoundRound()`、`startRoundForGame()` 的非声音分支和 session 清理路径都调用 `setSoundAttemptOutcome(null)`。`selectSoundCard()` 在判定后、`showAttemptFeedback()` 前写入：

```ts
setSoundAttemptOutcome({ selectedCardId: card.id, correct: attempt.correct })
```

把 `scheduleNextRound()` 的延迟从 `650` 改为命名常量：

```ts
const ROUND_FEEDBACK_MS = 1000
```

并使用 `ROUND_FEEDBACK_MS`。这会同时让顺序、数字、分类和声音反馈保持 1000ms。

- [x] **Step 6: 让试听卡播放后返回背面**

保留 `markCardPreviewed()` 作为进度记录，但渲染正面不得再读取 `card.previewed`。定义回翻完成时间：

```ts
const SOUND_CARD_RETURN_MS = 180
```

`autoPreviewSoundRound()` 仍在播放前设置 `soundPreviewingCardId`，在每次 `await playAudioSrc(card.audioSrc)` 返回后执行：

```ts
setSoundPreviewingCardId(null)
await wait(SOUND_CARD_RETURN_MS)
if (!canUseSoundPreviewRun(runId)) return
```

再继续下一轮循环。这个 180ms 只用于完成卡片回到背面的视觉动作；下一张卡设置自己的 id 后才翻开，任何时刻最多一张正面卡。

- [x] **Step 7: 重写声音卡渲染**

删除未再使用的 `SOUND_CATEGORY_LABEL`。把现有声音卡列表回调的形参改为 `(card, index)`，每张卡计算：

```tsx
const visualState = soundCardVisualState(card.id, soundPreviewingCardId, soundAttemptOutcome)
const showsFace = visualState === 'preview' || visualState === 'correct'
```

按钮 class 使用 `sound-card-${visualState}`。正面只渲染图片：

```tsx
{showsFace ? (
  <View className='sound-card-face'>
    <Image className='sound-card-image' src={card.imageSrc} mode='aspectFit' />
  </View>
) : (
  <Text className='card-back'>{index + 1}</Text>
)}
```

错误卡保持背面；错误语义由 `sound-card-wrong` 红色边框和下方 `game-feedback wrong` 文案共同表达。

- [x] **Step 8: 放大声音图片并补齐结果样式**

在 `app.scss` 中使用：

```scss
.sound-card {
  min-height: 210px;
  padding: 14px;
}

.sound-card-image {
  display: block;
  width: 158px;
  max-width: 100%;
  height: 158px;
}

.sound-card-preview,
.sound-card-correct {
  animation: card-flip-in 260ms ease-out;
}

.sound-card-correct {
  border-color: rgba(17, 163, 106, 0.72);
  background: rgba(234, 251, 240, 0.96);
}

.sound-card-wrong {
  border-color: $mc-danger;
  background: rgba(255, 235, 229, 0.7);
  box-shadow: 0 0 0 6px rgba(194, 65, 45, 0.16);
}
```

给反馈元素增加 `correct/wrong` class；错误 feedback 使用红棕文字和浅红背景。减少动态效果分支覆盖新的 preview/correct class。

- [x] **Step 9: 运行声音测试和构建**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/soundDiscrimination.test.ts src/pages/game-session/gameAudio.test.ts
cd miniapp && npm run build:weapp
```

Expected: 测试全部 PASS；构建成功；无未使用的 `SOUND_CATEGORY_LABEL`。

- [x] **Step 10: 提交声音卡任务**

```bash
git add miniapp/src/pages/game-session/soundDiscrimination.ts miniapp/src/pages/game-session/soundDiscrimination.test.ts miniapp/src/pages/game-session/index.tsx miniapp/src/app.scss
git commit -m "feat(小游戏): 完善声音翻牌与选择反馈"
```

---

### Task 4: 统一数字与分类反馈并增强拼图选中态

**Files:**
- Create: `miniapp/src/pages/game-session/choiceFeedback.ts`
- Create: `miniapp/src/pages/game-session/choiceFeedback.test.ts`
- Modify: `miniapp/src/pages/game-session/categorySwitch.ts`
- Modify: `miniapp/src/pages/game-session/categorySwitch.test.ts`
- Modify: `miniapp/src/pages/game-session/index.tsx:15, 162-185, 581-676, 975-1034, 1134-1161, 1334-1363, 1422-1449, 1505-1542`
- Modify: `miniapp/src/app.scss:962-987, 1084-1099, 1168-1181, 1197-1207`

**Interfaces:**
- Consumes: 数字选项索引、分类选项字符串、现有 `selectedPuzzleTileId`。
- Produces: `ChoiceOutcome<T>`、`ChoiceFeedbackState`、`choiceFeedbackState(option, outcome)`；页面 state `inhibitionOutcome`、`categoryOutcome`；样式类 `choice-correct`、`choice-wrong`。

- [x] **Step 1: 写通用单选反馈失败测试**

创建 `choiceFeedback.test.ts`：

```ts
import { describe, expect, it } from 'vitest'

import { choiceFeedbackState } from './choiceFeedback'

describe('choiceFeedbackState', () => {
  it('marks only the selected numeric option', () => {
    const outcome = { selected: 2, correct: false }
    expect(choiceFeedbackState(1, outcome)).toBe('idle')
    expect(choiceFeedbackState(2, outcome)).toBe('wrong')
  })

  it('marks a selected string option correct', () => {
    expect(choiceFeedbackState('水果', { selected: '水果', correct: true })).toBe('correct')
    expect(choiceFeedbackState('动物', { selected: '水果', correct: true })).toBe('idle')
  })

  it('keeps every option idle before an answer', () => {
    expect(choiceFeedbackState('水果', null)).toBe('idle')
  })
})
```

- [x] **Step 2: 运行测试确认模块缺失**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/choiceFeedback.test.ts
```

Expected: FAIL，提示无法解析 `choiceFeedback`。

- [x] **Step 3: 实现通用单选反馈**

创建 `choiceFeedback.ts`：

```ts
export type ChoiceOutcome<T> = {
  selected: T
  correct: boolean
}

export type ChoiceFeedbackState = 'idle' | 'correct' | 'wrong'

export function choiceFeedbackState<T>(
  option: T,
  outcome: ChoiceOutcome<T> | null
): ChoiceFeedbackState {
  if (!outcome || !Object.is(option, outcome.selected)) return 'idle'
  return outcome.correct ? 'correct' : 'wrong'
}
```

- [x] **Step 4: 写分类规则和颜色映射失败测试**

修改 `categorySwitch.test.ts`：

```ts
import { CATEGORY_ITEMS, createCategorySwitchRound } from './categorySwitch'

it('never generates the ambiguous scene rule at any difficulty', () => {
  ;(['简单', '中等', '困难'] as const).forEach((difficulty) => {
    for (const randomValue of [0, 0.25, 0.5, 0.75, 0.99]) {
      expect(createCategorySwitchRound(difficulty, { random: () => randomValue }).rule).not.toBe('scene')
    }
  })
})

it('matches approved dominant colors for the five current images', () => {
  expect(Object.fromEntries(CATEGORY_ITEMS.map((item) => [item.id, item.color]))).toEqual({
    pineapple: '黄色',
    bird: '蓝色',
    train: '蓝色',
    drum: '红色',
    phone: '蓝色',
  })
})
```

删除原“困难档可生成 scene”的断言，改为困难档只包含 `kind/color` 且仍为 4 个唯一选项。

- [x] **Step 5: 运行单选与分类测试确认失败**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/choiceFeedback.test.ts src/pages/game-session/categorySwitch.test.ts
```

Expected: `choiceFeedback` 测试 PASS；分类测试 FAIL，因为 ITEMS 未导出、火车仍是灰色且困难档仍可能生成 `scene`。

- [x] **Step 6: 收紧分类数据**

在 `categorySwitch.ts`：

```ts
export const CATEGORY_ITEMS: CategoryItem[] = [
  {
    id: 'pineapple',
    label: '菠萝',
    imageSrc: '/pages/game-session/assets/images/game-session/category_pineapple.png',
    fallback: '果',
    kind: '水果',
    color: '黄色',
    scene: '海岛',
  },
  {
    id: 'bird',
    label: '小鸟',
    imageSrc: '/pages/game-session/assets/images/game-session/category_bird.png',
    fallback: '鸟',
    kind: '动物',
    color: '蓝色',
    scene: '户外',
  },
  {
    id: 'train',
    label: '火车',
    imageSrc: '/pages/game-session/assets/images/game-session/category_train.png',
    fallback: '车',
    kind: '交通',
    color: '蓝色',
    scene: '室外',
  },
  {
    id: 'drum',
    label: '鼓',
    imageSrc: '/pages/game-session/assets/images/game-session/category_drum.png',
    fallback: '鼓',
    kind: '乐器',
    color: '红色',
    scene: '室内',
  },
  {
    id: 'phone',
    label: '电话',
    imageSrc: '/pages/game-session/assets/images/game-session/category_phone.png',
    fallback: '话',
    kind: '工具',
    color: '蓝色',
    scene: '室内',
  },
]

const CONFIG = {
  简单: { rules: ['kind'], optionLimit: 3, timeoutMs: 7000 },
  中等: { rules: ['kind', 'color'], optionLimit: 4, timeoutMs: 5500 },
  困难: { rules: ['kind', 'color'], optionLimit: 4, timeoutMs: 4200 },
} satisfies Record<GameDifficulty, { rules: CategoryRule[]; optionLimit: number; timeoutMs: number }>
```

`OPTIONS.scene` 和 `CategoryRule` 的 `scene` 成员可暂时保留，避免把“停用”扩大为不可逆模型删除；但所有 CONFIG 都不得引用 `scene`。把创建回合时使用的 `ITEMS` 引用改为 `CATEGORY_ITEMS`。

- [x] **Step 7: 接线数字与分类结果状态**

在 `index.tsx` 新增：

```ts
const [inhibitionOutcome, setInhibitionOutcome] = useState<ChoiceOutcome<number> | null>(null)
const [categoryOutcome, setCategoryOutcome] = useState<ChoiceOutcome<string> | null>(null)
```

`selectInhibition(index)` 和 `selectCategory(option)` 在现有判定后写入对应 outcome。`startInhibitionRound()`、`startCategoryRound()`、开始其他游戏和结束路径清空两个 state。

渲染选项时调用 `choiceFeedbackState()`，把返回值加入 class，并在非 idle 时渲染：

```tsx
<Text className='choice-result-mark'>{feedbackState === 'correct' ? '✓' : '✕'}</Text>
```

错误只标记患者所选按钮，不额外揭示正确答案。

- [x] **Step 8: 增强分类图片和拼图选中样式**

分类图片单独使用 `.category-image`，从共享 `122px` 提高到 `190px`，保持 `aspectFit`，不改变分类舞台结构。

强化现有拼图 selected 样式，不新增页面状态：

```scss
.puzzle-tile.selected {
  z-index: 1;
  border-color: $mc-coral;
  box-shadow: 0 0 0 7px rgba(194, 65, 45, 0.24);
  transform: scale(0.96);
}

.puzzle-tile.selected::after {
  content: '已选';
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 2;
  padding: 5px 9px;
  border-radius: 999px;
  color: #ffffff;
  background: $mc-danger;
  font-size: 18px;
  font-weight: 900;
}
```

保留 `selectPuzzleTile()` 现有第二次点击后的 `setSelectedPuzzleTileId(null)`；不要新增完成对勾或标题变化。减少动态效果分支取消缩放但保留边框和“已选”标记。

- [x] **Step 9: 运行相关测试和构建**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/choiceFeedback.test.ts src/pages/game-session/categorySwitch.test.ts src/pages/game-session/inhibition.test.ts src/pages/game-session/puzzle.test.ts
cd miniapp && npm run build:weapp
```

Expected: 测试全部 PASS；构建成功。

- [x] **Step 10: 提交选择反馈任务**

```bash
git add miniapp/src/pages/game-session/choiceFeedback.ts miniapp/src/pages/game-session/choiceFeedback.test.ts miniapp/src/pages/game-session/categorySwitch.ts miniapp/src/pages/game-session/categorySwitch.test.ts miniapp/src/pages/game-session/index.tsx miniapp/src/app.scss
git commit -m "feat(小游戏): 统一选择反馈并收紧分类规则"
```

---

### Task 5: 全量回归、真机验收与文档收口

**Files:**
- Modify: `docs/superpowers/specs/2026-08-31-cognitive-game-ui-scale-and-feedback-design.md`
- Modify: `docs/superpowers/plans/2026-08-31-cognitive-game-ui-scale-and-feedback.md`
- Modify: `docs/superpowers/README.md`
- Modify: `specs/patient-rehab-system/changelog.md`

**Interfaces:**
- Consumes: Tasks 1-4 的全部提交和构建产物 `miniapp/dist`。
- Produces: 全量自动化验证结果、微信开发者工具/真机验收记录、implemented 状态和追加式 changelog。

- [x] **Step 1: 运行小程序全量测试**

Run:

```bash
cd miniapp && npm run test
```

Expected: 全部 Vitest 测试 PASS；没有未处理 Promise 或计时器警告。

- [x] **Step 2: 构建微信小程序开发产物**

Run:

```bash
cd miniapp && npm run build:weapp
```

Expected: 构建成功；无 TypeScript、Sass 或资源路径错误。

- [x] **Step 3: 执行项目完成门禁**

按照 `AGENTS.md` 执行：

```bash
cd backend && pytest
cd frontend && npm run test
cd frontend && npm run lint
cd frontend && npm run build
```

Expected: 四条命令全部成功。如果出现与本计划无关的既有失败，保存完整命令、失败用例和首个错误，不得把任务报告为“全部完成”。

- [x] **Step 4: 在微信开发者工具执行六款游戏矩阵**

逐项记录结果：

```text
颜色顺序：简单/中等/困难；连续相同颜色；展示态暂停；500ms 过渡态暂停；逐槽位 ✓/✕。
图案顺序：简单/中等/困难；连续相同图案；长序列槽位换行；图片 aspectFit。
数字抑制：正确和错误按钮标记；1000ms 后换题。
分类切换：kind/color 两类切换；困难档不出现 scene；火车按蓝色判定。
声音辨别：4/6/8 卡；每张播放后翻回；正确翻开；错误保持背面红框；正面无小字。
拼图：2×2/2×3/3×3；第一块已选清楚；交换后清除；无新增对错提示。
```

同时检查固定底部控制条不遮挡舞台、槽位和 8 张声音卡。

- [x] **Step 5: 在至少一台真机检查计时与生命周期**

验证：

```text
顺序 item 阶段切后台再返回：从剩余观察时间继续。
顺序 transition 阶段切后台再返回：完成剩余 500ms，不跳项。
声音播放中暂停/恢复：不同时翻开两张卡，不串入下一题。
结果 1000ms 内暂停或整场到时：不重复记题、不重复调度下一题。
系统减少动态效果开启：仍能区分展示、过渡、正确、错误和选中状态。
```

- [x] **Step 6: 更新 spec、plan、索引和 changelog**

完成验证后：

1. 运行 `git log --format='%h %s' --reverse 09e6c2b..HEAD`，把输出中的实际代码提交短 SHA 原样写入 spec 顶部的 `实施基线 commit`。
2. 把本 plan 顶部状态改为 `implemented`，将完成项勾为 `- [x]`；使用执行当天的实际日期，并把上一步得到的代码提交短 SHA 按顺序写入顶部执行记录。文档收口提交完成后，再把它的实际短 SHA 追加到同一条执行记录。

3. 把 `docs/superpowers/README.md` 中 spec 和 plan 状态改为 `implemented`。
4. 在 `specs/patient-rehab-system/changelog.md` 末尾追加新版本条目，逐条记录：顺序大舞台与 500ms 过渡、声音翻牌结果、数字/分类反馈、拼图选中态、禁用 `scene` 和验证结果；禁止修改历史条目。

- [x] **Step 7: 提交文档收口**

```bash
git add docs/superpowers/specs/2026-08-31-cognitive-game-ui-scale-and-feedback-design.md docs/superpowers/plans/2026-08-31-cognitive-game-ui-scale-and-feedback.md docs/superpowers/README.md specs/patient-rehab-system/changelog.md
git commit -m "docs(小游戏): 记录交互优化实施结果"
```

- [x] **Step 8: 检查最终工作区与提交范围**

Run:

```bash
git status --short
git log --oneline -6
```

Expected: 本计划文件中记录的提交均存在；没有遗漏本任务产生的源代码或文档改动；用户的 `.swn` 和 `.impeccable/critique/` 文件未被加入任何提交。

---

## 完成定义

- 颜色和图案使用单项大舞台，相邻项之间存在完整 `500ms` 提示，连续相同项可区分。
- 顺序槽位显示患者实际选择并逐项标记对错，完整序列计分不变。
- 声音卡试听后翻回；答对翻开，答错保持背面红框；正面无小字。
- 数字和分类在具体选项上反馈；分类不再生成 `scene` 且颜色映射正确。
- 拼图选中态明显，交换后清除，无其他玩法变化。
- 1000ms 结果停留、暂停恢复、逐题数据、最终上传和补传均无回归。
- 自动化测试、微信构建、项目完成门禁和手动矩阵均有可核对结果。
