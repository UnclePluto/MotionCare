import type { GameCode, GameDifficulty } from './gameTypes'

export const DIFFICULTY_OPTIONS: GameDifficulty[] = ['简单', '中等', '困难']
export function normalizeDifficulty(value: string): GameDifficulty {
  return DIFFICULTY_OPTIONS.includes(value as GameDifficulty) ? value as GameDifficulty : '简单'
}

export function gameDifficultyDescription(code: GameCode, difficulty: GameDifficulty): string {
  const level = DIFFICULTY_OPTIONS.indexOf(difficulty)
  const count = [3, 4, 5][level]
  switch (code) {
    case 'game-memory-color-sequence': return `记住 ${count} 个颜色的顺序，每项展示 2 秒`
    case 'game-memory-pattern-sequence': return `记住 ${count} 个图案的顺序，每项展示 2 秒`
    case 'game-executive-inhibition': return `从 ${[4, 6, 9][level]} 个数字中选出不同的一个`
    case 'game-executive-category-switch': return `判断物品类别，从 ${count} 个选项中选择`
    case 'game-audiovisual-sound-discrimination': return `依次试听 ${count} 张声音卡片，再选择目标声音对应的卡片`
    case 'game-audiovisual-puzzle': return `交换 ${[4, 6, 9][level]} 块拼图的位置，拼回完整图片`
  }
}
