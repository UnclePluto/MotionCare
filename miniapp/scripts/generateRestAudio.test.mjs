import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const script = fileURLToPath(new URL('./generate-rest-audio.mjs', import.meta.url))
const env = { ...process.env, MIMO_API_KEY: '', PATH: '' }

describe('休息语音生成命令', () => {
  it('预览不需要密钥或音频工具，包含两分钟提示及数字倒数', () => {
    const result = spawnSync(process.execPath, [script, '--dry-run'], { env, encoding: 'utf8' })
    expect(result.status).toBe(0)
    expect(result.stdout).toContain('本组完成，请休息两分钟。还剩')
    for (const [key, text] of [['5', '五'], ['4', '四'], ['3', '三'], ['2', '二'], ['1', '一']]) {
      expect(result.stdout).toContain(`${key}: ${text}`)
    }
  })

  it('缺少小米密钥时在生成任何文件前停止', () => {
    const result = spawnSync(process.execPath, [script], { env, encoding: 'utf8' })
    expect(result.status).not.toBe(0)
    expect(result.stderr).toContain('MIMO_API_KEY')
    expect(result.stderr).not.toContain('say')
  })
})
