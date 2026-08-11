import { readFileSync, readdirSync } from 'node:fs'
import { relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { NEUTRAL_TERM_REPLACEMENTS } from './neutralTerminology'

const miniappRoot = process.cwd()
const sourceRoot = resolve(miniappRoot, 'src')
const excludedSourceFile = resolve(sourceRoot, 'copy/neutralTerminology.ts')
const productionExtensions = new Set(['.ts', '.tsx', '.json'])

function productionSourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const filePath = resolve(directory, entry.name)

    if (entry.isDirectory()) {
      return productionSourceFiles(filePath)
    }

    const isProductionFile = [...productionExtensions].some((extension) =>
      entry.name.endsWith(extension),
    )
    const isTestFile = /\.test\.tsx?$/.test(entry.name)

    return isProductionFile && !isTestFile && filePath !== excludedSourceFile ? [filePath] : []
  })
}

describe('生产展示文案中性术语门禁', () => {
  it('不允许原医疗词进入生产源码或项目配置', () => {
    const files = [
      ...productionSourceFiles(sourceRoot),
      resolve(miniappRoot, 'project.config.json'),
    ]

    for (const filePath of files) {
      const contents = readFileSync(filePath, 'utf8')
      const displayPath = relative(miniappRoot, filePath)

      for (const [source] of NEUTRAL_TERM_REPLACEMENTS) {
        expect(contents, `${displayPath} 命中原词「${source}」`).not.toContain(source)
      }
    }
  })
})
