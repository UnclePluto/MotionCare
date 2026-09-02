import { mkdtemp, mkdir, open, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import { assertPackageBudgets, measureWeappPackages } from './weappPackageSize.mjs'

const temporaryRoots = []

afterEach(async () => {
  await Promise.all(temporaryRoots.splice(0).map((root) => rm(root, { force: true, recursive: true })))
})

async function createDistFixture() {
  const distRoot = await mkdtemp(join(tmpdir(), 'motioncare-weapp-package-'))
  temporaryRoots.push(distRoot)
  return distRoot
}

async function writeSizedFile(distRoot, relativePath, bytes) {
  const absolutePath = join(distRoot, relativePath)
  await mkdir(dirname(absolutePath), { recursive: true })
  const file = await open(absolutePath, 'w')
  try {
    await file.truncate(bytes)
  } finally {
    await file.close()
  }
}

async function createClassifiedFixture(configKey = 'subPackages') {
  const distRoot = await createDistFixture()
  await writeSizedFile(distRoot, 'project.config.json', 100)
  await writeSizedFile(distRoot, 'pages/index/index.js', 300)
  await writeSizedFile(distRoot, 'pages/game-session/index.js', 500)
  await writeSizedFile(distRoot, 'pages/game-session/assets/audio/correct.m4a', 400)
  await writeSizedFile(distRoot, 'features/fake/index.js', 200)

  return {
    appConfig: {
      [configKey]: [
        { root: 'pages/game-session', pages: ['index'] },
        { root: 'features/fake', pages: ['index'] },
      ],
    },
    distRoot,
  }
}

function projectBudgets(overrides = {}) {
  return {
    hardPackage: 2 * 1024 * 1024,
    hardTotal: 20 * 1024 * 1024,
    main: 1200 * 1024,
    subpackage: 1500 * 1024,
    ...overrides,
  }
}

describe('measureWeappPackages', () => {
  it('classifies each file into the main package or exactly one subpackage', async () => {
    const { appConfig, distRoot } = await createClassifiedFixture()

    const report = await measureWeappPackages({ appConfig, distRoot })

    expect(report.main.bytes).toBe(400)
    expect(report.subpackages['pages/game-session'].bytes).toBe(900)
    expect(report.subpackages['features/fake'].bytes).toBe(200)
    expect(report.total.bytes).toBe(1500)
    expect(report.main.files.map((file) => file.path)).toEqual([
      'pages/index/index.js',
      'project.config.json',
    ])
    expect(() => assertPackageBudgets(report, projectBudgets())).not.toThrow()
  })

  it('also reads the lowercase subpackages app config form', async () => {
    const { appConfig, distRoot } = await createClassifiedFixture('subpackages')

    const report = await measureWeappPackages({ appConfig, distRoot })

    expect(report.main.bytes).toBe(400)
    expect(report.subpackages['pages/game-session'].bytes).toBe(900)
    expect(report.total.bytes).toBe(1500)
  })
})

describe('assertPackageBudgets', () => {
  it('rejects a main package above its soft budget with actionable details', async () => {
    const { appConfig, distRoot } = await createClassifiedFixture()
    const report = await measureWeappPackages({ appConfig, distRoot })

    expect(() => assertPackageBudgets(report, projectBudgets({ main: 399 }))).toThrow(
      /主包 \(main\).*实际 400 字节.*阈值 399 字节.*pages\/index\/index\.js.*project\.config\.json/s,
    )
  })

  it('rejects any subpackage above the shared soft budget', async () => {
    const { appConfig, distRoot } = await createClassifiedFixture()
    const report = await measureWeappPackages({ appConfig, distRoot })

    expect(() => assertPackageBudgets(report, projectBudgets({ subpackage: 899 }))).toThrow(
      /分包 \(pages\/game-session\).*实际 900 字节.*阈值 899 字节.*index\.js.*correct\.m4a/s,
    )
  })

  it('rejects the game package above its stricter package-specific soft budget', async () => {
    const { appConfig, distRoot } = await createClassifiedFixture()
    const report = await measureWeappPackages({ appConfig, distRoot })

    expect(() =>
      assertPackageBudgets(
        report,
        projectBudgets({
          subpackageOverrides: { 'pages/game-session': 899 },
        }),
      ),
    ).toThrow(/分包 \(pages\/game-session\).*实际 900 字节.*阈值 899 字节/s)
  })

  it('rejects a package above the 2 MiB hard limit before evaluating soft budgets', async () => {
    const distRoot = await createDistFixture()
    await writeSizedFile(distRoot, 'pages/game-session/index.js', 2 * 1024 * 1024 + 1)
    const report = await measureWeappPackages({
      appConfig: { subPackages: [{ root: 'pages/game-session', pages: ['index'] }] },
      distRoot,
    })

    expect(() =>
      assertPackageBudgets(
        report,
        projectBudgets({ main: 10 * 1024 * 1024, subpackage: 10 * 1024 * 1024 }),
      ),
    ).toThrow(
      /分包 \(pages\/game-session\).*实际 2097153 字节.*阈值 2097152 字节.*pages\/game-session\/index\.js/s,
    )
  })

  it('rejects total output above the 20 MiB hard limit while every package remains below 2 MiB', async () => {
    const distRoot = await createDistFixture()
    const subPackages = []
    for (let index = 0; index < 11; index += 1) {
      const root = `features/fake-${index}`
      subPackages.push({ root, pages: ['index'] })
      await writeSizedFile(distRoot, `${root}/index.js`, 1906502)
    }
    const report = await measureWeappPackages({ appConfig: { subPackages }, distRoot })

    expect(() =>
      assertPackageBudgets(
        report,
        projectBudgets({ main: 30 * 1024 * 1024, subpackage: 30 * 1024 * 1024 }),
      ),
    ).toThrow(/全部代码包 \(total\).*实际 20971522 字节.*阈值 20971520 字节/s)
  })

  it.each([
    'pages/game-session/assets/images',
    'features/motion-training/assets/audio/instructions',
  ])('rejects the forbidden output directory %s even when it is empty', async (forbiddenDirectory) => {
    const distRoot = await createDistFixture()
    await mkdir(join(distRoot, forbiddenDirectory), { recursive: true })
    const report = await measureWeappPackages({ appConfig: {}, distRoot })

    expect(() =>
      assertPackageBudgets(
        report,
        projectBudgets({
          forbiddenDirectories: [forbiddenDirectory],
        }),
      ),
    ).toThrow(new RegExp(`禁止目录.*${forbiddenDirectory.replaceAll('/', '\\/')}`))
  })

  it('shows only the ten largest files in descending byte order', async () => {
    const distRoot = await createDistFixture()
    for (let bytes = 1; bytes <= 12; bytes += 1) {
      await writeSizedFile(distRoot, `top-${String(bytes).padStart(2, '0')}.bin`, bytes)
    }
    const report = await measureWeappPackages({ appConfig: {}, distRoot })

    let message = ''
    try {
      assertPackageBudgets(report, projectBudgets({ main: 0 }))
    } catch (error) {
      message = error.message
    }

    expect(message).toMatch(/实际 78 字节.*阈值 0 字节/s)
    const listedFiles = message.match(/^- top-\d+\.bin: \d+ 字节$/gm) ?? []
    expect(listedFiles).toHaveLength(10)
    expect(listedFiles[0]).toBe('- top-12.bin: 12 字节')
    expect(listedFiles[9]).toBe('- top-03.bin: 3 字节')
    expect(message).not.toContain('top-02.bin')
    expect(message).not.toContain('top-01.bin')
  })
})
