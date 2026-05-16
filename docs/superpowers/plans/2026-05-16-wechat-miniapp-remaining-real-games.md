# 微信小程序剩余真实游戏 Implementation Plan

> 状态：implemented
> 日期：2026-05-16
> 范围：补齐微信小程序剩余 4 个官方真实认知游戏并接入训练记录上传
> 关联：`docs/superpowers/specs/2026-05-16-wechat-miniapp-remaining-real-games-design.md`
> 实施基线 commit：`f26bb97`

执行记录（2026-05-16, Codex）：Tasks 1-9 已落地于 commits `28e890d`, `2b29188`, `a29727d`, `a564b48`, `be3e237`, `33f18ee`, `f5637e7`, `2f36d42`, `599c305`, `3f32575`, `8f7ecb8`, `a24b533`, `4044266`, `d8099dc`, `2decf1d`, `a903f07`, `cc720aa`, `ee59414`, `a8182ff`, `f421c5b`, `88c28f9`, `aed427f`。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐微信小程序剩余 4 个官方真实认知游戏，使 6 个官方游戏都能从当前处方进入真实玩法并上传训练记录。

**Architecture:** 沿用现有 `game-session` 页面壳和 `TrainingRecord.form_data.raw_detail` 数据约定。新增 4 个纯玩法模块负责出题和判定，页面壳只扩展 source_key 映射、回合状态和渲染分支；声音辨别使用 `docs/other/sounds` 的真实音频，图片/声音资源通过 Taro copy 打包到小程序静态目录。

**Tech Stack:** Taro 4 + React 18 + TypeScript + Vitest；Django 5 + DRF + pytest-django；现有微信小程序 build:weapp。

---

## Execution Notes

- 对应 spec：`docs/superpowers/specs/2026-05-16-wechat-miniapp-remaining-real-games-design.md`。
- 用户明确要求：不创建新 worktree，继续在当前工作区/当前分支执行，因为需要跑微信编译。
- 用户已允许本阶段按任务 commit；所有 commit message 使用中文。
- 继续遵守 TDD：每个核心玩法模块先写失败测试，再实现。
- 不新增后端模型、migration 或 API。
- `.superpowers/brainstorm/` 是本地 brainstorm 产物，不纳入提交。

## File Structure

### Miniapp Assets and Config

- Modify: `miniapp/config/index.ts`
  - 增加 `src/assets/audio/sound-discrimination` 和 `src/assets/images/game-session` copy pattern。
- Modify: `miniapp/scripts/generate-game-audio.mjs`
  - 增加 4 个新游戏 intro 语音片段并重新生成 `pattern_intro.m4a`、`category_intro.m4a`、`sound_intro.m4a`、`puzzle_intro.m4a`。
- Create: `miniapp/scripts/generate-game-images.mjs`
  - 生成图案顺序、分类转换、拼图使用的静态 SVG 图片资源。
- Create generated assets under: `miniapp/src/assets/images/game-session/*.svg`
  - 使用 ASCII 文件名，微信端加载失败时页面有文字 fallback。
- Create copied assets under: `miniapp/src/assets/audio/sound-discrimination/*.m4a`
  - 从 `docs/other/sounds/*.m4a` 复制并重命名为 ASCII 文件名。

### Miniapp Game Modules

- Modify: `miniapp/src/pages/game-session/gameTypes.ts`
  - `GameCode` 扩展为 6 个官方 source_key。
- Create: `miniapp/src/pages/game-session/gameCatalog.ts`
  - 集中维护 6 个游戏的 metadata、intro key、资源路径和 label。
- Modify: `miniapp/src/pages/game-session/gameAudio.ts`
  - 增加 4 个 intro key。
  - 增加声音辨别音频 manifest。
  - 增加 `playAudioSrc(src: string)`，用于播放声音辨别卡片/目标音。
- Modify: `miniapp/src/pages/game-session/gameAudio.test.ts`
  - 覆盖新 intro key 和 sound manifest。
- Create: `miniapp/src/pages/game-session/patternSequence.ts`
- Create: `miniapp/src/pages/game-session/patternSequence.test.ts`
- Create: `miniapp/src/pages/game-session/categorySwitch.ts`
- Create: `miniapp/src/pages/game-session/categorySwitch.test.ts`
- Create: `miniapp/src/pages/game-session/soundDiscrimination.ts`
- Create: `miniapp/src/pages/game-session/soundDiscrimination.test.ts`
- Create: `miniapp/src/pages/game-session/puzzle.ts`
- Create: `miniapp/src/pages/game-session/puzzle.test.ts`

### Miniapp Page Integration

- Modify: `miniapp/src/pages/game-session/index.tsx`
  - 扩展游戏映射和渲染分支。
  - 复用现有 intro、计时、暂停、结束、上传逻辑。
  - 新增 4 个游戏的回合状态和交互 handler。
- Modify: `miniapp/src/types/patientApp.ts`
  - 当前处方动作增加 `source_key` 字段，供小程序精确匹配官方游戏。
- Modify: `miniapp/src/app.scss`
  - 增加图案格、分类按钮、声音翻卡、拼图网格样式。

### Backend Tests

- Modify: `backend/apps/patient_app/views.py`
  - 当前处方动作返回 `source_key`。
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py`
  - 覆盖患者端当前处方返回动作 source_key。
- Modify: `backend/apps/training/tests/test_training_current_prescription.py`
  - 参数化覆盖 4 个新增游戏编码可提交。

---

### Task 1: Static Assets, Catalog, and Audio Manifest

**Files:**
- Modify: `miniapp/config/index.ts`
- Modify: `miniapp/scripts/generate-game-audio.mjs`
- Create: `miniapp/scripts/generate-game-images.mjs`
- Create generated assets: `miniapp/src/assets/images/game-session/*.svg`
- Create generated intro audio: `miniapp/src/assets/audio/game-session/pattern_intro.m4a`, `category_intro.m4a`, `sound_intro.m4a`, `puzzle_intro.m4a`
- Create copied assets: `miniapp/src/assets/audio/sound-discrimination/*.m4a`
- Modify: `miniapp/src/pages/game-session/gameTypes.ts`
- Create: `miniapp/src/pages/game-session/gameCatalog.ts`
- Modify: `miniapp/src/pages/game-session/gameAudio.ts`
- Modify: `miniapp/src/pages/game-session/gameAudio.test.ts`

- [x] **Step 1: Add failing audio/catalog tests**

Modify `miniapp/src/pages/game-session/gameAudio.test.ts` to add tests:

```ts
import { GAME_AUDIO_SRC, GAME_AUDIO_TEXT, SOUND_DISCRIMINATION_AUDIO, playAudioSrc } from './gameAudio'

describe('remaining game audio manifest', () => {
  it('contains intro text and audio src for all remaining games', () => {
    expect(GAME_AUDIO_TEXT.pattern_intro).toContain('图案')
    expect(GAME_AUDIO_TEXT.category_intro).toContain('分类')
    expect(GAME_AUDIO_TEXT.sound_intro).toContain('声音')
    expect(GAME_AUDIO_TEXT.puzzle_intro).toContain('拼图')
    expect(GAME_AUDIO_SRC.pattern_intro).toBe('/assets/audio/game-session/pattern_intro.m4a')
    expect(GAME_AUDIO_SRC.category_intro).toBe('/assets/audio/game-session/category_intro.m4a')
    expect(GAME_AUDIO_SRC.sound_intro).toBe('/assets/audio/game-session/sound_intro.m4a')
    expect(GAME_AUDIO_SRC.puzzle_intro).toBe('/assets/audio/game-session/puzzle_intro.m4a')
  })

  it('maps each sound discrimination source to an ascii static path and category image key', () => {
    expect(SOUND_DISCRIMINATION_AUDIO).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: 'bird_1', label: '小鸟1', category: 'bird', src: '/assets/audio/sound-discrimination/bird_1.m4a' }),
        expect.objectContaining({ id: 'phone_2', label: '电话铃声2', category: 'phone', src: '/assets/audio/sound-discrimination/phone_2.m4a' }),
        expect.objectContaining({ id: 'drum_3', label: '鼓3', category: 'drum', src: '/assets/audio/sound-discrimination/drum_3.m4a' }),
      ])
    )
    expect(new Set(SOUND_DISCRIMINATION_AUDIO.map((item) => item.id)).size).toBe(SOUND_DISCRIMINATION_AUDIO.length)
  })

  it('plays arbitrary static audio src and reports success', async () => {
    const playback = playAudioSrc('/assets/audio/sound-discrimination/bird_1.m4a')
    audioCallbacks.ended?.()
    await expect(playback).resolves.toBe(true)
  })
})
```

If the existing test mock does not expose `audioCallbacks`, extend the current mock with the same callback object already used for `playGameAudio('start')`.

- [x] **Step 2: Run audio tests and verify failure**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/gameAudio.test.ts
```

Expected: FAIL because `pattern_intro`, `SOUND_DISCRIMINATION_AUDIO`, and `playAudioSrc` do not exist.

- [x] **Step 3: Extend `GameCode`**

Modify `miniapp/src/pages/game-session/gameTypes.ts`:

```ts
export type GameCode =
  | 'game-memory-color-sequence'
  | 'game-memory-pattern-sequence'
  | 'game-executive-inhibition'
  | 'game-executive-category-switch'
  | 'game-audiovisual-sound-discrimination'
  | 'game-audiovisual-puzzle'
```

- [x] **Step 4: Add game catalog**

Create `miniapp/src/pages/game-session/gameCatalog.ts`:

```ts
import type { GameCode } from './gameTypes'
import type { GameAudioKey } from './gameAudio'

export type GameKind = 'color' | 'pattern' | 'inhibition' | 'category' | 'sound' | 'puzzle'

export type GameCatalogItem = {
  code: GameCode
  kind: GameKind
  name: string
  introAudioKey: GameAudioKey
}

export const GAME_CATALOG: Record<GameCode, GameCatalogItem> = {
  'game-memory-color-sequence': {
    code: 'game-memory-color-sequence',
    kind: 'color',
    name: '颜色顺序记忆',
    introAudioKey: 'color_intro',
  },
  'game-memory-pattern-sequence': {
    code: 'game-memory-pattern-sequence',
    kind: 'pattern',
    name: '图案顺序记忆',
    introAudioKey: 'pattern_intro',
  },
  'game-executive-inhibition': {
    code: 'game-executive-inhibition',
    kind: 'inhibition',
    name: '反应抑制能力训练',
    introAudioKey: 'inhibition_intro',
  },
  'game-executive-category-switch': {
    code: 'game-executive-category-switch',
    kind: 'category',
    name: '分类转换任务',
    introAudioKey: 'category_intro',
  },
  'game-audiovisual-sound-discrimination': {
    code: 'game-audiovisual-sound-discrimination',
    kind: 'sound',
    name: '声音辨别',
    introAudioKey: 'sound_intro',
  },
  'game-audiovisual-puzzle': {
    code: 'game-audiovisual-puzzle',
    kind: 'puzzle',
    name: '拼图',
    introAudioKey: 'puzzle_intro',
  },
}

export const GAME_CODE_BY_SOURCE: Record<string, GameCode> = Object.keys(GAME_CATALOG).reduce(
  (result, code) => ({ ...result, [code]: code as GameCode }),
  {} as Record<string, GameCode>
)

export function gameCodeForActionSource(sourceKey: string | null | undefined): GameCode | null {
  return sourceKey && sourceKey in GAME_CODE_BY_SOURCE ? GAME_CODE_BY_SOURCE[sourceKey] : null
}
```

- [x] **Step 5: Extend audio manifest and generic audio playback**

Modify `miniapp/src/pages/game-session/gameAudio.ts`:

```ts
export type GameAudioKey =
  | 'color_intro'
  | 'pattern_intro'
  | 'inhibition_intro'
  | 'category_intro'
  | 'sound_intro'
  | 'puzzle_intro'
  | 'count_3'
  | 'count_2'
  | 'count_1'
  | 'start'
  | 'correct'
  | 'wrong'
  | 'complete'
  | 'manual_end'
  | 'tap'

export type SoundDiscriminationAudio = {
  id: string
  label: string
  category: 'bird' | 'train' | 'phone' | 'laugh' | 'drum'
  imageKey: 'bird' | 'train' | 'phone' | 'laugh' | 'drum'
  src: string
}

export const SOUND_DISCRIMINATION_AUDIO: SoundDiscriminationAudio[] = [
  { id: 'bird_1', label: '小鸟1', category: 'bird', imageKey: 'bird', src: '/assets/audio/sound-discrimination/bird_1.m4a' },
  { id: 'bird_2', label: '小鸟2', category: 'bird', imageKey: 'bird', src: '/assets/audio/sound-discrimination/bird_2.m4a' },
  { id: 'bird_3', label: '小鸟3', category: 'bird', imageKey: 'bird', src: '/assets/audio/sound-discrimination/bird_3.m4a' },
  { id: 'train_1', label: '火车汽笛声1', category: 'train', imageKey: 'train', src: '/assets/audio/sound-discrimination/train_1.m4a' },
  { id: 'train_2', label: '火车汽笛声2', category: 'train', imageKey: 'train', src: '/assets/audio/sound-discrimination/train_2.m4a' },
  { id: 'phone_1', label: '电话铃声1', category: 'phone', imageKey: 'phone', src: '/assets/audio/sound-discrimination/phone_1.m4a' },
  { id: 'phone_2', label: '电话铃声2', category: 'phone', imageKey: 'phone', src: '/assets/audio/sound-discrimination/phone_2.m4a' },
  { id: 'phone_3', label: '电话铃声3', category: 'phone', imageKey: 'phone', src: '/assets/audio/sound-discrimination/phone_3.m4a' },
  { id: 'laugh_1', label: '笑声1', category: 'laugh', imageKey: 'laugh', src: '/assets/audio/sound-discrimination/laugh_1.m4a' },
  { id: 'laugh_2', label: '笑声2', category: 'laugh', imageKey: 'laugh', src: '/assets/audio/sound-discrimination/laugh_2.m4a' },
  { id: 'laugh_3', label: '笑声3', category: 'laugh', imageKey: 'laugh', src: '/assets/audio/sound-discrimination/laugh_3.m4a' },
  { id: 'drum_1', label: '鼓1', category: 'drum', imageKey: 'drum', src: '/assets/audio/sound-discrimination/drum_1.m4a' },
  { id: 'drum_2', label: '鼓2', category: 'drum', imageKey: 'drum', src: '/assets/audio/sound-discrimination/drum_2.m4a' },
  { id: 'drum_3', label: '鼓3', category: 'drum', imageKey: 'drum', src: '/assets/audio/sound-discrimination/drum_3.m4a' },
]

function playStaticAudio(src: string): Promise<void> {
  if (isGameAudioMuted()) return Promise.resolve()
  return new Promise((resolve, reject) => {
    let audio: GameAudioContext | undefined
    let timeout: ReturnType<typeof setTimeout> | undefined
    let settled = false
    const finish = (failed = false) => {
      if (settled) return
      settled = true
      if (timeout !== undefined) clearTimeout(timeout)
      try {
        audio?.destroy()
      } catch {
        // Audio context cleanup failure should not crash a game session.
      }
      if (failed) reject(new Error('音频播放失败'))
      else resolve()
    }
    try {
      audio = Taro.createInnerAudioContext() as GameAudioContext
      audio.src = src
      audio.onEnded(() => finish(false))
      audio.onError(() => finish(true))
      if (typeof audio.onStop === 'function') audio.onStop(() => finish(false))
      if (typeof audio.onPause === 'function') audio.onPause(() => finish(false))
      timeout = setTimeout(() => finish(true), AUDIO_PLAYBACK_TIMEOUT_MS)
      audio.play()
    } catch {
      finish(true)
    }
  })
}

export function playAudioSrc(src: string): Promise<boolean> {
  return playStaticAudio(src)
    .then(() => true)
    .catch(() => false)
}
```

Keep `playGameAudio(key)` behavior non-blocking by delegating to `playStaticAudio(GAME_AUDIO_SRC[key]).catch(() => undefined)`.

- [x] **Step 6: Add remaining intro audio clips**

Modify `miniapp/scripts/generate-game-audio.mjs` and add the 4 new intro clips immediately after `color_intro`:

```js
  ['pattern_intro', '图案顺序记忆训练开始。请记住图片出现的顺序，随后按相同顺序点击。'],
  ['category_intro', '分类转换训练开始。请看清当前规则，再选择图片对应的分类。'],
  ['sound_intro', '声音辨别训练开始。请逐张翻开卡片试听声音，盖回后根据目标声音选择卡片。'],
  ['puzzle_intro', '拼图训练开始。请先记住完整图片，然后点击两块拼图交换位置，恢复正确顺序。'],
```

Then run:

```bash
cd miniapp && node scripts/generate-game-audio.mjs
```

Expected: `miniapp/src/assets/audio/game-session/` contains the existing audio files plus `pattern_intro.m4a`, `category_intro.m4a`, `sound_intro.m4a`, and `puzzle_intro.m4a`.

- [x] **Step 7: Add image generation script**

Create `miniapp/scripts/generate-game-images.mjs` with deterministic SVG output:

```js
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const outDir = join(process.cwd(), 'src/assets/images/game-session')
mkdirSync(outDir, { recursive: true })

const assets = [
  ['pattern_sun.svg', 'sun', '#f6c85f'],
  ['pattern_coconut.svg', 'coconut', '#5ca37a'],
  ['pattern_boat.svg', 'boat', '#4f8fc0'],
  ['pattern_lighthouse.svg', 'lighthouse', '#d96c5f'],
  ['pattern_shell.svg', 'shell', '#d59cc7'],
  ['category_pineapple.svg', 'fruit', '#f6c85f'],
  ['category_bird.svg', 'bird', '#6baed6'],
  ['category_train.svg', 'train', '#7b8794'],
  ['category_drum.svg', 'drum', '#c97a4a'],
  ['category_phone.svg', 'phone', '#4f8fc0'],
  ['sound_bird.svg', 'bird', '#6baed6'],
  ['sound_train.svg', 'train', '#7b8794'],
  ['sound_phone.svg', 'phone', '#4f8fc0'],
  ['sound_laugh.svg', 'laugh', '#f28e8e'],
  ['sound_drum.svg', 'drum', '#c97a4a'],
  ['puzzle_beach.svg', 'beach', '#6baed6'],
  ['puzzle_garden.svg', 'garden', '#5ca37a'],
  ['puzzle_lighthouse.svg', 'lighthouse', '#d96c5f'],
]

function svg(label, color) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="64" fill="#f7fbfb"/>
  <circle cx="256" cy="210" r="120" fill="${color}" opacity="0.92"/>
  <path d="M128 360 C180 320 220 390 256 350 C300 305 338 382 384 340" fill="none" stroke="#1f3f4a" stroke-width="24" stroke-linecap="round"/>
  <text x="256" y="455" text-anchor="middle" font-family="Arial, sans-serif" font-size="46" fill="#1f3f4a">${label}</text>
</svg>
`
}

for (const [filename, label, color] of assets) {
  writeFileSync(join(outDir, filename), svg(label, color))
}
```

- [x] **Step 8: Generate images and copy sound sources**

Run:

```bash
cd miniapp && node scripts/generate-game-images.mjs
mkdir -p src/assets/audio/sound-discrimination
cp ../docs/other/sounds/小鸟1.m4a src/assets/audio/sound-discrimination/bird_1.m4a
cp ../docs/other/sounds/小鸟2.m4a src/assets/audio/sound-discrimination/bird_2.m4a
cp ../docs/other/sounds/小鸟3.m4a src/assets/audio/sound-discrimination/bird_3.m4a
cp ../docs/other/sounds/火车汽笛声1.m4a src/assets/audio/sound-discrimination/train_1.m4a
cp ../docs/other/sounds/火车汽笛声2.m4a src/assets/audio/sound-discrimination/train_2.m4a
cp ../docs/other/sounds/电话铃声1.m4a src/assets/audio/sound-discrimination/phone_1.m4a
cp ../docs/other/sounds/电话铃声2.m4a src/assets/audio/sound-discrimination/phone_2.m4a
cp ../docs/other/sounds/电话铃声3.m4a src/assets/audio/sound-discrimination/phone_3.m4a
cp ../docs/other/sounds/笑声1.m4a src/assets/audio/sound-discrimination/laugh_1.m4a
cp ../docs/other/sounds/笑声2.m4a src/assets/audio/sound-discrimination/laugh_2.m4a
cp ../docs/other/sounds/笑声3.m4a src/assets/audio/sound-discrimination/laugh_3.m4a
cp ../docs/other/sounds/鼓1.m4a src/assets/audio/sound-discrimination/drum_1.m4a
cp ../docs/other/sounds/鼓2.m4a src/assets/audio/sound-discrimination/drum_2.m4a
cp ../docs/other/sounds/鼓3.m4a src/assets/audio/sound-discrimination/drum_3.m4a
```

Expected: `miniapp/src/assets/images/game-session/` contains SVGs and `miniapp/src/assets/audio/sound-discrimination/` contains 14 m4a files.

- [x] **Step 9: Update Taro copy config**

Modify `miniapp/config/index.ts` copy patterns:

```ts
copy: {
  patterns: [
    {
      from: 'src/assets/audio/game-session',
      to: 'dist/assets/audio/game-session'
    },
    {
      from: 'src/assets/audio/sound-discrimination',
      to: 'dist/assets/audio/sound-discrimination'
    },
    {
      from: 'src/assets/images/game-session',
      to: 'dist/assets/images/game-session'
    }
  ],
  options: {
  }
},
```

- [x] **Step 10: Run audio tests and build asset copy**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/gameAudio.test.ts
cd miniapp && npm run build:weapp
```

Expected: tests PASS and Webpack compiled successfully. Confirm `dist/assets/audio/game-session/pattern_intro.m4a`, `dist/assets/audio/sound-discrimination/bird_1.m4a`, and `dist/assets/images/game-session/pattern_sun.svg` exist.

- [x] **Step 11: Commit assets and catalog**

```bash
git add miniapp/config/index.ts miniapp/scripts/generate-game-audio.mjs miniapp/scripts/generate-game-images.mjs miniapp/src/assets/images/game-session miniapp/src/assets/audio/game-session miniapp/src/assets/audio/sound-discrimination miniapp/src/pages/game-session/gameTypes.ts miniapp/src/pages/game-session/gameCatalog.ts miniapp/src/pages/game-session/gameAudio.ts miniapp/src/pages/game-session/gameAudio.test.ts
git commit -m "feat(miniapp): 新增剩余游戏资源与目录"
```

---

### Task 2: Pattern Sequence Game Core

**Files:**
- Create: `miniapp/src/pages/game-session/patternSequence.test.ts`
- Create: `miniapp/src/pages/game-session/patternSequence.ts`

- [x] **Step 1: Write failing pattern sequence tests**

Create `miniapp/src/pages/game-session/patternSequence.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { createPatternSequenceRound, evaluatePatternSequenceAttempt } from './patternSequence'

describe('createPatternSequenceRound', () => {
  it('creates a simple 3-step pattern sequence from 3 patterns', () => {
    const round = createPatternSequenceRound('简单', () => 0)

    expect(round.patterns.map((item) => item.id)).toEqual(['sun', 'coconut', 'boat'])
    expect(round.sequence.map((item) => item.id)).toEqual(['sun', 'sun', 'sun'])
    expect(round.revealMs).toBe(900)
    expect(round.inputTimeoutMs).toBe(8000)
  })

  it('creates a difficult sequence with more patterns and shorter timing', () => {
    const round = createPatternSequenceRound('困难', () => 0.99)

    expect(round.patterns).toHaveLength(5)
    expect(round.sequence).toHaveLength(7)
    expect(round.revealMs).toBe(560)
    expect(round.inputTimeoutMs).toBe(5000)
  })
})

describe('evaluatePatternSequenceAttempt', () => {
  it('marks exact sequence as correct', () => {
    expect(evaluatePatternSequenceAttempt(['sun', 'boat'], ['sun', 'boat'])).toEqual({
      correct: true,
      expected: ['sun', 'boat'],
      actual: ['sun', 'boat'],
    })
  })

  it('marks wrong order as incorrect', () => {
    expect(evaluatePatternSequenceAttempt(['sun', 'boat'], ['boat', 'sun']).correct).toBe(false)
  })
})
```

- [x] **Step 2: Run pattern tests and verify failure**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/patternSequence.test.ts
```

Expected: FAIL with module-not-found for `patternSequence`.

- [x] **Step 3: Implement pattern sequence core**

Create `miniapp/src/pages/game-session/patternSequence.ts`:

```ts
import type { GameDifficulty } from './gameTypes'

export type PatternToken = {
  id: 'sun' | 'coconut' | 'boat' | 'lighthouse' | 'shell'
  label: string
  imageSrc: string
  fallback: string
}

export type PatternSequenceRound = {
  patterns: PatternToken[]
  sequence: PatternToken[]
  revealMs: number
  inputTimeoutMs: number
}

const PATTERN_POOL: PatternToken[] = [
  { id: 'sun', label: '太阳', imageSrc: '/assets/images/game-session/pattern_sun.svg', fallback: '日' },
  { id: 'coconut', label: '椰树', imageSrc: '/assets/images/game-session/pattern_coconut.svg', fallback: '椰' },
  { id: 'boat', label: '小船', imageSrc: '/assets/images/game-session/pattern_boat.svg', fallback: '船' },
  { id: 'lighthouse', label: '灯塔', imageSrc: '/assets/images/game-session/pattern_lighthouse.svg', fallback: '塔' },
  { id: 'shell', label: '贝壳', imageSrc: '/assets/images/game-session/pattern_shell.svg', fallback: '贝' },
]

const CONFIG: Record<GameDifficulty, { patternCount: number; minLength: number; maxLength: number; revealMs: number; inputTimeoutMs: number }> = {
  简单: { patternCount: 3, minLength: 3, maxLength: 3, revealMs: 900, inputTimeoutMs: 8000 },
  中等: { patternCount: 4, minLength: 4, maxLength: 5, revealMs: 720, inputTimeoutMs: 6500 },
  困难: { patternCount: 5, minLength: 5, maxLength: 7, revealMs: 560, inputTimeoutMs: 5000 },
}

function pickIndex(length: number, random: () => number): number {
  const value = random()
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.9999999999999999) : 0
  return Math.floor(normalized * length)
}

export function createPatternSequenceRound(difficulty: GameDifficulty, random: () => number = Math.random): PatternSequenceRound {
  const config = CONFIG[difficulty]
  const patterns = PATTERN_POOL.slice(0, config.patternCount)
  const length = config.minLength + pickIndex(config.maxLength - config.minLength + 1, random)
  const sequence = Array.from({ length }, () => patterns[pickIndex(patterns.length, random)])

  return {
    patterns,
    sequence,
    revealMs: config.revealMs,
    inputTimeoutMs: config.inputTimeoutMs,
  }
}

export function evaluatePatternSequenceAttempt(expected: string[], actual: string[]) {
  const correct = expected.length === actual.length && expected.every((token, index) => token === actual[index])
  return { correct, expected, actual }
}
```

- [x] **Step 4: Run pattern tests**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/patternSequence.test.ts
```

Expected: PASS.

- [x] **Step 5: Commit pattern sequence core**

```bash
git add miniapp/src/pages/game-session/patternSequence.ts miniapp/src/pages/game-session/patternSequence.test.ts
git commit -m "feat(miniapp): 新增图案顺序记忆玩法核心"
```

---

### Task 3: Category Switch Game Core

**Files:**
- Create: `miniapp/src/pages/game-session/categorySwitch.test.ts`
- Create: `miniapp/src/pages/game-session/categorySwitch.ts`

- [x] **Step 1: Write failing category switch tests**

Create `miniapp/src/pages/game-session/categorySwitch.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { createCategorySwitchRound, evaluateCategorySwitchAttempt } from './categorySwitch'

describe('createCategorySwitchRound', () => {
  it('creates a simple round using kind rule only', () => {
    const round = createCategorySwitchRound('简单', () => 0)

    expect(round.rule).toBe('kind')
    expect(round.item.id).toBe('pineapple')
    expect(round.correctOption).toBe('水果')
    expect(round.options).toEqual(['水果', '动物', '交通'])
    expect(round.timeoutMs).toBe(7000)
  })

  it('creates a medium round that can switch to color rule', () => {
    const round = createCategorySwitchRound('中等', () => 0.75)

    expect(['kind', 'color']).toContain(round.rule)
    expect(round.options.length).toBeGreaterThanOrEqual(3)
    expect(round.timeoutMs).toBe(5500)
  })

  it('creates a difficult round that can use scene rule', () => {
    const round = createCategorySwitchRound('困难', () => 0.99)

    expect(['kind', 'color', 'scene']).toContain(round.rule)
    expect(round.options).toContain(round.correctOption)
    expect(round.timeoutMs).toBe(4200)
  })
})

describe('evaluateCategorySwitchAttempt', () => {
  it('marks selected correct option as correct', () => {
    expect(evaluateCategorySwitchAttempt({ correctOption: '水果' }, '水果')).toEqual({
      correct: true,
      correctOption: '水果',
      selectedOption: '水果',
    })
  })

  it('marks different option as incorrect', () => {
    expect(evaluateCategorySwitchAttempt({ correctOption: '水果' }, '交通').correct).toBe(false)
  })
})
```

- [x] **Step 2: Run category tests and verify failure**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/categorySwitch.test.ts
```

Expected: FAIL with module-not-found for `categorySwitch`.

- [x] **Step 3: Implement category switch core**

Create `miniapp/src/pages/game-session/categorySwitch.ts`:

```ts
import type { GameDifficulty } from './gameTypes'

export type CategoryRule = 'kind' | 'color' | 'scene'

export type CategoryItem = {
  id: string
  label: string
  imageSrc: string
  fallback: string
  kind: string
  color: string
  scene: string
}

export type CategorySwitchRound = {
  item: CategoryItem
  rule: CategoryRule
  ruleLabel: string
  options: string[]
  correctOption: string
  timeoutMs: number
}

const ITEMS: CategoryItem[] = [
  { id: 'pineapple', label: '菠萝', imageSrc: '/assets/images/game-session/category_pineapple.svg', fallback: '果', kind: '水果', color: '黄色', scene: '海岛' },
  { id: 'bird', label: '小鸟', imageSrc: '/assets/images/game-session/category_bird.svg', fallback: '鸟', kind: '动物', color: '蓝色', scene: '户外' },
  { id: 'train', label: '火车', imageSrc: '/assets/images/game-session/category_train.svg', fallback: '车', kind: '交通', color: '灰色', scene: '室外' },
  { id: 'drum', label: '鼓', imageSrc: '/assets/images/game-session/category_drum.svg', fallback: '鼓', kind: '乐器', color: '红色', scene: '室内' },
  { id: 'phone', label: '电话', imageSrc: '/assets/images/game-session/category_phone.svg', fallback: '话', kind: '工具', color: '蓝色', scene: '室内' },
]

const RULE_LABEL: Record<CategoryRule, string> = {
  kind: '按物体类别选择',
  color: '按主要颜色选择',
  scene: '按使用场景选择',
}

const OPTIONS: Record<CategoryRule, string[]> = {
  kind: ['水果', '动物', '交通', '乐器', '工具'],
  color: ['黄色', '蓝色', '灰色', '红色'],
  scene: ['海岛', '户外', '室外', '室内'],
}

const CONFIG: Record<GameDifficulty, { rules: CategoryRule[]; optionLimit: number; timeoutMs: number }> = {
  简单: { rules: ['kind'], optionLimit: 3, timeoutMs: 7000 },
  中等: { rules: ['kind', 'color'], optionLimit: 4, timeoutMs: 5500 },
  困难: { rules: ['kind', 'color', 'scene'], optionLimit: 4, timeoutMs: 4200 },
}

function pickIndex(length: number, random: () => number): number {
  const value = random()
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.9999999999999999) : 0
  return Math.floor(normalized * length)
}

function correctFor(item: CategoryItem, rule: CategoryRule): string {
  if (rule === 'kind') return item.kind
  if (rule === 'color') return item.color
  return item.scene
}

function buildOptions(rule: CategoryRule, correctOption: string, limit: number): string[] {
  const values = OPTIONS[rule]
  const result = [correctOption, ...values.filter((item) => item !== correctOption)]
  return result.slice(0, limit)
}

export function createCategorySwitchRound(difficulty: GameDifficulty, random: () => number = Math.random): CategorySwitchRound {
  const config = CONFIG[difficulty]
  const item = ITEMS[pickIndex(ITEMS.length, random)]
  const rule = config.rules[pickIndex(config.rules.length, random)]
  const correctOption = correctFor(item, rule)

  return {
    item,
    rule,
    ruleLabel: RULE_LABEL[rule],
    options: buildOptions(rule, correctOption, config.optionLimit),
    correctOption,
    timeoutMs: config.timeoutMs,
  }
}

export function evaluateCategorySwitchAttempt(round: Pick<CategorySwitchRound, 'correctOption'>, selectedOption: string) {
  return {
    correct: selectedOption === round.correctOption,
    correctOption: round.correctOption,
    selectedOption,
  }
}
```

- [x] **Step 4: Run category tests**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/categorySwitch.test.ts
```

Expected: PASS.

- [x] **Step 5: Commit category switch core**

```bash
git add miniapp/src/pages/game-session/categorySwitch.ts miniapp/src/pages/game-session/categorySwitch.test.ts
git commit -m "feat(miniapp): 新增分类转换玩法核心"
```

---

### Task 4: Sound Discrimination Game Core

**Files:**
- Create: `miniapp/src/pages/game-session/soundDiscrimination.test.ts`
- Create: `miniapp/src/pages/game-session/soundDiscrimination.ts`

- [x] **Step 1: Write failing sound discrimination tests**

Create `miniapp/src/pages/game-session/soundDiscrimination.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { SOUND_DISCRIMINATION_AUDIO } from './gameAudio'
import { createSoundDiscriminationRound, evaluateSoundDiscriminationAttempt, markCardPreviewed } from './soundDiscrimination'

describe('createSoundDiscriminationRound', () => {
  it('creates a simple round with paired confusing variants', () => {
    const round = createSoundDiscriminationRound('简单', SOUND_DISCRIMINATION_AUDIO, () => 0)

    expect(round.cards).toHaveLength(4)
    expect(round.cards.map((card) => card.soundId)).toEqual(['bird_1', 'bird_2', 'train_1', 'train_2'])
    expect(round.target.soundId).toBe('bird_1')
    expect(round.cards.filter((card) => card.category === 'bird')).toHaveLength(2)
    expect(round.cards.filter((card) => card.category === 'train')).toHaveLength(2)
    expect(round.previewComplete).toBe(false)
  })

  it('uses same image for variants in one category but different sound ids', () => {
    const round = createSoundDiscriminationRound('简单', SOUND_DISCRIMINATION_AUDIO, () => 0)
    const birds = round.cards.filter((card) => card.category === 'bird')

    expect(new Set(birds.map((card) => card.imageSrc)).size).toBe(1)
    expect(new Set(birds.map((card) => card.soundId)).size).toBe(2)
  })

  it('creates a difficult round with more cards and target from cards', () => {
    const round = createSoundDiscriminationRound('困难', SOUND_DISCRIMINATION_AUDIO, () => 0.99)

    expect(round.cards.length).toBeGreaterThanOrEqual(8)
    expect(round.cards.map((card) => card.soundId)).toContain(round.target.soundId)
    expect(round.timeoutMs).toBe(5000)
  })
})

describe('markCardPreviewed', () => {
  it('marks a card as previewed and completes preview after all cards', () => {
    let round = createSoundDiscriminationRound('简单', SOUND_DISCRIMINATION_AUDIO, () => 0)
    for (const card of round.cards) {
      round = markCardPreviewed(round, card.id)
    }

    expect(round.cards.every((card) => card.previewed)).toBe(true)
    expect(round.previewComplete).toBe(true)
  })
})

describe('evaluateSoundDiscriminationAttempt', () => {
  it('requires exact sound id match', () => {
    expect(evaluateSoundDiscriminationAttempt({ target: { soundId: 'bird_2' } }, { soundId: 'bird_2' }).correct).toBe(true)
    expect(evaluateSoundDiscriminationAttempt({ target: { soundId: 'bird_2' } }, { soundId: 'bird_1' }).correct).toBe(false)
  })
})
```

- [x] **Step 2: Run sound tests and verify failure**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/soundDiscrimination.test.ts
```

Expected: FAIL with module-not-found for `soundDiscrimination`.

- [x] **Step 3: Implement sound discrimination core**

Create `miniapp/src/pages/game-session/soundDiscrimination.ts`:

```ts
import type { SoundDiscriminationAudio } from './gameAudio'
import type { GameDifficulty } from './gameTypes'

export type SoundCard = {
  id: string
  soundId: string
  label: string
  category: SoundDiscriminationAudio['category']
  imageKey: SoundDiscriminationAudio['imageKey']
  imageSrc: string
  audioSrc: string
  previewed: boolean
}

export type SoundDiscriminationRound = {
  cards: SoundCard[]
  target: SoundCard
  previewComplete: boolean
  timeoutMs: number
}

const CATEGORY_IMAGE_SRC: Record<SoundDiscriminationAudio['imageKey'], string> = {
  bird: '/assets/images/game-session/sound_bird.svg',
  train: '/assets/images/game-session/sound_train.svg',
  phone: '/assets/images/game-session/sound_phone.svg',
  laugh: '/assets/images/game-session/sound_laugh.svg',
  drum: '/assets/images/game-session/sound_drum.svg',
}

const CONFIG: Record<GameDifficulty, { pairCount: number; timeoutMs: number }> = {
  简单: { pairCount: 2, timeoutMs: 8000 },
  中等: { pairCount: 3, timeoutMs: 6500 },
  困难: { pairCount: 4, timeoutMs: 5000 },
}

function pickIndex(length: number, random: () => number): number {
  const value = random()
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.9999999999999999) : 0
  return Math.floor(normalized * length)
}

function groupedByCategory(sources: SoundDiscriminationAudio[]): SoundDiscriminationAudio[][] {
  const groups = new Map<string, SoundDiscriminationAudio[]>()
  for (const source of sources) {
    const current = groups.get(source.category) ?? []
    current.push(source)
    groups.set(source.category, current)
  }
  return Array.from(groups.values()).filter((items) => items.length >= 2)
}

function cardFromSource(source: SoundDiscriminationAudio, index: number): SoundCard {
  return {
    id: `${source.id}_${index}`,
    soundId: source.id,
    label: source.label,
    category: source.category,
    imageKey: source.imageKey,
    imageSrc: CATEGORY_IMAGE_SRC[source.imageKey],
    audioSrc: source.src,
    previewed: false,
  }
}

export function createSoundDiscriminationRound(
  difficulty: GameDifficulty,
  sources: SoundDiscriminationAudio[],
  random: () => number = Math.random
): SoundDiscriminationRound {
  const config = CONFIG[difficulty]
  const groups = groupedByCategory(sources)
  const selectedSources = groups
    .slice(0, config.pairCount)
    .flatMap((group) => group.slice(0, 2))
  const cards = selectedSources.map(cardFromSource)
  const target = cards[pickIndex(cards.length, random)]

  return {
    cards,
    target,
    previewComplete: false,
    timeoutMs: config.timeoutMs,
  }
}

export function markCardPreviewed(round: SoundDiscriminationRound, cardId: string): SoundDiscriminationRound {
  const cards = round.cards.map((card) => (card.id === cardId ? { ...card, previewed: true } : card))
  return {
    ...round,
    cards,
    previewComplete: cards.every((card) => card.previewed),
  }
}

export function evaluateSoundDiscriminationAttempt(
  round: Pick<SoundDiscriminationRound, 'target'> | { target: Pick<SoundCard, 'soundId'> },
  selected: Pick<SoundCard, 'soundId'>
) {
  return {
    correct: selected.soundId === round.target.soundId,
    targetSoundId: round.target.soundId,
    selectedSoundId: selected.soundId,
  }
}
```

- [x] **Step 4: Run sound tests**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/soundDiscrimination.test.ts
```

Expected: PASS.

- [x] **Step 5: Commit sound discrimination core**

```bash
git add miniapp/src/pages/game-session/soundDiscrimination.ts miniapp/src/pages/game-session/soundDiscrimination.test.ts
git commit -m "feat(miniapp): 新增声音辨别玩法核心"
```

---

### Task 5: Puzzle Game Core

**Files:**
- Create: `miniapp/src/pages/game-session/puzzle.test.ts`
- Create: `miniapp/src/pages/game-session/puzzle.ts`

- [x] **Step 1: Write failing puzzle tests**

Create `miniapp/src/pages/game-session/puzzle.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { createPuzzleRound, evaluatePuzzleCompletion, swapPuzzleTiles } from './puzzle'

describe('createPuzzleRound', () => {
  it('creates a simple 2x2 puzzle', () => {
    const round = createPuzzleRound('简单', () => 0)

    expect(round.rows).toBe(2)
    expect(round.cols).toBe(2)
    expect(round.tiles).toHaveLength(4)
    expect(round.previewMs).toBe(3500)
    expect(evaluatePuzzleCompletion(round.tiles)).toBe(false)
  })

  it('creates a difficult 3x3 puzzle', () => {
    const round = createPuzzleRound('困难', () => 0.99)

    expect(round.rows).toBe(3)
    expect(round.cols).toBe(3)
    expect(round.tiles).toHaveLength(9)
    expect(round.previewMs).toBe(2200)
  })
})

describe('swapPuzzleTiles', () => {
  it('swaps two tile positions', () => {
    const round = createPuzzleRound('简单', () => 0)
    const swapped = swapPuzzleTiles(round.tiles, round.tiles[0].id, round.tiles[1].id)

    expect(swapped[0].id).toBe(round.tiles[1].id)
    expect(swapped[1].id).toBe(round.tiles[0].id)
  })

  it('detects complete tile order', () => {
    const complete = [
      { id: 'tile_0', correctIndex: 0 },
      { id: 'tile_1', correctIndex: 1 },
    ]

    expect(evaluatePuzzleCompletion(complete)).toBe(true)
  })
})
```

- [x] **Step 2: Run puzzle tests and verify failure**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/puzzle.test.ts
```

Expected: FAIL with module-not-found for `puzzle`.

- [x] **Step 3: Implement puzzle core**

Create `miniapp/src/pages/game-session/puzzle.ts`:

```ts
import type { GameDifficulty } from './gameTypes'

export type PuzzleTile = {
  id: string
  correctIndex: number
}

export type PuzzleRound = {
  imageSrc: string
  rows: number
  cols: number
  previewMs: number
  tiles: PuzzleTile[]
}

const PUZZLE_IMAGES = [
  '/assets/images/game-session/puzzle_beach.svg',
  '/assets/images/game-session/puzzle_garden.svg',
  '/assets/images/game-session/puzzle_lighthouse.svg',
]

const CONFIG: Record<GameDifficulty, { rows: number; cols: number; previewMs: number }> = {
  简单: { rows: 2, cols: 2, previewMs: 3500 },
  中等: { rows: 2, cols: 3, previewMs: 2800 },
  困难: { rows: 3, cols: 3, previewMs: 2200 },
}

function pickIndex(length: number, random: () => number): number {
  const value = random()
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.9999999999999999) : 0
  return Math.floor(normalized * length)
}

function shuffledTiles(count: number): PuzzleTile[] {
  const ordered = Array.from({ length: count }, (_value, index) => ({ id: `tile_${index}`, correctIndex: index }))
  if (count < 2) return ordered
  return [ordered[1], ordered[0], ...ordered.slice(2)]
}

export function createPuzzleRound(difficulty: GameDifficulty, random: () => number = Math.random): PuzzleRound {
  const config = CONFIG[difficulty]
  const count = config.rows * config.cols
  return {
    imageSrc: PUZZLE_IMAGES[pickIndex(PUZZLE_IMAGES.length, random)],
    rows: config.rows,
    cols: config.cols,
    previewMs: config.previewMs,
    tiles: shuffledTiles(count),
  }
}

export function swapPuzzleTiles(tiles: PuzzleTile[], firstId: string, secondId: string): PuzzleTile[] {
  const firstIndex = tiles.findIndex((tile) => tile.id === firstId)
  const secondIndex = tiles.findIndex((tile) => tile.id === secondId)
  if (firstIndex < 0 || secondIndex < 0 || firstIndex === secondIndex) return tiles
  const next = [...tiles]
  const first = next[firstIndex]
  next[firstIndex] = next[secondIndex]
  next[secondIndex] = first
  return next
}

export function evaluatePuzzleCompletion(tiles: Array<Pick<PuzzleTile, 'correctIndex'>>): boolean {
  return tiles.every((tile, index) => tile.correctIndex === index)
}
```

- [x] **Step 4: Run puzzle tests**

Run:

```bash
cd miniapp && npx vitest run src/pages/game-session/puzzle.test.ts
```

Expected: PASS.

- [x] **Step 5: Commit puzzle core**

```bash
git add miniapp/src/pages/game-session/puzzle.ts miniapp/src/pages/game-session/puzzle.test.ts
git commit -m "feat(miniapp): 新增拼图玩法核心"
```

---

### Task 6: Patient App Current Prescription Source Key

**Files:**
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py`
- Modify: `backend/apps/patient_app/views.py`
- Modify: `miniapp/src/types/patientApp.ts`

- [x] **Step 1: Add failing patient app API test**

Modify `backend/apps/patient_app/tests/test_patient_app_api.py`:

```py
@pytest.mark.django_db
def test_current_prescription_includes_action_source_key(
    project_patient,
    doctor,
    active_prescription,
):
    game_action = _game_prescription_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.get("/api/patient-app/current-prescription/")

    assert response.status_code == 200, response.data
    action = next(item for item in response.data["actions"] if item["id"] == game_action.id)
    assert action["source_key"] == "game-memory-color-sequence"
```

- [x] **Step 2: Run patient app API test and verify failure**

Run:

```bash
cd backend && pytest apps/patient_app/tests/test_patient_app_api.py::test_current_prescription_includes_action_source_key -q
```

Expected: FAIL with `KeyError: 'source_key'`.

- [x] **Step 3: Return source_key in current prescription payload**

Modify `backend/apps/patient_app/views.py` in the current prescription action serializer dict:

```py
{
    "id": action.id,
    "action_library_item": action.action_library_item_id,
    "source_key": action.action_library_item.source_key,
    "action_name": action.action_name_snapshot,
    "training_type": action.training_type_snapshot,
    "internal_type": action.internal_type_snapshot,
    "action_type": action.action_type_snapshot,
    "action_instruction": action.action_instruction_snapshot,
    "video_url": action.video_url_snapshot,
    "has_ai_supervision": action.has_ai_supervision_snapshot,
    "weekly_frequency": action.weekly_frequency,
    "duration_minutes": action.duration_minutes,
    "weekly_target_count": action.weekly_target_count,
    "weekly_completed_count": completed_counts.get(action.id, 0),
    "difficulty": action.difficulty,
    "notes": action.notes,
    "sort_order": action.sort_order,
    "recent_record": serialize_training_record(recent_records.get(action.id)),
}
```

- [x] **Step 4: Update miniapp current prescription type**

Modify `miniapp/src/types/patientApp.ts` action shape:

```ts
source_key: string | null
```

Place it after `action_library_item`.

- [x] **Step 5: Run patient app API test**

Run:

```bash
cd backend && pytest apps/patient_app/tests/test_patient_app_api.py::test_current_prescription_includes_action_source_key -q
```

Expected: PASS.

- [x] **Step 6: Commit source key contract**

```bash
git add backend/apps/patient_app/views.py backend/apps/patient_app/tests/test_patient_app_api.py miniapp/src/types/patientApp.ts
git commit -m "feat(patient-app): 当前处方返回动作编码"
```

---

### Task 7: Integrate Remaining Games Into Game Session Page

**Files:**
- Modify: `miniapp/src/pages/game-session/index.tsx`
- Modify: `miniapp/src/types/patientApp.ts`
- Modify: `miniapp/src/app.scss`

- [x] **Step 1: Import new catalog and gameplay modules**

Modify imports in `miniapp/src/pages/game-session/index.tsx`:

```ts
import { Image } from '@tarojs/components'
import { GAME_CATALOG, gameCodeForActionSource } from './gameCatalog'
import { createPatternSequenceRound, evaluatePatternSequenceAttempt, type PatternSequenceRound, type PatternToken } from './patternSequence'
import { createCategorySwitchRound, evaluateCategorySwitchAttempt, type CategorySwitchRound } from './categorySwitch'
import { SOUND_DISCRIMINATION_AUDIO, playAudioSrc } from './gameAudio'
import {
  createSoundDiscriminationRound,
  evaluateSoundDiscriminationAttempt,
  markCardPreviewed,
  type SoundCard,
  type SoundDiscriminationRound,
} from './soundDiscrimination'
import { createPuzzleRound, evaluatePuzzleCompletion, swapPuzzleTiles, type PuzzleRound, type PuzzleTile } from './puzzle'
```

Remove the local `GAME_CODE_BY_SOURCE` constant and replace `gameCodeForAction(actionName)` with:

```ts
function gameCodeForAction(actionSourceKey: string | null | undefined): GameCode | null {
  return gameCodeForActionSource(actionSourceKey)
}
```

Use the `source_key` field added in Task 6 and adjust page lookup to call `gameCodeForAction(action.source_key)`.

- [x] **Step 2: Add state for the four new games**

Add state and refs near existing color/inhibition state:

```ts
const [activePatternRound, setActivePatternRound] = useState<PatternSequenceRound | null>(null)
const [activePatternInput, setActivePatternInput] = useState<string[]>([])
const [patternRevealing, setPatternRevealing] = useState(false)
const activePatternInputRef = useRef<string[]>([])

const [activeCategoryRound, setActiveCategoryRound] = useState<CategorySwitchRound | null>(null)

const [activeSoundRound, setActiveSoundRound] = useState<SoundDiscriminationRound | null>(null)
const [soundPhase, setSoundPhase] = useState<'preview' | 'choose'>('preview')
const [soundPlaybackError, setSoundPlaybackError] = useState('')

const [activePuzzleRound, setActivePuzzleRound] = useState<PuzzleRound | null>(null)
const [selectedPuzzleTileId, setSelectedPuzzleTileId] = useState<string | null>(null)
const [puzzlePreviewing, setPuzzlePreviewing] = useState(false)
```

In `resetSessionState()`, clear all new state and refs.

- [x] **Step 3: Add round starters**

Add starters following the existing `startColorRound()` and `startInhibitionRound()` pattern:

```ts
function startPatternRound() {
  if (endStartedRef.current || phaseRef.current !== 'playing') return
  clearRoundTimers()
  pendingNextRoundRef.current = false
  const round = createPatternSequenceRound(difficultyRef.current)
  unitLockedRef.current = false
  activePatternInputRef.current = []
  setActivePatternRound(round)
  setActivePatternInput([])
  setPatternRevealing(true)
  setActiveColorRound(null)
  setActiveInhibitionRound(null)
  setActiveCategoryRound(null)
  setActiveSoundRound(null)
  setActivePuzzleRound(null)
  setFeedback('')
  startPatternRevealTimer(round)
}

function startCategoryRound() {
  if (endStartedRef.current || phaseRef.current !== 'playing') return
  clearRoundTimers()
  pendingNextRoundRef.current = false
  unitLockedRef.current = false
  setActiveCategoryRound(createCategorySwitchRound(difficultyRef.current))
  setActiveColorRound(null)
  setActivePatternRound(null)
  setActiveInhibitionRound(null)
  setActiveSoundRound(null)
  setActivePuzzleRound(null)
  setFeedback('')
  startRoundTimeout(5500)
}

function startSoundRound() {
  if (endStartedRef.current || phaseRef.current !== 'playing') return
  clearRoundTimers()
  pendingNextRoundRef.current = false
  unitLockedRef.current = false
  setActiveSoundRound(createSoundDiscriminationRound(difficultyRef.current, SOUND_DISCRIMINATION_AUDIO))
  setSoundPhase('preview')
  setSoundPlaybackError('')
  setActiveColorRound(null)
  setActivePatternRound(null)
  setActiveInhibitionRound(null)
  setActiveCategoryRound(null)
  setActivePuzzleRound(null)
  setFeedback('')
}

function startPuzzleRound() {
  if (endStartedRef.current || phaseRef.current !== 'playing') return
  clearRoundTimers()
  pendingNextRoundRef.current = false
  unitLockedRef.current = false
  const round = createPuzzleRound(difficultyRef.current)
  setActivePuzzleRound(round)
  setSelectedPuzzleTileId(null)
  setPuzzlePreviewing(true)
  setActiveColorRound(null)
  setActivePatternRound(null)
  setActiveInhibitionRound(null)
  setActiveCategoryRound(null)
  setActiveSoundRound(null)
  setFeedback('')
  startPuzzlePreviewTimer(round)
}
```

Implement `startPatternRevealTimer(round)` like `startColorRevealTimer(round)`, using `round.sequence.length * round.revealMs` and then `startRoundTimeout(round.inputTimeoutMs)`.

Implement `startPuzzlePreviewTimer(round)` with `setTimeout(() => setPuzzlePreviewing(false), round.previewMs)`.

- [x] **Step 4: Dispatch new games in playing effect and next round scheduler**

Update the `useEffect` that starts rounds:

```ts
if (gameCode === 'game-memory-pattern-sequence' && !activePatternRound) {
  startPatternRound()
}
if (gameCode === 'game-executive-category-switch' && !activeCategoryRound) {
  startCategoryRound()
}
if (gameCode === 'game-audiovisual-sound-discrimination' && !activeSoundRound) {
  startSoundRound()
}
if (gameCode === 'game-audiovisual-puzzle' && !activePuzzleRound) {
  startPuzzleRound()
}
```

Update `beginPlaying()` and `scheduleNextRound()` with the same 6-way dispatch:

```ts
if (gameCodeRef.current === 'game-memory-color-sequence') startColorRound()
else if (gameCodeRef.current === 'game-memory-pattern-sequence') startPatternRound()
else if (gameCodeRef.current === 'game-executive-inhibition') startInhibitionRound()
else if (gameCodeRef.current === 'game-executive-category-switch') startCategoryRound()
else if (gameCodeRef.current === 'game-audiovisual-sound-discrimination') startSoundRound()
else if (gameCodeRef.current === 'game-audiovisual-puzzle') startPuzzleRound()
```

- [x] **Step 5: Use catalog intro text**

Replace the two-game intro branch:

```ts
const introKey: GameAudioKey = GAME_CATALOG[gameCode].introAudioKey
```

In setup hero muted text:

```tsx
<Text className='muted'>{GAME_AUDIO_TEXT[GAME_CATALOG[gameCode].introAudioKey]}</Text>
```

- [x] **Step 6: Add interaction handlers**

Add handlers:

```ts
function selectPattern(pattern: PatternToken) {
  if (phaseRef.current !== 'playing' || patternRevealing || unitLockedRef.current || !activePatternRound) return
  void playGameAudio('tap')
  const nextInput = [...activePatternInputRef.current, pattern.id]
  activePatternInputRef.current = nextInput
  setActivePatternInput(nextInput)
  if (nextInput.length < activePatternRound.sequence.length) return
  unitLockedRef.current = true
  const attempt = evaluatePatternSequenceAttempt(activePatternRound.sequence.map((item) => item.id), nextInput)
  appendUnitResult(attempt.correct)
  setFeedback(attempt.correct ? GAME_AUDIO_TEXT.correct : GAME_AUDIO_TEXT.wrong)
  void playGameAudio(attempt.correct ? 'correct' : 'wrong')
  scheduleNextRound()
}

function selectCategory(option: string) {
  if (phaseRef.current !== 'playing' || unitLockedRef.current || !activeCategoryRound) return
  unitLockedRef.current = true
  void playGameAudio('tap')
  const attempt = evaluateCategorySwitchAttempt(activeCategoryRound, option)
  appendUnitResult(attempt.correct)
  setFeedback(attempt.correct ? GAME_AUDIO_TEXT.correct : GAME_AUDIO_TEXT.wrong)
  void playGameAudio(attempt.correct ? 'correct' : 'wrong')
  scheduleNextRound()
}

async function previewSoundCard(card: SoundCard) {
  if (phaseRef.current !== 'playing' || soundPhase !== 'preview' || !activeSoundRound) return
  setSoundPlaybackError('')
  const previewPlayed = await playAudioSrc(card.audioSrc)
  if (!previewPlayed) {
    setSoundPlaybackError('声音播放异常，请重新试听这张卡片')
    return
  }
  const nextRound = markCardPreviewed(activeSoundRound, card.id)
  setActiveSoundRound(nextRound)
  if (nextRound.previewComplete) {
    setSoundPhase('choose')
    const targetPlayed = await playAudioSrc(nextRound.target.audioSrc)
    if (!targetPlayed) {
      setSoundPlaybackError('目标声音播放异常，请点击重播目标声音')
      return
    }
    startRoundTimeout(nextRound.timeoutMs)
  }
}

async function replayTargetSound() {
  if (!activeSoundRound || soundPhase !== 'choose') return
  setSoundPlaybackError('')
  const played = await playAudioSrc(activeSoundRound.target.audioSrc)
  if (!played) {
    setSoundPlaybackError('目标声音播放异常，请再次点击重播')
  }
}

function selectSoundCard(card: SoundCard) {
  if (phaseRef.current !== 'playing' || soundPhase !== 'choose' || unitLockedRef.current || !activeSoundRound) return
  unitLockedRef.current = true
  const attempt = evaluateSoundDiscriminationAttempt(activeSoundRound, card)
  appendUnitResult(attempt.correct)
  setFeedback(attempt.correct ? GAME_AUDIO_TEXT.correct : GAME_AUDIO_TEXT.wrong)
  void playGameAudio(attempt.correct ? 'correct' : 'wrong')
  scheduleNextRound()
}

function selectPuzzleTile(tile: PuzzleTile) {
  if (phaseRef.current !== 'playing' || puzzlePreviewing || unitLockedRef.current || !activePuzzleRound) return
  if (!selectedPuzzleTileId) {
    setSelectedPuzzleTileId(tile.id)
    return
  }
  const nextTiles = swapPuzzleTiles(activePuzzleRound.tiles, selectedPuzzleTileId, tile.id)
  const nextRound = { ...activePuzzleRound, tiles: nextTiles }
  setActivePuzzleRound(nextRound)
  setSelectedPuzzleTileId(null)
  if (evaluatePuzzleCompletion(nextTiles)) {
    unitLockedRef.current = true
    appendUnitResult(true)
    setFeedback(GAME_AUDIO_TEXT.correct)
    void playGameAudio('correct')
    scheduleNextRound()
  }
}
```

- [x] **Step 7: Render pattern sequence**

Add `renderPatternSequenceGame()` similar to color sequence:

```tsx
function renderPatternSequenceGame() {
  if (!activePatternRound) return renderLoadingRound()
  return (
    <View className='page game-session-page hainan-game-page'>
      {renderGameTopBar()}
      {phase === 'paused' ? <Text className='pending-upload-banner'>已暂停，点击继续后恢复训练</Text> : null}
      <Text className='section-title'>
        {phase === 'paused' ? '训练已暂停' : patternRevealing ? '请记住这个图案顺序' : '请按刚才的顺序点击图案'}
      </Text>
      {phase !== 'paused' ? (
        <View className='sequence-preview'>
          {patternRevealing
            ? activePatternRound.sequence.map((pattern, index) => (
                <View key={`${pattern.id}-${index}`} className='image-sequence-chip'>
                  <Image className='game-image' src={pattern.imageSrc} mode='aspectFit' />
                  <Text>{pattern.label}</Text>
                </View>
              ))
            : activePatternRound.sequence.map((_pattern, index) => (
                <Text key={index} className='sequence-chip hidden-chip'>
                  {index < activePatternInput.length ? '已选' : index + 1}
                </Text>
              ))}
        </View>
      ) : null}
      <View className='pattern-grid'>
        {activePatternRound.patterns.map((pattern) => (
          <Button key={pattern.id} className='image-tile' disabled={phase !== 'playing' || patternRevealing || unitLockedRef.current} onClick={() => selectPattern(pattern)}>
            <Image className='game-image' src={pattern.imageSrc} mode='aspectFit' />
            <Text>{pattern.label}</Text>
          </Button>
        ))}
      </View>
      {feedback ? <Text className='game-feedback'>{feedback}</Text> : null}
    </View>
  )
}
```

- [x] **Step 8: Render category switch**

Add `renderCategorySwitchGame()`:

```tsx
function renderCategorySwitchGame() {
  if (!activeCategoryRound) return renderLoadingRound()
  return (
    <View className='page game-session-page hainan-game-page'>
      {renderGameTopBar()}
      {phase === 'paused' ? <Text className='pending-upload-banner'>已暂停，点击继续后恢复训练</Text> : null}
      <Text className='section-title'>{activeCategoryRound.ruleLabel}</Text>
      <View className='category-card'>
        <Image className='category-image' src={activeCategoryRound.item.imageSrc} mode='aspectFit' />
        <Text className='category-label'>{activeCategoryRound.item.label}</Text>
      </View>
      <View className='category-options'>
        {activeCategoryRound.options.map((option) => (
          <Button key={option} className='category-option' disabled={phase !== 'playing' || unitLockedRef.current} onClick={() => selectCategory(option)}>
            {option}
          </Button>
        ))}
      </View>
      {feedback ? <Text className='game-feedback'>{feedback}</Text> : null}
    </View>
  )
}
```

- [x] **Step 9: Render sound discrimination**

Add `renderSoundDiscriminationGame()`:

```tsx
function renderSoundDiscriminationGame() {
  if (!activeSoundRound) return renderLoadingRound()
  return (
    <View className='page game-session-page hainan-game-page'>
      {renderGameTopBar()}
      {phase === 'paused' ? <Text className='pending-upload-banner'>已暂停，点击继续后恢复训练</Text> : null}
      <Text className='section-title'>
        {soundPhase === 'preview' ? '请逐张翻开卡片试听声音' : '请听目标声音，然后选择对应的背面卡片'}
      </Text>
      {soundPhase === 'choose' ? (
        <Button className='secondary-button' onClick={replayTargetSound}>
          重播目标声音
        </Button>
      ) : null}
      {soundPlaybackError ? <Text className='error'>{soundPlaybackError}</Text> : null}
      <View className='sound-card-grid'>
        {activeSoundRound.cards.map((card) => {
          const revealed = soundPhase === 'preview' && card.previewed
          return (
            <Button key={card.id} className={`sound-card ${revealed ? 'revealed' : ''}`} disabled={phase !== 'playing' || unitLockedRef.current} onClick={() => (soundPhase === 'preview' ? previewSoundCard(card) : selectSoundCard(card))}>
              {revealed ? (
                <>
                  <Image className='game-image' src={card.imageSrc} mode='aspectFit' />
                  <Text>{card.label}</Text>
                </>
              ) : (
                <Text className='card-back'>?</Text>
              )}
            </Button>
          )
        })}
      </View>
      {feedback ? <Text className='game-feedback'>{feedback}</Text> : null}
    </View>
  )
}
```

- [x] **Step 10: Render puzzle**

Add `renderPuzzleGame()`:

```tsx
function renderPuzzleGame() {
  if (!activePuzzleRound) return renderLoadingRound()
  return (
    <View className='page game-session-page hainan-game-page'>
      {renderGameTopBar()}
      {phase === 'paused' ? <Text className='pending-upload-banner'>已暂停，点击继续后恢复训练</Text> : null}
      <Text className='section-title'>{puzzlePreviewing ? '请记住完整图片' : '点击两块拼图交换位置'}</Text>
      {puzzlePreviewing ? (
        <Image className='puzzle-preview-image' src={activePuzzleRound.imageSrc} mode='aspectFit' />
      ) : (
        <View className={`puzzle-grid puzzle-grid-${activePuzzleRound.cols}`}>
          {activePuzzleRound.tiles.map((tile) => (
            <Button key={tile.id} className={`puzzle-tile ${selectedPuzzleTileId === tile.id ? 'selected' : ''}`} onClick={() => selectPuzzleTile(tile)}>
              <Image className='puzzle-tile-image' src={activePuzzleRound.imageSrc} mode='aspectFill' />
              <Text>{tile.correctIndex + 1}</Text>
            </Button>
          ))}
        </View>
      )}
      {feedback ? <Text className='game-feedback'>{feedback}</Text> : null}
    </View>
  )
}
```

This first implementation may show the same source image in every tile with an order number overlay. It still uses image assets and validates ordering by tile positions. Do not implement drag-and-drop.

- [x] **Step 11: Wire render dispatch**

Add dispatches before result phase:

```ts
if ((phase === 'playing' || phase === 'paused') && gameCode === 'game-memory-pattern-sequence') {
  return renderPatternSequenceGame()
}
if ((phase === 'playing' || phase === 'paused') && gameCode === 'game-executive-category-switch') {
  return renderCategorySwitchGame()
}
if ((phase === 'playing' || phase === 'paused') && gameCode === 'game-audiovisual-sound-discrimination') {
  return renderSoundDiscriminationGame()
}
if ((phase === 'playing' || phase === 'paused') && gameCode === 'game-audiovisual-puzzle') {
  return renderPuzzleGame()
}
```

- [x] **Step 12: Add styles**

Modify `miniapp/src/app.scss` inside/near `.game-session-page`:

```scss
.pattern-grid,
.category-options,
.sound-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.image-tile,
.category-option,
.sound-card,
.puzzle-tile {
  min-height: 132px;
  border: 2px solid rgba(47, 125, 143, 0.28);
  background: #ffffff;
  color: #173b45;
}

.game-image,
.category-image {
  width: 92px;
  height: 92px;
}

.image-sequence-chip {
  min-width: 116px;
  padding: 12px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
  text-align: center;
}

.category-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.92);
}

.sound-card {
  min-height: 170px;
}

.sound-card.revealed {
  border-color: #2f7d8f;
}

.card-back {
  font-size: 48px;
  font-weight: 700;
}

.puzzle-preview-image {
  width: 100%;
  height: 360px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.92);
}

.puzzle-grid {
  display: grid;
  gap: 8px;
}

.puzzle-grid-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.puzzle-grid-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.puzzle-tile {
  aspect-ratio: 1;
}

.puzzle-tile.selected {
  border-color: #d96c5f;
}

.puzzle-tile-image {
  width: 100%;
  height: 100%;
}
```

- [x] **Step 13: Run miniapp checks**

Run:

```bash
cd miniapp && npm run test
cd miniapp && npx tsc --noEmit --skipLibCheck
cd miniapp && npm run build:weapp
```

Expected: tests PASS, typecheck PASS, Webpack compiled successfully.

- [x] **Step 14: Commit page integration**

```bash
git add miniapp/src/pages/game-session/index.tsx miniapp/src/app.scss miniapp/src/types/patientApp.ts
git commit -m "feat(miniapp): 接入剩余真实游戏页面"
```

---

### Task 8: Backend Validation Coverage for New Game Codes

**Files:**
- Modify: `backend/apps/training/tests/test_training_current_prescription.py`

- [x] **Step 1: Add parameterized backend test**

Modify `backend/apps/training/tests/test_training_current_prescription.py` with a new test:

```py
@pytest.mark.parametrize(
    "source_key",
    [
        "game-memory-pattern-sequence",
        "game-executive-category-switch",
        "game-audiovisual-sound-discrimination",
        "game-audiovisual-puzzle",
    ],
)
def test_training_create_accepts_remaining_official_game_codes(active_prescription, source_key):
    game = ActionLibraryItem.objects.get(source_key=source_key)
    action = PrescriptionAction.objects.create_from_library_item(
        prescription=active_prescription,
        action=game,
        order=9,
    )

    record = create_training_record_for_current_prescription(
        project_patient=active_prescription.project_patient,
        prescription_action_id=action.id,
        training_date=date(2026, 5, 16),
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=10,
        score=88,
        form_data={
            "accuracy_rate": 80,
            "error_count": 2,
            "difficulty": "中等",
            "raw_detail": {
                "game_code": source_key,
                "ended_by": "timer",
                "ended_early": False,
                "prescribed_difficulty": "中等",
                "difficulty_adjusted": False,
                "difficulty_adjust_reason": "",
                "upload_mode": "direct",
                "retry_count": 0,
                "total_retry_count": 0,
                "session_duration_seconds": 600,
                "suggested_duration_minutes": 10,
                "completed_units": 10,
                "correct_units": 8,
            },
        },
        note="",
    )

    assert record.prescription_action == action
    assert record.form_data["raw_detail"]["game_code"] == source_key
```

Import `date` if this file does not already import it:

```py
from datetime import date
```

Import `TrainingRecord` if missing:

```py
from apps.training.models import TrainingRecord
```

- [x] **Step 2: Run backend targeted tests**

Run:

```bash
cd backend && pytest apps/training/tests/test_training_current_prescription.py -q
```

Expected: PASS.

- [x] **Step 3: Commit backend test coverage**

```bash
git add backend/apps/training/tests/test_training_current_prescription.py
git commit -m "test(training): 覆盖剩余游戏编码提交"
```

---

### Task 9: Final Verification and Plan Status

**Files:**
- Modify: `docs/superpowers/plans/2026-05-16-wechat-miniapp-remaining-real-games.md`

- [x] **Step 1: Run targeted miniapp tests**

Run:

```bash
cd miniapp && npx vitest run \
  src/pages/game-session/gameAudio.test.ts \
  src/pages/game-session/patternSequence.test.ts \
  src/pages/game-session/categorySwitch.test.ts \
  src/pages/game-session/soundDiscrimination.test.ts \
  src/pages/game-session/puzzle.test.ts
```

Expected: PASS.

- [x] **Step 2: Run miniapp full checks**

Run:

```bash
cd miniapp && npm run test
cd miniapp && npx tsc --noEmit --skipLibCheck
cd miniapp && npm run build:weapp
```

Expected: PASS and Webpack compiled successfully.

- [x] **Step 3: Run backend targeted checks**

Run:

```bash
cd backend && pytest apps/training/tests/test_training_current_prescription.py apps/training/tests/test_tracking_api.py -q
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

Expected: all commands exit 0. Existing warnings are acceptable only if they are warnings, not errors.

- [x] **Step 5: Verify static assets are present in build output**

Run:

```bash
test -f miniapp/dist/assets/audio/sound-discrimination/bird_1.m4a
test -f miniapp/dist/assets/images/game-session/pattern_sun.svg
test -f miniapp/dist/assets/images/game-session/puzzle_beach.svg
```

Expected: all `test -f` commands exit 0.

- [x] **Step 6: Update execution record in this plan**

At the top of this file, below the title, add a concrete execution record using the actual short SHAs from:

```bash
git log --oneline --reverse f26bb97..HEAD
```

The line must say that the remaining real games landed and verification passed, and it must include every short SHA printed by that command, comma-separated.

Then change all completed task checkboxes from `- [ ]` to `- [x]`.

- [x] **Step 7: Commit plan status**

```bash
git add docs/superpowers/plans/2026-05-16-wechat-miniapp-remaining-real-games.md
git commit -m "docs(plan): 标记小程序剩余真实游戏实施完成"
```
