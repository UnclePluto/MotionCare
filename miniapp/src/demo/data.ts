import { GAME_CATALOG } from '../pages/game-session/gameCatalog'
import type { GameCode } from '../pages/game-session/gameTypes'
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

export function createDemoCurrentPrescription(): NonNullable<CurrentPrescription> {
  const today = todayLocalDate()

  return {
    id: 888800,
    version: 1,
    status: 'active',
    effective_at: null,
    week_start: today,
    week_end: today,
    actions: DEMO_GAME_CODES.map(createDemoAction),
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
