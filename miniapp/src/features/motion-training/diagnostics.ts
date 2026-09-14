import Taro from '@tarojs/taro'
import { apiUrl } from '../../api/client'
import { getPatientAppToken } from '../../auth/token'
import { isDemoSession } from '../../demo/session'
import { diagnosticUuid, DIAGNOSTIC_QUEUE_KEY, getTrainingDiagnosticScope } from './diagnosticScope'

export type TrainingDiagnosticStage = 'recording' | 'compression' | 'file_read' | 'session' | 'status' | 'upload' | 'finalize'
export type TrainingDiagnosticContext = { clientSessionId?: string; videoId?: number; segmentIndex?: number; httpStatus?: number; diagnosticScope?: string | null }
type DiagnosticEvent = {
  event_id: string; occurred_at: string; stage: TrainingDiagnosticStage; error_code: string; message: string
  network_type: string; platform: string; sdk_version: string; app_version: string
  client_session_id?: string; video_id?: number; segment_index?: number; http_status?: number
}
const STAGES = new Set(['recording', 'compression', 'file_read', 'session', 'status', 'upload', 'finalize'])
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i
const KINDS = ['timeout', 'permission_denied', 'cancelled', 'file_not_found', 'storage_full', 'invalid_response', 'network_error', 'failed']
const AGE_MS = 15 * 24 * 60 * 60 * 1000
let active = false
let sending = false
let paused = false
let lastToken: string | undefined
let knownToken = false
let timer: ReturnType<typeof setTimeout> | undefined
let retryMs = 1000
let networkType = 'unknown'
let listening = false

function safeVersion(value: unknown): string {
  return typeof value === 'string' && value.length <= 32 && /^\d{1,4}(\.\d{1,4}){0,3}$/.test(value) ? value : 'unknown'
}
function network(value: unknown): string {
  return typeof value === 'string' && ['wifi', '2g', '3g', '4g', '5g', 'none', 'unknown', 'ethernet'].includes(value) ? value : 'unknown'
}
function metadata() {
  let platform = 'unknown', sdkVersion = 'unknown', appVersion = 'unknown'
  try { const value = Taro.getDeviceInfo().platform; if (['ios', 'android', 'devtools', 'windows', 'mac', 'ohos'].includes(value)) platform = value } catch { /* optional */ }
  try { sdkVersion = safeVersion(Taro.getAppBaseInfo().SDKVersion) } catch { /* optional */ }
  try { appVersion = safeVersion(Taro.getAccountInfoSync().miniProgram.version) } catch { /* optional */ }
  return { network_type: networkType, platform, sdk_version: sdkVersion, app_version: appVersion }
}
function identity(): { token: string; scope: string } | undefined {
  const token = getPatientAppToken()
  if (knownToken && lastToken !== token) { paused = false; retryMs = 1000 }
  knownToken = true; lastToken = token
  if (!token || isDemoSession()) return undefined
  return { token, scope: getTrainingDiagnosticScope(token) }
}
function persist(scope: string, events: DiagnosticEvent[]) {
  Taro.setStorageSync(DIAGNOSTIC_QUEUE_KEY, { scope, events })
}
function restoreEvent(raw: unknown): DiagnosticEvent | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const e = raw as DiagnosticEvent
  if (!UUID.test(e.event_id) || !STAGES.has(e.stage) || typeof e.occurred_at !== 'string'
    || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(e.occurred_at)
    || !(Date.parse(e.occurred_at) > Date.now() - AGE_MS && Date.parse(e.occurred_at) <= Date.now())) return undefined
  if (typeof e.error_code !== 'string' || !new RegExp(`^${e.stage}_(?:${KINDS.join('|')}|native_[0-9]{1,8}|http_[1-5][0-9]{2})$`).test(e.error_code)) return undefined
  const safeMessages = KINDS.map(kind => `${e.stage}: ${kind === 'invalid_response' ? 'invalid data' : kind.replace(/_/g, ' ')}`)
  if (!safeMessages.includes(e.message)) return undefined
  const event: DiagnosticEvent = {
    event_id: e.event_id, occurred_at: e.occurred_at, stage: e.stage, error_code: e.error_code, message: e.message,
    network_type: network(e.network_type),
    platform: ['ios', 'android', 'devtools', 'windows', 'mac', 'ohos'].includes(e.platform) ? e.platform : 'unknown',
    sdk_version: safeVersion(e.sdk_version), app_version: safeVersion(e.app_version)
  }
  if (typeof e.client_session_id === 'string' && UUID.test(e.client_session_id)) event.client_session_id = e.client_session_id
  if (Number.isSafeInteger(e.video_id) && e.video_id! > 0) event.video_id = e.video_id
  if (Number.isInteger(e.segment_index) && e.segment_index! >= 0 && e.segment_index! <= 2147483647) event.segment_index = e.segment_index
  if (Number.isInteger(e.http_status) && e.http_status! >= 100 && e.http_status! <= 599) event.http_status = e.http_status
  return event
}
function queue(scope: string): DiagnosticEvent[] {
  const saved = Taro.getStorageSync(DIAGNOSTIC_QUEUE_KEY)
  const events: unknown[] = saved?.scope === scope && Array.isArray(saved.events) ? saved.events : []
  const live = events.slice(-100).map(restoreEvent).filter((event): event is DiagnosticEvent => !!event)
  // Persist the reconstructed whitelist too, so old/unknown fields are removed locally.
  persist(scope, live)
  return live
}
function summarize(stage: TrainingDiagnosticStage, error: unknown, httpStatus?: number) {
  const value = error && typeof error === 'object' ? error as { errMsg?: unknown; errCode?: unknown; code?: unknown; message?: unknown } : {}
  const text = typeof value.errMsg === 'string' ? value.errMsg : typeof value.message === 'string' ? value.message : ''
  // Reconstruct from a fixed vocabulary; never copy substrings of native messages.
  const kind = /timeout|timed out/i.test(text) ? 'timeout'
    : /permission|auth deny|denied/i.test(text) ? 'permission_denied'
      : /cancel|abort/i.test(text) ? 'cancelled'
        : /not found|no such file|enoent/i.test(text) ? 'file_not_found'
          : /space|quota|storage full/i.test(text) ? 'storage_full'
            : /格式无效|invalid.*(?:response|file info)/i.test(text) ? 'invalid_response'
              : /network|offline|connect/i.test(text) ? 'network_error' : 'failed'
  const native = value.errCode ?? value.code
  const nativeCode = (typeof native === 'number' && Number.isInteger(native) && native >= 0 && native <= 99999999)
    || (typeof native === 'string' && /^\d{1,8}$/.test(native)) ? String(native) : undefined
  return {
    error_code: httpStatus ? `${stage}_http_${httpStatus}` : nativeCode ? `${stage}_native_${nativeCode}` : `${stage}_${kind}`,
    message: `${stage}: ${kind === 'invalid_response' ? 'invalid data' : kind.replace(/_/g, ' ')}`
  }
}
function schedule(delay: number) {
  if (!active || paused || timer) return
  timer = setTimeout(() => { timer = undefined; void flush() }, delay)
}
async function flush(): Promise<void> {
  if (!active || sending || paused) return
  sending = true
  let attemptedScope: string | undefined
  try {
    const owner = identity()
    if (!owner) return
    attemptedScope = owner.scope
    const event = queue(owner.scope)[0]
    if (!event) return
    const response = await Taro.request<{ event_id?: string }>({
      url: apiUrl('/patient-app/training-upload-diagnostics/'), method: 'POST', data: event,
      timeout: 15000,
      header: { 'content-type': 'application/json', Authorization: `Bearer ${owner.token}` }
    })
    const current = identity()
    if (!current || current.scope !== owner.scope || current.token !== owner.token) return
    const status = response.statusCode
    if ((status === 200 && response.data?.event_id === event.event_id) || [400, 413, 415, 422].includes(status)) {
      persist(owner.scope, queue(owner.scope).filter(item => item.event_id !== event.event_id))
      retryMs = 1000
      schedule(0)
    } else if (status === 401 || status === 403) {
      paused = true
    } else {
      schedule(retryMs); retryMs = Math.min(retryMs * 2, 60000)
    }
  } catch {
    schedule(retryMs); retryMs = Math.min(retryMs * 2, 60000)
  } finally {
    sending = false
    // A login change while the previous request was in flight must not strand the new queue.
    try { if (active && attemptedScope && identity()?.scope !== attemptedScope) schedule(0) } catch { /* isolated */ }
  }
}

// Capture before starting native/network work. Null intentionally fails closed.
export function captureTrainingDiagnosticScope(): string | null {
  try { return identity()?.scope ?? null } catch { return null }
}

export function reportTrainingDiagnostic(stage: TrainingDiagnosticStage, error: unknown, context: TrainingDiagnosticContext = {}): void {
  try {
    const owner = identity()
    if (!owner || !STAGES.has(stage)) return
    if ('diagnosticScope' in context && context.diagnosticScope !== owner.scope) return
    const status = Number.isInteger(context.httpStatus) && context.httpStatus! >= 100 && context.httpStatus! <= 599 ? context.httpStatus : undefined
    const event: DiagnosticEvent = { event_id: diagnosticUuid(), occurred_at: new Date().toISOString(), stage,
      ...summarize(stage, error, status), ...metadata() }
    if (typeof context.clientSessionId === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(context.clientSessionId)) event.client_session_id = context.clientSessionId
    if (Number.isSafeInteger(context.videoId) && context.videoId! > 0) event.video_id = context.videoId
    if (Number.isSafeInteger(context.segmentIndex) && context.segmentIndex! >= 0 && context.segmentIndex! <= 2147483647) event.segment_index = context.segmentIndex
    if (status !== undefined) event.http_status = status
    // All string fields above are bounded ASCII; this also caps future schema additions.
    if (JSON.stringify(event).length > 4096) return
    persist(owner.scope, [...queue(owner.scope), event].slice(-100))
    if (!timer) void flush()
  } catch { /* Diagnostics must never affect training. */ }
}
const onNetworkChange = (event: { isConnected: boolean; networkType?: string }) => {
  networkType = network(event.networkType)
  if (event.isConnected && active && !paused) {
    if (timer) clearTimeout(timer)
    timer = undefined
    void flush()
  }
}
export function startTrainingDiagnostics(): void {
  try {
    active = true
    try { if (!listening) { Taro.onNetworkStatusChange(onNetworkChange); listening = true } } catch { /* optional */ }
    try { void Promise.resolve(Taro.getNetworkType()).then(result => { networkType = network(result.networkType) }).catch(() => undefined) } catch { /* optional */ }
    void flush()
  } catch { /* isolated */ }
}
export function stopTrainingDiagnostics(): void {
  active = false
  if (timer) clearTimeout(timer)
  timer = undefined
  try { if (listening) Taro.offNetworkStatusChange(onNetworkChange) } catch { /* optional */ }
  listening = false
}
