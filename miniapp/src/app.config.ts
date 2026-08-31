export default defineAppConfig({
  pages: [
    'pages/bind/index',
    'pages/home/index',
    'pages/prescription/index',
    'pages/training/index',
    'pages/motion-training/index',
    'pages/motion-training/preview',
    'pages/motion-training/camera',
    'pages/motion-training/upload',
    'pages/shoulder-press/index',
    'pages/shoulder-press/preview',
    'pages/shoulder-press/camera',
    'pages/shoulder-press/upload',
    'pages/action-history/index'
  ],
  subPackages: [
    {
      root: 'pages/game-session',
      pages: ['index']
    }
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#ffffff',
    navigationBarTitleText: 'MotionCare',
    navigationBarTextStyle: 'black'
  }
})
