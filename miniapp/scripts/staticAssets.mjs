import { createHash, randomUUID } from 'node:crypto'
import { access, mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import sharp from 'sharp'

const GAME_IMAGE_KEYS = [
  'pattern_sun', 'pattern_coconut', 'pattern_boat', 'pattern_lighthouse', 'pattern_shell',
  'category_pineapple', 'category_bird', 'category_train', 'category_drum', 'category_phone',
  'sound_bird', 'sound_train', 'sound_phone', 'sound_laugh', 'sound_drum',
  'puzzle_beach', 'puzzle_garden', 'puzzle_lighthouse',
]

const MOTION_AUDIO_KEYS = [
  'motion-aerobic-high-knee',
  'motion-balance-sit-stand',
  'motion-resistance-row',
  'motion-resistance-leg-kickback',
  'motion-resistance-shoulder-press',
]

/**
 * @typedef {{
 *   kind: 'game-image' | 'motion-instruction-audio',
 *   key: string,
 *   relativePath: string,
 *   contentType: string,
 *   sizeBytes: number,
 *   sha256: string,
 *   width?: number,
 *   height?: number,
 * }} StaticAssetEntry
 */

/**
 * @typedef {{ assetVersion: string, manifestPath: string, entries: StaticAssetEntry[] }} StaticAssetBuildResult
 */

function sha256(content) {
  return createHash('sha256').update(content).digest('hex')
}

function assetVersionFor(entries) {
  const source = entries
    .map((entry) => `${entry.kind}:${entry.key}:${entry.sha256}`)
    .sort()
    .join('\n')

  return `v-${sha256(source).slice(0, 12)}`
}

function gameImageManifest(entries) {
  const paths = entries
    .filter((entry) => entry.kind === 'game-image')
    .map((entry) => `  ${entry.key}: '${entry.relativePath}',`)
    .join('\n')

  return `// 此文件由 scripts/build-static-assets.mjs 自动生成，请勿手动修改。\nexport const GAME_IMAGE_ASSET_PATHS = {\n${paths}\n} as const\n\nexport type GeneratedGameImageKey = keyof typeof GAME_IMAGE_ASSET_PATHS\n`
}

function motionAudioManifest(entries) {
  const paths = entries
    .filter((entry) => entry.kind === 'motion-instruction-audio')
    .map((entry) => `  '${entry.key}': '${entry.relativePath}',`)
    .join('\n')

  return `// 此文件由 scripts/build-static-assets.mjs 自动生成，请勿手动修改。\nimport type { MotionSourceKey } from './catalog'\n\nexport const MOTION_INSTRUCTION_AUDIO_ASSET_PATHS: Record<MotionSourceKey, string> = {\n${paths}\n}\n`
}

async function exists(path) {
  try {
    await access(path)
    return true
  } catch {
    return false
  }
}

async function writeAtomically(path, content) {
  await mkdir(dirname(path), { recursive: true })
  const temporaryPath = `${path}.${randomUUID()}.tmp`
  await writeFile(temporaryPath, content)
  await rename(temporaryPath, path)
}

async function assertFileEquals(path, expected) {
  let actual

  try {
    actual = await readFile(path)
  } catch {
    throw new Error(`Static asset output drift: missing ${path}`)
  }

  if (!actual.equals(Buffer.isBuffer(expected) ? expected : Buffer.from(expected))) {
    throw new Error(`Static asset output drift: ${path}`)
  }
}

async function buildEntries(projectRoot) {
  const images = await Promise.all(GAME_IMAGE_KEYS.map(async (key) => {
    const size = key.startsWith('puzzle_') ? 384 : 256
    const sourcePath = join(projectRoot, 'resources', 'game-images', 'source', `${key}.png`)
    const content = await sharp(sourcePath).resize(size, size).webp({ quality: 85 }).toBuffer()

    return {
      kind: 'game-image',
      key,
      contentType: 'image/webp',
      sizeBytes: content.length,
      sha256: sha256(content),
      width: size,
      height: size,
      content,
    }
  }))

  const audios = await Promise.all(MOTION_AUDIO_KEYS.map(async (key) => {
    const content = await readFile(join(projectRoot, 'resources', 'motion-instruction-audio', 'source', `${key}.m4a`))

    return {
      kind: 'motion-instruction-audio',
      key,
      contentType: 'audio/mp4',
      sizeBytes: content.length,
      sha256: sha256(content),
      content,
    }
  }))

  return [...images, ...audios]
}

function publicEntry(entry, assetVersion) {
  const extension = entry.kind === 'game-image' ? 'webp' : 'm4a'
  const relativePath = `${assetVersion}/${entry.key}.${entry.sha256.slice(0, 12)}.${extension}`
  const { content, ...publicFields } = entry

  return { ...publicFields, relativePath }
}

async function writeVersionDirectory(temporaryRoot, assetVersion, entries, manifest) {
  await mkdir(join(temporaryRoot, assetVersion), { recursive: true })
  for (const entry of entries) {
    await writeFile(join(temporaryRoot, entry.relativePath), entry.content)
  }
  await writeFile(join(temporaryRoot, assetVersion, 'manifest.json'), manifest)
}

async function assertVersionDirectory(versionDirectory, entries, manifest) {
  for (const entry of entries) {
    await assertFileEquals(join(dirname(versionDirectory), entry.relativePath), entry.content)
  }
  await assertFileEquals(join(versionDirectory, 'manifest.json'), manifest)
}

/**
 * 构建静态素材，并生成供 CDN 上传和运行时接线使用的确定性清单。
 *
 * @param {{ projectRoot: string, outputRoot: string, check: boolean }} options
 * @returns {Promise<StaticAssetBuildResult>}
 */
export async function buildStaticAssets({ projectRoot, outputRoot, check }) {
  const buildEntriesWithContent = await buildEntries(projectRoot)
  const assetVersion = assetVersionFor(buildEntriesWithContent)
  const entriesWithContent = buildEntriesWithContent.map((entry) => ({
    ...entry,
    relativePath: publicEntry(entry, assetVersion).relativePath,
  }))
  const entries = entriesWithContent.map(({ content, ...entry }) => entry)
  const manifest = `${JSON.stringify({ assetVersion, entries }, null, 2)}\n`
  const versionDirectory = join(outputRoot, assetVersion)
  const manifestPath = join(versionDirectory, 'manifest.json')
  const currentVersionPath = join(outputRoot, 'current-version.txt')
  const expectedCurrentVersion = assetVersion
  const generatedFiles = [
    [join(projectRoot, 'src', 'pages', 'game-session', 'gameImageAssetManifest.generated.ts'), gameImageManifest(entries)],
    [join(projectRoot, 'src', 'features', 'motion-training', 'instructionAudioAssetManifest.generated.ts'), motionAudioManifest(entries)],
  ]

  if (check) {
    await assertVersionDirectory(versionDirectory, entriesWithContent, manifest)
    await assertFileEquals(currentVersionPath, expectedCurrentVersion)
    await Promise.all(generatedFiles.map(([path, content]) => assertFileEquals(path, content)))
    return { assetVersion, manifestPath, entries }
  }

  await mkdir(outputRoot, { recursive: true })
  if (await exists(versionDirectory)) {
    await assertVersionDirectory(versionDirectory, entriesWithContent, manifest)
  } else {
    const temporaryRoot = join(outputRoot, `.tmp-${randomUUID()}`)
    await mkdir(temporaryRoot, { recursive: true })
    try {
      await writeVersionDirectory(temporaryRoot, assetVersion, entriesWithContent, manifest)
      await rename(join(temporaryRoot, assetVersion), versionDirectory)
    } finally {
      await rm(temporaryRoot, { recursive: true, force: true })
    }
  }

  await writeAtomically(currentVersionPath, expectedCurrentVersion)
  await Promise.all(generatedFiles.map(([path, content]) => writeAtomically(path, content)))

  return { assetVersion, manifestPath, entries }
}
