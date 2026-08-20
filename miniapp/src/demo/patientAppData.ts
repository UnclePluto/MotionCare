import { request } from '../api/client'
import type { MotionSourceKey } from '../features/motion-training/catalog'
import type { CurrentPrescription, HomeData } from '../types/patientApp'
import { createDemoCurrentPrescription, createDemoHomeData } from './data'
import { fetchDemoMotionVideoManifest } from './motionVideoManifest'
import { isDemoSession } from './session'

async function fetchDemoVideoUrls(): Promise<Partial<Record<MotionSourceKey, string>>> {
  try {
    return await fetchDemoMotionVideoManifest()
  } catch {
    return {}
  }
}

export function fetchPatientHomeData(): Promise<HomeData> {
  if (isDemoSession()) return fetchDemoVideoUrls().then(createDemoHomeData)
  return request<HomeData>('/patient-app/home/')
}

export function fetchCurrentPrescriptionData(): Promise<CurrentPrescription> {
  if (isDemoSession()) return fetchDemoVideoUrls().then(createDemoCurrentPrescription)
  return request<CurrentPrescription>('/patient-app/current-prescription/')
}
