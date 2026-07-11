import { PropsWithChildren } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'

import './app.scss'
import { resetRetryWindowForLaunch, startPendingGameUploadRetryLoop } from './pages/game-session/retryUpload'
import { reLaunchPendingShoulderPressUploadIfNeeded } from './pages/shoulder-press/pageState'

function App({ children }: PropsWithChildren<any>) {
  useDidShow(() => {
    void reLaunchPendingShoulderPressUploadIfNeeded(Taro).then((redirected) => {
      if (redirected) return
      resetRetryWindowForLaunch(Taro)
      startPendingGameUploadRetryLoop(Taro)
    })
  })

  return children
}

export default App
