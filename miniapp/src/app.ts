import { PropsWithChildren } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'

import './app.scss'
import { resetRetryWindowForLaunch, startPendingGameUploadRetryLoop } from './pages/game-session/retryUpload'

function App({ children }: PropsWithChildren<any>) {
  useDidShow(() => {
    resetRetryWindowForLaunch(Taro)
    startPendingGameUploadRetryLoop(Taro)
  })

  return children
}

export default App
