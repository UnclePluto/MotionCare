# Wechat Miniapp Game Experience Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the WeChat miniapp game experience with a distinct island-themed mobile game style, natural young female TTS, varied short feedback, and upgraded generated game artwork.

**Architecture:** Keep the existing `game-session` page and gameplay modules intact. Add small focused resource helpers for randomized feedback audio/text, update static asset references from SVG to PNG, replace local generation scripts with Xiaomi MiMo TTS and ChatGPT image assets, then scope visual changes under `.game-session-page` to avoid touching the rest of the miniapp.

**Tech Stack:** Taro 4, React 18, TypeScript, Sass, Vitest, WeChat miniapp static assets, Xiaomi MiMo V2.5 TTS API, built-in ChatGPT image generation.

---

## File Structure

- Modify `miniapp/src/pages/game-session/gameAudio.ts`: keep existing playback primitives; add typed feedback pools and a `playGameFeedback` helper.
- Modify `miniapp/src/pages/game-session/gameAudio.test.ts`: cover feedback pool shape, deterministic random selection, and playback source behavior.
- Modify `miniapp/src/pages/game-session/index.tsx`: use one helper for correct/wrong feedback text and audio instead of fixed `GAME_AUDIO_TEXT.correct/wrong`.
- Modify `miniapp/src/pages/game-session/patternSequence.ts`, `categorySwitch.ts`, `soundDiscrimination.ts`, `puzzle.ts`: switch game artwork paths from `.svg` to `.png`.
- Modify `miniapp/src/pages/game-session/patternSequence.test.ts`, `puzzle.test.ts`, and add assertions in `soundDiscrimination.test.ts` if needed: expect `.png` asset paths.
- Modify `miniapp/scripts/generate-game-audio.mjs`: replace macOS `say` implementation with Xiaomi MiMo V2.5 TTS, preserving local conversion to `.m4a`.
- Modify `miniapp/package.json`: add scripts for TTS generation and dry-run validation.
- Modify `miniapp/src/app.config.ts` and `miniapp/config/index.ts`: move the game page and heavy game assets into the `pages/game-session` subpackage.
- Add generated audio under `miniapp/src/pages/game-session/assets/audio/game-session/`: new Xiaomi-generated intro/feedback clips.
- Add generated images under `miniapp/src/pages/game-session/assets/images/game-session/`: 18 PNG assets matching the island game style.
- Modify `miniapp/src/app.scss`: rewrite game page visual styling inside `.game-session-page`.

Git commits are gated by explicit user approval in this repository. If the user authorizes commits during execution, use Chinese commit messages.

## Task 1: Add Feedback Pools And Playback Helper

**Files:**
- Modify: `miniapp/src/pages/game-session/gameAudio.ts`
- Modify: `miniapp/src/pages/game-session/gameAudio.test.ts`

- [x] **Step 1: Write failing tests for feedback pools**

Add these imports in `miniapp/src/pages/game-session/gameAudio.test.ts`:

```ts
import {
  GAME_AUDIO_SRC,
  GAME_AUDIO_TEXT,
  GAME_FEEDBACK,
  SOUND_DISCRIMINATION_AUDIO,
  pickGameFeedback,
  playGameFeedback,
  isGameAudioMuted,
  playAudioSrc,
  playGameAudio,
  setGameAudioMuted,
} from './gameAudio'
```

Add this test block after the existing `game audio catalog` tests:

```ts
describe('game feedback catalog', () => {
  it('defines short varied feedback clips', () => {
    expect(GAME_FEEDBACK.correct.map((item) => item.text)).toEqual([
      '很好',
      '答对啦',
      '继续保持',
      '反应很快',
    ])
    expect(GAME_FEEDBACK.wrong.map((item) => item.text)).toEqual([
      '没关系',
      '再试一题',
      '慢慢来',
      '调整一下',
    ])
    expect(GAME_FEEDBACK.correct.every((item) => item.src.endsWith('.m4a'))).toBe(true)
    expect(GAME_FEEDBACK.wrong.every((item) => item.src.endsWith('.m4a'))).toBe(true)
  })

  it('selects feedback deterministically when random is injected', () => {
    expect(pickGameFeedback('correct', () => 0).text).toBe('很好')
    expect(pickGameFeedback('correct', () => 0.74).text).toBe('继续保持')
    expect(pickGameFeedback('wrong', () => 0.99).text).toBe('调整一下')
  })
})
```

Add this test in the `playGameAudio` describe block:

```ts
it('plays the selected feedback clip and returns its text', () => {
  const { audio } = createMockAudio()
  taroMock.getStorageSync.mockReturnValue(false)
  taroMock.createInnerAudioContext.mockReturnValue(audio)

  const feedback = playGameFeedback('wrong', () => 0)

  expect(feedback.text).toBe('没关系')
  expect(audio.src).toBe('/assets/audio/game-session/wrong_1.m4a')
  expect(audio.play).toHaveBeenCalledTimes(1)
})
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/gameAudio.test.ts
```

Expected: FAIL because `GAME_FEEDBACK`, `pickGameFeedback`, and `playGameFeedback` are not exported yet.

- [x] **Step 3: Implement feedback helper**

In `miniapp/src/pages/game-session/gameAudio.ts`, add these types after `GameAudioKey`:

```ts
export type GameFeedbackKind = 'correct' | 'wrong'

export type GameFeedbackClip = {
  key: string
  text: string
  src: string
}
```

Keep `GAME_AUDIO_TEXT.correct` and `GAME_AUDIO_TEXT.wrong` for compatibility, but set them to short fallback text:

```ts
  correct: '很好',
  wrong: '没关系',
```

Add this catalog after `GAME_AUDIO_SRC`:

```ts
export const GAME_FEEDBACK: Record<GameFeedbackKind, GameFeedbackClip[]> = {
  correct: [
    { key: 'correct_1', text: '很好', src: '/assets/audio/game-session/correct_1.m4a' },
    { key: 'correct_2', text: '答对啦', src: '/assets/audio/game-session/correct_2.m4a' },
    { key: 'correct_3', text: '继续保持', src: '/assets/audio/game-session/correct_3.m4a' },
    { key: 'correct_4', text: '反应很快', src: '/assets/audio/game-session/correct_4.m4a' },
  ],
  wrong: [
    { key: 'wrong_1', text: '没关系', src: '/assets/audio/game-session/wrong_1.m4a' },
    { key: 'wrong_2', text: '再试一题', src: '/assets/audio/game-session/wrong_2.m4a' },
    { key: 'wrong_3', text: '慢慢来', src: '/assets/audio/game-session/wrong_3.m4a' },
    { key: 'wrong_4', text: '调整一下', src: '/assets/audio/game-session/wrong_4.m4a' },
  ],
}
```

Add these functions before `isGameAudioMuted`:

```ts
function pickIndex(length: number, random: () => number): number {
  const value = random()
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.9999999999999999) : 0
  return Math.floor(normalized * length)
}

export function pickGameFeedback(
  kind: GameFeedbackKind,
  random: () => number = Math.random
): GameFeedbackClip {
  const clips = GAME_FEEDBACK[kind]
  return clips[pickIndex(clips.length, random)]
}
```

Add this exported function after `playGameAudio`:

```ts
export function playGameFeedback(
  kind: GameFeedbackKind,
  random: () => number = Math.random
): GameFeedbackClip {
  const feedback = pickGameFeedback(kind, random)
  if (!isGameAudioMuted()) {
    void playStaticAudio(feedback.src)
  }
  return feedback
}
```

- [x] **Step 4: Run focused tests and verify pass**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/gameAudio.test.ts
```

Expected: PASS.

## Task 2: Use Random Short Feedback In Game Session

**Files:**
- Modify: `miniapp/src/pages/game-session/index.tsx`

- [x] **Step 1: Replace imports**

In `miniapp/src/pages/game-session/index.tsx`, replace the `gameAudio` import section so it includes `playGameFeedback`:

```ts
import {
  GAME_AUDIO_TEXT,
  isGameAudioMuted,
  playAudioSrc,
  playGameAudio,
  playGameFeedback,
  setGameAudioMuted,
  SOUND_DISCRIMINATION_AUDIO,
  type GameAudioKey,
} from './gameAudio'
```

- [x] **Step 2: Add a local feedback helper**

Add this helper near `uploadStateText`:

```ts
function feedbackKind(correct: boolean): 'correct' | 'wrong' {
  return correct ? 'correct' : 'wrong'
}
```

Inside `GameSessionPage`, add this function after `setSoundRoundPhase`:

```ts
  function showAttemptFeedback(correct: boolean) {
    const feedbackClip = playGameFeedback(feedbackKind(correct))
    setFeedback(feedbackClip.text)
  }
```

- [x] **Step 3: Replace fixed feedback call sites**

Replace the timeout feedback block:

```ts
    setFeedback(GAME_AUDIO_TEXT.wrong)
    void playGameAudio('wrong')
```

with:

```ts
    showAttemptFeedback(false)
```

Replace each repeated attempt block:

```ts
    setFeedback(attempt.correct ? GAME_AUDIO_TEXT.correct : GAME_AUDIO_TEXT.wrong)
    void playGameAudio(attempt.correct ? 'correct' : 'wrong')
```

with:

```ts
    showAttemptFeedback(attempt.correct)
```

Replace the puzzle success block:

```ts
      setFeedback(GAME_AUDIO_TEXT.correct)
      void playGameAudio('correct')
```

with:

```ts
      showAttemptFeedback(true)
```

- [x] **Step 4: Verify no fixed correct/wrong feedback remains in the page**

Run:

```bash
rg -n "GAME_AUDIO_TEXT\\.(correct|wrong)|playGameAudio\\('(correct|wrong)'\\)" miniapp/src/pages/game-session/index.tsx
```

Expected: no output.

- [x] **Step 5: Run focused tests**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session
```

Expected: PASS.

## Task 3: Switch Game Artwork References To PNG

**Files:**
- Modify: `miniapp/src/pages/game-session/patternSequence.ts`
- Modify: `miniapp/src/pages/game-session/categorySwitch.ts`
- Modify: `miniapp/src/pages/game-session/soundDiscrimination.ts`
- Modify: `miniapp/src/pages/game-session/puzzle.ts`
- Modify: `miniapp/src/pages/game-session/patternSequence.test.ts`
- Modify: `miniapp/src/pages/game-session/puzzle.test.ts`
- Modify: `miniapp/src/pages/game-session/soundDiscrimination.test.ts` if it asserts image paths

- [x] **Step 1: Write failing expectations for PNG paths**

In `miniapp/src/pages/game-session/patternSequence.test.ts`, change expected paths from `.svg` to `.png`, for example:

```ts
expect(round.patterns[0]).toMatchObject({
  id: 'sun',
  label: '太阳',
  imageSrc: '/assets/images/game-session/pattern_sun.png',
})
```

In `miniapp/src/pages/game-session/puzzle.test.ts`, change path expectations:

```ts
expect(round.imageSrc).toBe('/assets/images/game-session/puzzle_beach.png')
expect(beachRound.imageSrc).toBe('/assets/images/game-session/puzzle_beach.png')
expect(lighthouseRound.imageSrc).toBe('/assets/images/game-session/puzzle_lighthouse.png')
```

If `miniapp/src/pages/game-session/soundDiscrimination.test.ts` does not assert image paths, add:

```ts
it('uses png image assets for sound cards', () => {
  const round = createSoundDiscriminationRound('简单', SOUND_DISCRIMINATION_AUDIO, () => 0)

  expect(round.cards.every((card) => card.imageSrc.endsWith('.png'))).toBe(true)
})
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/patternSequence.test.ts src/pages/game-session/puzzle.test.ts src/pages/game-session/soundDiscrimination.test.ts
```

Expected: FAIL because production paths still end in `.svg`.

- [x] **Step 3: Update production paths**

In `miniapp/src/pages/game-session/patternSequence.ts`, replace the pool with:

```ts
const PATTERN_POOL: PatternToken[] = [
  { id: 'sun', label: '太阳', imageSrc: '/assets/images/game-session/pattern_sun.png', fallback: '日' },
  { id: 'coconut', label: '椰子树', imageSrc: '/assets/images/game-session/pattern_coconut.png', fallback: '椰' },
  { id: 'boat', label: '小船', imageSrc: '/assets/images/game-session/pattern_boat.png', fallback: '船' },
  { id: 'lighthouse', label: '灯塔', imageSrc: '/assets/images/game-session/pattern_lighthouse.png', fallback: '塔' },
  { id: 'shell', label: '贝壳', imageSrc: '/assets/images/game-session/pattern_shell.png', fallback: '贝' },
]
```

In `miniapp/src/pages/game-session/categorySwitch.ts`, replace each `imageSrc` extension with `.png`.

In `miniapp/src/pages/game-session/soundDiscrimination.ts`, replace `CATEGORY_IMAGE_SRC` with:

```ts
export const CATEGORY_IMAGE_SRC: Record<SoundDiscriminationCategory, string> = {
  bird: '/assets/images/game-session/sound_bird.png',
  train: '/assets/images/game-session/sound_train.png',
  phone: '/assets/images/game-session/sound_phone.png',
  laugh: '/assets/images/game-session/sound_laugh.png',
  drum: '/assets/images/game-session/sound_drum.png',
}
```

In `miniapp/src/pages/game-session/puzzle.ts`, replace `PUZZLE_IMAGES` with:

```ts
export const PUZZLE_IMAGES = [
  { key: 'beach', src: '/assets/images/game-session/puzzle_beach.png' },
  { key: 'garden', src: '/assets/images/game-session/puzzle_garden.png' },
  { key: 'lighthouse', src: '/assets/images/game-session/puzzle_lighthouse.png' },
] as const
```

- [x] **Step 4: Run focused tests and verify pass**

Run:

```bash
cd miniapp && npm run test -- src/pages/game-session/patternSequence.test.ts src/pages/game-session/puzzle.test.ts src/pages/game-session/soundDiscrimination.test.ts
```

Expected: PASS.

## Task 4: Replace Audio Generation Script With Xiaomi MiMo TTS

**Files:**
- Modify: `miniapp/scripts/generate-game-audio.mjs`
- Modify: `miniapp/package.json`

- [x] **Step 1: Add package scripts**

In `miniapp/package.json`, add these scripts:

```json
"generate-game-audio": "node scripts/generate-game-audio.mjs",
"generate-game-audio:dry-run": "node scripts/generate-game-audio.mjs --dry-run"
```

- [x] **Step 2: Replace the script implementation**

Replace `miniapp/scripts/generate-game-audio.mjs` with this implementation:

```js
import { mkdirSync, readdirSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const outDir = join(root, 'src/pages/game-session/assets/audio/game-session')
const dryRun = process.argv.includes('--dry-run')
const apiKey = process.env.MIMO_API_KEY

const model = 'mimo-v2.5-tts-voicedesign'
const voicePrompt = [
  '年轻女性，中文普通话，声音清亮自然、富有活力，像专业康复训练陪伴员。',
  '语气积极鼓励但不夸张，语速略快但不催促，咬字清楚，适合移动端小游戏短提示。',
].join('')

const clips = [
  ['color_intro', '颜色顺序记忆开始。记住亮起顺序，再按同样顺序点击。'],
  ['pattern_intro', '图案记忆开始。记住图案顺序，再按同样顺序点击。'],
  ['category_intro', '分类切换开始。看清提示，选择正确分类。'],
  ['sound_intro', '声音辨别开始。先试听卡片，再找到目标声音。'],
  ['puzzle_intro', '拼图训练开始。先看完整图，再交换拼图块。'],
  ['inhibition_intro', '反应训练开始。找出不一样的数字并点击。'],
  ['count_3', '三'],
  ['count_2', '二'],
  ['count_1', '一'],
  ['start', '开始'],
  ['correct_1', '很好'],
  ['correct_2', '答对啦'],
  ['correct_3', '继续保持'],
  ['correct_4', '反应很快'],
  ['wrong_1', '没关系'],
  ['wrong_2', '再试一题'],
  ['wrong_3', '慢慢来'],
  ['wrong_4', '调整一下'],
  ['complete', '本次训练完成，辛苦了。'],
  ['manual_end', '提前结束后，会保存本次部分训练。'],
  ['tap', '滴'],
]

const clipNames = new Set(clips.map(([name]) => name))

async function requestAudio(text) {
  const response = await fetch('https://api.xiaomimimo.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'api-key': apiKey,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: 'user', content: voicePrompt },
        { role: 'assistant', content: text },
      ],
      audio: {
        format: 'wav',
        optimize_text_preview: false,
      },
    }),
  })

  if (!response.ok) {
    const body = await response.text()
    throw new Error(`MiMo TTS request failed: ${response.status} ${body.slice(0, 500)}`)
  }

  const data = await response.json()
  const base64Audio = data?.choices?.[0]?.message?.audio?.data
  if (typeof base64Audio !== 'string' || base64Audio.length === 0) {
    throw new Error('MiMo TTS response did not include audio.data')
  }

  return Buffer.from(base64Audio, 'base64')
}

function cleanupOutputDirectory() {
  mkdirSync(outDir, { recursive: true })
  for (const entry of readdirSync(outDir)) {
    const path = join(outDir, entry)
    if (entry.endsWith('.wav') || entry.endsWith('.tmp')) {
      rmSync(path, { force: true })
      continue
    }
    if (entry.endsWith('.m4a')) {
      const name = entry.slice(0, -'.m4a'.length)
      if (!clipNames.has(name) && name !== 'correct' && name !== 'wrong') {
        rmSync(path, { force: true })
      }
    }
  }
}

function convertWavToM4a(wavPath, m4aPath) {
  const tempM4aPath = `${m4aPath}.tmp`
  rmSync(tempM4aPath, { force: true })
  execFileSync('afconvert', ['-f', 'm4af', '-d', 'aac', wavPath, tempM4aPath], {
    stdio: 'inherit',
  })
  renameSync(tempM4aPath, m4aPath)
}

if (dryRun) {
  console.log(`clips=${clips.length}`)
  for (const [name, text] of clips) {
    console.log(`${name}: ${text}`)
  }
  process.exit(0)
}

if (!apiKey) {
  throw new Error('MIMO_API_KEY is required to generate game audio')
}

cleanupOutputDirectory()

for (const [name, text] of clips) {
  const wavPath = join(outDir, `${name}.wav.tmp`)
  const m4aPath = join(outDir, `${name}.m4a`)
  rmSync(wavPath, { force: true })

  try {
    const audio = await requestAudio(text)
    writeFileSync(wavPath, audio)
    convertWavToM4a(wavPath, m4aPath)
    console.log(`generated ${name}.m4a`)
  } finally {
    rmSync(wavPath, { force: true })
    rmSync(`${m4aPath}.tmp`, { force: true })
  }
}
```

- [x] **Step 3: Run dry-run validation**

Run:

```bash
cd miniapp && npm run generate-game-audio:dry-run
```

Expected: output starts with `clips=21` and prints all clip names without requiring `MIMO_API_KEY`.

## Task 5: Generate Xiaomi TTS Audio Assets

**Files:**
- Add/Modify: `miniapp/src/pages/game-session/assets/audio/game-session/*.m4a`

- [x] **Step 1: Generate audio with an environment variable**

Run with the key injected only in the shell environment:

```bash
cd miniapp && MIMO_API_KEY="$MIMO_API_KEY" npm run generate-game-audio
```

Expected: logs contain `generated color_intro.m4a`, `generated correct_1.m4a`, and `generated wrong_4.m4a`. Logs must not print the API key.

- [x] **Step 2: Verify generated files exist**

Run:

```bash
find miniapp/src/pages/game-session/assets/audio/game-session -maxdepth 1 -type f -name '*.m4a' | sort
```

Expected: includes these new files:

```text
miniapp/src/pages/game-session/assets/audio/game-session/correct_1.m4a
miniapp/src/pages/game-session/assets/audio/game-session/correct_2.m4a
miniapp/src/pages/game-session/assets/audio/game-session/correct_3.m4a
miniapp/src/pages/game-session/assets/audio/game-session/correct_4.m4a
miniapp/src/pages/game-session/assets/audio/game-session/wrong_1.m4a
miniapp/src/pages/game-session/assets/audio/game-session/wrong_2.m4a
miniapp/src/pages/game-session/assets/audio/game-session/wrong_3.m4a
miniapp/src/pages/game-session/assets/audio/game-session/wrong_4.m4a
```

- [x] **Step 3: Spot-check audio metadata**

Run:

```bash
afinfo miniapp/src/pages/game-session/assets/audio/game-session/correct_1.m4a | sed -n '1,20p'
afinfo miniapp/src/pages/game-session/assets/audio/game-session/color_intro.m4a | sed -n '1,20p'
```

Expected: both commands identify playable MPEG-4 audio.

## Task 6: Generate And Save 18 PNG Game Images

**Files:**
- Add: `miniapp/src/pages/game-session/assets/images/game-session/pattern_sun.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/pattern_coconut.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/pattern_boat.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/pattern_lighthouse.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/pattern_shell.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/category_pineapple.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/category_bird.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/category_train.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/category_drum.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/category_phone.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/sound_bird.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/sound_train.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/sound_phone.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/sound_laugh.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/sound_drum.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/puzzle_beach.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/puzzle_garden.png`
- Add: `miniapp/src/pages/game-session/assets/images/game-session/puzzle_lighthouse.png`

- [x] **Step 1: Generate single-object option images**

Use built-in ChatGPT image generation. Generate one image per prompt and save the selected output to the matching target path.

Shared prompt prefix:

```text
Use case: stylized-concept
Asset type: square WeChat miniapp game option artwork
Style: bright island rehabilitation mini-game illustration, clean polished 3D-friendly vector-like bitmap, adult-friendly, energetic but not childish, crisp centered subject, soft aqua and warm sunlight palette, no text, no watermark, no UI chrome.
Composition: one clear object centered, generous padding, simple soft background, high contrast at small mobile size.
```

Subject prompts:

```text
pattern_sun.png: cheerful sun icon with warm rays, island morning mood.
pattern_coconut.png: coconut palm and coconut fruit, simple tropical cue.
pattern_boat.png: small sailboat on calm turquoise water.
pattern_lighthouse.png: red and white lighthouse beside blue sea.
pattern_shell.png: pink seashell with subtle beach texture.
category_pineapple.png: bright pineapple with green leaves.
category_bird.png: friendly blue island bird, clear silhouette.
category_train.png: small modern train, simple front-side angle.
category_drum.png: hand drum with warm coral accents.
category_phone.png: ringing smartphone, clear phone shape.
sound_bird.png: friendly blue island bird listening cue.
sound_train.png: small modern train with sound wave cue.
sound_phone.png: ringing smartphone with sound wave cue.
sound_laugh.png: smiling face expression for laughter sound, no text.
sound_drum.png: hand drum with sound wave cue.
```

- [x] **Step 2: Generate puzzle images**

Use built-in ChatGPT image generation. Save outputs to the matching target paths.

Puzzle prompt prefix:

```text
Use case: stylized-concept
Asset type: square WeChat miniapp puzzle source image
Style: bright island rehabilitation mini-game illustration, polished 3D-friendly bitmap, adult-friendly, clear local details for puzzle slicing, no text, no watermark, no UI chrome.
Composition: full square scene with distinct regions in each quadrant, strong recognizable shapes, balanced colors, no tiny details.
```

Puzzle prompts:

```text
puzzle_beach.png: sunny tropical beach with sea, sand, umbrella, small sailboat, and bright sky.
puzzle_garden.png: warm rehabilitation garden with flowers, path, bench, trees, and soft sunlight.
puzzle_lighthouse.png: seaside lighthouse scene with lighthouse, rocks, sea, clouds, and warm sun.
```

- [x] **Step 3: Verify images are present**

Run:

```bash
find miniapp/src/pages/game-session/assets/images/game-session -maxdepth 1 -type f -name '*.png' | sort | wc -l
```

Expected: `18`.

- [x] **Step 4: Inspect dimensions**

Run:

```bash
sips -g pixelWidth -g pixelHeight miniapp/src/pages/game-session/assets/images/game-session/*.png | sed -n '1,120p'
```

Expected: every file has non-zero square dimensions.

Implementation note: app-bundled PNGs were resized to 384x384 and stripped/quantized after generation to keep the miniapp asset bundle small while preserving mobile display quality.

## Task 7: Apply Island Game Visual Styling

**Files:**
- Modify: `miniapp/src/app.scss`

- [ ] **Step 1: Replace game-specific style block**

In `miniapp/src/app.scss`, replace the nested `.game-session-page { ... }` visual rules with this scoped direction while preserving existing class names:

```scss
.game-session-page {
  color: #073b4c;
  background:
    radial-gradient(circle at 88% 8%, rgba(255, 183, 3, 0.26), transparent 28%),
    linear-gradient(180deg, #e8faff 0%, #fff7de 58%, #ecfff4 100%);

  .paragraph {
    display: block;
    margin: 16px 0;
    color: rgba(7, 59, 76, 0.78);
    font-size: 26px;
    line-height: 1.58;
    white-space: pre-wrap;
  }

  .game-hero,
  .panel,
  .field-card,
  .category-card,
  .result-panel {
    border: 1px solid rgba(0, 169, 206, 0.18);
    border-radius: 28px;
    background: rgba(255, 255, 255, 0.82);
    box-shadow: 0 18px 48px rgba(7, 59, 76, 0.12);
  }

  .game-hero {
    gap: 14px;
    margin-bottom: 22px;
    padding: 30px 26px;
  }

  .intro-hero {
    min-height: 460px;
    align-items: center;
    justify-content: center;
    text-align: center;
  }

  .eyebrow {
    display: inline-flex;
    width: fit-content;
    padding: 8px 18px;
    border-radius: 999px;
    color: #00796b;
    background: rgba(46, 196, 182, 0.16);
    font-size: 22px;
    font-weight: 800;
  }

  .title {
    color: #073b4c;
    font-size: 38px;
    line-height: 1.18;
  }

  .section-title {
    color: #073b4c;
    font-size: 30px;
    font-weight: 800;
  }

  .game-topbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 18px;
  }

  .game-stat {
    flex: 1 1 100%;
    color: #073b4c;
    font-size: 28px;
    font-weight: 900;
  }

  .primary-button {
    border-radius: 999px;
    color: #ffffff;
    background: linear-gradient(135deg, #00a9ce, #2ec4b6);
    box-shadow: 0 12px 28px rgba(0, 169, 206, 0.24);
  }

  .secondary-button {
    border-radius: 999px;
    color: #073b4c;
    background: rgba(255, 255, 255, 0.74);
  }

  .danger-button {
    color: #b42318;
    background: #fff1f0;
  }

  .sequence-chip,
  .color-tile,
  .number-tile,
  .image-tile,
  .category-option,
  .sound-card,
  .puzzle-tile {
    border-radius: 24px;
    box-shadow: 0 12px 26px rgba(7, 59, 76, 0.1);
  }

  .hidden-chip {
    border: 2px dashed rgba(0, 169, 206, 0.52);
    color: #073b4c;
    background: rgba(255, 255, 255, 0.76);
  }

  .image-tile,
  .category-option,
  .sound-card,
  .number-tile {
    border: 2px solid rgba(0, 169, 206, 0.22);
    color: #073b4c;
    background: rgba(255, 255, 255, 0.84);
  }

  .game-image,
  .category-image {
    width: 118px;
    height: 118px;
  }

  .puzzle-preview-image {
    width: 100%;
    height: 380px;
    border: 2px solid rgba(0, 169, 206, 0.18);
    border-radius: 28px;
    background: rgba(255, 255, 255, 0.82);
    box-shadow: 0 18px 48px rgba(7, 59, 76, 0.12);
  }

  .puzzle-grid {
    display: grid;
    gap: 10px;
  }

  .puzzle-tile.selected {
    border-color: #ff6b6b;
    background: #fff7ed;
    box-shadow: 0 0 0 6px rgba(255, 107, 107, 0.16);
  }

  .game-feedback {
    display: block;
    margin-top: 18px;
    padding: 16px 20px;
    border-radius: 999px;
    color: #00796b;
    background: rgba(46, 196, 182, 0.14);
    font-size: 28px;
    font-weight: 900;
    text-align: center;
  }
}
```

Keep existing non-game global classes above the game block unchanged.

- [x] **Step 2: Run Sass/Taro build check**

Run:

```bash
cd miniapp && npm run build:weapp
```

Expected: build succeeds and writes `miniapp/dist`.

## Task 8: Build And Manual QA

**Files:**
- No planned source changes unless QA finds a defect.

- [x] **Step 1: Run all miniapp tests**

Run:

```bash
cd miniapp && npm run test
```

Expected: PASS.

- [x] **Step 2: Build WeChat miniapp**

Run:

```bash
cd miniapp && npm run build:weapp
```

Expected: PASS.

- [x] **Step 3: Check asset references**

Run:

```bash
rg -n "/assets/images/game-session/.*\\.svg" miniapp/src/pages/game-session
```

Expected: no output.

Run:

```bash
rg -n "correct_1|wrong_4|playGameFeedback" miniapp/src/pages/game-session
```

Expected: output includes `gameAudio.ts` and `index.tsx`.

- [x] **Step 4: Open WeChat devtools**

Run:

```bash
open -a /Applications/wechatwebdevtools.app /Users/nick/my_dev/workout/MotionCare/miniapp/dist
```

Expected: WeChat DevTools opens the built miniapp project. If it opens the IDE but not the project, manually open `/Users/nick/my_dev/workout/MotionCare/miniapp/dist`.

Verified: WeChat DevTools opened `miniapp/dist` and loaded `pages/home/index` in the simulator.

- [ ] **Step 5: Manual gameplay checklist**

Verify in the simulator:

```text
1. Enter color sequence, sound discrimination, and puzzle games from the current prescription.
2. Confirm setup page, intro countdown, playing state, pause state, and result page use the island visual style.
3. Answer correctly several times and confirm text/audio feedback varies across the short correct pool.
4. Answer incorrectly or time out several times and confirm text/audio feedback varies across the short wrong pool.
5. Toggle mute and confirm feedback text still shows while audio stops.
6. Confirm all 18 PNG images render without obvious distortion or cropped core subject.
7. Confirm result upload still reaches the existing TrainingRecord flow.
```

Note: Full simulator gameplay walkthrough was not completed in this pass; the built project opened successfully in WeChat DevTools, but the simulator stayed on the home route during click attempts. Static, unit, build, package, and asset validations above are complete.

## Review Remediation: Package Size And Audio Lifecycle

**Files:**
- Modify: `miniapp/src/app.config.ts`
- Modify: `miniapp/config/index.ts`
- Modify: `miniapp/src/pages/game-session/gameAudio.ts`
- Modify: `miniapp/src/pages/game-session/gameAudio.test.ts`
- Modify: `miniapp/src/pages/game-session/index.tsx`
- Modify: `miniapp/scripts/generate-game-audio.mjs`
- Move: game audio/image assets into `miniapp/src/pages/game-session/assets/`
- Delete: superseded SVG placeholder assets and `miniapp/scripts/generate-game-images.mjs`

- [x] **Step 1: Move game page and heavy assets into a subpackage**

`app.json` now emits `subPackages: [{ root: 'pages/game-session', pages: ['index'] }]`, and build output places game images/audio under `dist/pages/game-session/assets/`.

- [x] **Step 2: Stop active audio on mute, pause, end, and unmount**

`stopActiveGameAudio()` tracks active `InnerAudioContext` instances. `playAudioSrc()` returns `false` while muted so sound-discrimination cannot treat muted playback as successful.

- [x] **Step 3: Add tests for muted playback and active audio cleanup**

Focused game-session tests include muted playback and forced stop coverage.

- [x] **Step 4: Improve TTS generation failure diagnostics**

The Xiaomi TTS script wraps each clip generation with the clip name and includes a bounded HTTP response excerpt on provider failures.

- [x] **Step 5: Verify package placement**

Measured build output: main package approximately 0.30 MiB, game subpackage approximately 1.85 MiB.

## Self-Review Notes

- Spec coverage: visual style is covered by Task 7; Xiaomi TTS by Tasks 4-5; short randomized feedback by Tasks 1-2; all 18 generated images by Task 6; existing gameplay/API preservation by Tasks 2-3 and Task 8 verification.
- Type consistency: feedback functions are defined in Task 1 and consumed in Task 2 with the same names and return shape.
- Safety: no API key value appears in this plan; generation uses `MIMO_API_KEY` only.
