import type {
  PendingShoulderPressSegment,
  StorageLike,
} from './session'
import {
  loadShoulderPressSession,
  saveShoulderPressSession,
} from './session'
import { getSessionTotalBytes, TransferSpeedMeter } from './uploadMetrics'

type SegmentUploadProgress = {
  progress: number
  totalBytesSent: number
  totalBytesExpectedToSend: number
}

type QueueRunnerOptions = {
  storage: StorageLike
  upload: (input: {
    videoId: number
    segment: PendingShoulderPressSegment
    onProgress?: (progress: SegmentUploadProgress) => void
  }) => Promise<unknown>
  removeFile: (filePath: string) => Promise<void>
  onProgress?: (progress: {
    sequenceIndex: number
    progress: number
    uploadedBytes: number
    totalBytes: number
    bytesPerSecond: number
  }) => void
  now?: () => number
}

function retryDelay(retryCount: number): number {
  return Math.min(1_000 * (2 ** Math.max(retryCount - 1, 0)), 60_000)
}

let sharedInFlight: Promise<boolean> | null = null

export class SegmentQueueRunner {
  private readonly options: QueueRunnerOptions
  private inFlight: Promise<boolean> | null = null
  private drainFlight: Promise<void> | null = null

  constructor(options: QueueRunnerOptions) {
    this.options = options
  }

  runNext(): Promise<boolean> {
    if (this.inFlight) return this.inFlight
    if (sharedInFlight) return sharedInFlight
    const flight = this.processNext().finally(() => {
      this.inFlight = null
      if (sharedInFlight === flight) sharedInFlight = null
    })
    this.inFlight = flight
    sharedInFlight = flight
    return this.inFlight
  }

  drainAvailable(): Promise<void> {
    if (this.drainFlight) return this.drainFlight
    this.drainFlight = (async () => {
      while (await this.runNext()) {
        // Keep draining newly queued segments with one upload in flight.
      }
    })().finally(() => {
      this.drainFlight = null
    })
    return this.drainFlight
  }

  private async processNext(): Promise<boolean> {
    const now = this.options.now?.() ?? Date.now()
    const session = loadShoulderPressSession(this.options.storage)
    if (!session) return false
    const segment = [...session.segments]
      .sort((left, right) => left.sequenceIndex - right.sequenceIndex)
      .find((item) => (
        item.status === 'pending'
        || item.status === 'uploading'
        || item.status === 'confirmed'
        || (item.status === 'retrying' && (item.nextRetryAt ?? 0) <= now)
      ))
    if (!segment) return false

    try {
      if (segment.status !== 'confirmed') {
        segment.status = 'uploading'
        saveShoulderPressSession(this.options.storage, {
          ...session,
          segments: [...session.segments],
        })
        const speedMeter = new TransferSpeedMeter()
        speedMeter.sample(
          session.uploadedBytes ?? 0,
          this.options.now?.() ?? Date.now(),
        )
        let lastReportedProgress = 0
        const reportProgress = (progress: SegmentUploadProgress) => {
          const progressSession = loadShoulderPressSession(this.options.storage)
          if (!progressSession) return
          const completedBytes = progressSession.uploadedBytes ?? 0
          const expectedBytes = Math.max(progress.totalBytesExpectedToSend, 0)
          const currentBytes = expectedBytes > 0
            ? Math.round(
              segment.sizeBytes
                * Math.min(Math.max(progress.totalBytesSent / expectedBytes, 0), 1),
            )
            : Math.round(
              segment.sizeBytes * Math.min(Math.max(progress.progress / 100, 0), 1),
            )
          lastReportedProgress = Math.max(lastReportedProgress, progress.progress)
          this.options.onProgress?.({
            sequenceIndex: segment.sequenceIndex,
            progress: progress.progress,
            uploadedBytes: completedBytes + currentBytes,
            totalBytes: getSessionTotalBytes(progressSession),
            bytesPerSecond: speedMeter.sample(
              completedBytes + currentBytes,
              this.options.now?.() ?? Date.now(),
            ),
          })
        }
        await this.options.upload({
          videoId: session.videoId,
          segment,
          onProgress: reportProgress,
        })
        if (lastReportedProgress < 100) {
          reportProgress({
            progress: 100,
            totalBytesSent: segment.sizeBytes,
            totalBytesExpectedToSend: segment.sizeBytes,
          })
        }
        const confirmedSession = loadShoulderPressSession(this.options.storage)
        if (!confirmedSession) return false
        saveShoulderPressSession(this.options.storage, {
          ...confirmedSession,
          uploadedBytes: (confirmedSession.uploadedBytes ?? 0) + segment.sizeBytes,
          segments: confirmedSession.segments.map((item) => (
            item.sequenceIndex === segment.sequenceIndex
              ? { ...item, status: 'confirmed', lastError: undefined }
              : item
          )),
        })
      }
      await this.options.removeFile(segment.savedFilePath)
      const latest = loadShoulderPressSession(this.options.storage)
      if (latest) {
        saveShoulderPressSession(this.options.storage, {
          ...latest,
          segments: latest.segments.filter(
            (item) => item.sequenceIndex !== segment.sequenceIndex,
          ),
        })
      }
      return true
    } catch (reason) {
      const latest = loadShoulderPressSession(this.options.storage)
      if (latest) {
        const latestSegment = latest.segments.find(
          (item) => item.sequenceIndex === segment.sequenceIndex,
        )
        if (latestSegment?.status === 'confirmed') {
          saveShoulderPressSession(this.options.storage, {
            ...latest,
            segments: latest.segments.map((item) => (
              item.sequenceIndex === segment.sequenceIndex
                ? {
                  ...item,
                  lastError: reason instanceof Error ? reason.message : '删除本地视频分片失败',
                }
                : item
            )),
          })
          return false
        }
        const retryCount = segment.retryCount + 1
        saveShoulderPressSession(this.options.storage, {
          ...latest,
          segments: latest.segments.map((item) => (
            item.sequenceIndex === segment.sequenceIndex
              ? {
                ...item,
                status: 'retrying',
                retryCount,
                nextRetryAt: now + retryDelay(retryCount),
                lastError: reason instanceof Error ? reason.message : '视频分片上传失败',
              }
              : item
          )),
        })
      }
      return false
    }
  }
}
