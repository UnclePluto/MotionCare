import type { GameDifficulty } from './gameTypes'

export type CategoryRule = 'kind' | 'color' | 'scene'

export type CategoryItem = {
  id: string
  label: string
  imageSrc: string
  fallback: string
  kind: string
  color: string
  scene: string
}

export type CategorySwitchRound = {
  item: CategoryItem
  rule: CategoryRule
  ruleLabel: string
  options: string[]
  correctOption: string
  timeoutMs: number
}

export type CreateCategorySwitchRoundOptions = {
  previousRule?: CategoryRule
  random?: () => number
}

const ITEMS: CategoryItem[] = [
  {
    id: 'pineapple',
    label: '菠萝',
    imageSrc: '/assets/images/game-session/category_pineapple.svg',
    fallback: '果',
    kind: '水果',
    color: '黄色',
    scene: '海岛',
  },
  {
    id: 'bird',
    label: '小鸟',
    imageSrc: '/assets/images/game-session/category_bird.svg',
    fallback: '鸟',
    kind: '动物',
    color: '蓝色',
    scene: '户外',
  },
  {
    id: 'train',
    label: '火车',
    imageSrc: '/assets/images/game-session/category_train.svg',
    fallback: '车',
    kind: '交通',
    color: '灰色',
    scene: '室外',
  },
  {
    id: 'drum',
    label: '鼓',
    imageSrc: '/assets/images/game-session/category_drum.svg',
    fallback: '鼓',
    kind: '乐器',
    color: '红色',
    scene: '室内',
  },
  {
    id: 'phone',
    label: '电话',
    imageSrc: '/assets/images/game-session/category_phone.svg',
    fallback: '话',
    kind: '工具',
    color: '蓝色',
    scene: '室内',
  },
]

const RULE_LABEL: Record<CategoryRule, string> = {
  kind: '按物体类别选择',
  color: '按主要颜色选择',
  scene: '按使用场景选择',
}

const OPTIONS: Record<CategoryRule, string[]> = {
  kind: ['水果', '动物', '交通', '乐器', '工具'],
  color: ['黄色', '蓝色', '灰色', '红色'],
  scene: ['海岛', '户外', '室外', '室内'],
}

const CONFIG: Record<GameDifficulty, { rules: CategoryRule[]; optionLimit: number; timeoutMs: number }> = {
  简单: { rules: ['kind'], optionLimit: 3, timeoutMs: 7000 },
  中等: { rules: ['kind', 'color'], optionLimit: 4, timeoutMs: 5500 },
  困难: { rules: ['kind', 'color', 'scene'], optionLimit: 4, timeoutMs: 4200 },
}

function pickIndex(length: number, random: () => number): number {
  const value = random()
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.9999999999999999) : 0
  return Math.floor(normalized * length)
}

function correctFor(item: CategoryItem, rule: CategoryRule): string {
  if (rule === 'kind') return item.kind
  if (rule === 'color') return item.color
  return item.scene
}

function shuffle<T>(values: T[], random: () => number): T[] {
  const result = [...values]
  for (let index = result.length - 1; index > 0; index -= 1) {
    const swapIndex = pickIndex(index + 1, random)
    const current = result[index]
    result[index] = result[swapIndex]
    result[swapIndex] = current
  }
  return result
}

function pickRule(rules: CategoryRule[], random: () => number, previousRule?: CategoryRule): CategoryRule {
  const candidates = previousRule === undefined ? rules : rules.filter((rule) => rule !== previousRule)
  const availableRules = candidates.length > 0 ? candidates : rules
  return availableRules[pickIndex(availableRules.length, random)]
}

function buildOptions(rule: CategoryRule, correctOption: string, limit: number, random: () => number): string[] {
  const values = OPTIONS[rule]
  const result = [correctOption, ...values.filter((item) => item !== correctOption)].slice(0, limit)
  return shuffle(result, random)
}

export function createCategorySwitchRound(
  difficulty: GameDifficulty,
  options: CreateCategorySwitchRoundOptions = {}
): CategorySwitchRound {
  const random = options.random ?? Math.random
  const previousRule = options.previousRule
  const config = CONFIG[difficulty]
  const item = ITEMS[pickIndex(ITEMS.length, random)]
  const rule = pickRule(config.rules, random, previousRule)
  const correctOption = correctFor(item, rule)

  return {
    item,
    rule,
    ruleLabel: RULE_LABEL[rule],
    options: buildOptions(rule, correctOption, config.optionLimit, random),
    correctOption,
    timeoutMs: config.timeoutMs,
  }
}

export function evaluateCategorySwitchAttempt(round: Pick<CategorySwitchRound, 'correctOption'>, selectedOption: string) {
  return {
    correct: selectedOption === round.correctOption,
    correctOption: round.correctOption,
    selectedOption,
  }
}
