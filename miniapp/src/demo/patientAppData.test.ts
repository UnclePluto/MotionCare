import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { HomeData } from '../types/patientApp'

const requestMock = vi.hoisted(() => vi.fn())
const publicRequestMock = vi.hoisted(() => vi.fn())

vi.mock('../api/client', () => ({
  request: requestMock,
  publicRequest: publicRequestMock,
}))

const demoVideos = [
  'motion-aerobic-high-knee',
  'motion-balance-sit-stand',
  'motion-resistance-row',
  'motion-resistance-leg-kickback',
  'motion-resistance-shoulder-press',
].map((sourceKey) => ({
  source_key: sourceKey,
  video_url: `https://signed.example.com/${sourceKey}.mp4`,
}))

describe('患者端数据源', () => {
  beforeEach(() => {
    vi.resetModules()
    requestMock.mockReset()
    publicRequestMock.mockReset()
    publicRequestMock.mockResolvedValue({ videos: demoVideos })
  })

  it('开启演示会话时只用公开清单构造固定数据', async () => {
    const session = await import('./session')
    const dataSource = await import('./patientAppData')

    session.startDemoSession()

    await expect(dataSource.fetchPatientHomeData()).resolves.toMatchObject({
      patient: { name: '用户01' },
      project: { name: '功能展示' },
    })
    await expect(dataSource.fetchCurrentPrescriptionData()).resolves.toMatchObject({
      actions: expect.any(Array),
    })
    expect(requestMock).not.toHaveBeenCalled()
    expect(publicRequestMock).toHaveBeenCalledTimes(1)
    expect(publicRequestMock).toHaveBeenCalledWith('/patient-app/demo-motion-videos/')
  })

  it('未开启演示会话时使用真实患者端接口', async () => {
    const dataSource = await import('./patientAppData')
    const realPrescription = null
    const realHome: HomeData = {
      project_patient_id: 1,
      patient: { id: 1, name: '真实用户' },
      project: { id: 1, name: '真实项目' },
      today: '2026-08-12',
      current_prescription: realPrescription,
    }
    requestMock
      .mockResolvedValueOnce(realHome)
      .mockResolvedValueOnce(realPrescription)

    await expect(dataSource.fetchPatientHomeData()).resolves.toBe(realHome)
    await expect(dataSource.fetchCurrentPrescriptionData()).resolves.toBe(realPrescription)
    expect(requestMock).toHaveBeenNthCalledWith(1, '/patient-app/home/')
    expect(requestMock).toHaveBeenNthCalledWith(2, '/patient-app/current-prescription/')
    expect(publicRequestMock).not.toHaveBeenCalled()
  })

  it('公开清单失败时保留五个可进入摄像页的演示动作并标记视频不可用', async () => {
    const session = await import('./session')
    const dataSource = await import('./patientAppData')
    session.startDemoSession()
    publicRequestMock.mockRejectedValueOnce(new Error('manifest unavailable'))

    const prescription = await dataSource.fetchCurrentPrescriptionData({
      forceMotionVideoRefresh: true
    })
    const motionActions = prescription?.actions.filter((action) => (
      action.internal_type === 'motion'
    )) ?? []

    expect(motionActions).toHaveLength(5)
    expect(motionActions.every((action) => (
      action.video_unavailable === true && action.video_url === ''
    ))).toBe(true)
    expect(requestMock).not.toHaveBeenCalled()
  })
})
