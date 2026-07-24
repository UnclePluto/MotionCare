export type HomeActionContext = {
  actionId: number
  internalType: 'motion' | 'game' | 'video'
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
    throw new Error('该首页操作需要有效的处方动作')
  }
  return context
}

export const HOME_ACTIONS: readonly HomeAction[] = [
  {
    key: 'prescription',
    className: 'primary-button',
    requiresAction: false,
    label: () => '查看处方',
    url: () => '/pages/prescription/index'
  },
  {
    key: 'training',
    className: 'primary-button full-button',
    requiresAction: true,
    label: (context) => context?.internalType === 'game' ? '前往游戏训练' : '继续训练',
    url: (context) => {
      const action = requireAction(context)
      return action.internalType === 'game'
        ? '/pages/prescription/index'
        : `/pages/training/index?actionId=${action.actionId}`
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
