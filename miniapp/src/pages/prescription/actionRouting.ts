import { buildShoulderPressSessionUrl, SHOULDER_PRESS_SOURCE_KEY } from '../shoulder-press/session'
import { gameSessionUrl } from './gameSubpackage'

type RoutableAction = {
  id: number
  source_key: string | null
  internal_type: 'motion' | 'game' | 'video'
}

export function actionEntryUrl(action: RoutableAction): string {
  if (action.source_key === SHOULDER_PRESS_SOURCE_KEY) {
    return buildShoulderPressSessionUrl(action.id)
  }
  if (action.internal_type === 'game') {
    return gameSessionUrl(action.id)
  }
  return `/pages/training/index?actionId=${encodeURIComponent(String(action.id))}`
}

export function actionButtonLabel(action: RoutableAction): string {
  if (action.source_key === SHOULDER_PRESS_SOURCE_KEY) return '开始跟练'
  if (action.internal_type === 'game') return '开始游戏'
  return '开始训练'
}
