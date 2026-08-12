import { request } from '../api/client'
import type { CurrentPrescription, HomeData } from '../types/patientApp'
import { createDemoCurrentPrescription, createDemoHomeData } from './data'
import { isDemoSession } from './session'

export function fetchPatientHomeData(): Promise<HomeData> {
  if (isDemoSession()) return Promise.resolve(createDemoHomeData())
  return request<HomeData>('/patient-app/home/')
}

export function fetchCurrentPrescriptionData(): Promise<CurrentPrescription> {
  if (isDemoSession()) return Promise.resolve(createDemoCurrentPrescription())
  return request<CurrentPrescription>('/patient-app/current-prescription/')
}
