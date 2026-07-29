export default defineAppConfig({
  pages: [
    'pages/bind/index',
    'pages/home/index',
    'pages/prescription/index',
    'pages/training/index',
    'pages/shoulder-press/index',
    'pages/shoulder-press/upload',
    'pages/action-history/index',
    'pages/daily-health/index'
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
