import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { HOME_ACTIONS, type HomeActionContext } from './homeActions'

const sourceDirectory = resolve(process.cwd(), 'src')
const appConfigSource = readFileSync(resolve(sourceDirectory, 'app.config.ts'), 'utf8')
const homePageSource = readFileSync(resolve(sourceDirectory, 'pages/home/index.tsx'), 'utf8')
const patientAppTypesSource = readFileSync(resolve(sourceDirectory, 'types/patientApp.ts'), 'utf8')

describe('patient app home capabilities', () => {
  it('removes the manual health page, route, state and API path', () => {
    expect(appConfigSource).not.toContain('pages/daily-health/index')
    expect(homePageSource).not.toContain('has_daily_health_today')
    expect(homePageSource).not.toContain('/pages/daily-health/index')
    expect(patientAppTypesSource).not.toContain('has_daily_health_today')
    expect(patientAppTypesSource).not.toContain('DailyHealth')
    expect(() => readFileSync(resolve(sourceDirectory, 'pages/daily-health/index.tsx'), 'utf8')).toThrow()
  })

  it('renders the real home shortcuts from the shared action list', () => {
    expect(homePageSource).toContain('HOME_ACTIONS.map')
  })

  it('exposes only prescription, training and history shortcuts', () => {
    expect(HOME_ACTIONS.map((item) => item.key)).toEqual([
      'prescription',
      'training',
      'history'
    ])
    expect(HOME_ACTIONS.some((item) => String(item.key) === 'daily-health')).toBe(false)
  })

  it('keeps the existing prescription and training destinations and exposes action history', () => {
    const motionContext: HomeActionContext = { actionId: 42, internalType: 'motion' }
    const gameContext: HomeActionContext = { actionId: 42, internalType: 'game' }
    const byKey = Object.fromEntries(HOME_ACTIONS.map((item) => [item.key, item]))

    expect(byKey.prescription.label()).toBe('查看运动计划')
    expect(byKey.prescription.url(null)).toBe('/pages/prescription/index')
    expect(byKey.training.url(motionContext)).toBe('/pages/training/index?actionId=42')
    expect(byKey.training.url(gameContext)).toBe('/pages/game-session/index?actionId=42')
    expect(byKey.history.url(motionContext)).toBe('/pages/action-history/index?actionId=42')
  })
})
