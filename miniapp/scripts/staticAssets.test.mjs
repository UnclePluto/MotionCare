import { createHash } from 'node:crypto'
import { cp, mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { basename, join } from 'node:path'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { buildStaticAssets } from './staticAssets.mjs'

const expectedGameImageKeys = [
  'pattern_sun', 'pattern_coconut', 'pattern_boat', 'pattern_lighthouse', 'pattern_shell',
  'category_pineapple', 'category_bird', 'category_train', 'category_drum', 'category_phone',
  'sound_bird', 'sound_train', 'sound_phone', 'sound_laugh', 'sound_drum',
  'puzzle_beach', 'puzzle_garden', 'puzzle_lighthouse',
]

const expectedMotionAudioKeys = [
  'motion-aerobic-high-knee',
  'motion-balance-sit-stand',
  'motion-resistance-row',
  'motion-resistance-leg-kickback',
  'motion-resistance-shoulder-press',
]

const expectedMotionAudioSha256 = {
  'motion-aerobic-high-knee': 'd5650f7b5bee482aa32953e1f06e974cea6d97aa18bc007c5fbc7b5ec9302674',
  'motion-balance-sit-stand': 'b6e32e46d40466ded6a451aafab13dc3e6ca746e5dd53643055aa00168f66e24',
  'motion-resistance-row': '4e47b657633bf1527d68d15d7c687626ccedaa1c27a9402ae258eee6aa7a64cf',
  'motion-resistance-leg-kickback': '725ea66457c3ff7fac511a7fc3713eb2848f45c6fc96c070029fbb70342882e1',
  'motion-resistance-shoulder-press': '3fed2a4235efa9343b68fbcb30d453cfb763c63f8b145bc6308fad7773382809',
}

const repositoryRoot = join(import.meta.dirname, '..')
let fixtureRoot = ''

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex')
}

function fixtureOptions() {
  return {
    projectRoot: fixtureRoot,
    outputRoot: join(fixtureRoot, 'output', 'static-assets'),
    backendManifestRoot: join(fixtureRoot, 'backend-manifests'),
    check: false,
  }
}

beforeAll(async () => {
  fixtureRoot = await mkdtemp(join(tmpdir(), 'motioncare-static-assets-'))
  await Promise.all([
    cp(join(repositoryRoot, 'resources', 'game-images'), join(fixtureRoot, 'resources', 'game-images'), { recursive: true }),
    cp(join(repositoryRoot, 'resources', 'motion-instruction-audio'), join(fixtureRoot, 'resources', 'motion-instruction-audio'), { recursive: true }),
  ])
})

afterAll(async () => {
  if (fixtureRoot) await rm(fixtureRoot, { recursive: true, force: true })
})

describe('buildStaticAssets', () => {
  it('builds 18 images and 5 unchanged motion audios with a deterministic version', async () => {
    const first = await buildStaticAssets(fixtureOptions())
    const second = await buildStaticAssets(fixtureOptions())

    expect(first.assetVersion).toMatch(/^v-[a-f0-9]{12}$/)
    expect(second.assetVersion).toBe(first.assetVersion)
    expect(first.entries.filter((item) => item.kind === 'game-image').map((item) => item.key)).toEqual(expectedGameImageKeys)
    expect(first.entries.filter((item) => item.kind === 'motion-instruction-audio').map((item) => item.key)).toEqual(expectedMotionAudioKeys)
  })

  it('resizes card images and puzzle images to their fixed dimensions', async () => {
    const result = await buildStaticAssets(fixtureOptions())
    const { default: sharp } = await import('sharp')

    for (const entry of result.entries.filter((item) => item.kind === 'game-image')) {
      const metadata = await sharp(join(fixtureOptions().outputRoot, entry.relativePath)).metadata()
      const expectedSize = entry.key.startsWith('puzzle_') ? 384 : 256

      expect(metadata.width).toBe(expectedSize)
      expect(metadata.height).toBe(expectedSize)
      expect(entry.width).toBe(expectedSize)
      expect(entry.height).toBe(expectedSize)
    }
  })

  it('copies each motion audio byte-for-byte and includes every output hash in its filename', async () => {
    const result = await buildStaticAssets(fixtureOptions())

    for (const entry of result.entries) {
      const output = await readFile(join(fixtureOptions().outputRoot, entry.relativePath))

      expect(sha256(output)).toBe(entry.sha256)
      expect(basename(entry.relativePath)).toContain(entry.sha256.slice(0, 12))

      if (entry.kind === 'motion-instruction-audio') {
        const source = await readFile(join(fixtureRoot, 'resources', 'motion-instruction-audio', 'source', `${entry.key}.m4a`))
        expect(sha256(output)).toBe(sha256(source))
        expect(entry.sha256).toBe(expectedMotionAudioSha256[entry.key])
        expect(entry.contentType).toBe('audio/mp4')
        expect('width' in entry).toBe(false)
        expect('height' in entry).toBe(false)
      }
    }
  })

  it('rejects check mode when a generated output drifts', async () => {
    const result = await buildStaticAssets(fixtureOptions())
    const outputPath = join(fixtureOptions().outputRoot, result.entries[0].relativePath)
    const original = await readFile(outputPath)

    try {
      await writeFile(outputPath, 'drift')
      await expect(buildStaticAssets({ ...fixtureOptions(), check: true })).rejects.toThrow(/drift/i)
      expect((await stat(outputPath)).size).toBe(Buffer.byteLength('drift'))
    } finally {
      await writeFile(outputPath, original)
    }
  })

  it('writes the canonical manifest, current version, and separate TypeScript path maps', async () => {
    const result = await buildStaticAssets(fixtureOptions())
    const manifest = JSON.parse(await readFile(result.manifestPath, 'utf8'))
    const currentVersion = await readFile(join(fixtureOptions().outputRoot, 'current-version.txt'), 'utf8')
    const gameMap = await readFile(join(fixtureRoot, 'src', 'pages', 'game-session', 'gameImageAssetManifest.generated.ts'), 'utf8')
    const audioMap = await readFile(join(fixtureRoot, 'src', 'features', 'motion-training', 'instructionAudioAssetManifest.generated.ts'), 'utf8')

    expect(manifest).toEqual({ assetVersion: result.assetVersion, entries: result.entries })
    expect(currentVersion).toBe(result.assetVersion)
    expect(gameMap).toContain('export const GAME_IMAGE_ASSET_PATHS')
    expect(gameMap).toContain('export type GeneratedGameImageKey = keyof typeof GAME_IMAGE_ASSET_PATHS')
    expect(audioMap).toContain('export const MOTION_INSTRUCTION_AUDIO_ASSET_PATHS: Record<MotionSourceKey, string>')

    for (const entry of result.entries.filter((item) => item.kind === 'game-image')) {
      expect(gameMap).toContain(entry.relativePath)
      expect(audioMap).not.toContain(entry.key)
    }

    for (const entry of result.entries.filter((item) => item.kind === 'motion-instruction-audio')) {
      expect(audioMap).toContain(entry.relativePath)
      expect(gameMap).not.toContain(entry.key)
    }
  })

  it('生成前后端一致的完整清单且拒绝覆盖后端版本', async () => {
    const options = fixtureOptions()
    const result = await buildStaticAssets(options)
    const serverPath = join(options.backendManifestRoot, result.assetVersion + '.json')
    const original = await readFile(serverPath, 'utf8')
    expect(JSON.parse(original)).toEqual({
      assetVersion: result.assetVersion, entries: result.entries,
    })
    const clientText = await readFile(
      join(fixtureRoot, 'src/assets/staticAssetManifest.generated.ts'), 'utf8',
    )
    expect(clientText).toContain(JSON.stringify(result.assetVersion))
    for (const entry of result.entries) expect(clientText).toContain(entry.sha256)
    try {
      await writeFile(serverPath, '{"assetVersion":"corrupted","entries":[]}')
      await expect(buildStaticAssets(options)).rejects.toThrow(/drift/i)
      await expect(buildStaticAssets({ ...options, check: true })).rejects.toThrow(/drift/i)
    } finally {
      await writeFile(serverPath, original)
    }
  })

  it('rejects a motion audio source whose SHA-256 differs from the accepted recording', async () => {
    const key = 'motion-resistance-row'
    await writeFile(join(fixtureRoot, 'resources', 'motion-instruction-audio', 'source', `${key}.m4a`), 'replaced audio')

    await expect(buildStaticAssets(fixtureOptions())).rejects.toThrow(new RegExp(`${key}.*SHA-256`, 'i'))
  })
})
