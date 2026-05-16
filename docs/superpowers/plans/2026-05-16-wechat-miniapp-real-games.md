# 微信小程序真实游戏一期 Implementation Plan

执行记录（2026-05-16, codex）：微信小程序真实游戏一期已落地，验证通过。实施 commit：9a0feb3, 4cd6959, 5f6dc11, a5df871, 927ac28, 3fb3a10, 446a50b, fa7e432。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将小程序游戏占位页升级为两款患者可真实使用的认知小游戏：颜色顺序记忆和反应抑制能力训练，并保留现有训练记录回传链路。

**Architecture:** 小程序新增轻量 Game Session 壳，通用处理处方动作校验、难度调整、计时、暂停、音频、结果上传和失败补传；两款游戏各自实现纯玩法逻辑。后端继续使用 `TrainingRecord.form_data` 校验和保存游戏会话摘要，医生 Web 训练追踪只展示汇总指标、调难原因、提前结束和补传标记。

**Tech Stack:** Taro 4 + React 18 + TypeScript + Vitest；Django 5 + DRF + pytest-django；React 18 + Vite + Ant Design 5 + TanStack Query v5。

---

## Execution Notes

- 本计划对应 spec：`docs/superpowers/specs/2026-05-16-wechat-miniapp-real-games-design.md`。
- 当前计划生成时已有未提交文档改动：`docs/superpowers/specs/2026-05-16-wechat-miniapp-real-games-design.md`、`specs/patient-rehab-system/changelog.md`。执行代码任务时不要回退这些文档。
- 计划包含 commit 步骤以便工具切换；如果用户未授权提交，执行者应完成 `git status --short` 后暂停，不要擅自 commit。
- 所有 git 提交说明必须使用中文。
- 执行代码任务时使用 TDD：先写失败测试，再写实现，再跑测试。

## File Structure

### Miniapp

- Modify: `miniapp/package.json`
  - 增加 `test` 脚本和 `vitest` dev dependency。
- Modify: `miniapp/package-lock.json`
  - 由 `npm install -D vitest` 更新。
- Create: `miniapp/src/pages/game-session/gameTypes.ts`
  - 游戏通用类型、难度、结果 payload、处方动作适配类型。
- Create: `miniapp/src/pages/game-session/colorSequence.ts`
  - 颜色顺序记忆出题、判定。
- Create: `miniapp/src/pages/game-session/colorSequence.test.ts`
  - 覆盖颜色顺序记忆不同难度和判定。
- Create: `miniapp/src/pages/game-session/inhibition.ts`
  - 反应抑制题目生成、判定。
- Create: `miniapp/src/pages/game-session/inhibition.test.ts`
  - 覆盖反应抑制不同难度和判定。
- Create: `miniapp/src/pages/game-session/scoring.ts`
  - 统一分数、正确率、状态、时长计算。
- Create: `miniapp/src/pages/game-session/scoring.test.ts`
  - 覆盖到时完成、提前结束、边界分数。
- Create: `miniapp/src/pages/game-session/retryUpload.ts`
  - 一条待上传记录缓存、退避重试状态、下次打开重置一轮重试。
- Create: `miniapp/src/pages/game-session/retryUpload.test.ts`
  - 覆盖 10 次重试、超过后暂停、下次打开重启、成功清理。
- Create: `miniapp/src/pages/game-session/gameAudio.ts`
  - 音频资源清单、静音偏好、播放封装。
- Create: `miniapp/scripts/generate-game-audio.mjs`
  - 生成本期临时语音和音效资源。
- Create generated assets under: `miniapp/src/assets/audio/game-session/`
  - 语音与音效 `.m4a` 文件。
- Modify: `miniapp/src/pages/game-session/index.tsx`
  - 替换占位提交表单为真实游戏会话页。
- Modify: `miniapp/src/pages/prescription/index.tsx`
  - 展示待补传提示，进入处方页时触发补传检查。
- Modify: `miniapp/src/pages/home/index.tsx`
  - 首页展示待补传提示，进入首页时触发补传检查。
- Modify: `miniapp/src/app.ts`
  - 小程序进入前台时重置补传轮次并尝试补传。
- Modify: `miniapp/src/app.scss`
  - 增加海南康复主题、游戏网格、结果页、提示条、暂停层样式。

### Backend

- Modify: `backend/apps/training/game_results.py`
  - 增加 `raw_detail` 约定字段校验。
- Modify: `backend/apps/training/tests/test_training_current_prescription.py`
  - 覆盖新增游戏结果字段校验。
- Modify: `backend/apps/training/tracking.py`
  - 从 `form_data.raw_detail` 提取提前结束、上传方式、补传次数、调难原因。
- Modify: `backend/apps/training/tests/test_tracking_api.py`
  - 覆盖训练追踪返回新增字段。

### Doctor Web Frontend

- Modify: `frontend/src/pages/training-tracking/types.ts`
  - 增加最近训练记录的游戏会话摘要字段。
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
  - 最近训练记录表格展示提前结束、上传方式、补传次数、调难原因。
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`
  - 覆盖新增字段展示。

---

### Task 1: Miniapp Game Core and Test Harness

**Files:**
- Modify: `miniapp/package.json`
- Modify: `miniapp/package-lock.json`
- Create: `miniapp/src/pages/game-session/gameTypes.ts`
- Create: `miniapp/src/pages/game-session/colorSequence.ts`
- Create: `miniapp/src/pages/game-session/colorSequence.test.ts`
- Create: `miniapp/src/pages/game-session/inhibition.ts`
- Create: `miniapp/src/pages/game-session/inhibition.test.ts`
- Create: `miniapp/src/pages/game-session/scoring.ts`
- Create: `miniapp/src/pages/game-session/scoring.test.ts`

- [x] **Step 1: Add Vitest to the miniapp**

Run:

```bash
cd miniapp && npm install -D vitest
```

Then modify `miniapp/package.json` scripts so it includes:

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

Keep all existing scripts. Expected: `package.json` and `package-lock.json` change.

- [x] **Step 2: Write failing color sequence tests**

Create `miniapp/src/pages/game-session/colorSequence.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { createColorSequenceRound, evaluateColorSequenceAttempt } from './colorSequence'

describe('createColorSequenceRound', () => {
  it('creates a simple 3-step sequence from 3 colors', () => {
    const round = createColorSequenceRound('简单', () => 0)

    expect(round.colors).toEqual(['blue', 'green', 'yellow'])
    expect(round.sequence).toEqual(['blue', 'blue', 'blue'])
    expect(round.revealMs).toBe(900)
    expect(round.inputTimeoutMs).toBe(8000)
  })

  it('creates a difficult sequence with more colors and shorter timing', () => {
    const round = createColorSequenceRound('困难', () => 0.99)

    expect(round.colors).toEqual(['blue', 'green', 'yellow', 'red', 'teal'])
    expect(round.sequence.length).toBe(7)
    expect(round.revealMs).toBe(560)
    expect(round.inputTimeoutMs).toBe(5000)
  })
})

describe('evaluateColorSequenceAttempt', () => {
  it('marks an exact sequence as correct', () => {
    expect(evaluateColorSequenceAttempt(['blue', 'green'], ['blue', 'green'])).toEqual({
      correct: true,
      expected: ['blue', 'green'],
      actual: ['blue', 'green'],
    })
  })

  it('marks wrong order as incorrect', () => {
    expect(evaluateColorSequenceAttempt(['blue', 'green'], ['green', 'blue']).correct).toBe(false)
  })
})
```

- [x] **Step 3: Write failing inhibition tests**

Create `miniapp/src/pages/game-session/inhibition.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { createInhibitionRound, evaluateInhibitionAttempt } from './inhibition'

describe('createInhibitionRound', () => {
  it('creates a simple four-option round with one odd number', () => {
    const round = createInhibitionRound('简单', () => 0)

    expect(round.options).toEqual(['2', '1', '1', '1'])
    expect(round.correctIndex).toBe(0)
    expect(round.timeoutMs).toBe(7000)
  })

  it('creates a difficult nine-option round', () => {
    const round = createInhibitionRound('困难', () => 0.99)

    expect(round.options).toHaveLength(9)
    expect(round.correctIndex).toBeGreaterThanOrEqual(0)
    expect(round.correctIndex).toBeLessThan(9)
    expect(round.timeoutMs).toBe(4000)
  })
})

describe('evaluateInhibitionAttempt', () => {
  it('returns correct when selected index is the odd number', () => {
    expect(evaluateInhibitionAttempt({ correctIndex: 2 }, 2)).toEqual({
      correct: true,
      correctIndex: 2,
      selectedIndex: 2,
    })
  })

  it('returns incorrect when selected index is different', () => {
    expect(evaluateInhibitionAttempt({ correctIndex: 2 }, 1).correct).toBe(false)
  })
})
```

- [x] **Step 4: Write failing scoring tests**

Create `miniapp/src/pages/game-session/scoring.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { buildGameTrainingResult, minutesFromSeconds } from './scoring'

describe('minutesFromSeconds', () => {
  it('rounds positive seconds up to integer minutes', () => {
    expect(minutesFromSeconds(1)).toBe(1)
    expect(minutesFromSeconds(60)).toBe(1)
    expect(minutesFromSeconds(61)).toBe(2)
  })

  it('returns zero when duration is zero', () => {
    expect(minutesFromSeconds(0)).toBe(0)
  })
})

describe('buildGameTrainingResult', () => {
  it('builds completed result for timer ended session', () => {
    const result = buildGameTrainingResult({
      gameCode: 'game-memory-color-sequence',
      prescribedDifficulty: '简单',
      actualDifficulty: '中等',
      difficultyAdjustReason: '太简单，想提高难度',
      endedBy: 'timer',
      durationSeconds: 600,
      suggestedDurationMinutes: 10,
      completedUnits: 10,
      correctUnits: 8,
      uploadMode: 'direct',
      retryCount: 0,
      totalRetryCount: 0,
    })

    expect(result.status).toBe('completed')
    expect(result.actual_duration_minutes).toBe(10)
    expect(result.score).toBe(77)
    expect(result.form_data.accuracy_rate).toBe(80)
    expect(result.form_data.error_count).toBe(2)
    expect(result.form_data.difficulty).toBe('中等')
    expect(result.form_data.raw_detail.ended_early).toBe(false)
    expect(result.form_data.raw_detail.difficulty_adjusted).toBe(true)
  })

  it('builds partial result for manual ended session', () => {
    const result = buildGameTrainingResult({
      gameCode: 'game-executive-inhibition',
      prescribedDifficulty: '困难',
      actualDifficulty: '困难',
      difficultyAdjustReason: '',
      endedBy: 'manual',
      durationSeconds: 130,
      suggestedDurationMinutes: 10,
      completedUnits: 5,
      correctUnits: 5,
      uploadMode: 'retry',
      retryCount: 3,
      totalRetryCount: 13,
    })

    expect(result.status).toBe('partial')
    expect(result.actual_duration_minutes).toBe(3)
    expect(result.score).toBe(83)
    expect(result.form_data.raw_detail.upload_mode).toBe('retry')
    expect(result.form_data.raw_detail.retry_count).toBe(3)
    expect(result.form_data.raw_detail.total_retry_count).toBe(13)
  })
})
```

- [x] **Step 5: Run tests and verify they fail**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/colorSequence.test.ts src/pages/game-session/inhibition.test.ts src/pages/game-session/scoring.test.ts
```

Expected: FAIL with module-not-found errors for `colorSequence`, `inhibition`, and `scoring`.

- [x] **Step 6: Create shared game types**

Create `miniapp/src/pages/game-session/gameTypes.ts`:

```ts
export type GameDifficulty = '简单' | '中等' | '困难'
export type GameCode = 'game-memory-color-sequence' | 'game-executive-inhibition'
export type GameEndReason = 'timer' | 'manual'
export type GameUploadMode = 'direct' | 'retry'
export type TrainingStatus = 'completed' | 'partial' | 'missed'

export const GAME_DIFFICULTIES: GameDifficulty[] = ['简单', '中等', '困难']

export type GameTrainingPayload = {
  prescription_action: number
  training_date: string
  status: TrainingStatus
  actual_duration_minutes: number
  score: number
  form_data: {
    accuracy_rate: number
    error_count: number
    difficulty: GameDifficulty
    raw_detail: {
      game_code: GameCode
      ended_by: GameEndReason
      ended_early: boolean
      prescribed_difficulty: string
      difficulty_adjusted: boolean
      difficulty_adjust_reason: string
      upload_mode: GameUploadMode
      retry_count: number
      total_retry_count: number
      session_duration_seconds: number
      suggested_duration_minutes: number
      completed_units: number
      correct_units: number
    }
  }
  note: string
}

export type GameActionSummary = {
  id: number
  action_name: string
  action_type: string
  action_instruction: string
  duration_minutes: number | null
  weekly_target_count: number
  weekly_completed_count: number
  difficulty: string
  notes: string
}
```

- [x] **Step 7: Implement color sequence logic**

Create `miniapp/src/pages/game-session/colorSequence.ts`:

```ts
import type { GameDifficulty } from './gameTypes'

export type ColorToken = 'blue' | 'green' | 'yellow' | 'red' | 'teal'

export type ColorSequenceRound = {
  colors: ColorToken[]
  sequence: ColorToken[]
  revealMs: number
  inputTimeoutMs: number
}

const COLOR_POOL: ColorToken[] = ['blue', 'green', 'yellow', 'red', 'teal']

const CONFIG: Record<GameDifficulty, { colorCount: number; minLength: number; maxLength: number; revealMs: number; inputTimeoutMs: number }> = {
  简单: { colorCount: 3, minLength: 3, maxLength: 3, revealMs: 900, inputTimeoutMs: 8000 },
  中等: { colorCount: 4, minLength: 4, maxLength: 5, revealMs: 720, inputTimeoutMs: 6500 },
  困难: { colorCount: 5, minLength: 5, maxLength: 7, revealMs: 560, inputTimeoutMs: 5000 },
}

function pickIndex(length: number, random: () => number): number {
  return Math.min(length - 1, Math.floor(random() * length))
}

export function createColorSequenceRound(difficulty: GameDifficulty, random: () => number = Math.random): ColorSequenceRound {
  const config = CONFIG[difficulty]
  const colors = COLOR_POOL.slice(0, config.colorCount)
  const length = config.minLength + pickIndex(config.maxLength - config.minLength + 1, random)
  const sequence = Array.from({ length }, () => colors[pickIndex(colors.length, random)])

  return {
    colors,
    sequence,
    revealMs: config.revealMs,
    inputTimeoutMs: config.inputTimeoutMs,
  }
}

export function evaluateColorSequenceAttempt(expected: ColorToken[], actual: ColorToken[]) {
  const correct = expected.length === actual.length && expected.every((token, index) => token === actual[index])
  return { correct, expected, actual }
}
```

- [x] **Step 8: Implement inhibition logic**

Create `miniapp/src/pages/game-session/inhibition.ts`:

```ts
import type { GameDifficulty } from './gameTypes'

export type InhibitionRound = {
  options: string[]
  correctIndex: number
  timeoutMs: number
}

const CONFIG: Record<GameDifficulty, { optionCount: number; timeoutMs: number }> = {
  简单: { optionCount: 4, timeoutMs: 7000 },
  中等: { optionCount: 6, timeoutMs: 5500 },
  困难: { optionCount: 9, timeoutMs: 4000 },
}

function pickIndex(length: number, random: () => number): number {
  return Math.min(length - 1, Math.floor(random() * length))
}

export function createInhibitionRound(difficulty: GameDifficulty, random: () => number = Math.random): InhibitionRound {
  const config = CONFIG[difficulty]
  const baseDigit = String(pickIndex(8, random) + 1)
  const oddDigit = baseDigit === '9' ? '1' : String(Number(baseDigit) + 1)
  const correctIndex = pickIndex(config.optionCount, random)
  const options = Array.from({ length: config.optionCount }, (_value, index) => (index === correctIndex ? oddDigit : baseDigit))

  return {
    options,
    correctIndex,
    timeoutMs: config.timeoutMs,
  }
}

export function evaluateInhibitionAttempt(round: Pick<InhibitionRound, 'correctIndex'>, selectedIndex: number) {
  return {
    correct: selectedIndex === round.correctIndex,
    correctIndex: round.correctIndex,
    selectedIndex,
  }
}
```

- [x] **Step 9: Implement scoring logic**

Create `miniapp/src/pages/game-session/scoring.ts`:

```ts
import type { GameCode, GameDifficulty, GameEndReason, GameTrainingPayload, GameUploadMode, TrainingStatus } from './gameTypes'

type BuildGameTrainingResultInput = {
  gameCode: GameCode
  prescribedDifficulty: string
  actualDifficulty: GameDifficulty
  difficultyAdjustReason: string
  endedBy: GameEndReason
  durationSeconds: number
  suggestedDurationMinutes: number
  completedUnits: number
  correctUnits: number
  uploadMode: GameUploadMode
  retryCount: number
  totalRetryCount: number
}

export function minutesFromSeconds(seconds: number): number {
  if (seconds <= 0) return 0
  return Math.ceil(seconds / 60)
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function expectedUnits(suggestedDurationMinutes: number): number {
  return Math.max(1, suggestedDurationMinutes * 2)
}

export function buildGameTrainingResult(input: BuildGameTrainingResultInput): Omit<GameTrainingPayload, 'prescription_action' | 'training_date' | 'note'> {
  const completedUnits = Math.max(0, input.completedUnits)
  const correctUnits = clamp(input.correctUnits, 0, completedUnits)
  const errorCount = Math.max(0, completedUnits - correctUnits)
  const accuracyRate = completedUnits === 0 ? 0 : Math.round((correctUnits / completedUnits) * 100)
  const volumeBonus = Math.min(10, (completedUnits / expectedUnits(input.suggestedDurationMinutes)) * 10)
  const earlyPenalty = input.endedBy === 'manual' ? 10 : 0
  const score = clamp(Math.round(accuracyRate * 0.9 + volumeBonus - earlyPenalty), 0, 100)
  const status: TrainingStatus = input.endedBy === 'manual' ? 'partial' : 'completed'

  return {
    status,
    actual_duration_minutes: minutesFromSeconds(input.durationSeconds),
    score,
    form_data: {
      accuracy_rate: accuracyRate,
      error_count: errorCount,
      difficulty: input.actualDifficulty,
      raw_detail: {
        game_code: input.gameCode,
        ended_by: input.endedBy,
        ended_early: input.endedBy === 'manual',
        prescribed_difficulty: input.prescribedDifficulty,
        difficulty_adjusted: input.actualDifficulty !== input.prescribedDifficulty,
        difficulty_adjust_reason: input.difficultyAdjustReason,
        upload_mode: input.uploadMode,
        retry_count: input.retryCount,
        total_retry_count: input.totalRetryCount,
        session_duration_seconds: Math.max(0, Math.round(input.durationSeconds)),
        suggested_duration_minutes: input.suggestedDurationMinutes,
        completed_units: completedUnits,
        correct_units: correctUnits,
      },
    },
  }
}
```

- [x] **Step 10: Run game core tests**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/colorSequence.test.ts src/pages/game-session/inhibition.test.ts src/pages/game-session/scoring.test.ts
```

Expected: PASS.

- [x] **Step 11: Commit game core**

If commit is authorized, run:

```bash
git add miniapp/package.json miniapp/package-lock.json miniapp/src/pages/game-session/gameTypes.ts miniapp/src/pages/game-session/colorSequence.ts miniapp/src/pages/game-session/colorSequence.test.ts miniapp/src/pages/game-session/inhibition.ts miniapp/src/pages/game-session/inhibition.test.ts miniapp/src/pages/game-session/scoring.ts miniapp/src/pages/game-session/scoring.test.ts
git commit -m "feat(miniapp): 新增真实游戏核心逻辑"
```

---

### Task 2: Pending Upload Cache and Retry Window

**Files:**
- Create: `miniapp/src/pages/game-session/retryUpload.ts`
- Create: `miniapp/src/pages/game-session/retryUpload.test.ts`

- [x] **Step 1: Write failing retry tests**

Create `miniapp/src/pages/game-session/retryUpload.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'

import type { GameTrainingPayload } from './gameTypes'
import {
  RETRY_DELAYS_SECONDS,
  clearPendingGameUpload,
  loadPendingGameUpload,
  markRetryFailure,
  resetRetryWindowForLaunch,
  savePendingGameUpload,
} from './retryUpload'

function payload(): GameTrainingPayload {
  return {
    prescription_action: 100,
    training_date: '2026-05-16',
    status: 'completed',
    actual_duration_minutes: 10,
    score: 90,
    form_data: {
      accuracy_rate: 90,
      error_count: 1,
      difficulty: '中等',
      raw_detail: {
        game_code: 'game-memory-color-sequence',
        ended_by: 'timer',
        ended_early: false,
        prescribed_difficulty: '中等',
        difficulty_adjusted: false,
        difficulty_adjust_reason: '',
        upload_mode: 'direct',
        retry_count: 0,
        total_retry_count: 0,
        session_duration_seconds: 600,
        suggested_duration_minutes: 10,
        completed_units: 10,
        correct_units: 9,
      },
    },
    note: '',
  }
}

function memoryStorage() {
  const store = new Map<string, unknown>()
  return {
    getStorageSync: vi.fn((key: string) => store.get(key)),
    setStorageSync: vi.fn((key: string, value: unknown) => store.set(key, value)),
    removeStorageSync: vi.fn((key: string) => store.delete(key)),
  }
}

describe('pending game upload retry state', () => {
  it('stores one pending upload and clears it after success', () => {
    const storage = memoryStorage()

    savePendingGameUpload(storage, payload(), 1000)
    expect(loadPendingGameUpload(storage)?.payload.prescription_action).toBe(100)

    clearPendingGameUpload(storage)
    expect(loadPendingGameUpload(storage)).toBeNull()
  })

  it('pauses after ten failures in one launch window', () => {
    const storage = memoryStorage()
    savePendingGameUpload(storage, payload(), 1000)

    for (let index = 0; index < 10; index += 1) {
      markRetryFailure(storage, `失败 ${index + 1}`, 1000 + index * 1000)
    }

    const pending = loadPendingGameUpload(storage)
    expect(pending?.retry_count).toBe(10)
    expect(pending?.total_retry_count).toBe(10)
    expect(pending?.retry_paused_until_next_launch).toBe(true)
  })

  it('resets current retry count on next launch but preserves total retry count', () => {
    const storage = memoryStorage()
    savePendingGameUpload(storage, payload(), 1000)
    for (let index = 0; index < 10; index += 1) {
      markRetryFailure(storage, '网络失败', 1000)
    }

    resetRetryWindowForLaunch(storage)

    const pending = loadPendingGameUpload(storage)
    expect(pending?.retry_count).toBe(0)
    expect(pending?.total_retry_count).toBe(10)
    expect(pending?.retry_paused_until_next_launch).toBe(false)
  })

  it('uses capped retry delays', () => {
    expect(RETRY_DELAYS_SECONDS).toEqual([5, 10, 20, 40, 80, 160, 300, 300, 300, 300])
  })
})
```

- [x] **Step 2: Run retry tests and verify they fail**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/retryUpload.test.ts
```

Expected: FAIL with module-not-found for `retryUpload`.

- [x] **Step 3: Implement retry cache**

Create `miniapp/src/pages/game-session/retryUpload.ts`:

```ts
import type { GameTrainingPayload } from './gameTypes'

export const PENDING_GAME_UPLOAD_KEY = 'motioncare.pendingGameUpload'
export const RETRY_DELAYS_SECONDS = [5, 10, 20, 40, 80, 160, 300, 300, 300, 300] as const
export const MAX_RETRY_PER_LAUNCH = 10

type StorageLike = {
  getStorageSync(key: string): unknown
  setStorageSync(key: string, value: unknown): void
  removeStorageSync(key: string): void
}

export type PendingGameUpload = {
  payload: GameTrainingPayload
  retry_count: number
  total_retry_count: number
  next_retry_at: number
  last_error: string
  created_at: number
  retry_paused_until_next_launch: boolean
}

function isPendingGameUpload(value: unknown): value is PendingGameUpload {
  return Boolean(
    value &&
      typeof value === 'object' &&
      'payload' in value &&
      'retry_count' in value &&
      'total_retry_count' in value
  )
}

export function loadPendingGameUpload(storage: StorageLike): PendingGameUpload | null {
  const value = storage.getStorageSync(PENDING_GAME_UPLOAD_KEY)
  return isPendingGameUpload(value) ? value : null
}

export function savePendingGameUpload(storage: StorageLike, payload: GameTrainingPayload, now: number): PendingGameUpload {
  const pending: PendingGameUpload = {
    payload,
    retry_count: 0,
    total_retry_count: 0,
    next_retry_at: now,
    last_error: '',
    created_at: now,
    retry_paused_until_next_launch: false,
  }
  storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, pending)
  return pending
}

export function clearPendingGameUpload(storage: StorageLike): void {
  storage.removeStorageSync(PENDING_GAME_UPLOAD_KEY)
}

export function markRetryFailure(storage: StorageLike, error: string, now: number): PendingGameUpload | null {
  const pending = loadPendingGameUpload(storage)
  if (!pending) return null

  const retryCount = Math.min(MAX_RETRY_PER_LAUNCH, pending.retry_count + 1)
  const delayIndex = Math.min(retryCount - 1, RETRY_DELAYS_SECONDS.length - 1)
  const updated: PendingGameUpload = {
    ...pending,
    retry_count: retryCount,
    total_retry_count: pending.total_retry_count + 1,
    next_retry_at: now + RETRY_DELAYS_SECONDS[delayIndex] * 1000,
    last_error: error,
    retry_paused_until_next_launch: retryCount >= MAX_RETRY_PER_LAUNCH,
  }
  storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, updated)
  return updated
}

export function resetRetryWindowForLaunch(storage: StorageLike): PendingGameUpload | null {
  const pending = loadPendingGameUpload(storage)
  if (!pending) return null

  const updated: PendingGameUpload = {
    ...pending,
    retry_count: 0,
    next_retry_at: Date.now(),
    retry_paused_until_next_launch: false,
  }
  storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, updated)
  return updated
}
```

- [x] **Step 4: Run retry tests**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/retryUpload.test.ts
```

Expected: PASS.

- [x] **Step 5: Commit retry cache**

If commit is authorized, run:

```bash
git add miniapp/src/pages/game-session/retryUpload.ts miniapp/src/pages/game-session/retryUpload.test.ts
git commit -m "feat(miniapp): 新增游戏结果补传缓存"
```

---

### Task 3: Audio Resource Manifest and Generated Temporary Audio

**Files:**
- Create: `miniapp/scripts/generate-game-audio.mjs`
- Create generated assets: `miniapp/src/assets/audio/game-session/*.m4a`
- Create: `miniapp/src/pages/game-session/gameAudio.ts`

- [x] **Step 1: Add audio generation script**

Create `miniapp/scripts/generate-game-audio.mjs`:

```js
import { existsSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const outDir = join(root, 'src/assets/audio/game-session')

const clips = [
  ['color_intro', '颜色顺序记忆训练开始。请记住方块亮起的顺序，随后按相同顺序点击。'],
  ['inhibition_intro', '反应抑制训练开始。请从数字中找出不一样的那个，并点击它。'],
  ['count_3', '三'],
  ['count_2', '二'],
  ['count_1', '一'],
  ['start', '开始'],
  ['correct', '做得很好，答对了。'],
  ['wrong', '没关系，调整一下，继续下一题。'],
  ['complete', '本次训练完成，辛苦了。'],
  ['manual_end', '你将提前结束本次训练，系统会保存一次部分完成记录。'],
  ['tap', ' '],
]

mkdirSync(outDir, { recursive: true })

for (const [name, text] of clips) {
  const aiffPath = join(outDir, `${name}.aiff`)
  const m4aPath = join(outDir, `${name}.m4a`)
  if (!existsSync(m4aPath)) {
    execFileSync('say', ['-v', 'Tingting', '-o', aiffPath, text], { stdio: 'inherit' })
    execFileSync('afconvert', ['-f', 'm4af', '-d', 'aac', aiffPath, m4aPath], { stdio: 'inherit' })
  }
}
```

- [x] **Step 2: Generate audio files**

Run:

```bash
cd miniapp && node scripts/generate-game-audio.mjs
```

Expected: `miniapp/src/assets/audio/game-session/` contains `.m4a` files for each clip in the script.

- [x] **Step 3: Add audio manifest and playback helper**

Create `miniapp/src/pages/game-session/gameAudio.ts`:

```ts
import Taro from '@tarojs/taro'

export type GameAudioKey =
  | 'color_intro'
  | 'inhibition_intro'
  | 'count_3'
  | 'count_2'
  | 'count_1'
  | 'start'
  | 'correct'
  | 'wrong'
  | 'complete'
  | 'manual_end'
  | 'tap'

const AUDIO_MUTED_KEY = 'motioncare.gameAudioMuted'

export const GAME_AUDIO_TEXT: Record<GameAudioKey, string> = {
  color_intro: '请记住方块亮起的顺序，随后按相同顺序点击。',
  inhibition_intro: '请从数字中找出不一样的那个，并点击它。',
  count_3: '三',
  count_2: '二',
  count_1: '一',
  start: '开始',
  correct: '做得很好，答对了。',
  wrong: '没关系，调整一下，继续下一题。',
  complete: '本次训练完成，辛苦了。',
  manual_end: '提前结束后，系统会保存一次部分完成记录。',
  tap: '',
}

export const GAME_AUDIO_SRC: Record<GameAudioKey, string> = {
  color_intro: '/assets/audio/game-session/color_intro.m4a',
  inhibition_intro: '/assets/audio/game-session/inhibition_intro.m4a',
  count_3: '/assets/audio/game-session/count_3.m4a',
  count_2: '/assets/audio/game-session/count_2.m4a',
  count_1: '/assets/audio/game-session/count_1.m4a',
  start: '/assets/audio/game-session/start.m4a',
  correct: '/assets/audio/game-session/correct.m4a',
  wrong: '/assets/audio/game-session/wrong.m4a',
  complete: '/assets/audio/game-session/complete.m4a',
  manual_end: '/assets/audio/game-session/manual_end.m4a',
  tap: '/assets/audio/game-session/tap.m4a',
}

export function isGameAudioMuted(): boolean {
  return Taro.getStorageSync(AUDIO_MUTED_KEY) === true
}

export function setGameAudioMuted(value: boolean): void {
  Taro.setStorageSync(AUDIO_MUTED_KEY, value)
}

export function playGameAudio(key: GameAudioKey): Promise<void> {
  if (isGameAudioMuted()) return Promise.resolve()
  return new Promise((resolve) => {
    const audio = Taro.createInnerAudioContext()
    audio.src = GAME_AUDIO_SRC[key]
    audio.onEnded(() => {
      audio.destroy()
      resolve()
    })
    audio.onError(() => {
      audio.destroy()
      resolve()
    })
    audio.play()
  })
}
```

- [x] **Step 4: Build miniapp to verify assets are bundled**

Run:

```bash
cd miniapp && npm run build:weapp
```

Expected: PASS, and build output includes audio assets under `dist/assets/audio/game-session/` or the Taro equivalent static asset path.

- [x] **Step 5: Commit audio assets**

If commit is authorized, run:

```bash
git add miniapp/scripts/generate-game-audio.mjs miniapp/src/assets/audio/game-session miniapp/src/pages/game-session/gameAudio.ts
git commit -m "feat(miniapp): 新增游戏语音与音效资源"
```

---

### Task 4: Real Game Session Page

**Files:**
- Modify: `miniapp/src/pages/game-session/index.tsx`
- Modify: `miniapp/src/app.scss`

- [x] **Step 1: Replace existing game page with session states**

Modify `miniapp/src/pages/game-session/index.tsx` so it imports the new modules:

```ts
import { Button, Input, Picker, Text, View } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { useEffect, useMemo, useRef, useState } from 'react'

import { request } from '../../api/client'
import type { CurrentPrescription } from '../../types/patientApp'
import { todayLocalDate } from '../../utils/date'
import { createColorSequenceRound, evaluateColorSequenceAttempt, type ColorSequenceRound, type ColorToken } from './colorSequence'
import { GAME_AUDIO_TEXT, isGameAudioMuted, playGameAudio, setGameAudioMuted } from './gameAudio'
import type { GameActionSummary, GameCode, GameDifficulty, GameEndReason, GameTrainingPayload } from './gameTypes'
import { createInhibitionRound, evaluateInhibitionAttempt, type InhibitionRound } from './inhibition'
import { savePendingGameUpload } from './retryUpload'
import { buildGameTrainingResult } from './scoring'
```

Add these local state types near the imports:

```ts
type SessionPhase = 'loading' | 'setup' | 'intro' | 'playing' | 'paused' | 'result'

type UnitResult = {
  correct: boolean
}

type UploadState = 'idle' | 'uploading' | 'uploaded' | 'pending_retry'

const DIFFICULTY_OPTIONS: GameDifficulty[] = ['简单', '中等', '困难']

const GAME_CODE_BY_SOURCE: Record<string, GameCode> = {
  'game-memory-color-sequence': 'game-memory-color-sequence',
  'game-executive-inhibition': 'game-executive-inhibition',
}

const COLOR_LABEL: Record<ColorToken, string> = {
  blue: '蓝',
  green: '绿',
  yellow: '黄',
  red: '红',
  teal: '青',
}
```

Remove the old `parseOptionalNumber` helper and the old manual score/duration form state; the real game flow computes score, duration, correct rate, and error count automatically.

Inside `GameSessionPage`, replace the old form state with these states:

```ts
const [phase, setPhase] = useState<SessionPhase>('loading')
const [prescription, setPrescription] = useState<CurrentPrescription>(null)
const [loaded, setLoaded] = useState(false)
const [difficultyIndex, setDifficultyIndex] = useState(0)
const [difficultyReason, setDifficultyReason] = useState('')
const [elapsedSeconds, setElapsedSeconds] = useState(0)
const [unitResults, setUnitResults] = useState<UnitResult[]>([])
const [feedback, setFeedback] = useState('')
const [muted, setMuted] = useState(isGameAudioMuted())
const [uploadState, setUploadState] = useState<UploadState>('idle')
const [resultPayload, setResultPayload] = useState<GameTrainingPayload | null>(null)
const [error, setError] = useState('')
const [activeColorRound, setActiveColorRound] = useState<ColorSequenceRound | null>(null)
const [activeColorInput, setActiveColorInput] = useState<ColorToken[]>([])
const [activeInhibitionRound, setActiveInhibitionRound] = useState<InhibitionRound | null>(null)
const targetSecondsRef = useRef(600)
```

- [x] **Step 2: Add helpers that infer game code and default difficulty**

In `index.tsx`, add:

```ts
function normalizeDifficulty(value: string): GameDifficulty {
  return DIFFICULTY_OPTIONS.includes(value as GameDifficulty) ? (value as GameDifficulty) : '简单'
}

function gameCodeForAction(actionName: string): GameCode {
  if (actionName.includes('反应抑制')) return 'game-executive-inhibition'
  return 'game-memory-color-sequence'
}

function suggestedDurationMinutes(action: GameActionSummary): number {
  return action.duration_minutes && action.duration_minutes > 0 ? action.duration_minutes : 10
}

function textForEndReason(reason: GameEndReason) {
  return reason === 'timer' ? '已按处方建议时长完成' : '已提前结束，本次记录为部分完成'
}
```

Add a top bar helper used by both games:

```tsx
function renderGameTopBar() {
  return (
    <View className='game-topbar'>
      <Text className='game-stat'>剩余 {Math.max(0, targetSecondsRef.current - elapsedSeconds)} 秒</Text>
      <Button className='secondary-button' onClick={() => setPhase(phase === 'paused' ? 'playing' : 'paused')}>
        {phase === 'paused' ? '继续' : '暂停'}
      </Button>
      <Button
        className='secondary-button'
        onClick={() => {
          const nextMuted = !muted
          setMuted(nextMuted)
          setGameAudioMuted(nextMuted)
        }}
      >
        {muted ? '开启声音' : '关闭声音'}
      </Button>
      <Button className='secondary-button' onClick={() => endSession('manual')}>
        提前结束
      </Button>
    </View>
  )
}
```

This deliberately uses action name fallback because current miniapp action payload does not expose `source_key`.

- [x] **Step 3: Implement setup and difficulty adjustment behavior**

Replace the first render branch after loaded/action validation with setup UI:

```tsx
if (phase === 'setup') {
  const prescribedDifficulty = normalizeDifficulty(action.difficulty)
  const adjusted = difficulty !== prescribedDifficulty
  return (
    <View className='page game-session-page hainan-game-page'>
      <View className='game-hero'>
        <Text className='eyebrow'>海南康复训练</Text>
        <Text className='title'>{action.action_name}</Text>
        <Text className='paragraph'>{action.action_instruction}</Text>
      </View>

      <View className='panel'>
        <View className='row'>
          <Text className='label'>处方建议时长</Text>
          <Text className='value'>{suggestedDurationMinutes(action)} 分钟</Text>
        </View>
        <View className='row'>
          <Text className='label'>处方默认难度</Text>
          <Text className='value'>{prescribedDifficulty}</Text>
        </View>
      </View>

      <View className='field-card'>
        <Text className='label'>本次训练难度</Text>
        <Picker mode='selector' range={DIFFICULTY_OPTIONS} value={difficultyIndex} onChange={(event) => setDifficultyIndex(Number(event.detail.value))}>
          <Text className='value'>{difficulty}</Text>
        </Picker>
      </View>

      {adjusted ? (
        <View className='field-card'>
          <Text className='label'>调整难度原因</Text>
          <Text className='muted'>请填写原因，医生端可见</Text>
          <Input className='input' value={difficultyReason} onInput={(event) => setDifficultyReason(event.detail.value)} />
        </View>
      ) : null}

      {error ? <Text className='error'>{error}</Text> : null}

      <Button className='primary-button' onClick={startIntro}>
        开始游戏
      </Button>
    </View>
  )
}
```

The `startIntro` function must reject adjusted difficulty with an empty reason:

```ts
async function startIntro() {
  const prescribedDifficulty = normalizeDifficulty(action?.difficulty ?? '')
  if (difficulty !== prescribedDifficulty && !difficultyReason.trim()) {
    setError('调整难度后需要填写原因')
    return
  }
  setError('')
  setPhase('intro')
  await playGameAudio(gameCode === 'game-memory-color-sequence' ? 'color_intro' : 'inhibition_intro')
  await playGameAudio('count_3')
  await playGameAudio('count_2')
  await playGameAudio('count_1')
  await playGameAudio('start')
  beginPlaying()
}
```

- [x] **Step 4: Implement play loop dispatch**

Use a single interval for remaining seconds:

```ts
useEffect(() => {
  if (phase !== 'playing') return undefined
  const timer = setInterval(() => {
    setElapsedSeconds((value) => {
      const next = value + 1
      if (next >= targetSecondsRef.current) {
        endSession('timer')
      }
      return next
    })
  }, 1000)
  return () => clearInterval(timer)
}, [phase])
```

Use separate render branches:

```tsx
if (phase === 'playing' && gameCode === 'game-memory-color-sequence') {
  return renderColorSequenceGame()
}

if (phase === 'playing' && gameCode === 'game-executive-inhibition') {
  return renderInhibitionGame()
}
```

The color branch should render large colored tiles with text labels:

```tsx
function renderColorSequenceGame() {
  const round = activeColorRound as ColorSequenceRound
  return (
    <View className='page game-session-page hainan-game-page'>
      {renderGameTopBar()}
      <Text className='section-title'>请按刚才亮起的顺序点击颜色</Text>
      <View className='color-grid'>
        {round.colors.map((color) => (
          <Button key={color} className={`color-tile color-${color}`} onClick={() => selectColor(color)}>
            {COLOR_LABEL[color]}
          </Button>
        ))}
      </View>
      {feedback ? <Text className='game-feedback'>{feedback}</Text> : null}
    </View>
  )
}
```

The inhibition branch should render large number tiles:

```tsx
function renderInhibitionGame() {
  const round = activeInhibitionRound as InhibitionRound
  return (
    <View className='page game-session-page hainan-game-page'>
      {renderGameTopBar()}
      <Text className='section-title'>请选择不一样的数字</Text>
      <View className='number-grid'>
        {round.options.map((value, index) => (
          <Button key={`${value}-${index}`} className='number-tile' onClick={() => selectInhibition(index)}>
            {value}
          </Button>
        ))}
      </View>
      {feedback ? <Text className='game-feedback'>{feedback}</Text> : null}
    </View>
  )
}
```

- [x] **Step 5: Implement end and upload behavior**

Add upload function:

```ts
async function uploadResult(payload: GameTrainingPayload) {
  setUploadState('uploading')
  try {
    await request('/patient-app/training-records/', {
      method: 'POST',
      data: payload,
    })
    setUploadState('uploaded')
  } catch (err) {
    savePendingGameUpload(Taro, payload, Date.now())
    setUploadState('pending_retry')
    setError(err instanceof Error ? err.message : '上传失败，已保存待补传记录')
  }
}
```

Add end function:

```ts
function endSession(reason: GameEndReason) {
  if (!action || phase === 'result') return
  const base = buildGameTrainingResult({
    gameCode,
    prescribedDifficulty: normalizeDifficulty(action.difficulty),
    actualDifficulty: difficulty,
    difficultyAdjustReason: difficultyReason.trim(),
    endedBy: reason,
    durationSeconds: elapsedSeconds,
    suggestedDurationMinutes: suggestedDurationMinutes(action),
    completedUnits: unitResults.length,
    correctUnits: unitResults.filter((item) => item.correct).length,
    uploadMode: 'direct',
    retryCount: 0,
    totalRetryCount: 0,
  })
  const payload: GameTrainingPayload = {
    ...base,
    prescription_action: action.id,
    training_date: todayLocalDate(),
    note: reason === 'manual' ? '患者提前结束本次游戏训练' : '',
  }
  setResultPayload(payload)
  setPhase('result')
  playGameAudio(reason === 'manual' ? 'manual_end' : 'complete')
  uploadResult(payload)
}
```

The result page must display `score`、`accuracy_rate`、`error_count`、`difficulty`、`textForEndReason` and upload state.

- [x] **Step 6: Add game page styles**

Modify `miniapp/src/app.scss` and append:

```scss
.hainan-game-page {
  background: #eef8f6;
}

.game-hero {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
  padding: 24px;
  border: 1px solid #b7dfd7;
  border-radius: 8px;
  background: #fffaf0;
}

.eyebrow {
  display: block;
  color: #0f766e;
  font-size: 22px;
  font-weight: 600;
}

.game-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}

.game-stat {
  color: #0f172a;
  font-size: 24px;
  font-weight: 600;
}

.color-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.color-tile,
.number-tile {
  min-height: 150px;
  border-radius: 8px;
  color: #ffffff;
  font-size: 32px;
  font-weight: 700;
}

.color-blue { background: #2563eb; }
.color-green { background: #16a34a; }
.color-yellow { background: #d97706; }
.color-red { background: #dc2626; }
.color-teal { background: #0f766e; }

.number-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.number-tile {
  border: 2px solid #0f766e;
  color: #0f172a;
  background: #ffffff;
  font-size: 44px;
}

.game-feedback {
  display: block;
  margin-top: 18px;
  color: #0f766e;
  font-size: 28px;
  font-weight: 700;
}

.pending-upload-banner {
  display: block;
  margin: 16px 0;
  padding: 18px;
  border: 1px solid #f59e0b;
  border-radius: 8px;
  color: #92400e;
  background: #fffbeb;
  font-size: 24px;
}
```

- [x] **Step 7: Type-check and build miniapp**

Run:

```bash
cd miniapp && npx tsc --noEmit --skipLibCheck
cd miniapp && npm run build:weapp
```

Expected: both PASS.

- [x] **Step 8: Commit real game session page**

If commit is authorized, run:

```bash
git add miniapp/src/pages/game-session/index.tsx miniapp/src/app.scss
git commit -m "feat(miniapp): 实现真实游戏训练页"
```

---

### Task 5: App Foreground Retry Recovery

**Files:**
- Modify: `miniapp/src/app.ts`
- Modify: `miniapp/src/pages/home/index.tsx`
- Modify: `miniapp/src/pages/prescription/index.tsx`

- [x] **Step 1: Add foreground retry helper**

Modify the import section of `miniapp/src/pages/game-session/retryUpload.ts`:

```ts
import { request } from '../../api/client'
import type { GameTrainingPayload } from './gameTypes'
```

Then append:

```ts
export async function tryUploadPendingGameRecord(storage: StorageLike, now: number = Date.now()): Promise<'none' | 'uploaded' | 'waiting' | 'failed'> {
  const pending = loadPendingGameUpload(storage)
  if (!pending) return 'none'
  if (pending.retry_paused_until_next_launch) return 'waiting'
  if (pending.next_retry_at > now) return 'waiting'

  const payload = {
    ...pending.payload,
    form_data: {
      ...pending.payload.form_data,
      raw_detail: {
        ...pending.payload.form_data.raw_detail,
        upload_mode: 'retry' as const,
        retry_count: pending.retry_count,
        total_retry_count: pending.total_retry_count,
      },
    },
  }

  try {
    await request('/patient-app/training-records/', { method: 'POST', data: payload })
    clearPendingGameUpload(storage)
    return 'uploaded'
  } catch (err) {
    markRetryFailure(storage, err instanceof Error ? err.message : '上传失败', now)
    return 'failed'
  }
}
```

- [x] **Step 2: Use app foreground hook**

Modify `miniapp/src/app.ts`:

```ts
import { PropsWithChildren } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'

import { resetRetryWindowForLaunch, tryUploadPendingGameRecord } from './pages/game-session/retryUpload'

import './app.scss'

function App({ children }: PropsWithChildren<any>) {
  useDidShow(() => {
    resetRetryWindowForLaunch(Taro)
    tryUploadPendingGameRecord(Taro)
  })

  return children
}

export default App
```

- [x] **Step 3: Show pending upload banner on home page**

Modify `miniapp/src/pages/home/index.tsx` to import:

```ts
import Taro, { useDidShow } from '@tarojs/taro'
import { loadPendingGameUpload, tryUploadPendingGameRecord } from '../game-session/retryUpload'
```

Add state:

```ts
const [hasPendingGameUpload, setHasPendingGameUpload] = useState(false)
```

Inside the existing `useDidShow`, after loading home data:

```ts
setHasPendingGameUpload(Boolean(loadPendingGameUpload(Taro)))
tryUploadPendingGameRecord(Taro).finally(() => {
  setHasPendingGameUpload(Boolean(loadPendingGameUpload(Taro)))
})
```

Render near the top of the page:

```tsx
{hasPendingGameUpload ? <Text className='pending-upload-banner'>有一条游戏训练记录待上传，系统会自动重试。</Text> : null}
```

- [x] **Step 4: Show pending upload banner on prescription page**

Modify `miniapp/src/pages/prescription/index.tsx` to import:

```ts
import { loadPendingGameUpload, tryUploadPendingGameRecord } from '../game-session/retryUpload'
```

Add the same `hasPendingGameUpload` state and `useDidShow` retry refresh pattern as the home page. Render the same banner before action cards.

- [x] **Step 5: Type-check and test retry helper**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/retryUpload.test.ts
cd miniapp && npx tsc --noEmit --skipLibCheck
```

Expected: PASS.

- [x] **Step 6: Commit foreground retry**

If commit is authorized, run:

```bash
git add miniapp/src/app.ts miniapp/src/pages/home/index.tsx miniapp/src/pages/prescription/index.tsx miniapp/src/pages/game-session/retryUpload.ts
git commit -m "feat(miniapp): 恢复小程序前台后补传游戏记录"
```

---

### Task 6: Backend Game Result Validation

**Files:**
- Modify: `backend/apps/training/game_results.py`
- Modify: `backend/apps/training/tests/test_training_current_prescription.py`

- [x] **Step 1: Write failing backend validation tests**

Append to `backend/apps/training/tests/test_training_current_prescription.py`:

```python
@pytest.mark.django_db
def test_training_create_accepts_real_game_raw_detail(active_prescription):
    game = ActionLibraryItem.objects.get(source_key="game-memory-color-sequence")
    game_action = active_prescription.add_action_snapshot(game)

    record = create_training_record(
        project_patient=active_prescription.project_patient,
        training_date="2026-05-16",
        prescription_action=game_action,
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=10,
        score=90,
        form_data={
            "accuracy_rate": 90,
            "error_count": 1,
            "difficulty": "中等",
            "raw_detail": {
                "game_code": "game-memory-color-sequence",
                "ended_by": "timer",
                "ended_early": False,
                "prescribed_difficulty": "简单",
                "difficulty_adjusted": True,
                "difficulty_adjust_reason": "太简单，想提高难度",
                "upload_mode": "retry",
                "retry_count": 2,
                "total_retry_count": 12,
                "session_duration_seconds": 600,
                "suggested_duration_minutes": 10,
                "completed_units": 10,
                "correct_units": 9,
            },
        },
    )

    assert record.form_data["raw_detail"]["total_retry_count"] == 12


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("raw_detail", "message"),
    [
        ({"ended_by": "unknown"}, "游戏结束方式必须是 timer 或 manual"),
        ({"ended_early": "false"}, "游戏提前结束标记必须是布尔值"),
        ({"retry_count": -1}, "游戏补传次数必须是非负整数"),
        ({"total_retry_count": True}, "游戏累计补传次数必须是非负整数"),
        ({"upload_mode": "later"}, "游戏上传方式必须是 direct 或 retry"),
        ({"game_code": "wrong-game"}, "游戏编码必须匹配处方动作"),
    ],
)
def test_training_create_rejects_invalid_real_game_raw_detail(
    active_prescription, raw_detail, message
):
    game = ActionLibraryItem.objects.get(source_key="game-memory-color-sequence")
    game_action = active_prescription.add_action_snapshot(game)

    with pytest.raises(ValidationError, match=message):
        create_training_record(
            project_patient=active_prescription.project_patient,
            training_date="2026-05-16",
            prescription_action=game_action,
            status=TrainingRecord.Status.COMPLETED,
            form_data={
                "accuracy_rate": 90,
                "error_count": 1,
                "difficulty": "中等",
                "raw_detail": raw_detail,
            },
        )
```

- [x] **Step 2: Run backend tests and verify failure**

Run:

```bash
cd backend && pytest apps/training/tests/test_training_current_prescription.py -q
```

Expected: FAIL on the newly added invalid `raw_detail` cases because current validation only checks object shape.

- [x] **Step 3: Implement raw_detail validation**

Modify `backend/apps/training/game_results.py`:

```python
from django.core.exceptions import ValidationError

from apps.prescriptions.models import ActionLibraryItem, PrescriptionAction


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_non_negative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_raw_detail(prescription_action: PrescriptionAction, raw_detail: dict) -> None:
    game_code = raw_detail.get("game_code")
    if game_code not in (None, ""):
        source_key = prescription_action.action_library_item.source_key
        if source_key and game_code != source_key:
            raise ValidationError("游戏编码必须匹配处方动作")

    ended_by = raw_detail.get("ended_by")
    if ended_by not in (None, "", "timer", "manual"):
        raise ValidationError("游戏结束方式必须是 timer 或 manual")

    ended_early = raw_detail.get("ended_early")
    if ended_early is not None and not isinstance(ended_early, bool):
        raise ValidationError("游戏提前结束标记必须是布尔值")

    upload_mode = raw_detail.get("upload_mode")
    if upload_mode not in (None, "", "direct", "retry"):
        raise ValidationError("游戏上传方式必须是 direct 或 retry")

    for key in ("retry_count", "total_retry_count"):
        value = raw_detail.get(key)
        if value not in (None, "") and not _is_non_negative_int(value):
            raise ValidationError("游戏补传次数必须是非负整数" if key == "retry_count" else "游戏累计补传次数必须是非负整数")

    for key in ("session_duration_seconds", "suggested_duration_minutes", "completed_units", "correct_units"):
        value = raw_detail.get(key)
        if value not in (None, "") and not _is_non_negative_int(value):
            raise ValidationError("游戏会话数值必须是非负整数")


def validate_game_result_fields(
    prescription_action: PrescriptionAction,
    *,
    form_data,
) -> None:
    if prescription_action.internal_type_snapshot != ActionLibraryItem.InternalType.GAME:
        return
    if form_data in (None, ""):
        return
    if not isinstance(form_data, dict):
        raise ValidationError("游戏结果明细必须是对象")

    accuracy_rate = form_data.get("accuracy_rate")
    if accuracy_rate not in (None, ""):
        if not _is_number(accuracy_rate) or accuracy_rate < 0 or accuracy_rate > 100:
            raise ValidationError("正确率必须在 0 到 100 之间")

    error_count = form_data.get("error_count")
    if error_count not in (None, ""):
        if not _is_non_negative_int(error_count):
            raise ValidationError("错误次数必须是非负整数")

    difficulty = form_data.get("difficulty")
    if difficulty is not None and not isinstance(difficulty, str):
        raise ValidationError("游戏难度必须是文本")

    raw_detail = form_data.get("raw_detail")
    if raw_detail not in (None, ""):
        if not isinstance(raw_detail, dict):
            raise ValidationError("游戏原始明细必须是对象")
        _validate_raw_detail(prescription_action, raw_detail)
```

- [x] **Step 4: Run backend validation tests**

Run:

```bash
cd backend && pytest apps/training/tests/test_training_current_prescription.py -q
```

Expected: PASS.

- [x] **Step 5: Commit backend validation**

If commit is authorized, run:

```bash
git add backend/apps/training/game_results.py backend/apps/training/tests/test_training_current_prescription.py
git commit -m "fix(training): 校验真实游戏结果明细"
```

---

### Task 7: Doctor Tracking Fields for Real Game Sessions

**Files:**
- Modify: `backend/apps/training/tracking.py`
- Modify: `backend/apps/training/tests/test_tracking_api.py`
- Modify: `frontend/src/pages/training-tracking/types.ts`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`

- [x] **Step 1: Add backend tracking test expectations**

In `backend/apps/training/tests/test_tracking_api.py`, update the existing recent record fixture that creates a game record so its `form_data` contains:

```python
form_data={
    "accuracy_rate": 95,
    "error_count": 1,
    "difficulty": "中等",
    "raw_detail": {
        "ended_early": True,
        "difficulty_adjust_reason": "今天状态不佳",
        "upload_mode": "retry",
        "retry_count": 2,
        "total_retry_count": 12,
    },
},
```

In the response assertions for `recent_records`, add:

```python
assert completed_game["game_ended_early"] is True
assert completed_game["game_difficulty_adjust_reason"] == "今天状态不佳"
assert completed_game["game_upload_mode"] == "retry"
assert completed_game["game_retry_count"] == 2
assert completed_game["game_total_retry_count"] == 12
```

- [x] **Step 2: Run backend tracking test and verify failure**

Run:

```bash
cd backend && pytest apps/training/tests/test_tracking_api.py -q
```

Expected: FAIL because the tracking response does not yet include the new fields.

- [x] **Step 3: Add backend raw_detail extractors**

Modify `backend/apps/training/tracking.py` and add helpers near `_form_difficulty`:

```python
def _form_raw_detail(form_data):
    value = form_data.get("raw_detail") if isinstance(form_data, dict) else None
    return value if isinstance(value, dict) else {}


def _raw_bool(form_data, key):
    value = _form_raw_detail(form_data).get(key)
    return value if isinstance(value, bool) else None


def _raw_text(form_data, key):
    value = _form_raw_detail(form_data).get(key)
    return value if isinstance(value, str) else None


def _raw_int(form_data, key):
    value = _form_raw_detail(form_data).get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None
```

Then update `recent_records()` row serialization with:

```python
"game_ended_early": _raw_bool(record.form_data, "ended_early"),
"game_difficulty_adjust_reason": _raw_text(record.form_data, "difficulty_adjust_reason"),
"game_upload_mode": _raw_text(record.form_data, "upload_mode"),
"game_retry_count": _raw_int(record.form_data, "retry_count"),
"game_total_retry_count": _raw_int(record.form_data, "total_retry_count"),
```

- [x] **Step 4: Run backend tracking tests**

Run:

```bash
cd backend && pytest apps/training/tests/test_tracking_api.py -q
```

Expected: PASS.

- [x] **Step 5: Update frontend types**

Modify `frontend/src/pages/training-tracking/types.ts` `TrackingRecentRecord`:

```ts
export type TrackingRecentRecord = {
  id: number;
  training_date: string;
  status: string;
  prescription: number;
  prescription_version: number;
  prescription_action: number;
  action_name: string;
  internal_type: string;
  action_type: string;
  actual_duration_minutes: number | null;
  score: number | null;
  game_accuracy_rate: number | null;
  game_error_count: number | null;
  game_difficulty: string | null;
  game_ended_early: boolean | null;
  game_difficulty_adjust_reason: string | null;
  game_upload_mode: string | null;
  game_retry_count: number | null;
  game_total_retry_count: number | null;
  note: string;
};
```

- [x] **Step 6: Update frontend detail test fixture and assertions**

In `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`, update `trackingDetail.recent_records[0]`:

```ts
game_ended_early: true,
game_difficulty_adjust_reason: "今天状态不佳",
game_upload_mode: "retry",
game_retry_count: 2,
game_total_retry_count: 12,
```

In the first test, add assertions:

```ts
expect(screen.getByText("提前结束")).toBeInTheDocument();
expect(screen.getByText("补传")).toBeInTheDocument();
expect(screen.getByText("12 次")).toBeInTheDocument();
expect(screen.getByText("今天状态不佳")).toBeInTheDocument();
```

- [x] **Step 7: Update frontend columns**

Modify `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx` near labels:

```ts
const UPLOAD_MODE_LABEL: Record<string, string> = {
  direct: "实时上传",
  retry: "补传",
};
```

Add columns in 最近训练记录 after 难度:

```tsx
{
  title: "结束方式",
  dataIndex: "game_ended_early",
  render: (value: boolean | null, record) =>
    record.internal_type === "game" ? (value ? <Tag color="orange">提前结束</Tag> : <Tag color="green">到时完成</Tag>) : "—",
},
{
  title: "上传方式",
  dataIndex: "game_upload_mode",
  render: (value: string | null) => (value ? UPLOAD_MODE_LABEL[value] ?? value : "—"),
},
{
  title: "补传次数",
  dataIndex: "game_total_retry_count",
  render: (value: number | null) => (value == null ? "—" : `${value} 次`),
},
{
  title: "调难原因",
  dataIndex: "game_difficulty_adjust_reason",
  render: (value: string | null) => value || "—",
},
```

- [x] **Step 8: Run frontend detail test**

Run:

```bash
cd frontend && npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
```

Expected: PASS.

- [x] **Step 9: Commit tracking fields**

If commit is authorized, run:

```bash
git add backend/apps/training/tracking.py backend/apps/training/tests/test_tracking_api.py frontend/src/pages/training-tracking/types.ts frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
git commit -m "feat(training): 展示真实游戏训练摘要"
```

---

### Task 8: Full Verification and Plan Status

**Files:**
- Modify: `docs/superpowers/plans/2026-05-16-wechat-miniapp-real-games.md`

- [x] **Step 1: Run targeted backend tests**

Run:

```bash
cd backend && pytest apps/training/tests/test_training_current_prescription.py apps/training/tests/test_tracking_api.py -q
```

Expected: PASS.

- [x] **Step 2: Run targeted frontend tests**

Run:

```bash
cd frontend && npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
```

Expected: PASS.

- [x] **Step 3: Run miniapp tests and type check**

Run:

```bash
cd miniapp && npm run test
cd miniapp && npx tsc --noEmit --skipLibCheck
cd miniapp && npm run build:weapp
```

Expected: PASS.

- [x] **Step 4: Run broader regression checks**

Run:

```bash
cd backend && pytest
cd frontend && npm run test
cd frontend && npm run lint
cd frontend && npm run build
```

Expected: PASS.

- [x] **Step 5: Update execution record in this plan**

At the top of `docs/superpowers/plans/2026-05-16-wechat-miniapp-real-games.md`, add:

```text
执行记录（YYYY-MM-DD, codex）：微信小程序真实游戏一期已落地，验证通过。实施 commit：<实际 short SHA 列表>
```

Replace `YYYY-MM-DD` and `<实际 short SHA 列表>` with the real values from execution.

- [x] **Step 6: Commit plan status**

If commit is authorized, run:

```bash
git add docs/superpowers/plans/2026-05-16-wechat-miniapp-real-games.md
git commit -m "docs(plan): 标记小程序真实游戏一期实施完成"
```

## Self-Review

- Spec coverage: 两款游戏、Game Session 壳、处方时长、提前结束、调难原因、语音音效、自动上传、10 次退避补传、下次打开重启、后端校验、医生端展示和验证命令均有对应任务。
- Scope check: 本计划只实现两款真实小游戏和训练记录链路收口；其余 4 个游戏、独立 `GameSession` 模型、每轮明细和游戏版本管理保持非目标。
- Type consistency: `GameDifficulty`、`GameCode`、`GameEndReason`、`GameUploadMode`、`GameTrainingPayload` 在小程序核心、补传和页面任务中一致；后端与医生端字段统一使用 `game_ended_early`、`game_upload_mode`、`game_retry_count`、`game_total_retry_count`、`game_difficulty_adjust_reason`。
