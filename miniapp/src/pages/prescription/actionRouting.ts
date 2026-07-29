import { buildShoulderPressSessionUrl, SHOULDER_PRESS_SOURCE_KEY } from '../shoulder-press/session'

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
    return `/pages/game-session/index?actionId=${action.id}`
  }
  return `/pages/training/index?actionId=${action.id}`
}

export function actionButtonLabel(action: RoutableAction): string {
  if (action.source_key === SHOULDER_PRESS_SOURCE_KEY) return '开始跟练'
  return action.internal_type === 'game' ? '开始游戏' : '开始训练'
}
