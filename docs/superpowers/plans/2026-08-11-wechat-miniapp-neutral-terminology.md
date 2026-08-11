> 状态：implemented
> 日期：2026-08-11
> 范围：仅替换微信小程序用户可见的医疗相关词语，并上传开发版
> 关联：`docs/superpowers/specs/2026-08-11-wechat-miniapp-neutral-terminology-design.md`；`CONTEXT.md`
> 实施基线 commit：`337b6fe`
>
> 执行记录（2026-08-11, Codex）：Tasks 1–6 已完成。实现提交：`0b0c963`、`d929eb1`、`fc3621d`、`f6938e8`、`85da5d9`、`68e9721`；全量 Vitest `377/377` 通过；开发构建 `npm run build:weapp` 与生产构建 `TARO_APP_CONFIG_ENV=production TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api npm run build:weapp:prod` 均通过；上传前远端 `origin/main` 为 `68e9721`。微信 CLI 于 2026-08-11 以版本 `2026.08.11.2`、描述“性能优化”上传，退出码 `0`，输出 `✔ upload`，并确认 AppID `wx095c9a6c41b60112`。微信后台开发版列表未自动读取，平台侧显示待人工确认。

# 微信小程序中性术语实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅在微信小程序用户可见文案和错误提示中机械替换医疗相关词语，并上传版本 `2026.08.11.2` 的开发版。

**Architecture:** 页面固定文案直接按固定词表替换；接口错误通过 `neutralizeMiniappMessage(message: string): string` 在展示边界机械转换。内部英文变量、API 字段、路由、正常业务数据、Web 与后端保持不变。

**Tech Stack:** Taro 4、React 18、TypeScript、Vitest、微信开发者工具 CLI、Git

## Global Constraints

- 修改范围只能位于 `miniapp/`、本计划文件和对应测试；不得修改 `frontend/`、`backend/`、数据库或线上服务。
- 固定替换：患者、病人→用户；医生、医护→指导老师；处方→运动计划；康复→运动；医疗→运动服务；诊疗→运动指导；医嘱→运动说明；治疗→训练；医院→服务机构；疾病→身体情况。
- 采用机械替换，不额外润色替换结果。
- 用户输入、姓名、项目名称、动作名称和接口正常业务数据不得经过术语转换。
- API 字段、请求路径、TypeScript 类型、内部英文变量和测试名称不得因本需求重命名。
- AppID 保持 `wx095c9a6c41b60112`，线上 API 保持 `https://mcare-wx.whestsun.com/api`。
- 开发版版本固定为 `2026.08.11.2`，描述固定为 `性能优化`。
- 不读取、使用或保存 AppSecret。
- 任一测试、构建、复审或上传步骤失败时立即停止，不得宣称发布成功。

---

## 文件结构

- Create: `miniapp/src/copy/neutralTerminology.ts` — 集中声明固定替换表并转换错误展示文本。
- Create: `miniapp/src/copy/neutralTerminology.test.ts` — 覆盖全部固定替换和中性文本不变。
- Create: `miniapp/src/copy/neutralTerminologySource.test.ts` — 扫描生产展示文件，防止原词回归。
- Modify: `miniapp/src/api/client.ts`、`miniapp/src/api/safeError.ts`、`miniapp/src/api/client.test.ts` — 统一转换通用接口错误。
- Modify: `miniapp/project.config.json`、首页/绑定/运动计划/动作历史文件与测试 — 替换通用页面文案。
- Modify: `miniapp/src/pages/game-session/index.tsx`、`retryUpload.ts`、`retryUpload.test.ts` — 替换游戏训练文案和重试错误。
- Modify: `miniapp/src/pages/shoulder-press/*.tsx`、`workflow.ts` 及对应测试 — 替换肩部推举文案和工作流错误。
- Modify: `docs/superpowers/plans/2026-08-11-wechat-miniapp-neutral-terminology.md` — 记录执行和发布结果。

### Task 1: 建立固定术语转换器与通用错误边界

**Files:**
- Create: `miniapp/src/copy/neutralTerminology.ts`
- Create: `miniapp/src/copy/neutralTerminology.test.ts`
- Modify: `miniapp/src/api/client.ts`
- Modify: `miniapp/src/api/safeError.ts`
- Modify: `miniapp/src/api/client.test.ts`

**Interfaces:**
- Produces: `neutralizeMiniappMessage(message: string): string`。
- Consumes: 通用 API 的 `detail`、`message` 与微信请求错误文本。

- [x] **Step 1: 写转换器和 API 错误的失败测试**

创建 `neutralTerminology.test.ts`，覆盖以下精确矩阵：

```ts
const cases = [
  ['患者', '用户'],
  ['病人', '用户'],
  ['医生', '指导老师'],
  ['医护', '指导老师'],
  ['处方', '运动计划'],
  ['康复', '运动'],
  ['医疗', '运动服务'],
  ['诊疗', '运动指导'],
  ['医嘱', '运动说明'],
  ['治疗', '训练'],
  ['医院', '服务机构'],
  ['疾病', '身体情况'],
] as const

it.each(cases)('replaces %s with %s', (source, target) => {
  expect(neutralizeMiniappMessage(`提示：${source}`)).toBe(`提示：${target}`)
})

it('keeps neutral text unchanged', () => {
  expect(neutralizeMiniappMessage('训练记录上传失败')).toBe('训练记录上传失败')
})
```

在 `client.test.ts` 增加：

```ts
expect(safeApiErrorMessage({
  detail: '患者处方已更新，请联系医生或医护',
})).toBe('用户运动计划已更新，请联系指导老师或指导老师')

expect(safeError.networkRequestErrorMessage({
  errMsg: 'request:fail 医疗诊疗医嘱治疗医院疾病病人康复',
})).toBe('网络请求失败：request:fail 运动服务运动指导运动说明训练服务机构身体情况用户运动')
```

- [x] **Step 2: 运行测试并观察 RED**

Run:

```bash
cd miniapp
npx vitest run src/copy/neutralTerminology.test.ts src/api/client.test.ts
```

Expected: FAIL，原因是转换器尚不存在或错误文本仍包含原词。

- [x] **Step 3: 实现固定机械替换**

在 `neutralTerminology.ts` 实现：

```ts
export const NEUTRAL_TERM_REPLACEMENTS = [
  ['患者', '用户'],
  ['病人', '用户'],
  ['医生', '指导老师'],
  ['医护', '指导老师'],
  ['处方', '运动计划'],
  ['康复', '运动'],
  ['医疗', '运动服务'],
  ['诊疗', '运动指导'],
  ['医嘱', '运动说明'],
  ['治疗', '训练'],
  ['医院', '服务机构'],
  ['疾病', '身体情况'],
] as const

export function neutralizeMiniappMessage(message: string): string {
  return NEUTRAL_TERM_REPLACEMENTS.reduce(
    (result, [source, target]) => result.replaceAll(source, target),
    message,
  )
}
```

在 `safeApiErrorMessage` 返回安全文本前、`networkRequestErrorMessage` 拼接安全详情前调用该函数。敏感凭据过滤顺序保持不变。

- [x] **Step 4: 运行 GREEN 与回归测试**

Run:

```bash
cd miniapp
npx vitest run src/copy/neutralTerminology.test.ts src/api/client.test.ts src/pages/shoulder-press/api.test.ts
```

Expected: 全部通过，敏感凭据隐藏测试继续通过。

- [x] **Step 5: 提交转换器**

Run:

```bash
git add miniapp/src/copy/neutralTerminology.ts miniapp/src/copy/neutralTerminology.test.ts miniapp/src/api/client.ts miniapp/src/api/safeError.ts miniapp/src/api/client.test.ts
git commit -m "feat(miniapp): 统一转换医疗相关提示词"
```

### Task 2: 机械替换通用页面文案

**Files:**
- Modify: `miniapp/project.config.json`
- Modify: `miniapp/src/pages/action-history/index.tsx`
- Modify: `miniapp/src/pages/bind/index.tsx`
- Modify: `miniapp/src/pages/home/index.tsx`
- Modify: `miniapp/src/pages/home/homeActions.ts`
- Modify: `miniapp/src/pages/home/homeActions.test.ts`
- Modify: `miniapp/src/pages/prescription/index.tsx`

**Interfaces:**
- Consumes: Global Constraints 中的固定替换表。
- Produces: 通用页面和项目描述中不再出现原词。

- [x] **Step 1: 增加首页新文案断言**

在 `homeActions.test.ts` 的快捷入口测试中增加：

```ts
expect(byKey.prescription.label()).toBe('查看运动计划')
```

- [x] **Step 2: 运行目标测试并观察 RED**

Run:

```bash
cd miniapp
npx vitest run src/pages/home/homeActions.test.ts
```

Expected: FAIL，实际标签仍为 `查看处方`。

- [x] **Step 3: 按固定词表机械替换全部通用页面**

对 Files 列出的生产文件逐个替换所有原词，不润色组合结果。示例：

```text
MotionCare 患者端小程序 → MotionCare 用户端小程序
输入医生提供的绑定码，开始你的康复训练。 → 输入指导老师提供的绑定码，开始你的运动训练。
当前处方 → 当前运动计划
今日康复 → 今日运动
```

- [x] **Step 4: 验证目标测试与文件扫描**

Run:

```bash
cd miniapp
npx vitest run src/pages/home/homeActions.test.ts
cd ..
rg -n '患者|病人|医生|医护|处方|康复|医疗|诊疗|医嘱|治疗|医院|疾病' \
  miniapp/project.config.json \
  miniapp/src/pages/action-history/index.tsx \
  miniapp/src/pages/bind/index.tsx \
  miniapp/src/pages/home/index.tsx \
  miniapp/src/pages/home/homeActions.ts \
  miniapp/src/pages/prescription/index.tsx
```

Expected: Vitest 通过；`rg` 无匹配并以退出码 1 结束。

- [x] **Step 5: 提交通用页面替换**

Run:

```bash
git add miniapp/project.config.json miniapp/src/pages/action-history/index.tsx miniapp/src/pages/bind/index.tsx miniapp/src/pages/home/index.tsx miniapp/src/pages/home/homeActions.ts miniapp/src/pages/home/homeActions.test.ts miniapp/src/pages/prescription/index.tsx
git commit -m "fix(miniapp): 中性化通用页面文案"
```

### Task 3: 机械替换游戏训练文案与重试错误

**Files:**
- Modify: `miniapp/src/pages/game-session/index.tsx`
- Modify: `miniapp/src/pages/game-session/retryUpload.ts`
- Modify: `miniapp/src/pages/game-session/retryUpload.test.ts`

**Interfaces:**
- Consumes: `neutralizeMiniappMessage(message: string): string`。
- Produces: 游戏训练固定文案和接口重试错误均使用中性词。

- [x] **Step 1: 写游戏错误转换失败测试**

在 `retryUpload.test.ts` 导入 `Taro` 与 `postGameTrainingRecord`，增加：

```ts
it('neutralizes medical terms returned by the training upload API', async () => {
  vi.mocked(Taro.request).mockResolvedValueOnce({
    statusCode: 400,
    data: { detail: '患者处方已更新，请联系医护' },
  } as never)

  await expect(postGameTrainingRecord(payload()))
    .rejects.toThrow('用户运动计划已更新，请联系指导老师')
})
```

- [x] **Step 2: 运行测试并观察 RED**

Run:

```bash
cd miniapp
npx vitest run src/pages/game-session/retryUpload.test.ts
```

Expected: FAIL，错误仍包含原词。

- [x] **Step 3: 转换重试错误并机械替换页面文案**

在 `retryUpload.ts` 的响应 `detail`、`message` 和最终错误展示文本进入 `Error` 或待重试记录前调用 `neutralizeMiniappMessage`。在 `index.tsx` 中机械替换固定文案和小程序生成的备注，包括：

```text
患者提前结束本次游戏训练 → 用户提前结束本次游戏训练
请填写原因，医生端可见 → 请填写原因，指导老师端可见
返回处方 → 返回运动计划
```

- [x] **Step 4: 验证游戏测试与文件扫描**

Run:

```bash
cd miniapp
npx vitest run src/pages/game-session/retryUpload.test.ts
cd ..
rg -n '患者|病人|医生|医护|处方|康复|医疗|诊疗|医嘱|治疗|医院|疾病' \
  miniapp/src/pages/game-session/index.tsx \
  miniapp/src/pages/game-session/retryUpload.ts
```

Expected: Vitest 通过；`rg` 无匹配并以退出码 1 结束。

- [x] **Step 5: 提交游戏文案替换**

Run:

```bash
git add miniapp/src/pages/game-session/index.tsx miniapp/src/pages/game-session/retryUpload.ts miniapp/src/pages/game-session/retryUpload.test.ts
git commit -m "fix(miniapp): 中性化游戏训练文案"
```

### Task 4: 机械替换肩部推举文案与工作流错误

**Files:**
- Modify: `miniapp/src/pages/shoulder-press/index.tsx`
- Modify: `miniapp/src/pages/shoulder-press/preview.tsx`
- Modify: `miniapp/src/pages/shoulder-press/camera.tsx`
- Modify: `miniapp/src/pages/shoulder-press/upload.tsx`
- Modify: `miniapp/src/pages/shoulder-press/workflow.ts`
- Modify: `miniapp/src/pages/shoulder-press/workflow.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Consumes: `neutralizeMiniappMessage(message: string): string` 与固定替换表。
- Produces: 肩部推举全流程不再展示原词。

- [x] **Step 1: 把既有可见文案断言改成目标词**

精确更新测试断言：

```text
处方已更新，请重新进入 → 运动计划已更新，请重新进入
返回当前处方 → 返回当前运动计划
返回处方 → 返回运动计划
```

测试夹具中的项目名 `康复研究` 属于正常业务数据，保持不变。

- [x] **Step 2: 运行测试并观察 RED**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/workflow.test.ts src/pages/shoulder-press/pages.test.tsx
```

Expected: FAIL，生产页面和工作流仍返回原词。

- [x] **Step 3: 转换工作流错误并机械替换页面文案**

在 `shoulderPressUploadErrorMessage` 返回安全中文错误前调用 `neutralizeMiniappMessage`。对四个页面文件中的固定文案做机械替换；不得修改项目名、动作数据、API 字段或录制状态机。

- [x] **Step 4: 运行 GREEN 与肩部推举回归**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/workflow.test.ts src/pages/shoulder-press/pages.test.tsx src/pages/shoulder-press/api.test.ts
cd ..
rg -n '患者|病人|医生|医护|处方|康复|医疗|诊疗|医嘱|治疗|医院|疾病' \
  miniapp/src/pages/shoulder-press/index.tsx \
  miniapp/src/pages/shoulder-press/preview.tsx \
  miniapp/src/pages/shoulder-press/camera.tsx \
  miniapp/src/pages/shoulder-press/upload.tsx \
  miniapp/src/pages/shoulder-press/workflow.ts
```

Expected: Vitest 全部通过；`rg` 无匹配并以退出码 1 结束。

- [x] **Step 5: 提交肩部推举替换**

Run:

```bash
git add miniapp/src/pages/shoulder-press/index.tsx miniapp/src/pages/shoulder-press/preview.tsx miniapp/src/pages/shoulder-press/camera.tsx miniapp/src/pages/shoulder-press/upload.tsx miniapp/src/pages/shoulder-press/workflow.ts miniapp/src/pages/shoulder-press/workflow.test.ts miniapp/src/pages/shoulder-press/pages.test.tsx
git commit -m "fix(miniapp): 中性化动作训练文案"
```

### Task 5: 增加生产文案回归门禁并完成全量验证

**Files:**
- Create: `miniapp/src/copy/neutralTerminologySource.test.ts`

**Interfaces:**
- Consumes: `NEUTRAL_TERM_REPLACEMENTS` 与 Tasks 1–4 的生产文件。
- Produces: 可持续阻止原词重新进入生产展示文件的自动化门禁。

- [x] **Step 1: 创建生产源码扫描测试**

测试递归读取 `miniapp/src` 下的 `.ts`、`.tsx`、`.json` 生产文件及 `miniapp/project.config.json`，排除：

```text
*.test.ts
*.test.tsx
src/copy/neutralTerminology.ts
```

对每个剩余文件断言不包含 `NEUTRAL_TERM_REPLACEMENTS` 的任一原词；失败信息必须包含文件路径和命中的原词。

- [x] **Step 2: 运行术语门禁与小程序全量测试**

Run:

```bash
cd miniapp
npx vitest run src/copy/neutralTerminologySource.test.ts
npm test
```

Expected: 术语门禁通过；全量 Vitest 无失败。

- [x] **Step 3: 运行开发与生产构建**

Run:

```bash
cd miniapp
npm run build:weapp
TARO_APP_CONFIG_ENV=production \
TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api \
npm run build:weapp:prod
```

Expected: 两次构建均退出码 0。

- [x] **Step 4: 核对生产产物和源码差异**

Run:

```bash
node -e "const c=require('./miniapp/dist/project.config.json'); if(c.appid!=='wx095c9a6c41b60112') throw new Error('构建产物 AppID 错误'); console.log(c.appid)"
rg -F 'https://mcare-wx.whestsun.com/api' miniapp/dist -g '*.js'
git diff --check
git status --short
```

Expected: 输出正确 AppID；线上 API 至少命中一个 JavaScript 产物；差异检查通过；仅源码扫描测试尚未提交。

- [x] **Step 5: 提交回归门禁**

Run:

```bash
git add miniapp/src/copy/neutralTerminologySource.test.ts
git commit -m "test(miniapp): 阻止医疗词回归展示文案"
```

### Task 6: 最终复审、推送并上传开发版

**Files:**
- Modify: `docs/superpowers/plans/2026-08-11-wechat-miniapp-neutral-terminology.md`

**Interfaces:**
- Consumes: Tasks 1–5 的提交、生产构建产物、微信开发者工具登录态和新 AppID 开发权限。
- Produces: 远端 `main`、开发版 `2026.08.11.2` 和可追溯发布记录。

- [x] **Step 1: 完成逐任务复审和发布前全分支复审**

复审范围从实施基线 `337b6fe` 到最新实现提交。Critical、Important、未裁决的 Minor 或规格不合规均必须先解决；复审通过前不得推送。

- [x] **Step 2: 推送已复审的 main**

Run:

```bash
git fetch origin main
git merge-base --is-ancestor origin/main HEAD
git push origin main
```

Expected: 远端 `main` 快进到已复审提交；若祖先检查或推送失败，立即停止。

- [x] **Step 3: 上传微信开发版**

Run:

```bash
/Applications/wechatwebdevtools.app/Contents/MacOS/cli upload \
  --project /private/tmp/motioncare-main-release/miniapp \
  --version 2026.08.11.2 \
  --desc "性能优化" \
  --lang zh
```

Expected: CLI 退出码 0，并明确输出 `✔ upload`；否则停止且不得记录为完成。

- [x] **Step 4: 更新计划执行记录**

在本文顶部将状态改为 `implemented`，追加实际测试数量、双构建结果、实现提交号、远端提交号和 CLI 上传成功证据，并把所有已完成 checkbox 改为 `[x]`。微信后台版本列表若无法自动读取，明确记录为平台侧待确认，不伪造验证结果。

- [x] **Step 5: 提交并推送发布记录**

Run:

```bash
git add docs/superpowers/plans/2026-08-11-wechat-miniapp-neutral-terminology.md
git commit -m "docs(miniapp): 记录中性术语开发版发布"
git push origin main
git status --short
```

Expected: 发布记录提交并推送成功，最终工作区无输出。
