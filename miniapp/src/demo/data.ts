import { GAME_CATALOG } from '../game/catalog'
import type { GameCode } from '../game/catalog'
import { SHOULDER_PRESS_SOURCE_KEY } from '../pages/shoulder-press/session'
import type { CurrentPrescription, HomeData } from '../types/patientApp'
import { todayLocalDate } from '../utils/date'

const DEMO_GAME_CODES: readonly GameCode[] = [
  'game-memory-color-sequence',
  'game-memory-pattern-sequence',
  'game-executive-inhibition',
  'game-executive-category-switch',
  'game-audiovisual-sound-discrimination',
  'game-audiovisual-puzzle',
]

export const DEMO_SHOULDER_PRESS_VIDEO_URL = 'https://cdn.whestsun.com/examples/shoulder-press/IMG_0383_SDR.mp4?e=2101639122&token=wDcTeQDwD9lRRZ4uxwE1qEbRbIZHvRXSbA0eLBpW:18Lf7MbPH0Rag3TpJUBldzuGHAY='

function createDemoAction(gameCode: GameCode, index: number) {
  const id = 888801 + index

  return {
    id,
    action_library_item: id,
    source_key: gameCode,
    action_name: GAME_CATALOG[gameCode].name,
    training_type: '游戏训练',
    internal_type: 'game' as const,
    action_type: '益智游戏',
    action_instruction: `${GAME_CATALOG[gameCode].name}功能体验`,
    video_url: '',
    has_ai_supervision: false,
    weekly_frequency: '体验一次',
    duration_minutes: 1,
    weekly_target_count: 1,
    weekly_completed_count: 0,
    difficulty: '简单',
    notes: '',
    sort_order: index + 1,
    recent_record: null,
  }
}

function createDemoShoulderPressAction() {
  return {
    id: 888807,
    action_library_item: 888807,
    source_key: SHOULDER_PRESS_SOURCE_KEY,
    action_name: '肩部推举',
    training_type: '抗阻训练',
    internal_type: 'motion' as const,
    action_type: '抗阻训练',
    action_instruction: '保持身体稳定，双臂缓慢向上推举，再平稳回到起始位置。',
    video_url: DEMO_SHOULDER_PRESS_VIDEO_URL,
    has_ai_supervision: false,
    weekly_frequency: '体验一次',
    duration_minutes: 1,
    weekly_target_count: 1,
    weekly_completed_count: 0,
    difficulty: '简单',
    notes: '',
    sort_order: 7,
    recent_record: null,
  }
}

export function createDemoCurrentPrescription(): NonNullable<CurrentPrescription> {
  const today = todayLocalDate()

  return {
    id: 888800,
    version: 1,
    status: 'active',
    effective_at: null,
    week_start: today,
    week_end: today,
    actions: [
      ...DEMO_GAME_CODES.map(createDemoAction),
      createDemoShoulderPressAction(),
    ],
  }
}

export function createDemoHomeData(): HomeData {
  return {
    project_patient_id: 8888,
    patient: { id: 8888, name: '用户01' },
    project: { id: 8888, name: '功能展示' },
    today: todayLocalDate(),
    current_prescription: createDemoCurrentPrescription(),
  }
}
