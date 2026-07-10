import { PropsWithChildren } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'

import './app.scss'
import { resetRetryWindowForLaunch, startPendingGameUploadRetryLoop } from './pages/game-session/retryUpload'
import {
  buildShoulderPressUploadUrl,
  loadPendingShoulderPressSession
} from './pages/shoulder-press/session'

function App({ children }: PropsWithChildren<any>) {
  useDidShow(() => {
    const pendingShoulderPress = loadPendingShoulderPressSession(Taro)
    if (pendingShoulderPress && !pendingShoulderPress.finalized) {
      Taro.reLaunch({ url: buildShoulderPressUploadUrl() })
      return
    }
    resetRetryWindowForLaunch(Taro)
    startPendingGameUploadRetryLoop(Taro)
  })

  return children
}

export default App
