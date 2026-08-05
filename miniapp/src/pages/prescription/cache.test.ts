import { beforeEach, describe, expect, it } from 'vitest'

import type { CurrentPrescription } from '../../types/patientApp'
import {
  clearCurrentPrescriptionCache,
  readCurrentPrescriptionCache,
  writeCurrentPrescriptionCache
} from './cache'

const PRESCRIPTION: NonNullable<CurrentPrescription> = {
  id: 1,
  version: 1,
  status: 'active',
  effective_at: null,
  week_start: '2026-08-03',
  week_end: '2026-08-09',
  actions: []
}

describe('current prescription process cache', () => {
  beforeEach(() => clearCurrentPrescriptionCache())

  it('distinguishes a cache miss from a cached null prescription', () => {
    expect(readCurrentPrescriptionCache()).toBeUndefined()

    writeCurrentPrescriptionCache(null)

    expect(readCurrentPrescriptionCache()).toBeNull()
  })

  it('returns the current process value and clears it explicitly', () => {
    writeCurrentPrescriptionCache(PRESCRIPTION)
    expect(readCurrentPrescriptionCache()).toBe(PRESCRIPTION)

    clearCurrentPrescriptionCache()

    expect(readCurrentPrescriptionCache()).toBeUndefined()
  })
})
