// 本地预生成语音：不调用在线语音服务，不上传任何素材。
import { execFileSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
const root = dirname(dirname(fileURLToPath(import.meta.url)))
const output = join(root, 'resources', 'motion-rest-audio', 'source')
mkdirSync(output, { recursive: true })
const phrases = {
  start: '本组完成，请休息三分钟。还剩', sets: '组。', thirty: '还剩三十秒，请准备下一组。',
  ready: '休息结束，准备好后请点击开始下一组。',
  0: '零', 1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八', 9: '九',
  ten: '十', hundred: '百', thousand: '千', wan: '万', yi: '亿',
}
for (const [key, phrase] of Object.entries(phrases)) {
  const intermediate = join(output, `${key}.aiff`)
  execFileSync('say', ['-v', 'Tingting', '-r', '175', '-o', intermediate, phrase])
  const duration = Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', intermediate], { encoding: 'utf8' }).trim())
  if (!Number.isFinite(duration) || duration <= 0) throw new Error(`本地语音 ${key} 无有效音轨，请允许访问 macOS 语音服务后重试`)
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', intermediate, '-af', 'silenceremove=start_periods=1:start_threshold=-45dB:stop_periods=-1:stop_threshold=-45dB', '-c:a', 'aac', '-b:a', '48k', join(output, `motion-rest-${key}.m4a`)])
}
execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'aevalsrc=0.09*sin(2*PI*880*t)*exp(-80*t):s=22050:d=1', '-c:a', 'aac', '-b:a', '32k', join(output, 'motion-rest-tick.m4a')])
execFileSync('find', [output, '-name', '*.aiff', '-delete'])
