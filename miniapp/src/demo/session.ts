export const DEMO_BINDING_CODE = '8888' as const

let demoSessionActive = false

export function startDemoSession(): void {
  demoSessionActive = true
}

export function isDemoSession(): boolean {
  return demoSessionActive
}
