import { PropsWithChildren } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'

import './app.scss'
import { resetRetryWindowForLaunch, startPendingGameUploadRetryLoop } from './pages/game-session/retryUpload'
import { handlePendingShoulderPressUploadOnAppShow } from './pages/shoulder-press/pageState'

function App({ children }: PropsWithChildren<any>) {
  useDidShow(() => {
    void handlePendingShoulderPressUploadOnAppShow(Taro).then((handled) => {
      if (handled) return
      resetRetryWindowForLaunch(Taro)
      startPendingGameUploadRetryLoop(Taro)
    })
  })

  return children
}

export default App
