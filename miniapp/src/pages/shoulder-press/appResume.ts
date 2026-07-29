import type { ShoulderPressSession } from './session'

const ACTIVE_SHOULDER_PRESS_ROUTES = new Set([
  'pages/shoulder-press/camera',
  'pages/shoulder-press/upload',
])

export function shouldResumeShoulderPressUpload(
  session: ShoulderPressSession | null,
  currentRoute: string,
): boolean {
  return Boolean(session) && !ACTIVE_SHOULDER_PRESS_ROUTES.has(currentRoute)
}
