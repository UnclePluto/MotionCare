import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { buildStaticAssets } from './staticAssets.mjs'

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)))
const check = process.argv.includes('--check')

try {
  const result = await buildStaticAssets({
    projectRoot,
    outputRoot: join(projectRoot, 'output', 'static-assets'),
    backendManifestRoot: join(projectRoot, '..', 'backend', 'apps', 'common', 'miniapp_static_asset_manifests'),
    check,
  })
  console.log(`${check ? 'checked' : 'built'} ${result.entries.length} static assets (${result.assetVersion})`)
} catch (error) {
  console.error(error instanceof Error ? error.message : error)
  process.exitCode = 1
}
