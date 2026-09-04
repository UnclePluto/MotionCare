import { readdir, stat } from 'node:fs/promises'
import { join } from 'node:path'

function normalizeRelativePath(value, label) {
  if (typeof value !== 'string') {
    throw new TypeError(`${label} 必须是字符串`)
  }

  const normalized = value
    .replaceAll('\\', '/')
    .replace(/^\.\/+/, '')
    .replace(/^\/+|\/+$/g, '')
  if (!normalized || normalized.split('/').some((part) => part === '.' || part === '..' || part === '')) {
    throw new Error(`${label} 不是合法的相对路径：${value}`)
  }
  return normalized
}

async function collectOutputEntries(distRoot) {
  const directories = []
  const files = []

  async function walk(relativeDirectory = '') {
    const absoluteDirectory = relativeDirectory ? join(distRoot, relativeDirectory) : distRoot
    const entries = await readdir(absoluteDirectory, { withFileTypes: true })

    for (const entry of entries) {
      const relativePath = relativeDirectory ? `${relativeDirectory}/${entry.name}` : entry.name
      const absolutePath = join(distRoot, relativePath)
      const metadata = await stat(absolutePath)
      if (metadata.isDirectory()) {
        directories.push(relativePath)
        await walk(relativePath)
      } else if (metadata.isFile()) {
        files.push({ bytes: metadata.size, path: relativePath })
      }
    }
  }

  await walk()
  return {
    directories: directories.sort(),
    files: files.sort((left, right) => left.path.localeCompare(right.path)),
  }
}

function packageReport(name, files) {
  return {
    bytes: files.reduce((total, file) => total + file.bytes, 0),
    files,
    name,
  }
}

export async function measureWeappPackages({ distRoot, appConfig }) {
  const packageConfig = appConfig?.subPackages ?? appConfig?.subpackages ?? []
  if (!Array.isArray(packageConfig)) {
    throw new TypeError('app.json 的 subPackages/subpackages 必须是数组')
  }

  const roots = packageConfig.map((entry, index) =>
    normalizeRelativePath(entry?.root, `第 ${index + 1} 个分包 root`),
  )
  if (new Set(roots).size !== roots.length) {
    throw new Error('app.json 包含重复的分包 root')
  }

  const classifiedRoots = [...roots].sort((left, right) => right.length - left.length)
  const { directories, files } = await collectOutputEntries(distRoot)
  const mainFiles = []
  const subpackageFiles = Object.fromEntries(roots.map((root) => [root, []]))

  for (const file of files) {
    const root = classifiedRoots.find(
      (candidate) => file.path === candidate || file.path.startsWith(`${candidate}/`),
    )
    if (root) {
      subpackageFiles[root].push(file)
    } else {
      mainFiles.push(file)
    }
  }

  const subpackages = Object.fromEntries(
    roots.map((root) => [root, packageReport(root, subpackageFiles[root])]),
  )

  return {
    directories,
    main: packageReport('main', mainFiles),
    subpackages,
    total: packageReport('total', files),
  }
}

function largestFiles(files) {
  return [...files]
    .sort((left, right) => right.bytes - left.bytes || left.path.localeCompare(right.path))
    .slice(0, 10)
}

function packageDiagnostic(label, report, threshold) {
  const files = largestFiles(report.files)
  const details = files.length
    ? files.map((file) => `- ${file.path}: ${file.bytes} 字节`).join('\n')
    : '- 无文件'
  return `${label} (${report.name})，实际 ${report.bytes} 字节，阈值 ${threshold} 字节。\n` +
    `最大的 10 个文件（最多展示 10 个）：\n${details}`
}

function budgetError(label, report, threshold) {
  return new Error(`包体预算超限：${packageDiagnostic(label, report, threshold)}`)
}

function assertThreshold(label, report, threshold) {
  if (typeof threshold === 'number' && report.bytes > threshold) {
    throw budgetError(label, report, threshold)
  }
}

export function assertPackageBudgets(report, budgets) {
  for (const forbiddenDirectory of budgets.forbiddenDirectories ?? []) {
    const normalized = normalizeRelativePath(forbiddenDirectory, '禁止目录')
    if (report.directories.includes(normalized)) {
      const subpackageName = Object.keys(report.subpackages)
        .sort((left, right) => right.length - left.length)
        .find((name) => normalized === name || normalized.startsWith(`${name}/`))
      const packageReport = subpackageName ? report.subpackages[subpackageName] : report.main
      const label = subpackageName ? '分包' : '主包'
      const threshold = subpackageName
        ? budgets.subpackageOverrides?.[subpackageName] ?? budgets.subpackage
        : budgets.main
      throw new Error(
        `小程序代码包中存在禁止目录：${normalized}\n` +
          packageDiagnostic(label, packageReport, threshold),
      )
    }
  }

  assertThreshold('主包', report.main, budgets.hardPackage)
  for (const name of Object.keys(report.subpackages).sort()) {
    assertThreshold('分包', report.subpackages[name], budgets.hardPackage)
  }
  assertThreshold('全部代码包', report.total, budgets.hardTotal)

  assertThreshold('主包', report.main, budgets.main)
  for (const name of Object.keys(report.subpackages).sort()) {
    const threshold = budgets.subpackageOverrides?.[name] ?? budgets.subpackage
    assertThreshold('分包', report.subpackages[name], threshold)
  }
}
