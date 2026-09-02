import { fileURLToPath } from 'node:url'

import postcss from 'postcss'
import * as sass from 'sass'
import { describe, expect, it } from 'vitest'

function compiledGameStyles() {
  const appScssPath = fileURLToPath(new URL('../../app.scss', import.meta.url))
  return postcss.parse(sass.compile(appScssPath).css)
}

function declarationsFor(selector: string): Record<string, string> {
  const declarations: Record<string, string> = {}
  compiledGameStyles().walkRules((rule) => {
    const selectors = rule.selector.split(',').map((item) => item.trim())
    if (!selectors.includes(selector)) return
    rule.walkDecls((declaration) => {
      declarations[declaration.prop] = declaration.value
    })
  })
  return declarations
}

describe('游戏选中样式', () => {
  it('拼图选中态只使用完整边框，不叠加覆盖层、光晕或缩放', () => {
    const selectedSelector = '.game-session-page .puzzle-tile.selected'
    const selectedStyle = declarationsFor(selectedSelector)
    const overlaySelectors: string[] = []

    compiledGameStyles().walkRules((rule) => {
      if (rule.selector.includes('.puzzle-tile.selected::after')) overlaySelectors.push(rule.selector)
    })

    expect(selectedStyle.border).toBe('4px solid #ff6b5a')
    expect(selectedStyle['box-shadow']).toBeUndefined()
    expect(selectedStyle.transform).toBeUndefined()
    expect(overlaySelectors).toEqual([])
  })

  it('声音卡初始盖牌和答错时不翻转，只在试听回盖时播放回转动画', () => {
    const backStyle = declarationsFor('.game-session-page .sound-card-back .sound-card-flip')
    const wrongStyle = declarationsFor('.game-session-page .sound-card-wrong .sound-card-flip')
    const returnedStyle = declarationsFor('.game-session-page .sound-card-returned .sound-card-flip')

    expect(backStyle.animation).toBeUndefined()
    expect(wrongStyle.animation).toBeUndefined()
    expect(returnedStyle.animation).toBe('card-flip-back 180ms ease-out')
  })

  it('声音卡与拼图块覆盖全局按压缩放，保持选中和错误状态稳定', () => {
    expect(declarationsFor('.game-session-page .sound-card:active').transform).toBe('none')
    expect(declarationsFor('.game-session-page .puzzle-tile:active').transform).toBe('none')
  })

  it('声音编号背面参与正常布局且不依赖 backface visibility', () => {
    const backFaceStyle = declarationsFor('.game-session-page .sound-card-back-face')
    const compiledCss = compiledGameStyles().toString()

    expect(backFaceStyle.display).toBe('flex')
    expect(backFaceStyle.width).toBe('100%')
    expect(backFaceStyle['min-height']).toBe('182px')
    expect(backFaceStyle.position).toBeUndefined()
    expect(compiledCss).not.toContain('backface-visibility')
  })
})
