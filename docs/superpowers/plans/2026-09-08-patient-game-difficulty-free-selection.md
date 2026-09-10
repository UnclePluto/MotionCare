# 患者游戏难度自由选择实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 六款游戏在开始前开放三档自由选择，点击即生效，取消反馈要求，并以颜色和勾选清晰展示当前档位。

**Architecture:** 沿用 GameSessionPage 的准备阶段、现有三档状态与出题器，移除上限和原因门禁。训练记录继续使用原协议，新记录原因传空字符串，历史数据和补传协议保持兼容。视觉变更集中在现有准备页及样式，不重构整个游戏会话。

**Tech Stack:** Taro 4.2、React 18、TypeScript、SCSS、Vitest；Django/pytest 用于记录兼容验证。

**Spec:** `docs/superpowers/specs/2026-09-08-patient-game-difficulty-free-selection-design.md`（2026-09-08 已确认）

> 状态：implementing；Task 1–2 已在本地实施、验证并通过逐任务及最终独立审查；未提交、未合并、未发布。
> 日期：2026-09-08
> 代码基线：`c58d7aa`
> 工作区：`/Users/nick/my_dev/workout/MotionCare/.worktrees/game-difficulty-704`

## Global Constraints

- 仅在开始游戏前调整，简单、中等、困难三档均可选择。
- 可以高于或低于指导老师设定的难度。
- 点击档位立即生效，无需填写原因、提交反馈或再次确认。
- 使用颜色表达档位，同时以文字和勾选表达选择状态，不只依赖颜色。
- 进入时使用处方默认难度；调整仅用于本次训练，退出重新进入恢复处方默认值。
- `form_data.difficulty`：本次实际难度。
- `raw_detail.prescribed_difficulty`：进入时对应的处方难度。
- `raw_detail.difficulty_adjusted`：实际难度是否与处方难度不同；提高与降低都可为 true。
- `raw_detail.difficulty_adjust_reason`：新版本创建的记录统一为空字符串，保留字段以兼容现有类型和接口，不填入虚构原因。
- 历史记录及已缓存待补传记录保持原内容，包括其中已有的原因。
- 微信小程序与患者 H5 使用同一交互规则。
- 不修改 Excel 档位参数、2 秒序列展示、题目文案、音频或签名素材机制；图片准备门禁继续有效。
- 原根工作区及上一轮未提交的发布审计记录必须保留。当前三个旧审计文件和两个 node_modules 符号链接均已知来自本会话，不应重复询问或清理。
- 用户已批准设计与计划，并选择子代理逐任务实施及独立审查。不得推送主线、部署或上传新版本。遵循用户“不主动提交”偏好，未经明确提交授权不运行 git add/commit；不得将上一轮 `c58d7aa` 的发布授权扩大到新提交。

---

## 文件职责与任务边界

| 文件 | 职责 | 任务 |
| --- | --- | --- |
| `miniapp/src/pages/game-session/index.tsx` | 三档选择、会话难度初始化、移除反馈状态、上传空原因 | 1 |
| `miniapp/src/pages/game-session/gameDifficulty.ts` | 删除不再使用的反馈常量，保留档位和规则说明 | 1 |
| `miniapp/src/pages/game-session/index.integration.test.tsx` | 实际出题、门禁、选择、重进、结果记录回归 | 1 |
| `miniapp/src/pages/game-session/retryUpload.test.ts` | 新难度与历史原因在补传中保持原样 | 1 |
| `backend/apps/training/tests/test_training_current_prescription.py` | 上下调且原因为空的保存契约 | 1 |
| `miniapp/src/app.scss` | 等宽三档、三组配色、勾选与聚焦状态 | 2 |
| 两份旧游戏 spec、文档索引、changelog、本 spec/plan | 决策替代、执行与验证记录 | 2 |

`scoring.ts`、`gameTypes.ts`、`retryUpload.ts` 和后端生产代码应保持原协议。只有契约回归揭示实际问题时才做最小修正并说明原因，不能为删除反馈界面而删除历史字段。

## Task 1：三档自由选择与无反馈记录

**Files:**
- Modify: `miniapp/src/pages/game-session/index.tsx`
- Modify: `miniapp/src/pages/game-session/gameDifficulty.ts`
- Test: `miniapp/src/pages/game-session/index.integration.test.tsx`
- Test: `miniapp/src/pages/game-session/retryUpload.test.ts`
- Test: `backend/apps/training/tests/test_training_current_prescription.py`

**Interfaces:**
- Consumes: `DIFFICULTY_OPTIONS: GameDifficulty[]`、`normalizeDifficulty(value: string): GameDifficulty`、`gameDifficultyDescription(code: GameCode, difficulty: GameDifficulty): string`。
- Consumes: 现有页面测试辅助函数 `renderGame(sourceKey, actionName, difficulty?)`、`enterPlaying(page)`、`findAll`、`click`、`flushPromises`、`numberTiles`。
- Produces: 准备页三个 Button，`aria-label` 分别为简单、中等、困难；共有类 `difficulty-level-option`、颜色类 `difficulty-level-0/1/2`、选中类 `is-selected`、`aria-pressed`。
- Produces: 每个按钮内部含 `difficulty-level-check` 和 `difficulty-level-label`；外层继续使用 `difficulty-level-options`，Task 2 依赖这些稳定样式入口。
- Produces: `buildGameTrainingResult` 的页面调用继续携带 `difficultyAdjustReason: ''`；函数签名和旧数据不变。

- [x] **Step 1：核对工作边界并记录任务基线。**

读取 AGENTS.md、已批准 spec、此任务；复用现有隔离工作区，确认最新 HEAD 没有未知变化。不要操作原根的脏文件，不暂存 node_modules 链接。以下只读命令在隔离工作区执行：

```sh
git status --short
git log --oneline -15
git rev-parse HEAD
```

- [x] **Step 2：用真实页面交互替换过时的“只能降低／原因必填”用例。**

保留该文件的图片准备和生命周期回归，仅替换 `GameSessionPage 开始前降低难度` 测试组。新测试使用已有 helper，并增加下面的辅助函数；按钮文字包含勾选，所以按 `aria-label` 找档位，不依赖拼接后的全文。

```tsx
function chooseDifficulty(page: RenderedPage, level: string) {
  const option = findAll(page.element, (item) =>
    item.type === 'Button' && item.props['aria-label'] === level
  )[0]
  expect(option).toBeTruthy()
  click(option)
  page.rerender()
}

it.each([
  ['简单', '困难', 9],
  ['困难', '简单', 4],
  ['中等', '中等', 6],
])('处方%s可直接开始%s，记录空原因', async (prescribed, actual, count) => {
  prescriptionHarness.demo = false
  const page = await renderGame('game-executive-inhibition', '反应抑制', prescribed)
  const options = findAll(page.element, (item) => hasClass(item, 'difficulty-level-option'))
  expect(options.map((item) => item.props['aria-label'])).toEqual(['简单', '中等', '困难'])
  chooseDifficulty(page, actual)
  expect(findAll(page.element, (item) => hasClass(item, 'difficulty-reason-option'))).toHaveLength(0)
  expect(findAll(page.element, (item) => item.type === 'Input')).toHaveLength(0)
  await enterPlaying(page)
  expect(numberTiles(page.element)).toHaveLength(count)
  expect(findAll(page.element, (item) => hasClass(item, 'difficulty-level-option'))).toHaveLength(0)
  click(findButtonByText(page.element, '提前结束'))
  await flushPromises()
  page.rerender()
  expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledWith(expect.objectContaining({
    form_data: expect.objectContaining({
      difficulty: actual,
      raw_detail: expect.objectContaining({
        prescribed_difficulty: prescribed,
        difficulty_adjusted: actual !== prescribed,
        difficulty_adjust_reason: '',
      }),
    }),
  }))
  page.unmount()
})
```

增加完整准备页矩阵（六个 sourceKey 为 `game-memory-color-sequence`、`game-memory-pattern-sequence`、`game-executive-inhibition`、`game-executive-category-switch`、`game-audiovisual-sound-discrimination`、`game-audiovisual-puzzle`）：

```tsx
const difficultyGames = [
  ['game-memory-color-sequence', '颜色顺序记忆'],
  ['game-memory-pattern-sequence', '图案顺序记忆'],
  ['game-executive-inhibition', '反应抑制'],
  ['game-executive-category-switch', '分类转换'],
  ['game-audiovisual-sound-discrimination', '声音辨别'],
  ['game-audiovisual-puzzle', '拼图'],
] as const
const preparationCases = difficultyGames.flatMap(([code, name]) =>
  ['简单', '中等', '困难'].map((level) => [code, name, level] as const)
)
it.each(preparationCases)('%s默认%s相关准备状态：%s', async (code, name, level) => {
  const page = await renderGame(code, name, level)
  const options = findAll(page.element, (item) => hasClass(item, 'difficulty-level-option'))
  expect(options.map((item) => item.props['aria-label'])).toEqual(['简单', '中等', '困难'])
  expect(options.filter((item) => item.props['aria-pressed']).map((item) => item.props['aria-label'])).toEqual([level])
  expect(textContent(page.element)).toContain('仅用于本次训练')
  expect(textContent(page.element)).not.toContain('降低难度')
  page.unmount()
})
```

同组补充以下实际交互，代码直接复用 `chooseDifficulty`，避免只测试纯样式类：

```tsx
it('连续切换与重复点击使用最后档位，切回处方后不记调整', async () => {
  prescriptionHarness.demo = false
  const page = await renderGame('game-executive-inhibition', '反应抑制', '中等')
  for (const level of ['困难', '简单', '中等', '中等']) chooseDifficulty(page, level)
  await enterPlaying(page)
  expect(numberTiles(page.element)).toHaveLength(6)
  click(findButtonByText(page.element, '提前结束'))
  await flushPromises()
  expect(retryUploadHarness.postGameTrainingRecord).toHaveBeenCalledWith(expect.objectContaining({
    form_data: expect.objectContaining({
      difficulty: '中等',
      raw_detail: expect.objectContaining({ difficulty_adjusted: false, difficulty_adjust_reason: '' }),
    }),
  }))
  page.unmount()
})

it('退出重进恢复处方默认档位', async () => {
  const first = await renderGame('game-executive-inhibition', '反应抑制', '中等')
  chooseDifficulty(first, '困难')
  first.unmount()
  reactHarness.reset()
  taroHarness.reset()
  const second = await renderGame('game-executive-inhibition', '反应抑制', '中等')
  expect(findAll(second.element, (item) => hasClass(item, 'difficulty-level-option') && item.props['aria-pressed'])
    .map((item) => item.props['aria-label'])).toEqual(['中等'])
  second.unmount()
})
```

保留原分类题文案与 4 个选项的实际断言，改为直接选择中等再开始。给现有“图片未全部准备完成”用例在点击开始前插入 `chooseDifficulty(page, '困难')`，确认调难不绕过素材门禁。

- [x] **Step 3：先运行新页面测试，确认因旧行为失败。**

```sh
cd miniapp
npm run test -- src/pages/game-session/index.integration.test.tsx
```

预期旧实现缺少完整三档按钮、不能上调或要求原因而失败。记录失败用例与退出码；测试基础设施错误不能冒充 RED。

- [x] **Step 4：最小修改准备页状态及结果输入。**

从 import 中移除 `DIFFICULTY_REASONS`、不再使用的 `Input`；删除 `difficultyReason`、`otherDifficultyReason`、`showDifficultyChoices` 及对应 ref、加载重置、effect。删除派生的 `lowerDifficulties`、`recordedDifficultyReason`、仅服务于旧 UI 的 `adjustedDifficulty` 和索引；删除开始函数的难度上限与原因校验。

增加唯一用户选择入口，保持 ref 与可见状态同步，避免依赖延迟 effect：

```tsx
function selectDifficulty(level: GameDifficulty) {
  if (phaseRef.current !== 'setup') return
  difficultyRef.current = level
  setDifficultyIndex(DIFFICULTY_OPTIONS.indexOf(level))
  setError('')
}
```

加载处方时在已有 `setDifficultyIndex` 前同步写入 `difficultyRef.current = defaultDifficulty`。删除原只用于 state→ref 同步的 difficulty effect；`startIntro` 直接消费已同步的 ref，不再用可能较旧的渲染闭包重新覆盖它。初始化与选择仍仅接受规范化三档值。

保留准备页难度标题、数值和说明，把其余旧切换入口、恢复按钮和整个反馈面板替换为：

```tsx
<View className='difficulty-level-options'>
  {DIFFICULTY_OPTIONS.map((level, index) => (
    <Button
      key={level}
      className={`difficulty-level-option difficulty-level-${index}${difficulty === level ? ' is-selected' : ''}`}
      aria-label={level}
      aria-pressed={difficulty === level}
      onClick={() => selectDifficulty(level)}
    >
      <Text className='difficulty-level-check' aria-hidden='true'>
        {difficulty === level ? '✓' : ''}
      </Text>
      <Text className='difficulty-level-label'>{level}</Text>
    </Button>
  ))}
</View>
<Text className='muted'>仅用于本次训练</Text>
```

`endSession` 的现有 builder 调用改为 `difficultyAdjustReason: ''`。只删除 `gameDifficulty.ts` 中的 `DIFFICULTY_REASONS` 导出，其余档位、归一化和规则文案保持不变。

- [x] **Step 5：补传与后端兼容回归，保留历史原因。**

在 `retryUpload.test.ts` 增加以下用例，确认新旧 payload 均不会在补传时被重新解释。历史原因用例预计基线已通过，作为兼容守护，不要求人为制造失败。

```ts
it.each(['', '今天状态不佳'])('补传保留困难档与原始原因：%s', async (reason) => {
  const storage = memoryStorage()
  const record = payload()
  record.form_data.difficulty = '困难'
  record.form_data.raw_detail.prescribed_difficulty = '简单'
  record.form_data.raw_detail.difficulty_adjusted = true
  record.form_data.raw_detail.difficulty_adjust_reason = reason
  savePendingGameUpload(storage, record, 1000)
  const uploader = vi.fn().mockResolvedValue(undefined)
  await expect(tryUploadPendingGameRecord(storage, 1_000_000, uploader)).resolves.toBe('uploaded')
  expect(uploader).toHaveBeenCalledWith(expect.objectContaining({
    form_data: expect.objectContaining({
      difficulty: '困难',
      raw_detail: expect.objectContaining({
        prescribed_difficulty: '简单', difficulty_adjusted: true, difficulty_adjust_reason: reason,
      }),
    }),
  }))
  expect(loadPendingGameUpload(storage)).toBeNull()
})
```

在 `test_training_current_prescription.py` 追加记录兼容用例（生产 API 不因此改动）：

```python
@pytest.mark.django_db
@pytest.mark.parametrize('prescribed,actual', [('简单', '困难'), ('困难', '简单')])
def test_game_difficulty_change_accepts_empty_reason(active_prescription, prescribed, actual):
    game = ActionLibraryItem.objects.get(source_key='game-memory-color-sequence')
    action = active_prescription.add_action_snapshot(game)
    record = create_training_record(
        project_patient=active_prescription.project_patient,
        training_date='2026-09-08',
        prescription_action=action,
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=10,
        score=90,
        form_data={
            'accuracy_rate': 90, 'error_count': 1, 'difficulty': actual,
            'raw_detail': {
                'game_code': 'game-memory-color-sequence',
                'prescribed_difficulty': prescribed,
                'difficulty_adjusted': True,
                'difficulty_adjust_reason': '',
            },
        },
    )
    record.refresh_from_db()
    assert record.form_data['difficulty'] == actual
    assert record.form_data['raw_detail']['prescribed_difficulty'] == prescribed
    assert record.form_data['raw_detail']['difficulty_adjusted'] is True
    assert record.form_data['raw_detail']['difficulty_adjust_reason'] == ''
```

- [x] **Step 6：运行聚焦验证并检查残留引用。**

```sh
cd miniapp
npm run test -- src/pages/game-session/index.integration.test.tsx src/pages/game-session/scoring.test.ts src/pages/game-session/retryUpload.test.ts src/pages/game-session/gameImagePreloader.test.ts
./node_modules/.bin/eslint src/pages/game-session/index.tsx src/pages/game-session/index.integration.test.tsx src/pages/game-session/gameDifficulty.ts src/pages/game-session/retryUpload.test.ts
```

```sh
cd backend
QINIU_BUCKET=motioncare-training PYTHONPATH=../packages/motion_analysis_contract/src /Users/nick/my_dev/workout/MotionCare/backend/.venv/bin/python -m pytest apps/training/tests/test_training_current_prescription.py -q
```

```sh
rg -n 'DIFFICULTY_REASONS|difficultyReasonRef|setDifficultyReason|showDifficultyChoices|lowerDifficulties|请选择降低难度|不能高于指导老师' miniapp/src/pages/game-session
git diff --check
```

预期聚焦测试通过、无新增 lint 错误，废弃业务引用无匹配。新回归应覆盖上调、下调、未调整、重进和实际出题；既有媒体生命周期用例不得删除。记录现有 lint 警告与新增问题的区别。完成 Task 1 的独立审查后进入 Task 2；未授权提交时仅保留工作区差异与执行记录。

## Task 2：按钮配色、真实页面截图及最终收口

**Files:**
- Modify: `miniapp/src/app.scss`
- Modify: `miniapp/src/pages/game-session/index.tsx`（仅 H5 键盘访问接线）
- Test: `miniapp/src/pages/game-session/index.integration.test.tsx`（如需覆盖新增接线）
- Modify: `docs/superpowers/specs/2026-05-16-wechat-miniapp-real-games-design.md`
- Modify: `docs/superpowers/specs/2026-05-16-wechat-miniapp-remaining-real-games-design.md`
- Modify: `docs/superpowers/README.md`
- Modify: `specs/patient-rehab-system/changelog.md`（只追加，保留已有未提交发布记录）
- Modify: 本 spec、实施计划的执行状态
- Temporary: `/private/tmp/motioncare-difficulty-visual/`（仅本地视觉演示，不发布）
- Output: 本地视觉截图，不纳入小程序生产包

**Interfaces:**
- Consumes: Task 1 的 `.difficulty-level-options`、`.difficulty-level-option`、`.difficulty-level-0/1/2`、`.is-selected`、`.difficulty-level-check`、`.difficulty-level-label`。
- Consumes: Task 1 已通过的行为与记录协议；不再次调整选择逻辑。
- Produces: 三列等宽档位按钮、六种颜色状态、聚焦轮廓、真实本地页面截图及验证记录。

- [x] **Step 1：替换旧反馈样式为三档视觉。**

读取 impeccable 的界面规范后，在 `.hainan-game-page` 的现有难度样式位置替换旧选项块。删除只服务于已移除反馈／切换入口的 `.difficulty-reason-options`、`.difficulty-reason-option`、`.difficulty-toggle`；先确认无其他源码使用。保留 `.game-difficulty-panel` 和 `.difficulty-description`。

```scss
.difficulty-level-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.difficulty-level-option {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
  min-height: 104px;
  margin: 0;
  padding: 16px 8px;
  box-sizing: border-box;
  border: 2px solid currentColor;
  border-radius: 16px;
  font-size: 28px;
  font-weight: 700;
  line-height: 1.5;
  white-space: nowrap;
  box-shadow: none;

  &::after { border: 0; }
  &:focus-visible { outline: 4px solid $mc-ink; outline-offset: 4px; }
}

.difficulty-level-check { display: inline-block; width: 1em; flex: 0 0 1em; }
.difficulty-level-label { min-width: 0; }

@each $index, $light, $dark in
  (0, #ecfdf5, #0f766e),
  (1, #eff6ff, #1d4ed8),
  (2, #fff7ed, #9a3412) {
  .difficulty-level-#{$index} {
    color: $dark;
    background: $light;
    border-color: $dark;
    &.is-selected { color: #fff; background: $dark; }
  }
}
```

Taro designWidth=750，源码 104px 的最小高度在 320px 视口约为 44.37 CSS px，375px 视口约为 52px。通过最终浏览器计算尺寸核对，不能仅凭源数值宣称达标。纯配色与布局不新增镜像 CSS 实现的单元测试，以渲染检查验证。

- [x] **Step 2：生成本地真实页面演示构建。**

线上 H5 绑定页依赖微信登录，不能用注入伪登录的方式冒充线上验收。使用本地临时副本的现有 demo 数据和真实游戏页面，自动启用内存演示会话，仅用于截图；不修改正式 `src/app.ts`，不读取真实患者 token，不上传训练记录。

以下 Python 从 miniapp 目录执行，若临时目录已有内容则停止并检查所属任务，不覆盖未知文件：

```sh
python3 - <<'PY'
from pathlib import Path
import shutil
src = Path.cwd()
dst = Path('/private/tmp/motioncare-difficulty-visual/miniapp')
dst.mkdir(parents=True, exist_ok=False)
for name in ['src', 'config', 'types', 'shared']:
    source = src / name
    if source.exists():
        shutil.copytree(source, dst / name)
for name in ['package.json', 'babel.config.js', 'tsconfig.json']:
    shutil.copy2(src / name, dst / name)
(dst / 'node_modules').symlink_to((src / 'node_modules').resolve(), target_is_directory=True)
entry = dst / 'src/app.ts'
entry.write_text("import { startDemoSession } from './demo/session'\nstartDemoSession()\n" + entry.read_text())
print(dst)
PY
```

在临时 miniapp 目录构建（默认沙箱的 Taro 原生编译可能因 macOS 系统配置读取失败；使用正常审批机制执行，不把编译器权限问题当作产品缺陷）：

```sh
TARO_APP_CONFIG_ENV=production TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api TARO_APP_ASSET_BASE_URL=https://cdn.whestsun.com/motioncare/static-assets npm run build:h5
python3 -m http.server 8787 --bind 127.0.0.1 --directory dist
```

本地页面 `http://127.0.0.1:8787/#/pages/game-session/index?actionId=888801` 使用颜色顺序演示动作，无外置图片请求。明确将产物标注为“本地演示页面”，并在正式差异检查中确认自动 demo 启用未进入正式源码。

- [x] **Step 3：实际操作与截图验收。**

使用可用浏览器工具；如从终端使用 Playwright，先读对应技能。打开本地页面，分别在宽度 320、375、414 CSS 像素、高度 900 下点击简单、中等、困难并截图。文件命名 `difficulty-<width>-<easy|medium|hard>.png`，均置于 `/private/tmp/motioncare-difficulty-visual/screenshots/`。

每个视口检查：三个按钮可见且等宽；实际点击区域高宽均至少 44px；标签及勾选不溢出；切换前后按钮矩形位置相同；页面无横向滚动；难度文字和规则随选择更新；无原因面板。375px 下使用 Tab 检查聚焦轮廓，点击开始确认显示实际游戏页面且不出现原因提示。选出 375px 三张和最窄视口一张展示给用户。

计算配色对比度，预期简单 5.20/5.47、中等 6.16/6.70、困难 6.88/7.31（未选中/选中），均至少 4.5:1。以 spec 的颜色为准，截图中如发现容器样式覆盖则仅修复对应布局，再检查受影响视口。

- [x] **Step 4：追加设计替代说明并记录实际完成状态。**

在两份旧游戏 spec 的正文前追加同一决策指向，保留旧正文：

```markdown
## 2026-09-08 患者自由调整难度

难度选择与反馈要求以 `2026-09-08-patient-game-difficulty-free-selection-design.md` 为准：患者开始前可自由选择简单、中等、困难，点击即生效，无需填写原因；处方难度作为默认值，选择仅用于本次训练。此前“只能降低”及“原因必填”的相关约定已由本次决策替代，其余玩法规则继续适用。
```

文档索引添加本 spec/plan；changelog 只追加本次变更及实际验证结果，不能改写前一轮发布事实。本 spec/plan 只在对应步骤已实施及验证后标记状态；不能提前写发布成功或真机通过。

- [x] **Step 5：按项目要求完成最终验证。**

以下命令按目录执行；每项只运行到取得可信结果，源码变化后才补受影响检查。命令中的测试桶值只用于 pytest 进程，不上传任何素材。

```sh
cd backend
QINIU_BUCKET=motioncare-training PYTHONPATH=../packages/motion_analysis_contract/src /Users/nick/my_dev/workout/MotionCare/backend/.venv/bin/python -m pytest -q
```

```sh
cd frontend
npm run test -- --maxWorkers=2 --minWorkers=2
npm run lint
npm run build
```

```sh
cd miniapp
npm run test
TARO_APP_CONFIG_ENV=production TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api TARO_APP_ASSET_BASE_URL=https://cdn.whestsun.com/motioncare/static-assets npm run build:h5
TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api TARO_APP_ASSET_BASE_URL=https://cdn.whestsun.com/motioncare/static-assets npm run build:weapp:prod
npm run check:weapp-package-size
```

正式微信构建放在最后，避免 H5 覆盖最终 dist；该构建不包含临时本地演示入口。主包和分包按现有脚本预算校验，独立 TypeScript 的既有失败不能被构建成功掩盖。后台数据库连接与 Taro 原生编译权限使用正常审批，不输出 .env 或密钥。

- [x] **Step 6：审查最终差异并交付截图和验证结果。**

```sh
git diff --check
git diff --stat
rg -n 'startDemoSession\(\)' miniapp/src/app.ts
```

最后一项应无匹配；仅临时副本启用自动 demo。使用 requesting-code-review 审查 spec 与实现，处理实际问题后按 verification-before-completion 报告。提交权限仍按用户当前授权，不能执行无差别暂存、推送或生产部署。保留原根文件、上一轮审计文档及真实素材。

## 计划自审与交接

覆盖关系：spec §1/2/3/5 → Task 1；§4 → Task 2 Steps 1–3；§6 → Task 1 测试与 Task 2 Steps 3/5/6；§7 → Task 2 Step 4。接口名称与源码对齐；档位颜色、数据字段、开始门禁及临时演示边界均写明。计划自审由主控完成，不为编写计划派发子代理。

计划执行方式由用户选择。推荐子代理逐任务实施与独立审查；也可由当前会话使用 executing-plans 顺序实施。此计划及任何勾选均不能替代真实执行证据。

执行修正（2026-09-08）：实页发现 H5 的 TARO-BUTTON-CORE 默认无 tabindex/role，Tab 后焦点停留 BODY，只有 :focus-visible CSS 无法满足 spec。Task 2 补充最小 H5 限定的聚焦与键盘激活接线；以实际 Tab 聚焦、轮廓、Enter/Space 激活及 Space 不滚屏验证，不改变微信触摸交互和三档业务规则。此修正必须纳入 Task 2 独立审查。

执行收口（2026-09-08, codex）：Task 1–2 全部完成，最终独立审查无新增问题。后端 1237、小程序 1001、管理端 317 项测试通过；管理端 lint 退出 0（5 项既有警告），管理端及正式 H5/微信构建、微信包体检查通过。小程序定向 lint 的 6 项既有错误和 3 项警告、既有构建体积提示均已审查披露。已完成本地 H5 三视口与键盘验收，未进行微信真机验收。本轮改动与审查快照保留在隔离工作区，未提交、未合并、未发布。详细证据见本计划对应 SDD 目录的 task-1-report.md、task-2-report.md 与 final-review.md。

发布记录（2026-09-09, codex）：用户明确要求打包并提交微信开发版。使用本隔离工作区已审查的未提交改动重新执行生产微信构建及包体检查，均退出 0；正式 API 与素材来源、三档难度界面、正式入口检查通过。微信开发者工具 CLI 以版本 7.0.4、描述“患者开始前自由调整难度，取消反馈要求，优化难度按钮配色”上传，退出 0 且返回 ✔ upload。微信上传后总包 1597259 B、主包 558242 B、游戏分包 1039017 B。仅上传开发版，未设体验版、未提审、未正式上架，未部署 H5；未创建代码提交或推送。回执保存在本计划 SDD 目录 motioncare-weapp-704-free-difficulty-upload-20260909.json/.log。

版本更正（2026-09-09, codex）：用户纠正本轮版本应为 7.0.5。复用同一已验证正式构建包，以 --version 7.0.5 重新上传微信开发版，CLI 退出 0 并返回 ✔ upload，上传总包 1597259 B。此前误用 7.0.4 的上传事实保留，当前最新开发版已更新为 7.0.5；未设体验版、未提审或正式上架。回执为本计划 SDD 目录 motioncare-weapp-705-free-difficulty-upload-20260909.json/.log。
