import { PropsWithChildren } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'

import './app.scss'
import { getPatientAppToken } from './auth/token'
import { isDemoSession } from './demo/session'
import {
  resetRetryWindowForLaunch,
  startPendingGameUploadRetryLoop,
  stopPendingGameUploadRetryLoop
} from './pages/game-session/retryUpload'
import { handlePendingShoulderPressUploadOnAppShow } from './pages/shoulder-press/pageState'

function App({ children }: PropsWithChildren<any>) {
  useDidShow(() => {
    if (isDemoSession()) {
      stopPendingGameUploadRetryLoop()
      return
    }
    if (!getPatientAppToken()) {
      stopPendingGameUploadRetryLoop()
      return
    }
    void handlePendingShoulderPressUploadOnAppShow(Taro).then((handled) => {
      if (handled) return
      resetRetryWindowForLaunch(Taro)
      startPendingGameUploadRetryLoop(Taro)
    })
  })

  return children
}

export default App
