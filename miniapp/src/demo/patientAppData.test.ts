import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { HomeData } from '../types/patientApp'

const requestMock = vi.hoisted(() => vi.fn())

vi.mock('../api/client', () => ({ request: requestMock }))

describe('患者端数据源', () => {
  beforeEach(() => {
    vi.resetModules()
    requestMock.mockReset()
  })

  it('开启演示会话时返回固定数据且不发起网络请求', async () => {
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
  })
})
