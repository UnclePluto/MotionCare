export const OFFICIAL_MOTION_SOURCE_KEYS = [
  'motion-aerobic-high-knee',
  'motion-balance-sit-stand',
  'motion-resistance-row',
  'motion-resistance-leg-kickback',
  'motion-resistance-shoulder-press'
] as const

export type MotionSourceKey = typeof OFFICIAL_MOTION_SOURCE_KEYS[number]

export function isOfficialMotionSourceKey(value: unknown): value is MotionSourceKey {
  return typeof value === 'string' && (OFFICIAL_MOTION_SOURCE_KEYS as readonly string[]).includes(value)
}
