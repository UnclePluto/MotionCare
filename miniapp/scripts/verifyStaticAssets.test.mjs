import { createHash } from 'node:crypto'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { verifyStaticAssets } from './verify-static-assets.mjs'


let fixtureRoot = ''

function sha256(body) {
  return createHash('sha256').update(body).digest('hex')
}

function buildFixtureEntries() {
  return Array.from({ length: 23 }, (_, index) => {
    const isAudio = index >= 18
    const body = Buffer.from(`public-static-asset-${index}`)
    const suffix = isAudio ? 'm4a' : 'webp'
    return {
      kind: isAudio ? 'motion-instruction-audio' : 'game-image',
      key: `asset-${index}`,
      contentType: isAudio ? 'audio/mp4' : 'image/webp',
      sizeBytes: body.byteLength,
      sha256: sha256(body),
      relativePath: `v-fixture/asset-${index}.${sha256(body).slice(0, 12)}.${suffix}`,
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
      'https://cdn.example.test/motioncare/static-assets/v-fixture/asset-0.b6793b4f9525.webp',
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
    const manifestPath = await writeManifest(entries)

    await expect(verifyStaticAssets({
      manifestPath,
      baseUrl: 'https://cdn.example.test/motioncare/static-assets',
      fetchImpl: async () => responseFor(entries[0]),
    })).rejects.toThrow(/媒体类型/)
  })

  it.each([
    ['non-200 response', { status: 404 }, /HTTP 200/],
    ['wrong response byte count', { body: Buffer.from('short') }, /字节数/],
    ['wrong Content-Length', { headers: { 'content-length': '999' } }, /Content-Length/],
    ['wrong SHA-256', { body: Buffer.from('public-static-asset-X') }, /SHA-256/],
    ['wrong media type', { headers: { 'content-type': 'image/png' } }, /媒体类型/],
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
