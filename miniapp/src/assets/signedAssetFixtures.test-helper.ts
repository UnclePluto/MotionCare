import { STATIC_ASSET_MANIFEST } from './staticAssetManifest.generated'

export function signedAssetFixture(issuedAt = 1_800_000_000, token = 'fixture:signature') {
  return {
    asset_version: STATIC_ASSET_MANIFEST.assetVersion,
    issued_at: issuedAt,
    expires_at: issuedAt + 600,
    assets: STATIC_ASSET_MANIFEST.entries.map((entry) => ({
      key: entry.key,
      relative_path: entry.relativePath,
      content_type: entry.contentType,
      size_bytes: entry.sizeBytes,
      sha256: entry.sha256,
      url: 'https://cdn.example.com/motioncare/static-assets/' + entry.relativePath
        + '?e=' + (issuedAt + 600) + '&token=' + encodeURIComponent(token),
    })),
  }
}
