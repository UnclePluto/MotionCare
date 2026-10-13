// 开发阶段预生成小米 MiMo 语音；密钥仅从环境读取，不进入小程序。
import { execFileSync, spawnSync } from 'node:child_process'
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
const root = dirname(dirname(fileURLToPath(import.meta.url)))
const output = join(root, 'resources', 'motion-rest-audio', 'source')
const phrases = {
  start: '本组完成，请休息两分钟。还剩', sets: '组。', thirty: '还剩三十秒，请准备下一组。',
  ready: '休息结束，准备好后请点击开始下一组。',
  0: '零', 1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八', 9: '九',
  ten: '十', hundred: '百', thousand: '千', wan: '万', yi: '亿',
}
if (process.argv.includes('--dry-run')) {
  for (const [key, phrase] of Object.entries(phrases)) console.log(`${key}: ${phrase}`)
  process.exit(0)
}
const apiKey = process.env.MIMO_API_KEY
if (!apiKey) throw new Error('生成休息语音需要 MIMO_API_KEY 环境变量')
const staging = mkdtempSync(join(tmpdir(), 'motioncare-mimo-rest-'))
const ffmpeg = args => execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...args], { stdio: 'pipe' })
const durationOf = path => Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path], { encoding: 'utf8' }).trim())
const trim = 'silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse'
function audioGain(path) {
  const result = spawnSync('ffmpeg', ['-hide_banner', '-i', path, '-af', 'volumedetect', '-f', 'null', '-'], { encoding: 'utf8' })
  const mean = Number(result.stderr.match(/mean_volume: ([-\d.]+) dB/)?.[1])
  const peak = Number(result.stderr.match(/max_volume: ([-\d.]+) dB/)?.[1])
  if (result.status !== 0 || !Number.isFinite(mean) || !Number.isFinite(peak)) throw new Error('语音音量无法校验')
  return Math.min(-20 - mean, -2 - peak)
}

try {
  // 固定同一小米女声音色；只传口播文字，不传本地音频或患者数据。
  const voice = '茉莉'
  for (const [key, phrase] of Object.entries(phrases)) {
    const response = await fetch('https://api.xiaomimimo.com/v1/chat/completions', {
      method: 'POST',
      headers: { 'api-key': apiKey, 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(90000),
      body: JSON.stringify({
        model: 'mimo-v2.5-tts',
        messages: [
          { role: 'user', content: '温和自然的成年普通话女声，像康复治疗师面对面指导。吐字清晰、语气亲切；只读中文，不说英文、不添加嗯或哦等语气词。数字单字清楚利落，不拖长尾音。' },
          { role: 'assistant', content: /^\d$/.test(key) ? `${phrase}。` : phrase },
        ],
        audio: { format: 'wav', voice },
      }),
    })
    if (!response.ok) throw new Error(`小米语音 ${key} 生成失败，HTTP ${response.status}`)
    const payload = await response.json()
    const data = payload?.choices?.[0]?.message?.audio?.data
    if (typeof data !== 'string' || !data) throw new Error(`小米语音 ${key} 未返回音频`)
    const raw = join(staging, `${key}.wav`)
    const trimmed = join(staging, `${key}-trimmed.wav`)
    const target = join(staging, `motion-rest-${key}.m4a`)
    writeFileSync(raw, Buffer.from(data, 'base64'))
    ffmpeg(['-i', raw, '-af', trim, '-ac', '1', '-ar', '24000', trimmed])
    const length = durationOf(trimmed)
    if (!Number.isFinite(length) || length <= 0) throw new Error(`小米语音 ${key} 无有效音轨`)
    const tempo = /^\d$/.test(key) ? Math.max(1, length / 0.8) : 1
    if (tempo > 1.5) throw new Error(`小米数字语音 ${key} 过长，请重新生成`)
    const paced = join(staging, `${key}-paced.wav`)
    ffmpeg(['-i', trimmed, '-af', `atempo=${tempo}`, '-ac', '1', '-ar', '24000', paced])
    ffmpeg(['-i', paced, '-af', `volume=${audioGain(paced)}dB`, '-ac', '1', '-ar', '24000', '-c:a', 'aac', '-b:a', '48k', target])
    const duration = durationOf(target)
    const maximum = /^\d$/.test(key) ? 1 : 12
    if (!Number.isFinite(duration) || duration <= 0 || duration >= maximum) throw new Error(`小米语音 ${key} 成品时长不合适，请重新生成`)
    console.log(`已生成 motion-rest-${key}.m4a，${duration.toFixed(3)} 秒`)
  }
  // 全部口播生成并校验后才替换；原节拍音效无需语音合成。
  mkdirSync(output, { recursive: true })
  for (const key of Object.keys(phrases)) copyFileSync(join(staging, `motion-rest-${key}.m4a`), join(output, `motion-rest-${key}.m4a`))
} finally {
  rmSync(staging, { recursive: true, force: true })
}
