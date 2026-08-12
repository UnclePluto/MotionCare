import { readFileSync, readdirSync } from 'node:fs'
import { dirname, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

const SRC_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    if (!entry.name.match(/\.tsx?$/) || entry.name.includes('.test.')) return []
    return [path]
  })
}

function isRuntimeImport(node: ts.ImportDeclaration): boolean {
  if (!node.importClause) return true
  if (node.importClause.isTypeOnly) return false
  const bindings = node.importClause.namedBindings
  return !bindings || !ts.isNamedImports(bindings) || bindings.elements.some((element) => !element.isTypeOnly)
}

describe('游戏目录主包边界', () => {
  it('禁止演示主包生产源码运行时导入分包模块', () => {
    const appConfig = readFileSync(resolve(SRC_ROOT, 'app.config.ts'), 'utf8')
    const subpackageRoots = [...appConfig.matchAll(/\broot:\s*['"]([^'"]+)['"]/g)]
      .map((match) => match[1])
    const violations: string[] = []

    for (const file of sourceFiles(resolve(SRC_ROOT, 'demo'))) {
      const sourceRelativePath = relative(SRC_ROOT, file).replaceAll('\\', '/')
      if (subpackageRoots.some((root) => sourceRelativePath.startsWith(`${root}/`))) continue

      const source = ts.createSourceFile(
        file,
        readFileSync(file, 'utf8'),
        ts.ScriptTarget.Latest,
        true,
        file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
      )
      for (const node of source.statements) {
        if (!ts.isImportDeclaration(node) || !isRuntimeImport(node)) continue
        if (!ts.isStringLiteral(node.moduleSpecifier) || !node.moduleSpecifier.text.startsWith('.')) continue

        const target = relative(SRC_ROOT, resolve(dirname(file), node.moduleSpecifier.text))
          .replaceAll('\\', '/')
        if (subpackageRoots.some((root) => target === root || target.startsWith(`${root}/`))) {
          violations.push(`${sourceRelativePath} -> ${node.moduleSpecifier.text}`)
        }
      }
    }

    expect(violations).toEqual([])
  })

  it('共享目录保持六个游戏的代码、名称与来源映射契约', async () => {
    const { GAME_CATALOG, gameCodeForActionSource } = await import('./catalog')

    expect(Object.values(GAME_CATALOG).map((game) => [game.code, game.name])).toEqual([
      ['game-memory-color-sequence', '颜色顺序记忆'],
      ['game-memory-pattern-sequence', '图案顺序记忆'],
      ['game-executive-inhibition', '反应抑制'],
      ['game-executive-category-switch', '分类切换'],
      ['game-audiovisual-sound-discrimination', '声音辨别'],
      ['game-audiovisual-puzzle', '拼图'],
    ])
    expect(gameCodeForActionSource('game-audiovisual-puzzle')).toBe('game-audiovisual-puzzle')
    expect(gameCodeForActionSource('unknown')).toBeNull()
    expect(gameCodeForActionSource(null)).toBeNull()
  })
})
