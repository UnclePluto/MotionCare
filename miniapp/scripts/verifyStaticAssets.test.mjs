import { createHash } from 'node:crypto'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { verifyStaticAssets } from './verify-static-assets.mjs'


let fixtureRoot = ''

const canonicalImageKeys = [
  'pattern_sun', 'pattern_coconut', 'pattern_boat', 'pattern_lighthouse', 'pattern_shell',
  'category_pineapple', 'category_bird', 'category_train', 'category_drum', 'category_phone',
  'sound_bird', 'sound_train', 'sound_phone', 'sound_laugh', 'sound_drum',
  'puzzle_beach', 'puzzle_garden', 'puzzle_lighthouse',
]

const canonicalAudioKeys = [
  'motion-aerobic-high-knee',
  'motion-balance-sit-stand',
  'motion-resistance-row',
  'motion-resistance-leg-kickback',
  'motion-resistance-shoulder-press',
]

const canonicalKeys = [...canonicalImageKeys, ...canonicalAudioKeys]

function sha256(body) {
  return createHash('sha256').update(body).digest('hex')
}

function buildFixtureEntries() {
  return canonicalKeys.map((key, index) => {
    const isAudio = canonicalAudioKeys.includes(key)
    const body = Buffer.from(`public-static-asset-${index}`)
    const suffix = isAudio ? 'm4a' : 'webp'
    return {
      kind: isAudio ? 'motion-instruction-audio' : 'game-image',
      key,
      contentType: isAudio ? 'audio/mp4' : 'image/webp',
      sizeBytes: body.byteLength,
      sha256: sha256(body),
      relativePath: `v-fixture/${key}.${sha256(body).slice(0, 12)}.${suffix}`,
      body,
    }
  })
}

async function writeManifest(entries) {
  const manifestPath = join(fixtureRoot, 'manifest.json')
  await writeFile(manifestPath, JSON.stringify({
    assetVersion: 'v-fixture',
    entries: entries.map(({ body: _body, ...entry }) => entry),
  }))
  return manifestPath
}

function responseFor(entry, overrides = {}) {
  const body = overrides.body ?? entry.body
  const headers = {
    'content-type': entry.contentType,
    'content-length': String(body.byteLength),
    'cache-control': 'public, max-age=31536000, immutable',
    ...overrides.headers,
  }
  return new Response(body, { status: overrides.status ?? 200, headers })
}

beforeEach(async () => {
  fixtureRoot = await mkdtemp(join(tmpdir(), 'motioncare-cdn-verifier-'))
})

afterEach(async () => {
  if (fixtureRoot) await rm(fixtureRoot, { recursive: true, force: true })
})

describe('verifyStaticAssets', () => {
  it('verifies all 23 public objects and returns their canonical URLs', async () => {
    const entries = buildFixtureEntries()
    const manifestPath = await writeManifest(entries)
    const byPath = new Map(entries.map((entry) => [entry.relativePath, entry]))
    const fetchImpl = async (url) => {
      const relativePath = new URL(url).pathname.replace('/motioncare/static-assets/', '')
      return responseFor(byPath.get(relativePath))
    }

    const verified = await verifyStaticAssets({
      manifestPath,
      baseUrl: 'https://cdn.example.test/motioncare/static-assets',
      fetchImpl,
    })

    expect(verified).toHaveLength(23)
    expect(verified[0].url).toBe(
      'https://cdn.example.test/motioncare/static-assets/v-fixture/pattern_sun.b6793b4f9525.webp',
    )
  })

  it('requires exactly 23 manifest entries', async () => {
    const entries = buildFixtureEntries().slice(0, 22)
    const manifestPath = await writeManifest(entries)

    await expect(verifyStaticAssets({
      manifestPath,
      baseUrl: 'https://cdn.example.test/motioncare/static-assets',
      fetchImpl: async () => responseFor(entries[0]),
    })).rejects.toThrow(/23/)
  })

  it('rejects a manifest kind whose media type belongs to the other asset class', async () => {
    const entries = buildFixtureEntries()
    entries[0].contentType = 'audio/mp4'
    entries[0].kind = 'motion-instruction-audio'
    const manifestPath = await writeManifest(entries)
    let responseIndex = 0

    await expect(verifyStaticAssets({
      manifestPath,
      baseUrl: 'https://cdn.example.test/motioncare/static-assets',
      fetchImpl: async () => responseFor(entries[responseIndex++]),
    })).rejects.toThrow(/媒体类型/)
  })

  it('rejects a duplicate canonical key even when the entry count stays 23', async () => {
    const entries = buildFixtureEntries()
    entries.at(-1).key = entries[0].key
    const manifestPath = await writeManifest(entries)
    let responseIndex = 0

    await expect(verifyStaticAssets({
      manifestPath,
      baseUrl: 'https://cdn.example.test/motioncare/static-assets',
      fetchImpl: async () => responseFor(entries[responseIndex++]),
    })).rejects.toThrow(/23 项规范素材/)
  })

  it('rejects an unknown key even when the entry count stays 23', async () => {
    const entries = buildFixtureEntries()
    entries.at(-1).key = 'unknown-static-asset'
    const manifestPath = await writeManifest(entries)
    let responseIndex = 0

    await expect(verifyStaticAssets({
      manifestPath,
      baseUrl: 'https://cdn.example.test/motioncare/static-assets',
      fetchImpl: async () => responseFor(entries[responseIndex++]),
    })).rejects.toThrow(/23 项规范素材/)
  })

  it.each([
    ['extra directory', ({ version, key, prefix }) => `${version}/nested/${key}.${prefix}.webp`],
    ['wrong business key', ({ version, prefix }) => `${version}/wrong-key.${prefix}.webp`],
    ['extra filename segment', ({ version, key, prefix }) => `${version}/${key}.extra.${prefix}.webp`],
    ['wrong hash prefix', ({ version, key, prefix }) => `${version}/${key}.000000000000.${prefix}.webp`],
    ['wrong extension', ({ version, key, prefix }) => `${version}/${key}.${prefix}.m4a`],
    ['absolute path', ({ key, prefix }) => `/tmp/${key}.${prefix}.webp`],
    ['literal current segment', ({ version, key, prefix }) => `${version}/./${key}.${prefix}.webp`],
    ['encoded current segment', ({ version, key, prefix }) => `${version}/%2e/${key}.${prefix}.webp`],
    ['double-encoded current segment', ({ version, key, prefix }) => `${version}/%252e/${key}.${prefix}.webp`],
    ['literal parent segment', ({ version, key, prefix }) => `${version}/../${key}.${prefix}.webp`],
    ['encoded parent segment', ({ version, key, prefix }) => `${version}/%2e%2e/${key}.${prefix}.webp`],
    ['double-encoded parent segment', ({ version, key, prefix }) => `${version}/%252e%252e/${key}.${prefix}.webp`],
    ['encoded slash', ({ version, key, prefix }) => `${version}/${key}%2fescape.${prefix}.webp`],
    ['double-encoded slash', ({ version, key, prefix }) => `${version}/${key}%252fescape.${prefix}.webp`],
    ['invalid percent escape', ({ version, key, prefix }) => `${version}/${key}%ZZ.${prefix}.webp`],
  ])('rejects a non-canonical path: %s', async (_name, buildPath) => {
    const entries = buildFixtureEntries()
    const first = entries[0]
    first.relativePath = buildPath({
      version: 'v-fixture',
      key: first.key,
      prefix: first.sha256.slice(0, 12),
    })
    const manifestPath = await writeManifest(entries)
    let responseIndex = 0

    await expect(verifyStaticAssets({
      manifestPath,
      baseUrl: 'https://cdn.example.test/motioncare/static-assets',
      fetchImpl: async () => responseFor(entries[responseIndex++]),
    })).rejects.toThrow(/规范路径/)
  })

  it.each([
    ['non-200 response', { status: 404 }, /HTTP 200/],
    ['wrong response byte count', { body: Buffer.from('short') }, /字节数/],
    ['wrong Content-Length', { headers: { 'content-length': '999' } }, /Content-Length/],
    ['wrong SHA-256', { body: Buffer.from('public-static-asset-X') }, /SHA-256/],
    ['wrong media type', { headers: { 'content-type': 'image/png' } }, /媒体类型/],
    ['missing public', { headers: { 'cache-control': 'max-age=31536000, immutable' } }, /public/],
    ['private cache', { headers: { 'cache-control': 'public, private, max-age=31536000, immutable' } }, /private/],
    ['private field cache', { headers: { 'cache-control': 'public, private="Set-Cookie", max-age=31536000, immutable' } }, /private/],
    ['no-store cache', { headers: { 'cache-control': 'public, no-store, max-age=31536000, immutable' } }, /no-store/],
    ['no-cache cache', { headers: { 'cache-control': 'public, no-cache, max-age=31536000, immutable' } }, /no-cache/],
    ['missing max-age', { headers: { 'cache-control': 'public, immutable' } }, /max-age=31536000/],
    ['missing immutable', { headers: { 'cache-control': 'public, max-age=31536000' } }, /immutable/],
  ])('rejects %s', async (_name, override, expectedMessage) => {
    const entries = buildFixtureEntries()
    const manifestPath = await writeManifest(entries)
    const first = entries[0]
    const fetchImpl = async (url) => {
      const relativePath = new URL(url).pathname.replace('/motioncare/static-assets/', '')
      const entry = entries.find((candidate) => candidate.relativePath === relativePath)
      return responseFor(entry, entry === first ? override : {})
    }

    await expect(verifyStaticAssets({
      manifestPath,
      baseUrl: 'https://cdn.example.test/motioncare/static-assets',
      fetchImpl,
    })).rejects.toThrow(expectedMessage)
  })

  it('rejects a non-HTTPS public base URL', async () => {
    const entries = buildFixtureEntries()
    const manifestPath = await writeManifest(entries)

    await expect(verifyStaticAssets({
      manifestPath,
      baseUrl: 'http://cdn.example.test/motioncare/static-assets',
      fetchImpl: async () => responseFor(entries[0]),
    })).rejects.toThrow(/HTTPS/)
  })
})
