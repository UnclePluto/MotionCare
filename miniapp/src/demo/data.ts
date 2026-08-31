import { GAME_CATALOG } from '../game/catalog'
import type { GameCode } from '../game/catalog'
import type { MotionSourceKey } from '../features/motion-training/catalog'
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

type DemoMotionVideoUrls = Partial<Record<MotionSourceKey, string>>

const DEMO_MOTION_ACTIONS: ReadonlyArray<{
  id: number
  sourceKey: MotionSourceKey
  name: string
  trainingType: string
  instruction: string
}> = [
  {
    id: 888808,
    sourceKey: 'motion-aerobic-high-knee',
    name: '椰林步道模拟（原地高抬腿+摆臂）',
    trainingType: '有氧训练',
    instruction: '原地高抬腿并自然摆臂，保持躯干稳定。',
  },
  {
    id: 888809,
    sourceKey: 'motion-balance-sit-stand',
    name: '坐站转移训练',
    trainingType: '平衡训练',
    instruction: '双脚稳定踩地，从坐姿平稳站起，再缓慢坐下。',
  },
  {
    id: 888810,
    sourceKey: 'motion-resistance-row',
    name: '坐姿划船',
    trainingType: '抗阻训练',
    instruction: '保持背部挺直，双肘贴近身体向后拉，再缓慢还原。',
  },
  {
    id: 888811,
    sourceKey: 'motion-resistance-leg-kickback',
    name: '腿部后踢',
    trainingType: '抗阻训练',
    instruction: '保持躯干稳定，单腿缓慢向后伸展，再平稳回到起始位置。',
  },
  {
    id: 888807,
    sourceKey: 'motion-resistance-shoulder-press',
    name: '肩部推举',
    trainingType: '抗阻训练',
    instruction: '保持身体稳定，双臂缓慢向上推举，再平稳回到起始位置。',
  },
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

function createDemoMotionAction(
  definition: typeof DEMO_MOTION_ACTIONS[number],
  index: number,
  videoUrls: DemoMotionVideoUrls
) {
  const videoUrl = videoUrls[definition.sourceKey]?.trim() ?? ''
  return {
    id: definition.id,
    action_library_item: definition.id,
    source_key: definition.sourceKey,
    action_name: definition.name,
    training_type: definition.trainingType,
    internal_type: 'motion' as const,
    action_type: definition.trainingType,
    action_instruction: definition.instruction,
    video_url: videoUrl,
    video_unavailable: !videoUrl,
    has_ai_supervision: false,
    weekly_frequency: '体验一次',
    duration_minutes: 10,
    weekly_target_count: 1,
    weekly_completed_count: 0,
    difficulty: '简单',
    notes: '',
    sort_order: index + 7,
    recent_record: null,
  }
}

export function createDemoCurrentPrescription(
  videoUrls: DemoMotionVideoUrls
): NonNullable<CurrentPrescription> {
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
      ...DEMO_MOTION_ACTIONS.map((definition, index) => (
        createDemoMotionAction(definition, index, videoUrls)
      )),
    ],
  }
}

export function createDemoHomeData(videoUrls: DemoMotionVideoUrls): HomeData {
  return {
    project_patient_id: 8888,
    patient: { id: 8888, name: '用户01' },
    project: { id: 8888, name: '功能展示' },
    today: todayLocalDate(),
    current_prescription: createDemoCurrentPrescription(videoUrls),
  }
}
