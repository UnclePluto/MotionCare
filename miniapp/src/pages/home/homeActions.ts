import { actionEntryUrl } from '../prescription/actionRouting'

export type HomeActionContext = {
  actionId: number
  internalType: 'motion' | 'game' | 'video'
  sourceKey?: string | null
}

export type HomeAction = {
  key: 'prescription' | 'training' | 'history'
  className: string
  requiresAction: boolean
  label: (context: HomeActionContext | null) => string
  url: (context: HomeActionContext | null) => string
}

function requireAction(context: HomeActionContext | null): HomeActionContext {
  if (!context) {
    throw new Error('该首页操作需要有效的运动计划动作')
  }
  return context
}

export const HOME_ACTIONS: readonly HomeAction[] = [
  {
    key: 'prescription',
    className: 'primary-button',
    requiresAction: false,
    label: () => '查看运动计划',
    url: () => '/pages/prescription/index'
  },
  {
    key: 'training',
    className: 'primary-button full-button',
    requiresAction: true,
    label: (context) => context?.internalType === 'game' ? '前往游戏训练' : '继续训练',
    url: (context) => {
      const action = requireAction(context)
      return actionEntryUrl({
        id: action.actionId,
        internal_type: action.internalType,
        source_key: action.sourceKey ?? null,
      })
    }
  },
  {
    key: 'history',
    className: 'secondary-button full-button',
    requiresAction: true,
    label: () => '查看训练历史',
    url: (context) => `/pages/action-history/index?actionId=${requireAction(context).actionId}`
  }
]
