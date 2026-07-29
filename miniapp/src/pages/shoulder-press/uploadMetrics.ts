import type { ShoulderPressSession } from './session'

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB']

export function getSessionTotalBytes(session: ShoulderPressSession): number {
  if (typeof session.totalBytes === 'number') return Math.max(0, session.totalBytes)
  return Math.max(
    0,
    (session.uploadedBytes ?? 0)
      + session.segments.reduce((total, segment) => total + segment.sizeBytes, 0),
  )
}

export function formatBytes(bytes: number): string {
  let value = Math.max(0, bytes)
  let unitIndex = 0
  while (value >= 1024 && unitIndex < BYTE_UNITS.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  if (unitIndex === 0) return `${Math.round(value)} ${BYTE_UNITS[unitIndex]}`
  return `${value.toFixed(2)} ${BYTE_UNITS[unitIndex]}`
}

export function formatTransferSpeed(bytesPerSecond: number): string {
  return `${formatBytes(bytesPerSecond)}/s`
}

export class TransferSpeedMeter {
  private previousBytes: number | null = null
  private previousTimestamp: number | null = null

  sample(uploadedBytes: number, timestamp: number): number {
    if (this.previousBytes === null || this.previousTimestamp === null) {
      this.previousBytes = uploadedBytes
      this.previousTimestamp = timestamp
      return 0
    }
    const elapsedMilliseconds = timestamp - this.previousTimestamp
    const transferredBytes = uploadedBytes - this.previousBytes
    this.previousBytes = uploadedBytes
    this.previousTimestamp = timestamp
    if (elapsedMilliseconds <= 0 || transferredBytes <= 0) return 0
    return Math.round((transferredBytes * 1_000) / elapsedMilliseconds)
  }
}
