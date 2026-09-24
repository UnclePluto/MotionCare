import { beforeEach, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ upload: vi.fn() }))
vi.mock('@tarojs/taro', () => ({ default: { uploadFile: mocks.upload } }))
import { uploadDirectVideo } from './directUpload'
const grant = { video_id: 1, status: 'recording', upload_url: 'https://upload.example.test', object_key: 'server-key.mp4', upload_token: 'scoped-token' }
const file = { path: 'whole.mp4', sizeBytes: 100 * 1024 * 1024, durationMs: 300000, persistence: 'saved' as const }
beforeEach(() => { mocks.upload.mockReset() })
it('100 MB 整文件一次直传，仅携带限定对象凭证并报告真实字节进度', async () => {
  mocks.upload.mockImplementation(options => {
    options.success({ statusCode: 200, data: JSON.stringify({ key: grant.object_key, hash: 'A'.repeat(28) }) })
    return { onProgressUpdate: (fn: Function) => fn({ progress: 50, totalBytesSent: file.sizeBytes / 2 }) }
  })
  const onProgress = vi.fn()
  await uploadDirectVideo({ file, grant, onProgress })
  expect(mocks.upload).toHaveBeenCalledTimes(1)
  expect(mocks.upload.mock.calls[0][0]).toMatchObject({ url: grant.upload_url, name: 'file', filePath: file.path, formData: { key: grant.object_key, token: grant.upload_token } })
  expect(mocks.upload.mock.calls[0][0].header).toBeUndefined()
  expect(onProgress).toHaveBeenCalledWith(50, file.sizeBytes / 2)
})
it.each(['http://upload.example.test', 'https://user:password@upload.example.test', 'https://upload.example.test?token=secret'])('拒绝无效授权地址 %s', async url => {
  await expect(uploadDirectVideo({ file, grant: { ...grant, upload_url: url } })).rejects.toThrow()
  expect(mocks.upload).not.toHaveBeenCalled()
})
it.each([{ statusCode: 200, data: '{}' }, { statusCode: 200, data: '{' }, { statusCode: 200, data: JSON.stringify({ key: 'other', hash: 'A'.repeat(28) }) }, { statusCode: 401, data: 'token=secret' }])('响应不符不算上传成功且错误不暴露凭证', async response => {
  mocks.upload.mockImplementation(options => { options.success(response); return {} })
  await expect(uploadDirectVideo({ file, grant })).rejects.toThrow('视频上传未确认，请重试')
})
it('账号变化中止正在进行的完整文件上传', async () => {
  vi.useFakeTimers()
  let active = true
  const abort = vi.fn()
  mocks.upload.mockReturnValue({ abort })
  const result = uploadDirectVideo({ file, grant, isActive: () => active })
  const rejected = expect(result).rejects.toThrow('视频上传未确认')
  active = false
  await vi.advanceTimersByTimeAsync(250)
  await rejected
  expect(abort).toHaveBeenCalledTimes(1)
  vi.useRealTimers()
})
