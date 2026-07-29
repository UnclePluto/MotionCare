import { PropsWithChildren } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'

import './app.scss'
import { resetRetryWindowForLaunch, startPendingGameUploadRetryLoop } from './pages/game-session/retryUpload'
import { shouldResumeShoulderPressUpload } from './pages/shoulder-press/appResume'
import {
  buildShoulderPressUploadUrl,
  loadShoulderPressSession,
} from './pages/shoulder-press/session'

function App({ children }: PropsWithChildren<any>) {
  useDidShow(() => {
    resetRetryWindowForLaunch(Taro)
    startPendingGameUploadRetryLoop(Taro)
    const pages = Taro.getCurrentPages()
    const currentRoute = pages[pages.length - 1]?.route ?? ''
    if (shouldResumeShoulderPressUpload(loadShoulderPressSession(Taro), currentRoute)) {
      void Taro.reLaunch({ url: buildShoulderPressUploadUrl() })
    }
  })

  return children
}

export default App
