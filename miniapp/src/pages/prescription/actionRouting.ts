import { buildMotionTrainingGuideUrl } from '../../features/motion-training/action'
import { isOfficialMotionSourceKey } from '../../features/motion-training/catalog'
import { gameSessionUrl } from './gameSubpackage'

type RoutableAction = {
  id: number
  source_key: string | null
  internal_type: 'motion' | 'game' | 'video'
}

export function actionEntryUrl(action: RoutableAction): string {
  if (action.internal_type === 'motion' && isOfficialMotionSourceKey(action.source_key)) {
    return buildMotionTrainingGuideUrl(action.id)
  }
  if (action.internal_type === 'game') {
    return gameSessionUrl(action.id)
  }
  return `/pages/training/index?actionId=${encodeURIComponent(String(action.id))}`
}

export function actionButtonLabel(action: RoutableAction): string {
  if (action.internal_type === 'motion' && isOfficialMotionSourceKey(action.source_key)) return '开始跟练'
  if (action.internal_type === 'game') return '开始游戏'
  return '开始训练'
}
