import { createHash } from 'node:crypto'
import { execFileSync, spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { cp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const contract = JSON.parse(await readFile(join(root, 'config/weapp-release.json'), 'utf8'))
const outputDirectory = 'deploy_versions/weapp'

export function resolveUploadMetadata(args = []) {
  const [version = contract.version, description = contract.description] = args
  if (![0, 2].includes(args.length) || !/^[0-9][A-Za-z0-9._-]{0,49}$/.test(version) || !description?.trim()) {
    throw new Error('用法：npm run upload:weapp，或 npm run upload:weapp -- <版本号> "版本说明"')
  }
  return { version, description }
}

export function releaseEnvironment(env) {
  for (const [key, expected, label] of [
    ['TARO_APP_API_BASE_URL', contract.apiBaseUrl, 'API'],
    ['TARO_APP_ASSET_BASE_URL', contract.assetBaseUrl, '素材'],
  ]) {
    if (env[key] !== undefined && env[key] !== expected) {
      throw new Error(`${label} 地址与正式发布配置不一致，请检查环境变量；禁止覆盖正式地址`)
    }
  }
  return {
    ...env,
    NODE_ENV: 'production',
    TARO_APP_CONFIG_ENV: 'production',
    TARO_APP_API_BASE_URL: contract.apiBaseUrl,
    TARO_APP_ASSET_BASE_URL: contract.assetBaseUrl,
  }
}

async function filesIn(directory, prefix = '') {
  const files = []
  for (const entry of await readdir(join(directory, prefix), { withFileTypes: true })) {
    const relative = join(prefix, entry.name)
    if (entry.isSymbolicLink()) throw new Error(`发布目录不允许符号链接：${relative}`)
    if (entry.isDirectory()) files.push(...await filesIn(directory, relative))
    else if (entry.isFile()) files.push(relative)
  }
  return files.sort()
}

export async function checkRelease(directory) {
  const project = JSON.parse(await readFile(join(directory, 'project.config.json'), 'utf8'))
  if (project.appid !== contract.appid) throw new Error('正式产物 AppID 不匹配')
  if (project.setting?.urlCheck !== true) throw new Error('正式产物必须开启域名校验')
  if (project.miniprogramRoot !== './') throw new Error('正式产物必须使用独立的小程序根目录')
  const files = await filesIn(directory)
  if (files.includes('project.private.config.json')) throw new Error('发布包不得携带开发者工具私有配置')
  for (const required of ['app.json', 'app.js']) {
    if (!files.includes(required)) throw new Error(`正式产物缺少 ${required}`)
  }
  const urls = new Set()
  const hashes = {}
  for (const file of files) {
    const body = await readFile(join(directory, file))
    hashes[file] = createHash('sha256').update(body).digest('hex')
    if (!file.endsWith('.js')) continue
    const text = body.toString('utf8')
    // 只检查业务 API/素材基础地址，避免将框架文档链接误判为请求地址。
    for (const match of text.matchAll(/https?:\/\/[^\s"'`<>\\]+/g)) {
      const value = match[0]
      if (/\/(?:api|static-assets)(?:[/?#]|$)/.test(value)) urls.add(value)
    }
  }
  for (const url of urls) {
    if (url !== contract.apiBaseUrl && url !== contract.assetBaseUrl) {
      throw new Error('产物含开发或未知的 API/素材地址，禁止发布')
    }
  }
  if (!urls.has(contract.apiBaseUrl)) throw new Error('产物缺少正式 API 地址')
  if (!urls.has(contract.assetBaseUrl)) throw new Error('产物缺少正式素材地址')
  return { ...contract, hashes }
}

function run(command, args, options) {
  const result = spawnSync(command, args, { ...options, stdio: 'inherit', timeout: 600_000 })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(`发布步骤失败：${command}，退出码 ${result.status}`)
}

export function validateDevtoolsResult(result, info) {
  const output = `${result.stdout || ''}\n${result.stderr || ''}`
  if (result.error || result.status !== 0 || /\[error\]|✖/.test(output)
    || !/[✔√]\s*(?:upload\b|上传)/.test(output)) {
    throw new Error('微信开发者工具未明确报告上传成功，请检查输出')
  }
  if (!Number.isSafeInteger(info?.size?.total) || info.size.total <= 0) {
    throw new Error('微信开发者工具缺少有效的本次上传结果文件')
  }
}

export async function prepareRelease({ root: projectRoot, env, run: execute = run, verifyRemote = true }) {
  const directory = join(projectRoot, outputDirectory)
  await rm(directory, { recursive: true, force: true })
  try {
    const buildEnv = releaseEnvironment(env)
    const options = { cwd: projectRoot, env: buildEnv }
    await execute(process.execPath, ['scripts/build-static-assets.mjs'], options)
    await execute(process.execPath, ['scripts/build-static-assets.mjs', '--check'], options)
    const assetVersion = (await readFile(join(projectRoot, 'output/static-assets/current-version.txt'), 'utf8')).trim()
    if (!/^[A-Za-z0-9_-]+$/.test(assetVersion)) throw new Error('固定素材版本无效')
    if (verifyRemote) {
      const localPython = join(projectRoot, '../backend/.venv/bin/python')
      await execute(env.PYTHON || (existsSync(localPython) ? localPython : 'python3'), [
        'manage.py', 'verify_miniapp_signed_assets',
        '--source-root', join(projectRoot, 'output/static-assets', assetVersion),
        '--api-base-url', contract.apiBaseUrl,
      ], { ...options, cwd: join(projectRoot, '../backend') })
    }
    await execute(process.execPath, ['node_modules/@tarojs/cli/bin/taro', 'build', '--type', 'weapp'], options)
    const configPath = join(directory, 'project.config.json')
    const project = JSON.parse(await readFile(configPath, 'utf8'))
    project.setting = { ...project.setting, urlCheck: true }
    project.miniprogramRoot = './'
    await writeFile(configPath, JSON.stringify(project, null, 2))
    const report = await checkRelease(directory)
    await execute(process.execPath, ['scripts/check-weapp-package-size.mjs', directory], options)
    return { directory, report }
  } catch (error) {
    // 失败后不留下一个看似可以上传的半成品或旧包。
    await rm(directory, { recursive: true, force: true })
    throw error
  }
}

function git(args) {
  return execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim()
}

async function main() {
  const [mode = 'build', ...args] = process.argv.slice(2)
  if (mode === 'check') {
    if (args.length > 1) throw new Error('用法：check [产物目录]')
    const report = await checkRelease(resolve(root, args[0] || outputDirectory))
    console.log(`正式产物地址与 AppID 校验通过：${report.apiBaseUrl}`)
    return
  }
  if (!['build', 'build-ci', 'upload'].includes(mode)) throw new Error('仅支持 build、build-ci、check、upload')
  if (mode !== 'upload' && args.length) throw new Error('build 不接受额外参数')
  // 不能从落后于实际发布基线的旧工作区生成“正式”预览或上传包。
  // CI 可检验浅克隆的标签提交；实际发布仍必须通过远端主分支基线检查。
  if (mode !== 'build-ci') {
    const baseline = spawnSync('git', ['merge-base', '--is-ancestor', 'origin/main', 'HEAD'], { cwd: root })
    if (baseline.status !== 0) throw new Error('当前工作区落后于远端主分支或缺少发布基线，禁止正式构建；请使用已同步的发布工作区')
  }
  await readFile(join(root, 'src/assets/signedAssetManifest.ts')).catch(() => {
    throw new Error('当前源码缺少已落地的私有素材签名流程，禁止正式构建')
  })
  const { version, description } = mode === 'upload' ? resolveUploadMetadata(args) : {}
  let commit
  if (mode === 'upload') {
    if (git(['branch', '--show-current']) !== 'main' || git(['status', '--porcelain'])) {
      throw new Error('上传必须从干净的 main 工作区执行；请先审查并提交改动')
    }
    commit = git(['rev-parse', 'HEAD'])
  }
  await mkdir(join(root, 'deploy_versions'), { recursive: true })
  const lock = join(root, 'deploy_versions/.weapp-release-lock')
  await mkdir(lock).catch(() => { throw new Error('已有正式构建/上传进行中；请勿并发执行') })
  try {
    if (mode === 'upload') run('npm', ['test'], { cwd: root, env: process.env })
    const { directory, report } = await prepareRelease({ root, env: process.env, verifyRemote: mode !== 'build-ci' })
    if (mode !== 'upload') {
      console.log(`${mode === 'build-ci' ? 'CI构建通过（未执行线上私有素材验收）' : '正式构建及门禁通过'}：${directory}\nAPI：${report.apiBaseUrl}\n素材：${report.assetBaseUrl}`)
      return
    }
    if (git(['status', '--porcelain']) || git(['rev-parse', 'HEAD']) !== commit) {
      throw new Error('构建期间源码发生变化，禁止上传')
    }
    const versionRoot = join(root, 'deploy_versions', version)
    await mkdir(versionRoot) // 已存在的版本不能覆盖。
    const uploadRoot = join(versionRoot, 'miniprogram')
    await cp(directory, uploadRoot, { recursive: true, errorOnExist: true, force: false })
    const snapshot = await checkRelease(uploadRoot)
    if (JSON.stringify(snapshot.hashes) !== JSON.stringify(report.hashes)) throw new Error('发布快照与已验证产物不一致')
    const receipt = { ...snapshot, version, description, commit, createdAt: new Date().toISOString(), status: 'prepared' }
    const receiptPath = join(versionRoot, 'release.json')
    await writeFile(receiptPath, JSON.stringify(receipt, null, 2))
    const infoPath = join(versionRoot, 'wechat-upload.json')
    const result = spawnSync(process.env.WECHAT_DEVTOOLS_CLI || '/Applications/wechatwebdevtools.app/Contents/MacOS/cli', [
      'upload', '--project', uploadRoot, '--version', version, '--desc', description, '--lang', 'zh',
      '--info-output', infoPath,
    ], { cwd: root, env: process.env, encoding: 'utf8', timeout: 600_000, maxBuffer: 10 * 1024 * 1024 })
    process.stdout.write(result.stdout || '')
    process.stderr.write(result.stderr || '')
    const info = await readFile(infoPath, 'utf8').then(JSON.parse).catch(() => null)
    validateDevtoolsResult(result, info)
    receipt.status = 'cli-upload-succeeded-awaiting-platform-and-device-verification'
    await writeFile(receiptPath, JSON.stringify(receipt, null, 2))
    console.log(`CLI 上传成功，记录：${receiptPath}\n仍需核对微信后台版本、合法域名，并在关闭调试的真机上验证登录。`)
  } finally {
    await rm(lock, { recursive: true, force: true })
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1 })
}
