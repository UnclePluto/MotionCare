import { cp, mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

import { checkRelease, prepareRelease, releaseEnvironment, resolveUploadMetadata, validateDevtoolsResult } from './weapp-release.mjs'

const api = 'https://mcare-wx.whestsun.com/api'
const assets = 'https://cdn.whestsun.com/motioncare/static-assets'
const roots = []
afterEach(async () => {
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
})

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), 'motioncare-release-'))
  roots.push(root)
  await mkdir(join(root, 'output/static-assets'), { recursive: true })
  await writeFile(join(root, 'output/static-assets/current-version.txt'), 'v-fixture')
  await writeFile(join(root, 'project.config.json'), JSON.stringify({
    appid: 'wx095c9a6c41b60112', miniprogramRoot: './', setting: { urlCheck: true },
  }))
  await writeFile(join(root, 'app.json'), JSON.stringify({ pages: ['pages/bind/index'] }))
  await writeFile(join(root, 'app.js'), `const api=${JSON.stringify(api)};const assets=${JSON.stringify(assets)};`)
  return root
}

describe('微信正式发布门禁', () => {
  it('默认上传版本和描述使用本次发布配置', () => {
    expect(resolveUploadMetadata()).toEqual({ version: '7.1.1', description: 'bugs fix' })
  })

  it('允许完整覆盖版本和描述，拒绝只提供版本', () => {
    expect(resolveUploadMetadata(['7.1.2', '下一版说明'])).toEqual({ version: '7.1.2', description: '下一版说明' })
    expect(() => resolveUploadMetadata(['7.1.2'])).toThrow('用法')
  })

  it('微信 CLI 即使退出码为 0，只要输出错误就不能算成功', () => {
    expect(() => validateDevtoolsResult({ status: 0, stdout: '[error] { code: 10 }' }, { size: { total: 100 } }))
      .toThrow('开发者工具')
  })

  it('微信 CLI 成功输出还必须有本次生成的包体结果', () => {
    expect(() => validateDevtoolsResult({ status: 0, stdout: '✔ upload' }, {})).toThrow('结果')
    expect(() => validateDevtoolsResult({ status: 0, stdout: '✔ upload' }, { size: { total: 100 } })).not.toThrow()
    expect(() => validateDevtoolsResult({ status: 1, stdout: '✔ upload' }, { size: { total: 100 } })).toThrow()
  })
  it.each(['http://10.21.60.161:8000/api', 'https://127.0.0.1/api', 'https://wrong.example.com/api'])('拒绝被环境变量覆盖的正式 API：%s', value => {
    expect(() => releaseEnvironment({ TARO_APP_API_BASE_URL: value })).toThrow('API')
  })

  it('生产构建固定环境，并拒绝开发素材地址', () => {
    expect(releaseEnvironment({ NODE_ENV: 'development', TARO_APP_CONFIG_ENV: 'development' }))
      .toMatchObject({ NODE_ENV: 'production', TARO_APP_CONFIG_ENV: 'production', TARO_APP_API_BASE_URL: api })
    expect(() => releaseEnvironment({ TARO_APP_ASSET_BASE_URL: 'http://10.0.0.1/static-assets' })).toThrow('素材')
  })

  it('允许经过校验的正式包', async () => {
    await expect(checkRelease(await fixture())).resolves.toMatchObject({ appid: 'wx095c9a6c41b60112', apiBaseUrl: api })
  })

  it('开发地址即使与正式地址同时存在也必须阻止发布', async () => {
    const root = await fixture()
    await writeFile(join(root, 'common.js'), 'const url="http://10.21.60.161:8000/api"')
    await expect(checkRelease(root)).rejects.toThrow('开发或未知')
  })

  it('缺少正式 API 的旧包不能通过', async () => {
    const root = await fixture()
    await writeFile(join(root, 'app.js'), `const assets=${JSON.stringify(assets)}`)
    await expect(checkRelease(root)).rejects.toThrow('API')
  })

  it.each([
    { appid: 'wxwrong', setting: { urlCheck: true } },
    { appid: 'wx095c9a6c41b60112', setting: { urlCheck: false } },
  ])('拒绝 AppID 错误或关闭域名校验的包', async config => {
    const root = await fixture()
    await writeFile(join(root, 'project.config.json'), JSON.stringify(config))
    await expect(checkRelease(root)).rejects.toThrow()
  })

  it('拒绝私有配置绕过域名校验', async () => {
    const root = await fixture()
    await writeFile(join(root, 'project.private.config.json'), '{"setting":{"urlCheck":false}}')
    await expect(checkRelease(root)).rejects.toThrow('私有配置')
  })

  it('构建失败先清除旧正式产物，且不继续包体验证', async () => {
    const root = await fixture()
    await mkdir(join(root, 'deploy_versions/weapp'), { recursive: true })
    await writeFile(join(root, 'deploy_versions/weapp/app.js'), 'stale')
    const calls = []
    await expect(prepareRelease({ root, env: {}, run: async (command, args) => {
      calls.push([command, args])
      throw new Error('构建失败')
    } })).rejects.toThrow('构建失败')
    await expect(readFile(join(root, 'deploy_versions/weapp/app.js'))).rejects.toThrow()
    expect(calls).toHaveLength(1)
  })

  it('私有签名素材验收失败时必须在构建和上传前停止', async () => {
    const root = await fixture()
    const calls = []
    await expect(prepareRelease({ root, env: {}, run: async (command, args) => {
      calls.push(args)
      if (args.includes('verify_miniapp_signed_assets')) throw new Error('HTTP 401')
    } })).rejects.toThrow('HTTP 401')
    expect(calls.some(args => args.includes('build'))).toBe(false)
  })

  it('配置校验失败也清除旧产物', async () => {
    const root = await fixture()
    const directory = join(root, 'deploy_versions/weapp')
    await mkdir(directory, { recursive: true })
    await writeFile(join(directory, 'app.js'), 'stale')
    await expect(prepareRelease({ root, env: { TARO_APP_API_BASE_URL: 'http://localhost/api' } })).rejects.toThrow('API')
    await expect(readFile(join(directory, 'app.js'))).rejects.toThrow()
  })

  it('构建地址校验失败时停止，不执行后续检查', async () => {
    const root = await fixture()
    const source = await fixture()
    await writeFile(join(source, 'common.js'), 'const api="http://10.21.60.161:8000/api"')
    const calls = []
    await expect(prepareRelease({ root, env: {}, run: async (command, args) => {
      calls.push(args)
      if (args.includes('build')) await cp(source, join(root, 'deploy_versions/weapp'), { recursive: true })
    } })).rejects.toThrow('开发或未知')
    expect(calls.some(args => args[0] === 'scripts/check-weapp-package-size.mjs')).toBe(false)
    await expect(readFile(join(root, 'deploy_versions/weapp/app.js'))).rejects.toThrow()
  })

  it('正式构建环境与包体检查使用同一独立产物，开发目录不被覆盖', async () => {
    const root = await fixture()
    const source = await fixture()
    await mkdir(join(root, 'dist'))
    await writeFile(join(root, 'dist/app.js'), 'development')
    const calls = []
    const result = await prepareRelease({ root, env: { NODE_ENV: 'development' }, run: async (command, args, options) => {
      calls.push({ args, env: options.env })
      if (args.includes('build')) await cp(source, join(root, 'deploy_versions/weapp'), { recursive: true })
    } })
    expect(calls[0].env).toMatchObject({ NODE_ENV: 'production', TARO_APP_API_BASE_URL: api })
    expect(calls.at(-1).args).toEqual(['scripts/check-weapp-package-size.mjs', join(root, 'deploy_versions/weapp')])
    expect(result.report.apiBaseUrl).toBe(api)
    expect(await readFile(join(root, 'dist/app.js'), 'utf8')).toBe('development')
  })

  it('CI离线构建保留本地素材与包体检查，但不依赖生产签名凭据', async () => {
    const root = await fixture()
    const source = await fixture()
    const calls = []
    await prepareRelease({ root, env: {}, verifyRemote: false, run: async (command, args) => {
      calls.push(args)
      if (args.includes('build')) await cp(source, join(root, 'deploy_versions/weapp'), { recursive: true })
    } })
    expect(calls.some(args => args.includes('verify_miniapp_signed_assets'))).toBe(false)
    expect(calls.slice(0, 2)).toEqual([
      ['scripts/build-static-assets.mjs'],
      ['scripts/build-static-assets.mjs', '--check'],
    ])
    expect(calls.at(-1)[0]).toBe('scripts/check-weapp-package-size.mjs')
  })
})
