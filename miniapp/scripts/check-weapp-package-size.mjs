import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import { assertPackageBudgets, measureWeappPackages } from './weappPackageSize.mjs'

const MIB = 1024 * 1024
const distRoot = resolve(process.cwd(), 'dist')

function formatPackage(label, report) {
  return `${label} (${report.name}): ${report.bytes} 字节 (${(report.bytes / 1024).toFixed(2)} KiB)`
}

async function main() {
  const appConfig = JSON.parse(await readFile(resolve(distRoot, 'app.json'), 'utf8'))
  const report = await measureWeappPackages({ appConfig, distRoot })

  assertPackageBudgets(report, {
    forbiddenDirectories: [
      'pages/game-session/assets/images',
      'features/motion-training/assets/audio/instructions',
    ],
    hardPackage: 2 * MIB,
    hardTotal: 20 * MIB,
    main: 1.2 * MIB,
    subpackage: 1.5 * MIB,
    subpackageOverrides: {
      'pages/game-session': 1.3 * MIB,
    },
  })

  console.log('微信小程序代码包体检查通过')
  console.log(formatPackage('主包', report.main))
  for (const name of Object.keys(report.subpackages).sort()) {
    console.log(formatPackage('分包', report.subpackages[name]))
  }
  console.log(formatPackage('总包', report.total))
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error)
  process.exitCode = 1
})
