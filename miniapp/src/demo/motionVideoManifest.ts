import { publicRequest } from '../api/client'
import {
  isOfficialMotionSourceKey,
  OFFICIAL_MOTION_SOURCE_KEYS,
  type MotionSourceKey
} from '../features/motion-training/catalog'

const DEMO_MOTION_VIDEO_MANIFEST_PATH = '/patient-app/demo-motion-videos/'
const DEMO_MOTION_VIDEO_MANIFEST_TTL_MS = 60_000
const DEMO_MOTION_VIDEO_MANIFEST_ERROR = '演示视频暂时不可用，请稍后重试'

type CachedManifest = {
  createdAt: number
  promise: Promise<Record<MotionSourceKey, string>>
}

let cachedManifest: CachedManifest | null = null

function isHttpsUrl(value: string): boolean {
  return /^https:\/\/[^/\s?#]+(?:[/?#][^\s]*)?$/i.test(value)
}

function parseManifest(response: unknown): Record<MotionSourceKey, string> {
  const videos = response && typeof response === 'object'
    ? (response as { videos?: unknown }).videos
    : null
  if (!Array.isArray(videos) || videos.length !== OFFICIAL_MOTION_SOURCE_KEYS.length) {
    throw new Error(DEMO_MOTION_VIDEO_MANIFEST_ERROR)
  }

  const manifest = {} as Record<MotionSourceKey, string>
  const seen = new Set<MotionSourceKey>()
  for (const video of videos) {
    if (!video || typeof video !== 'object') {
      throw new Error(DEMO_MOTION_VIDEO_MANIFEST_ERROR)
    }
    const sourceKey = (video as { source_key?: unknown }).source_key
    const rawVideoUrl = (video as { video_url?: unknown }).video_url
    if (
      !isOfficialMotionSourceKey(sourceKey) ||
      seen.has(sourceKey) ||
      typeof rawVideoUrl !== 'string'
    ) {
      throw new Error(DEMO_MOTION_VIDEO_MANIFEST_ERROR)
    }
    const videoUrl = rawVideoUrl.trim()
    if (!isHttpsUrl(videoUrl)) {
      throw new Error(DEMO_MOTION_VIDEO_MANIFEST_ERROR)
    }
    seen.add(sourceKey)
    manifest[sourceKey] = videoUrl
  }

  if (OFFICIAL_MOTION_SOURCE_KEYS.some((sourceKey) => !seen.has(sourceKey))) {
    throw new Error(DEMO_MOTION_VIDEO_MANIFEST_ERROR)
  }
  return manifest
}

export function fetchDemoMotionVideoManifest(): Promise<Record<MotionSourceKey, string>> {
  const now = Date.now()
  if (
    cachedManifest &&
    now - cachedManifest.createdAt < DEMO_MOTION_VIDEO_MANIFEST_TTL_MS
  ) {
    return cachedManifest.promise
  }

  const promise = publicRequest<unknown>(DEMO_MOTION_VIDEO_MANIFEST_PATH)
    .then(parseManifest)
    .catch((error) => {
      if (cachedManifest?.promise === promise) cachedManifest = null
      throw error
    })
  cachedManifest = { createdAt: now, promise }
  return promise
}
