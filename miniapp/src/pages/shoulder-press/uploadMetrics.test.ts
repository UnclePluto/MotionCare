import { describe, expect, it } from 'vitest'

import {
  TransferSpeedMeter,
  formatBytes,
  formatTransferSpeed,
} from './uploadMetrics'

describe('肩部推举上传指标', () => {
  it('用相邻采样的字节差计算实时传输速度', () => {
    const meter = new TransferSpeedMeter()

    expect(meter.sample(1_000, 1_000)).toBe(0)
    expect(meter.sample(2_500, 2_000)).toBe(1_500)
    expect(meter.sample(3_000, 2_500)).toBe(1_000)
  })

  it('忽略字节回退并在长时间无进展时归零', () => {
    const meter = new TransferSpeedMeter()

    meter.sample(2_000, 1_000)
    expect(meter.sample(1_000, 2_000)).toBe(0)
    expect(meter.sample(1_000, 5_500)).toBe(0)
  })

  it('以适合手机阅读的单位展示大小和速度', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1_572_864)).toBe('1.50 MB')
    expect(formatTransferSpeed(1_572_864)).toBe('1.50 MB/s')
  })
})
