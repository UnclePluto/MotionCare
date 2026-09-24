import Taro from '@tarojs/taro'
import type { CountedVideoFile } from './countedFiles'

export type DirectUploadGrant = { video_id: number; status: string; upload_url?: string; upload_token?: string; object_key?: string; expires_at?: string }

export function uploadDirectVideo({ file, grant, onProgress, isActive }: {
  file: CountedVideoFile; grant: DirectUploadGrant
  onProgress?: (percent: number, bytes: number) => void; isActive?: () => boolean
}): Promise<void> {
  if (!grant.upload_url || !/^https:\/\/[a-zA-Z0-9][a-zA-Z0-9.-]*(?::[0-9]{1,5})?\/?$/.test(grant.upload_url)
      || !grant.upload_token || !grant.object_key || (isActive && !isActive())) {
    return Promise.reject(new Error('视频上传授权无效，请重试'))
  }
  return new Promise((resolve, reject) => {
    let settled = false
    let timer: ReturnType<typeof setInterval> | undefined
    const finish = (ok: boolean) => {
      if (settled) return
      settled = true; if (timer) clearInterval(timer)
      if (ok) resolve(); else reject(new Error('视频上传未确认，请重试'))
    }
    try {
      const task = Taro.uploadFile({
        url: grant.upload_url!, name: 'file', filePath: file.path, timeout: 600000,
        formData: { key: grant.object_key!, token: grant.upload_token! },
        success: response => {
          if (isActive && !isActive()) { finish(false); return }
          try {
            const data = JSON.parse(response.data)
            finish(response.statusCode >= 200 && response.statusCode < 300 && data.key === grant.object_key && /^[A-Za-z0-9_-]{28}$/.test(data.hash))
          } catch { finish(false) }
        }, fail: () => finish(false)
      })
      task.onProgressUpdate?.(event => {
        if (!isActive || isActive()) onProgress?.(Math.min(100, Math.max(0, event.progress)), Math.min(file.sizeBytes, Math.max(0, event.totalBytesSent)))
      })
      if (isActive && !settled) timer = setInterval(() => {
        if (!isActive()) { finish(false); task.abort() }
      }, 250)
    } catch { finish(false) }
  })
}
