import type { CameraContext } from './recorder'
import type { CountedRecorderEvent } from './countedRecorder'

export const RECORDING_BUILD = 'counted-single-video-1'

type Event = 'camera_ready' | 'camera_error' | 'camera_stop' | 'page_hide' | 'page_show' | 'group_start' | 'group_finish' | 'group_saved' | 'group_abandon' | 'stop_slow' | 'save_call' | 'save_success' | 'save_failure'
  | 'start_call' | 'start_success' | 'start_failure' | 'start_throw' | 'timeout_video' | 'stop_call' | 'stop_success' | 'stop_failure' | 'stop_throw'
  | CountedRecorderEvent
type Entry = { event: Event; elapsedMs: number; group: number; generation: number; hasVideo?: boolean; timeout?: number; code?: number; reason?: string }

// This journal contains only fixed event names, counters and sanitized native codes.
// It stays on the page until the user explicitly copies it for diagnosis.
export function createRecordingTrace(now = Date.now, systemInfo: object = {}) {
  const environment: Record<string, string> = {}
  for (const key of ['platform', 'system', 'version', 'SDKVersion', 'model']) {
    const value = (systemInfo as Record<string, unknown>)[key]
    if (typeof value === 'string') environment[key] = value.replace(/[\r\n\t]/g, ' ').slice(0, 80)
  }
  const startedAt = now()
  const events: Entry[] = []
  let group = 0
  let generation = 0
  function record(event: Event, fields: Partial<Entry> = {}) {
    events.push({ event, elapsedMs: Math.max(0, now() - startedAt), group, generation, ...fields })
    if (events.length > 400) events.shift()
  }
  function failure(error: unknown): Pick<Entry, 'code' | 'reason'> {
    const value = error && typeof error === 'object' ? error as { errCode?: unknown; errMsg?: unknown } : {}
    const code = typeof value.errCode === 'number' && Number.isSafeInteger(value.errCode) ? value.errCode : undefined
    const text = typeof value.errMsg === 'string' ? value.errMsg : ''
    const reason = /not.*record|no.*record/i.test(text) ? 'not_recording' : /already|is recording/i.test(text) ? 'already_recording'
      : /timeout/i.test(text) ? 'timeout' : /permission|auth/i.test(text) ? 'permission' : 'unknown'
    return { code, reason }
  }
  return {
    mark(event: Event, groupIndex?: number) {
      if (event === 'group_start' && groupIndex !== undefined) group = groupIndex
      record(event)
    },
    export() { return JSON.stringify({ schema: 2, build: RECORDING_BUILD, environment, startedAt: new Date(startedAt).toISOString(), events }) },
    wrap(camera: CameraContext): CameraContext {
      return {
        startRecord(options) {
          const id = ++generation
          const ownGroup = group
          const fields = { generation: id, group: ownGroup }
          record('start_call', { ...fields, timeout: options.timeout })
          try {
            camera.startRecord({ ...options,
              success: () => { record('start_success', fields); options.success?.() },
              fail: error => { record('start_failure', { ...fields, ...failure(error) }); options.fail?.(error) },
              timeoutCallback: result => { record('timeout_video', { ...fields, hasVideo: !!result.tempVideoPath }); options.timeoutCallback?.(result) }
            })
          } catch (error) { record('start_throw', { ...fields, ...failure(error) }); throw error }
        },
        stopRecord(options) {
          const fields = { generation, group }
          record('stop_call', fields)
          try {
            camera.stopRecord({ ...options,
              success: result => { record('stop_success', { ...fields, hasVideo: !!result.tempVideoPath }); options.success?.(result) },
              fail: error => { record('stop_failure', { ...fields, ...failure(error) }); options.fail?.(error) }
            })
          } catch (error) { record('stop_throw', { ...fields, ...failure(error) }); throw error }
        }
      }
    }
  }
}
