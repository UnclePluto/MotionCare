import { describe, expect, it } from 'vitest'
import { createRecordingTrace } from './recordingTrace'

describe('真机录制诊断', () => {
  it('导出运行环境白名单和收尾阶段，排除设备标识及其他系统信息', () => {
    const trace = createRecordingTrace(() => 0, {
      platform: 'ios', system: 'iOS 26.6.1', version: '8.0.78', SDKVersion: '3.17.0',
      model: 'iPhone 13', deviceId: 'private-device', token: 'private-token'
    })
    trace.mark('segment_stop')
    trace.mark('stop_timeout')
    const result = JSON.parse(trace.export())
    expect(result.environment).toEqual({ platform: 'ios', system: 'iOS 26.6.1', version: '8.0.78', SDKVersion: '3.17.0', model: 'iPhone 13' })
    expect(result.events.map((event: any) => event.event)).toEqual(['segment_stop', 'stop_timeout'])
    expect(trace.export()).not.toMatch(/private-device|private-token/)
  })
  it('区分发出停止与收到视频，保留耗时并排除视频路径和原始错误', () => {
    let now = 0
    let stop: any
    const trace = createRecordingTrace(() => now)
    const camera = trace.wrap({ startRecord: options => options.success?.(), stopRecord: options => { stop = options } })
    camera.startRecord({ timeout: 5 })
    now = 7000; camera.stopRecord({})
    const waiting = JSON.parse(trace.export())
    expect(waiting.events.map((event: any) => event.event)).toEqual(['start_call', 'start_success', 'stop_call'])
    expect(waiting.events[2].elapsedMs).toBe(7000)
    now = 19000; stop.success({ tempVideoPath: 'wxfile://private-patient-video.mp4' })
    const done = JSON.parse(trace.export())
    expect(done.events.at(-1)).toMatchObject({ event: 'stop_success', elapsedMs: 19000, hasVideo: true })
    expect(trace.export()).not.toContain('private-patient')
  })
  it('回调和同步异常不被诊断吞掉，记录经过筛选的错误码', () => {
    const trace = createRecordingTrace(() => 0)
    let error: unknown
    const camera = trace.wrap({ startRecord: options => options.fail?.({ errCode: 1001, errMsg: 'secret token' }), stopRecord: () => { throw new Error('private path') } })
    camera.startRecord({ fail: value => { error = value } })
    expect(error).toMatchObject({ errCode: 1001 })
    expect(() => camera.stopRecord({})).toThrow('private path')
    expect(trace.export()).toContain('1001')
    expect(trace.export()).not.toMatch(/secret token|private path/)
  })
  it('长时间录制的诊断记录有容量上限', () => {
    const trace = createRecordingTrace(() => 0)
    for (let i = 0; i < 1000; i++) trace.mark('camera_ready')
    expect(JSON.parse(trace.export()).events).toHaveLength(400)
  })
})
