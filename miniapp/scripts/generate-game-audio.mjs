import { mkdirSync, readdirSync, renameSync, rmSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const outDir = join(root, 'src/assets/audio/game-session')

const preferredVoice = 'Tingting'

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
  ['tap', '滴'],
]

const clipNames = new Set(clips.map(([name]) => name))

function sayToAiff(text, aiffPath) {
  try {
    execFileSync('say', ['-v', preferredVoice, '-o', aiffPath, text], { stdio: 'inherit' })
  } catch {
    execFileSync('say', ['-o', aiffPath, text], { stdio: 'inherit' })
  }
}

mkdirSync(outDir, { recursive: true })

for (const entry of readdirSync(outDir)) {
  const path = join(outDir, entry)
  if (entry.endsWith('.aiff') || entry.endsWith('.tmp')) {
    rmSync(path, { force: true })
    continue
  }

  if (entry.endsWith('.m4a')) {
    const name = entry.slice(0, -'.m4a'.length)
    if (!clipNames.has(name)) {
      rmSync(path, { force: true })
    }
  }
}

for (const [name, text] of clips) {
  const aiffPath = join(outDir, `${name}.aiff.tmp`)
  const tempM4aPath = join(outDir, `${name}.m4a.tmp`)
  const m4aPath = join(outDir, `${name}.m4a`)
  rmSync(aiffPath, { force: true })
  rmSync(tempM4aPath, { force: true })

  try {
    sayToAiff(text, aiffPath)
    execFileSync('afconvert', ['-f', 'm4af', '-d', 'aac', aiffPath, tempM4aPath], {
      stdio: 'inherit',
    })
    renameSync(tempM4aPath, m4aPath)
    console.log(`generated ${name}.m4a`)
  } finally {
    rmSync(aiffPath, { force: true })
    rmSync(tempM4aPath, { force: true })
  }
}
