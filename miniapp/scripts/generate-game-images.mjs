import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const outDir = join(root, 'src/assets/images/game-session')

const images = [
  ['pattern_sun', '#facc15', '#f97316', 'sun'],
  ['pattern_coconut', '#22c55e', '#854d0e', 'coconut'],
  ['pattern_boat', '#38bdf8', '#ef4444', 'boat'],
  ['pattern_lighthouse', '#f8fafc', '#dc2626', 'lighthouse'],
  ['pattern_shell', '#f9a8d4', '#fb7185', 'shell'],
  ['category_pineapple', '#facc15', '#16a34a', 'pineapple'],
  ['category_bird', '#60a5fa', '#f97316', 'bird'],
  ['category_train', '#94a3b8', '#334155', 'train'],
  ['category_drum', '#f97316', '#7c2d12', 'drum'],
  ['category_phone', '#a78bfa', '#4c1d95', 'phone'],
  ['sound_bird', '#60a5fa', '#f97316', 'bird'],
  ['sound_train', '#94a3b8', '#334155', 'train'],
  ['sound_phone', '#a78bfa', '#4c1d95', 'phone'],
  ['sound_laugh', '#fde68a', '#f59e0b', 'laugh'],
  ['sound_drum', '#f97316', '#7c2d12', 'drum'],
  ['puzzle_beach', '#38bdf8', '#facc15', 'beach'],
  ['puzzle_garden', '#4ade80', '#f472b6', 'garden'],
  ['puzzle_lighthouse', '#f8fafc', '#dc2626', 'lighthouse'],
]

function shapeFor(kind, primary, secondary) {
  if (kind === 'sun') {
    return `
      <circle cx="128" cy="128" r="48" fill="${primary}"/>
      <g stroke="${secondary}" stroke-width="14" stroke-linecap="round">
        <path d="M128 34v30M128 192v30M34 128h30M192 128h30M61 61l21 21M174 174l21 21M195 61l-21 21M82 174l-21 21"/>
      </g>`
  }
  if (kind === 'coconut') {
    return `
      <path d="M82 78c18-29 57-39 84-20 28 19 35 60 17 90-19 30-58 43-88 25-30-18-33-66-13-95z" fill="${secondary}"/>
      <circle cx="112" cy="108" r="8" fill="${primary}"/><circle cx="139" cy="102" r="8" fill="${primary}"/><circle cx="128" cy="130" r="8" fill="${primary}"/>
      <path d="M112 52c-8-19-2-35 18-47 9 20 5 36-18 47zM139 54c8-23 26-34 52-31-8 25-26 36-52 31z" fill="${primary}"/>`
  }
  if (kind === 'boat') {
    return `
      <path d="M50 156h156l-24 34H76z" fill="${secondary}"/>
      <path d="M128 42v104" stroke="#334155" stroke-width="10" stroke-linecap="round"/>
      <path d="M134 52v84h58c-12-42-32-68-58-84z" fill="${primary}"/>
      <path d="M122 66v70H70c10-34 27-57 52-70z" fill="#f8fafc"/>
      <path d="M42 202c22-10 42-10 64 0s42 10 64 0 33-9 48-3" fill="none" stroke="${primary}" stroke-width="10" stroke-linecap="round"/>`
  }
  if (kind === 'lighthouse') {
    return `
      <path d="M94 214l17-126h34l17 126z" fill="${primary}" stroke="#334155" stroke-width="8"/>
      <path d="M104 136h48M99 174h58" stroke="${secondary}" stroke-width="16"/>
      <path d="M101 86h54l-8-34h-38z" fill="${secondary}"/>
      <path d="M72 58h112" stroke="${secondary}" stroke-width="12" stroke-linecap="round"/>
      <path d="M56 214h144" stroke="#334155" stroke-width="10" stroke-linecap="round"/>`
  }
  if (kind === 'shell') {
    return `
      <path d="M58 174c17-64 43-100 70-100s53 36 70 100c-35 20-105 20-140 0z" fill="${primary}" stroke="${secondary}" stroke-width="8"/>
      <path d="M128 78v107M90 100l28 87M166 100l-28 87M70 140l39 52M186 140l-39 52" stroke="${secondary}" stroke-width="6" stroke-linecap="round"/>`
  }
  if (kind === 'pineapple') {
    return `
      <path d="M86 106c0-34 84-34 84 0v55c0 55-84 55-84 0z" fill="${primary}" stroke="#854d0e" stroke-width="8"/>
      <path d="M93 124h70M91 150h74M101 181h54M104 113l54 74M152 113l-54 74" stroke="#854d0e" stroke-width="5"/>
      <path d="M128 82c-24-15-28-38-13-65 13 19 18 39 13 65zM131 83c4-29 23-48 57-55-8 32-27 50-57 55zM125 83c-15-25-40-36-73-34 16 29 41 40 73 34z" fill="${secondary}"/>`
  }
  if (kind === 'bird') {
    return `
      <path d="M58 140c22-52 75-80 124-50 43 27 31 91-20 102-53 11-107-4-104-52z" fill="${primary}"/>
      <path d="M174 102l35 18-35 18z" fill="${secondary}"/>
      <circle cx="151" cy="105" r="7" fill="#0f172a"/>
      <path d="M88 145c25 7 47 5 66-6" stroke="#f8fafc" stroke-width="9" stroke-linecap="round"/>
      <path d="M116 190v24M148 188v26" stroke="${secondary}" stroke-width="8" stroke-linecap="round"/>`
  }
  if (kind === 'train') {
    return `
      <rect x="50" y="92" width="154" height="82" rx="16" fill="${primary}" stroke="${secondary}" stroke-width="8"/>
      <rect x="74" y="112" width="38" height="28" rx="6" fill="#e0f2fe"/>
      <rect x="127" y="112" width="38" height="28" rx="6" fill="#e0f2fe"/>
      <circle cx="88" cy="184" r="16" fill="${secondary}"/><circle cx="166" cy="184" r="16" fill="${secondary}"/>
      <path d="M40 206h176" stroke="${secondary}" stroke-width="10" stroke-linecap="round"/>`
  }
  if (kind === 'drum') {
    return `
      <ellipse cx="128" cy="78" rx="62" ry="24" fill="#fed7aa" stroke="${secondary}" stroke-width="8"/>
      <path d="M66 78v86c0 14 28 26 62 26s62-12 62-26V78" fill="${primary}" stroke="${secondary}" stroke-width="8"/>
      <path d="M84 100l88 58M172 100l-88 58" stroke="#fed7aa" stroke-width="8"/>
      <path d="M62 48l44 36M194 48l-44 36" stroke="${secondary}" stroke-width="9" stroke-linecap="round"/>`
  }
  if (kind === 'phone') {
    return `
      <rect x="83" y="42" width="90" height="172" rx="22" fill="${primary}" stroke="${secondary}" stroke-width="8"/>
      <rect x="99" y="68" width="58" height="104" rx="8" fill="#f5f3ff"/>
      <circle cx="128" cy="192" r="9" fill="#f5f3ff"/>
      <path d="M188 76c14 21 14 51 0 72M207 58c23 34 23 82 0 116" stroke="${primary}" stroke-width="9" stroke-linecap="round"/>`
  }
  if (kind === 'laugh') {
    return `
      <circle cx="128" cy="128" r="78" fill="${primary}" stroke="${secondary}" stroke-width="8"/>
      <path d="M92 112c9-9 20-9 29 0M135 112c9-9 20-9 29 0" stroke="#7c2d12" stroke-width="8" stroke-linecap="round"/>
      <path d="M82 142c18 42 74 52 104 0z" fill="#fff7ed" stroke="#7c2d12" stroke-width="8"/>
      <path d="M91 148h90" stroke="#7c2d12" stroke-width="5"/>`
  }
  if (kind === 'beach') {
    return `
      <path d="M28 94c47-32 102-31 200 0v134H28z" fill="${primary}"/>
      <path d="M28 150c58-24 119-25 200 0v78H28z" fill="${secondary}"/>
      <circle cx="58" cy="54" r="23" fill="#f97316"/>
      <path d="M72 194c33-16 68-16 112 0" stroke="#0f766e" stroke-width="10" stroke-linecap="round"/>`
  }
  if (kind === 'garden') {
    return `
      <rect x="34" y="128" width="188" height="86" rx="20" fill="${primary}"/>
      <path d="M70 128c18-48 44-48 58 0M128 128c22-65 55-65 75 0" fill="#16a34a"/>
      <circle cx="82" cy="86" r="22" fill="${secondary}"/><circle cx="170" cy="78" r="22" fill="#facc15"/>
      <path d="M82 108v55M170 100v63" stroke="#166534" stroke-width="8" stroke-linecap="round"/>`
  }
  return `<circle cx="128" cy="128" r="72" fill="${primary}" stroke="${secondary}" stroke-width="10"/>`
}

function svgFor(name, primary, secondary, kind) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256" role="img" aria-label="${name}">
  <rect width="256" height="256" rx="36" fill="#f8fafc"/>
  <circle cx="206" cy="50" r="18" fill="#e2e8f0"/>
  ${shapeFor(kind, primary, secondary)}
</svg>
`
}

mkdirSync(outDir, { recursive: true })

for (const [name, primary, secondary, kind] of images) {
  writeFileSync(join(outDir, `${name}.svg`), svgFor(name, primary, secondary, kind))
  console.log(`generated ${name}.svg`)
}
