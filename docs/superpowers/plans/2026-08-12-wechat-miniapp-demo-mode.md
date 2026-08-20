> 状态：implemented
> 日期：2026-08-12
> 范围：实现微信小程序审核用游戏演示模式，并上传开发版
> 关联：`docs/superpowers/specs/2026-08-12-wechat-miniapp-demo-mode-design.md`；`CONTEXT.md`
> 实施基线 commit：`a86641e`
>
> 执行记录（2026-08-12, Codex）：Task 1 已落地于 commits `ef0d705`、`b8eb196`。
> 执行记录（2026-08-12, Codex）：Task 2 已落地于 commits `de38d4f`、`6609e49`。
> 执行记录（2026-08-12, Codex）：Task 3 已落地于 commits `3249c47`、`22d1cd6`。
> 执行记录（2026-08-12, Codex）：Task 4 已落地于 commit `118d9ab`。
> 执行记录（2026-08-13, Codex）：Task 5 的静态收口、测试框架修正与最终复审修复已落地于 commits `d609b87`、`6a5cf13`、`f289638`；最终复审已批准，全量测试 415/415 通过，开发与生产构建通过。
> 执行记录（2026-08-13, Codex）：演示模式实现已推送至 `main`；微信开发版 `2026.08.12.1` 已通过 CLI 上传成功，AppID `wx095c9a6c41b60112`，描述“性能优化”；平台开发版本列表待人工确认，未提交审核、未发布正式版。
> 后续修订（2026-08-20, codex）：原六游戏方案继续作为历史实施记录；当前演示计划另追加无录制、无上传的肩部推举摄像体验，准则以关联 spec 的同日修订为准。
> 补充执行记录（2026-08-20, codex）：演示肩部推举恢复独立动作预览与摄像训练指导小窗；全量 Vitest `422/422` 及生产构建通过，微信开发版 `7.0.0` 已重新上传，描述“修复bug与优化性能”。

# 微信小程序游戏演示模式实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在微信小程序绑定页输入 `8888` 后进入完全隔离、进程内有效的六游戏演示模式，并将验证通过的版本上传为 `2026.08.12.1` 开发版。

**Architecture:** 用模块级内存保存演示开关，以固定数据工厂提供首页和运动计划数据，并通过显式数据加载层在演示数据与真实 API 之间选择。绑定页、应用生命周期、首页、运动计划和游戏结果页均直接识别演示模式，从而绕过真实 token、接口、缓存、录像恢复和训练补传；真实用户流程保持原状。

**Tech Stack:** Taro 4、React 18、TypeScript、Vitest、微信开发者工具 CLI、Git

## Global Constraints

- 只修改 `miniapp/`、本计划文件和对应测试，不修改 Web 管理端、后端、数据库、七牛云或线上 API。
- 演示入口固定为精确四位代码 `8888`，在开发和生产构建中永久启用。
- 演示身份固定为用户 `用户01`、项目 `功能展示`。
- 演示运动计划固定包含六个游戏：颜色顺序记忆、图案顺序记忆、反应抑制、分类切换、声音辨别、拼图。
- 每个演示游戏建议时长固定为 1 分钟，默认难度固定为“简单”。
- 演示状态只能保存在当前 JavaScript 进程内，不得写入 Storage、token、cookie 或服务端。
- 演示模式不得调用绑定、首页、当前运动计划或训练记录业务接口；不得读取、覆盖、删除真实用户的运动计划缓存、游戏待补传记录或录像待上传记录。
- 演示游戏允许正常完成和提前结束；结果只在当前页面内展示，不上传、不补传、不持久化。
- 小程序用户可见文案继续遵守 `CONTEXT.md` 中性术语词表和静态门禁。
- AppID 保持 `wx095c9a6c41b60112`，生产 API 保持 `https://mcare-wx.whestsun.com/api`。
- 开发版版本固定为 `2026.08.12.1`，描述固定为 `性能优化`。
- 不读取、使用、输出或保存 AppSecret。
- 任一自动化测试、构建、代码复审或上传步骤失败时立即停止，不得报告开发版发布成功。

---

## 文件结构

- Create: `miniapp/src/demo/session.ts` — 保存进程内演示状态并暴露固定绑定码。
- Create: `miniapp/src/demo/session.test.ts` — 验证状态仅在当前模块实例中存活。
- Create: `miniapp/src/demo/data.ts` — 生成互不共享引用的演示首页和六游戏运动计划数据。
- Create: `miniapp/src/demo/data.test.ts` — 固化身份、六游戏、时长、难度与对象隔离。
- Create: `miniapp/src/demo/patientAppData.ts` — 在演示数据和真实首页/运动计划 API 之间显式选择。
- Create: `miniapp/src/demo/patientAppData.test.ts` — 验证演示无网络、真实模式请求原接口。
- Modify: `miniapp/src/app.ts` — 未登录和演示模式跳过真实录像恢复及游戏补传。
- Modify: `miniapp/src/pages/bind/index.tsx` — 特判 `8888`，开启演示且不做真实绑定。
- Modify: `miniapp/src/pages/home/index.tsx` — 使用数据加载层，展示演示横幅并隐藏历史和补传 UI。
- Modify: `miniapp/src/pages/prescription/index.tsx` — 使用数据加载层，展示六游戏并绕过真实缓存、补传和历史。
- Modify: `miniapp/src/pages/game-session/index.tsx` — 使用数据加载层，演示结果只在页面内展示并固定返回运动计划。
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx` — 复用现有页面测试框架，覆盖绑定、生命周期、首页、运动计划和游戏演示闭环。
- Modify: `docs/superpowers/plans/2026-08-12-wechat-miniapp-demo-mode.md` — 记录实施、验证和开发版上传结果。

### Task 1: 建立进程内演示会话、固定数据与显式数据源

**Files:**
- Create: `miniapp/src/demo/session.ts`
- Create: `miniapp/src/demo/session.test.ts`
- Create: `miniapp/src/demo/data.ts`
- Create: `miniapp/src/demo/data.test.ts`
- Create: `miniapp/src/demo/patientAppData.ts`
- Create: `miniapp/src/demo/patientAppData.test.ts`

**Interfaces:**
- Produces: `DEMO_BINDING_CODE: '8888'`。
- Produces: `startDemoSession(): void`、`isDemoSession(): boolean`。
- Produces: `createDemoHomeData(): HomeData`、`createDemoCurrentPrescription(): NonNullable<CurrentPrescription>`。
- Produces: `fetchPatientHomeData(): Promise<HomeData>`、`fetchCurrentPrescriptionData(): Promise<CurrentPrescription>`。
- Consumes: `GAME_CATALOG`、`request<T>()`、`HomeData`、`CurrentPrescription`。

- [x] **Step 1: 写会话生命周期失败测试**

创建 `session.test.ts`：

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('演示会话', () => {
  beforeEach(() => vi.resetModules())

  it('只在当前模块实例中保持开启', async () => {
    const first = await import('./session')
    expect(first.DEMO_BINDING_CODE).toBe('8888')
    expect(first.isDemoSession()).toBe(false)
    first.startDemoSession()
    expect(first.isDemoSession()).toBe(true)

    vi.resetModules()
    const restarted = await import('./session')
    expect(restarted.isDemoSession()).toBe(false)
  })
})
```

- [x] **Step 2: 写演示数据和数据源失败测试**

在 `data.test.ts` 断言：

```ts
const expectedGames = [
  ['game-memory-color-sequence', '颜色顺序记忆'],
  ['game-memory-pattern-sequence', '图案顺序记忆'],
  ['game-executive-inhibition', '反应抑制'],
  ['game-executive-category-switch', '分类切换'],
  ['game-audiovisual-sound-discrimination', '声音辨别'],
  ['game-audiovisual-puzzle', '拼图'],
] as const

const first = createDemoHomeData()
const second = createDemoHomeData()
expect(first.patient.name).toBe('用户01')
expect(first.project.name).toBe('功能展示')
expect(first.current_prescription?.actions.map((action) => [action.source_key, action.action_name]))
  .toEqual(expectedGames)
expect(first.current_prescription?.actions.every((action) => (
  action.internal_type === 'game' && action.duration_minutes === 1 && action.difficulty === '简单'
))).toBe(true)
expect(first).not.toBe(second)
expect(first.current_prescription).not.toBe(second.current_prescription)
expect(first.current_prescription?.actions).not.toBe(second.current_prescription?.actions)
```

在 `patientAppData.test.ts` mock `../api/client` 后分别动态导入模块，断言：

```ts
session.startDemoSession()
await expect(dataSource.fetchPatientHomeData()).resolves.toMatchObject({
  patient: { name: '用户01' },
  project: { name: '功能展示' },
})
await expect(dataSource.fetchCurrentPrescriptionData()).resolves.toMatchObject({
  actions: expect.any(Array),
})
expect(requestMock).not.toHaveBeenCalled()
```

以及在未开启演示时：

```ts
const realPrescription = null
const realHome: HomeData = {
  project_patient_id: 1,
  patient: { id: 1, name: '真实用户' },
  project: { id: 1, name: '真实项目' },
  today: '2026-08-12',
  current_prescription: realPrescription,
}
requestMock
  .mockResolvedValueOnce(realHome)
  .mockResolvedValueOnce(realPrescription)
await expect(dataSource.fetchPatientHomeData()).resolves.toBe(realHome)
await expect(dataSource.fetchCurrentPrescriptionData()).resolves.toBe(realPrescription)
expect(requestMock).toHaveBeenNthCalledWith(1, '/patient-app/home/')
expect(requestMock).toHaveBeenNthCalledWith(2, '/patient-app/current-prescription/')
```

- [x] **Step 3: 运行目标测试并观察 RED**

Run:

```bash
cd miniapp
npx vitest run src/demo/session.test.ts src/demo/data.test.ts src/demo/patientAppData.test.ts
```

Expected: FAIL，三个生产模块尚不存在。

- [x] **Step 4: 实现最小进程内会话**

在 `session.ts` 实现：

```ts
export const DEMO_BINDING_CODE = '8888' as const

let demoSessionActive = false

export function startDemoSession(): void {
  demoSessionActive = true
}

export function isDemoSession(): boolean {
  return demoSessionActive
}
```

不得添加 Storage 调用或生产用重置函数。

- [x] **Step 5: 实现固定演示数据工厂**

在 `data.ts` 声明以下固定顺序，并用稳定 ID `888800`（运动计划）和 `888801`–`888806`（动作）逐项创建动作：

```ts
const DEMO_GAME_CODES: readonly GameCode[] = [
  'game-memory-color-sequence',
  'game-memory-pattern-sequence',
  'game-executive-inhibition',
  'game-executive-category-switch',
  'game-audiovisual-sound-discrimination',
  'game-audiovisual-puzzle',
]
```

每个动作包含完整字段：

```ts
{
  id,
  action_library_item: id,
  source_key: gameCode,
  action_name: GAME_CATALOG[gameCode].name,
  training_type: '游戏训练',
  internal_type: 'game',
  action_type: '益智游戏',
  action_instruction: `${GAME_CATALOG[gameCode].name}功能体验`,
  video_url: '',
  has_ai_supervision: false,
  weekly_frequency: '体验一次',
  duration_minutes: 1,
  weekly_target_count: 1,
  weekly_completed_count: 0,
  difficulty: '简单',
  notes: '',
  sort_order: index + 1,
  recent_record: null,
}
```

`createDemoCurrentPrescription()` 每次返回以下新对象，其中 `today` 来自 `todayLocalDate()`：

```ts
{
  id: 888800,
  version: 1,
  status: 'active',
  effective_at: null,
  week_start: today,
  week_end: today,
  actions: DEMO_GAME_CODES.map(createDemoAction),
}
```

`createDemoHomeData()` 每次调用该工厂并返回：

```ts
{
  project_patient_id: 8888,
  patient: { id: 8888, name: '用户01' },
  project: { id: 8888, name: '功能展示' },
  today: todayLocalDate(),
  current_prescription: createDemoCurrentPrescription(),
}
```

- [x] **Step 6: 实现显式数据源选择**

在 `patientAppData.ts` 实现：

```ts
export function fetchPatientHomeData(): Promise<HomeData> {
  if (isDemoSession()) return Promise.resolve(createDemoHomeData())
  return request<HomeData>('/patient-app/home/')
}

export function fetchCurrentPrescriptionData(): Promise<CurrentPrescription> {
  if (isDemoSession()) return Promise.resolve(createDemoCurrentPrescription())
  return request<CurrentPrescription>('/patient-app/current-prescription/')
}
```

不得修改通用 `request` 实现或伪造 token。

- [x] **Step 7: 运行 GREEN 和中性术语门禁**

Run:

```bash
cd miniapp
npx vitest run \
  src/demo/session.test.ts \
  src/demo/data.test.ts \
  src/demo/patientAppData.test.ts \
  src/copy/neutralTerminologySource.test.ts
```

Expected: 全部通过；演示数据无受限展示词。

- [x] **Step 8: 提交演示基础模块**

Run:

```bash
git add miniapp/src/demo
git commit -m "feat(miniapp): 建立隔离演示数据源"
```

### Task 2: 接入绑定页和应用生命周期隔离

**Files:**
- Modify: `miniapp/src/app.ts`
- Modify: `miniapp/src/pages/bind/index.tsx`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Consumes: `DEMO_BINDING_CODE`、`startDemoSession()`、`isDemoSession()`。
- Consumes: `getPatientAppToken()`、`stopPendingGameUploadRetryLoop()`。
- Produces: `8888` 无真实鉴权进入首页；演示或未登录时应用前台不恢复真实上传任务。

本 Task 扩展现有测试 harness：在 Taro mock 增加 `login: vi.fn()`，在组件 mock 增加 `Input: 'Input'`，在 `retryMocks` 增加 `stopPendingGameUploadRetryLoop: vi.fn()`；导入 `BindPage`、`getPatientAppToken`、`setPatientAppToken` 和 `* as session`。在现有主 `describe` 之后新建文件末尾的 `describe('审核演示模式', ...)`，真实流程用例必须写在第一个 `startDemoSession()` 调用之前；首次演示用例之后的演示测试各自再次调用 `startDemoSession()`，该调用是幂等的。

- [x] **Step 1: 写绑定入口失败测试**

在现有页面测试框架中导入 `BindPage`，输入 `8888` 并点击“绑定账号”，断言：

```ts
expect(taroHarness.taroMock.login).not.toHaveBeenCalled()
expect(requestMock).not.toHaveBeenCalledWith('/patient-app/bind/', expect.anything())
expect(getPatientAppToken()).toBeUndefined()
expect(retryMocks.stopPendingGameUploadRetryLoop).toHaveBeenCalledTimes(1)
expect(taroHarness.taroMock.redirectTo).toHaveBeenCalledWith({ url: '/pages/home/index' })
expect(session.isDemoSession()).toBe(true)
```

另加普通绑定码 `1234` 回归：

```ts
expect(taroHarness.taroMock.login).toHaveBeenCalledTimes(1)
expect(requestMock).toHaveBeenCalledWith('/patient-app/bind/', {
  method: 'POST',
  data: { code: '1234', wx_openid: 'wx-code' },
})
expect(getPatientAppToken()).toBe('real-token')
```

通过以下方式写入绑定码，避免直接调用 `unknown` 类型属性：

```ts
const onInput = findFirstByType(page.element, 'Input').props.onInput
if (typeof onInput !== 'function') throw new Error('绑定码输入事件不存在')
onInput({ detail: { value: '8888' } })
page.rerender()
```

真实绑定测试将 `login` mock 为 `{ code: 'wx-code' }`，并将 `requestMock` mock 为含 `token: 'real-token'` 的完整绑定响应。

- [x] **Step 2: 写应用生命周期失败测试**

覆盖三种状态：

```ts
// 无 token、非演示
expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()
expect(retryMocks.startPendingGameUploadRetryLoop).not.toHaveBeenCalled()

// 有真实 token
setPatientAppToken('real-token')
expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()
expect(retryMocks.startPendingGameUploadRetryLoop).toHaveBeenCalledTimes(1)

// 演示模式
session.startDemoSession()
expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()
expect(retryMocks.startPendingGameUploadRetryLoop).not.toHaveBeenCalled()
expect(retryMocks.stopPendingGameUploadRetryLoop).toHaveBeenCalledTimes(1)
expect(session.isDemoSession()).toBe(true)
```

每种状态单独渲染 `App` 并执行对应 `showCallbacks[0]`。演示用例预先写入一份 `PENDING_SHOULDER_PRESS_SESSION_KEY` manifest，连续执行两次前台回调，确认演示状态仍为 true、不跳录像上传页且 manifest 保持不变；这样同时验证后台返回保持演示以及真实上传隔离，不为整份页面测试 mock 掉肩部推举模块。

- [x] **Step 3: 运行目标测试并观察 RED**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/pages.test.tsx -t "演示绑定|应用演示生命周期"
```

Expected: FAIL；`8888` 仍调用真实绑定，应用仍无条件恢复上传。

- [x] **Step 4: 在绑定页增加最前置演示分支**

在 `submit()` 完成四位校验后、设置真实 `loading` 和调用 `Taro.login` 前加入：

```ts
if (normalizedCode === DEMO_BINDING_CODE) {
  startDemoSession()
  stopPendingGameUploadRetryLoop()
  Taro.redirectTo({ url: '/pages/home/index' })
  return
}
```

保留现有 `useDidShow` 的真实 token 优先跳转行为。不得写入或清除 token、运动计划缓存、待补传记录。

- [x] **Step 5: 收紧应用前台恢复条件**

在 `app.ts` 的 `useDidShow` 开头按以下顺序判断：

```ts
if (isDemoSession()) {
  stopPendingGameUploadRetryLoop()
  return
}
if (!getPatientAppToken()) {
  stopPendingGameUploadRetryLoop()
  return
}
```

只有真实 token 存在时才执行原有肩部推举恢复、`resetRetryWindowForLaunch(Taro)` 和 `startPendingGameUploadRetryLoop(Taro)`。

- [x] **Step 6: 运行 GREEN 和真实绑定回归**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/pages.test.tsx -t "演示绑定|应用演示生命周期|绑定"
```

Expected: 新增演示测试和既有真实绑定测试全部通过。

- [x] **Step 7: 提交入口与生命周期**

Run:

```bash
git add miniapp/src/app.ts miniapp/src/pages/bind/index.tsx miniapp/src/pages/shoulder-press/pages.test.tsx
git commit -m "feat(miniapp): 接入审核演示入口"
```

### Task 3: 接入演示首页与六游戏运动计划

**Files:**
- Modify: `miniapp/src/pages/home/index.tsx`
- Modify: `miniapp/src/pages/prescription/index.tsx`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Consumes: `isDemoSession()`、`fetchPatientHomeData()`、`fetchCurrentPrescriptionData()`。
- Produces: 无网络的演示首页和完整六游戏运动计划。

- [x] **Step 1: 写演示首页失败测试**

开启演示后渲染 `HomePage`，触发 `useDidShow` 并等待 Promise，断言：

```ts
expect(textContent(page.element)).toContain('演示模式，仅供功能体验，数据不会保存。')
expect(textContent(page.element)).toContain('用户01')
expect(textContent(page.element)).toContain('功能展示')
expect(findButtonByText(page.element, '查看运动计划')).toBeTruthy()
expect(findButtonByText(page.element, '开始训练')).toBeTruthy()
expect(findAll(page.element, (element) => (
  element.type === 'Button' && textContent(element).includes('查看训练历史')
))).toHaveLength(0)
expect(requestMock).not.toHaveBeenCalled()
expect(retryMocks.tryUploadPendingGameRecord).not.toHaveBeenCalled()
expect(taroHarness.taroMock.reLaunch).not.toHaveBeenCalled()
```

测试开始前用 `writeCurrentPrescriptionCache(PRESCRIPTION)` 放入真实缓存；渲染后断言页面仍展示演示数据，且 `readCurrentPrescriptionCache()` 仍严格等于 `PRESCRIPTION`，证明演示首页既不采用也不覆盖真实缓存。点击“开始训练”后还要断言进入动作 `888801` 的现有游戏路由。

- [x] **Step 2: 写演示运动计划失败测试**

开启演示后渲染 `PrescriptionPage`，断言：

```ts
for (const name of ['颜色顺序记忆', '图案顺序记忆', '反应抑制', '分类切换', '声音辨别', '拼图']) {
  expect(textContent(page.element)).toContain(name)
}
expect(findAll(page.element, (element) => (
  element.type === 'Button' && textContent(element).includes('开始游戏')
))).toHaveLength(6)
expect(textContent(page.element)).not.toContain('查看历史')
expect(textContent(page.element)).not.toContain('待补传')
expect(requestMock).not.toHaveBeenCalled()
expect(retryMocks.tryUploadPendingGameRecord).not.toHaveBeenCalled()
```

测试开始前同样放入真实 `PRESCRIPTION` 缓存，渲染后断言六游戏数据未被真实缓存替换，且缓存仍保持原引用。逐个取得六个“开始游戏”按钮并点击，在每次点击前清理导航 mock，断言路由中的 `actionId` 依次为 `888801`–`888806`。

- [x] **Step 3: 运行目标测试并观察 RED**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/pages.test.tsx -t "演示首页|演示运动计划"
```

Expected: FAIL；页面仍请求真实接口、显示历史入口且没有演示横幅。

- [x] **Step 4: 修改首页数据和副作用边界**

在 `HomePage` 渲染时读取一次 `const demoMode = isDemoSession()`：

- `loadHomeData()` 改用 `fetchPatientHomeData()`；仅 `!demoMode` 时写真实运动计划缓存。
- 补传订阅 effect 在 `demoMode` 时直接返回 `undefined`。
- `useDidShow` 在演示模式只清空错误、加载演示数据和清空补传横幅，然后返回。
- 演示模式不调用录像恢复、待补传读取、上传重试或补传循环。
- 首页 hero 下新增精确横幅 `演示模式，仅供功能体验，数据不会保存。`。
- 渲染 `HOME_ACTIONS` 时过滤 `history`；训练入口在演示模式将标签覆盖为 `开始训练`。

真实模式继续执行原有数据加载、缓存、补传和三个首页入口。

- [x] **Step 5: 修改运动计划数据和副作用边界**

在 `PrescriptionPage` 渲染时读取一次 `const demoMode = isDemoSession()`：

- `useState` 初值在演示模式不得调用 `readCurrentPrescriptionCache()`。
- `loadPrescriptionData()` 改用 `fetchCurrentPrescriptionData()`；仅 `!demoMode` 时写缓存。
- 补传订阅 effect 和 `useDidShow` 的恢复分支在演示模式跳过，演示分支只加载固定运动计划。
- 演示模式不渲染补传横幅、最近记录文本和“查看历史”按钮。
- 六个游戏仍调用现有 `loadGameSessionSubpackage` 与 `actionEntryUrl(action)`，不得复制游戏路由规则。

- [x] **Step 6: 运行 GREEN 与真实页面回归**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/pages.test.tsx -t "演示首页|演示运动计划|首页|当前运动计划"
```

Expected: 演示和真实页面目标测试全部通过。

- [x] **Step 7: 提交演示页面**

Run:

```bash
git add miniapp/src/pages/home/index.tsx miniapp/src/pages/prescription/index.tsx miniapp/src/pages/shoulder-press/pages.test.tsx
git commit -m "feat(miniapp): 展示六游戏演示计划"
```

### Task 4: 隔离演示游戏结果与返回路径

**Files:**
- Modify: `miniapp/src/pages/game-session/index.tsx`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Consumes: `isDemoSession()`、`fetchCurrentPrescriptionData()`。
- Produces: `UploadState` 新状态 `demo_local`，其展示文本为 `本次演示不保存`。

本 Task 将 `GameSessionPage` 导入现有页面测试，并补齐测试 harness：组件 mock 增加 `Image: 'Image'` 和 `Picker: 'Picker'`；React mock 增加 `useMemo: (factory) => factory()`；`retryMocks` 增加 `postGameTrainingRecord: vi.fn()` 和 `savePendingGameUploadAfterActiveRetry: vi.fn()`。`Input` 已由 Task 2 提供。

- [x] **Step 1: 写六游戏可加载失败测试**

对动作 ID `888801`–`888806` 参数化渲染 `GameSessionPage`，触发 `useDidShow` 并等待加载，断言：

```ts
expect(requestMock).not.toHaveBeenCalled()
expect(textContent(page.element)).toContain(expectedGameName)
expect(textContent(page.element)).not.toContain('当前游戏动作不存在')
```

六个期望名称与 Task 1 的 `expectedGames` 顺序相同。

- [x] **Step 2: 写六游戏正常和提前结束的本地结果失败测试**

用六个动作 ID 与 `timer` / `manual` 两种结束方式构成 12 组参数化用例。每组都重新渲染页面、进入 playing 并断言：

```ts
expect(textContent(page.element)).toContain('得分')
expect(textContent(page.element)).toContain('正确率')
expect(textContent(page.element)).toContain('本次演示不保存')
expect(retryMocks.postGameTrainingRecord).not.toHaveBeenCalled()
expect(retryMocks.savePendingGameUploadAfterActiveRetry).not.toHaveBeenCalled()
expect(retryMocks.startPendingGameUploadRetryLoop).not.toHaveBeenCalled()
expect(taroHarness.taroMock.setStorageSync).not.toHaveBeenCalledWith(
  'motioncare.pendingGameUpload',
  expect.anything(),
)
```

正常结束先点击“开始游戏”，推进介绍步骤的假计时器直至进入 playing，再推进 60 个一秒计时；提前结束在进入 playing 后点击现有“提前结束”按钮。两种结果均点击“返回运动计划”并断言：

```ts
expect(taroHarness.taroMock.redirectTo).toHaveBeenCalledWith({ url: '/pages/prescription/index' })
expect(taroHarness.taroMock.navigateBack).not.toHaveBeenCalled()
```

- [x] **Step 3: 运行目标测试并观察 RED**

Run:

```bash
cd miniapp
npx vitest run src/pages/shoulder-press/pages.test.tsx -t "演示游戏"
```

Expected: FAIL；游戏仍请求真实运动计划并尝试上传结果。

- [x] **Step 4: 切换游戏数据源并增加本地结果状态**

在 `GameSessionPage` 中：

- 用 `fetchCurrentPrescriptionData()` 替换直接请求当前运动计划。
- 页面渲染时读取 `const demoMode = isDemoSession()`。
- 将 `UploadState` 扩展为 `'demo_local'`。
- 在 `uploadStateText()` 中返回精确文案 `本次演示不保存`。
- `endSession()` 设置结果和结果页 phase 后：演示模式只执行 `setUploadState('demo_local')`，真实模式才执行 `void uploadResult(payload)`。
- 演示模式不得调用 `postGameTrainingRecord`、保存待补传或启动补传循环。
- 结果页“返回运动计划”在演示模式使用 `Taro.redirectTo({ url: '/pages/prescription/index' })`，真实模式继续 `Taro.navigateBack()`。

结果计算继续复用 `buildGameTrainingResult`，不得新增一套演示计分规则。

- [x] **Step 5: 运行 GREEN 与真实上传回归**

Run:

```bash
cd miniapp
npx vitest run \
  src/pages/shoulder-press/pages.test.tsx \
  src/pages/game-session/scoring.test.ts \
  src/pages/game-session/retryUpload.test.ts
```

Expected: 演示闭环通过；真实直接上传、失败补传、计分和肩部推举页面回归全部通过。

- [x] **Step 6: 提交演示游戏闭环**

Run:

```bash
git add miniapp/src/pages/game-session/index.tsx miniapp/src/pages/shoulder-press/pages.test.tsx
git commit -m "feat(miniapp): 隔离演示游戏结果"
```

### Task 5: 完成全量验证与代码复审

**Files:**
- Verify: `miniapp/src/**`
- Verify generated only: `miniapp/dist/**`

**Interfaces:**
- Consumes: Tasks 1–4 的全部实现提交。
- Produces: 可发布且未破坏真实流程的微信小程序生产构建。

- [x] **Step 1: 运行小程序全量测试**

Run:

```bash
cd miniapp
npm test
```

Expected: Vitest 全量通过，无未处理 Promise rejection 或失败测试。

- [x] **Step 2: 运行开发构建**

Run:

```bash
cd miniapp
npm run build:weapp
```

Expected: Taro 开发构建退出码为 0。

- [x] **Step 3: 运行生产构建**

Run:

```bash
cd miniapp
TARO_APP_CONFIG_ENV=production \
TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api \
npm run build:weapp:prod
```

Expected: Taro 生产构建退出码为 0，生成 `miniapp/dist`。

- [x] **Step 4: 静态核对 AppID、线上 API 与敏感信息**

Run:

```bash
node -e "const c=require('./miniapp/dist/project.config.json'); if(c.appid!=='wx095c9a6c41b60112') throw new Error('构建产物 AppID 错误'); console.log(c.appid)"
rg -F "https://mcare-wx.whestsun.com/api" miniapp/dist -g '*.js'
git diff a86641e -- miniapp | rg -ni "app.?secret|secret[[:space:]]*[:=]" || true
git diff --check
```

Expected: 输出正确 AppID；产物至少命中一次线上 API；敏感信息扫描无命中；`git diff --check` 通过。

- [x] **Step 5: 执行代码复审**

使用 `superpowers:requesting-code-review` 对实施基线 `a86641e` 到当前 HEAD 进行复审，逐项核对：

```text
8888 不真实登录或写 token
演示首页、运动计划、游戏结果无业务网络请求
真实缓存和补传记录不读、不写、不删
六个游戏均可进入
正常完成和提前结束均只展示本地结果
进程重启后演示状态失效
真实绑定、真实上传和恢复流程无回归
```

Expected: 无 Critical 或 Important finding；如有则先按 `superpowers:receiving-code-review` 验证并修复，再重跑 Task 5 全部步骤。

- [x] **Step 6: 确认提交和工作区状态**

Run:

```bash
git log --oneline a86641e..HEAD
git status --short
```

Expected: 只包含演示模式相关中文提交；构建产物未进入 Git；工作区无输出。

### Task 6: 推送 main 并上传微信开发版

**Files:**
- Modify: `docs/superpowers/plans/2026-08-12-wechat-miniapp-demo-mode.md`

**Interfaces:**
- Consumes: Task 5 已通过复审的源码、生产构建产物、微信开发者工具登录态和上传权限。
- Produces: 远端 `main`、微信开发版 `2026.08.12.1` 和可追溯执行记录。

- [x] **Step 1: 同步并核对远端 main**

Run:

```bash
git fetch origin main
git merge-base --is-ancestor origin/main HEAD
git status --short
```

Expected: 远端 `main` 是当前 HEAD 的祖先，工作区无输出；若远端已前进则停止，先集成并重新执行 Task 5。

- [x] **Step 2: 推送已复审的 main**

Run:

```bash
git push origin main
```

Expected: 远端 `main` 快进到当前已复审提交。

- [x] **Step 3: 上传微信开发版**

Run:

```bash
/Applications/wechatwebdevtools.app/Contents/MacOS/cli upload \
  --project /private/tmp/motioncare-main-release/miniapp \
  --version 2026.08.12.1 \
  --desc "性能优化" \
  --lang zh
```

Expected: CLI 退出码为 0，并明确输出 `✔ upload`；若提示未登录、权限不足、AppID 不匹配或平台拒绝，则停止并原样报告错误。

- [ ] **Step 4: 核对微信开发版本信息**

在微信开发者工具或公众平台核对：

```text
AppID：wx095c9a6c41b60112
版本号：2026.08.12.1
描述：性能优化
```

Expected: 开发版本列表出现上述版本；不点击“提交审核”或“发布”。若无法自动读取平台列表，明确标记为“CLI 上传成功，平台列表待人工确认”。

- [x] **Step 5: 更新计划执行记录**

将本文顶部状态改为 `implemented`，把完成步骤改为 `[x]`，并追加：

```text
执行记录（2026-08-12, Codex）：演示模式实现、复审、全量测试和双构建均通过；main 已推送；微信开发版 2026.08.12.1 已上传，描述“性能优化”。
```

同时用 `git log --oneline a86641e..HEAD` 的实际提交号替换执行记录中的实现提交清单，不手写猜测提交号。

- [x] **Step 6: 提交并推送发布记录**

Run:

```bash
git add docs/superpowers/plans/2026-08-12-wechat-miniapp-demo-mode.md
git commit -m "docs(miniapp): 记录演示模式开发版发布"
git push origin main
git status --short
```

Expected: 文档提交和推送成功；最终工作区无输出。
