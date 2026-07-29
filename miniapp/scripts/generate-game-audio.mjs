import { mkdirSync, renameSync, rmSync, writeFileSync } from 'node:fs'
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
  ['count_3', '3'],
  ['count_2', '2'],
  ['count_1', '1'],
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
]

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
      audio: { format: 'wav' },
    }),
  })

  if (!response.ok) {
    const body = await response.text()
    const excerpt = body.trim().slice(0, 500)
    throw new Error(`MiMo TTS request failed: ${response.status}${excerpt ? `: ${excerpt}` : ''}`)
  }

  const data = await response.json()
  const base64Audio = data?.choices?.[0]?.message?.audio?.data
  if (typeof base64Audio !== 'string' || base64Audio.length === 0) {
    throw new Error('MiMo TTS response did not include audio.data')
  }

  return Buffer.from(base64Audio, 'base64')
}

function cleanupGeneratedTempFiles() {
  mkdirSync(outDir, { recursive: true })

  for (const [name] of clips) {
    rmSync(join(outDir, `${name}.wav.tmp`), { force: true })
    rmSync(join(outDir, `${name}.m4a.tmp`), { force: true })
  }
}

function assertAfconvertAvailable() {
  try {
    execFileSync('which', ['afconvert'], { stdio: 'ignore' })
  } catch {
    throw new Error('afconvert is required on macOS to convert wav to m4a')
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

cleanupGeneratedTempFiles()
assertAfconvertAvailable()

for (const [name, text] of clips) {
  const wavPath = join(outDir, `${name}.wav.tmp`)
  const m4aPath = join(outDir, `${name}.m4a`)
  rmSync(wavPath, { force: true })

  try {
    const audio = await requestAudio(text)
    writeFileSync(wavPath, audio)
    convertWavToM4a(wavPath, m4aPath)
    console.log(`generated ${name}.m4a`)
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    throw new Error(`Failed to generate ${name}: ${message}`)
  } finally {
    rmSync(wavPath, { force: true })
    rmSync(`${m4aPath}.tmp`, { force: true })
  }
}
