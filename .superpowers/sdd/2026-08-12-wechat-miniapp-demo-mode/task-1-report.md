# Task 1 实施报告：进程内演示会话、固定数据与显式数据源

## 实现内容

- 新增仅存在于当前模块实例的演示会话：绑定码固定为 `8888`，会话仅可开启，不使用 Storage，也未增加生产重置函数。
- 新增演示数据工厂：每次返回独立对象，固定生成六个游戏动作（计划 ID `888800`，动作 ID `888801`–`888806`），日期通过 `todayLocalDate()` 生成。
- 新增显式患者端数据源：演示会话开启时返回演示首页/计划数据；否则保持调用真实的两个患者端接口。
- 未修改绑定页、App、首页、运动计划页、游戏页、通用 `request` 或 token 逻辑。

## 文件

- `miniapp/src/demo/session.ts`
- `miniapp/src/demo/session.test.ts`
- `miniapp/src/demo/data.ts`
- `miniapp/src/demo/data.test.ts`
- `miniapp/src/demo/patientAppData.ts`
- `miniapp/src/demo/patientAppData.test.ts`

## RED

命令：

```bash
cd miniapp
npx vitest run src/demo/session.test.ts src/demo/data.test.ts src/demo/patientAppData.test.ts
```

结果：按预期失败。`session.ts`、`data.ts`、`patientAppData.ts` 均尚不存在，Vitest 分别报告 `Cannot find module './session'`、`Cannot find module './data'` 与 `Cannot find module './patientAppData'`；共 3 个测试文件失败、3 个测试失败。

## GREEN

命令：

```bash
cd miniapp
npx vitest run \
  src/demo/session.test.ts \
  src/demo/data.test.ts \
  src/demo/patientAppData.test.ts \
  src/copy/neutralTerminologySource.test.ts
```

结果：通过。`4 passed` 测试文件，`5 passed` 测试；无失败或警告。

## 自审

- 已逐项核对绑定码、六个游戏的固定顺序、计划/动作 ID、动作完整字段、每日日期来源和动作新对象语义。
- 已逐项核对演示与真实接口分支；演示分支不调用 `request`，真实分支保持原路径与泛型返回类型。
- 已检查仅新增本任务指定的 `miniapp/src/demo` 文件，无页面与通用请求层变更；`git diff --check` 无空白错误。

## 关注点

- 额外运行 `cd miniapp && npx tsc --noEmit` 未通过，错误位于既有 Taro 依赖声明、现有 `api/client.ts`、`shoulder-press` 等多个非本任务文件；输出中没有 `src/demo` 报错。任务指定的 Vitest GREEN 与中性术语门禁均已通过。

---

## 修复轮次 1/5（2026-08-12）

### 修复内容

- 将 `GameCode`、六游戏代码/名称/类型/引导音频键目录元数据，以及 `gameCodeForActionSource()` 提取到主包共享模块 `miniapp/src/game/catalog.ts`。
- `miniapp/src/demo/data.ts` 与分包 `miniapp/src/pages/game-session/index.tsx` 均改为依赖共享目录；删除原分包 `gameCatalog.ts`，消除演示主包到游戏分包的运行时依赖。
- `gameTypes.ts` 从共享目录导入并继续导出 `GameCode`，保持现有分包内调用方的类型契约不变。
- 扩展演示数据测试，直接调用两次 `createDemoCurrentPrescription()`，逐层验证计划对象、actions 数组以及六个对应 action 对象均不共享引用。

### RED 与保护性测试

边界 RED 命令：

```bash
cd miniapp
npx vitest run src/game/catalog.test.ts
```

首次架构扫描发现 4 条主包到游戏分包的运行时导入，其中本轮目标为 `demo/data.ts -> ../pages/game-session/gameCatalog`，另 3 条是既有 `retryUpload` 跨分包依赖。由于后者涉及本任务明确不修改的 App、首页和运动计划页，测试随后收窄到本轮演示主包源码；再次运行仍按预期失败：

```text
demo/data.ts -> ../pages/game-session/gameCatalog
Cannot find module './catalog'
Test Files  1 failed (1)
Tests       2 failed (2)
```

深独立性保护测试命令：

```bash
cd miniapp
npx vitest run src/demo/data.test.ts
```

结果：`1 passed` 测试文件、`2 passed` 测试。当前工厂通过 `map(createDemoAction)` 已天然逐项新建 action，因此新增断言没有真实缺口可触发；按要求保留为保护性测试，未通过临时篡改生产代码伪造 RED。

### GREEN 与回归验证

目标 GREEN 命令：

```bash
cd miniapp
npx vitest run src/game/catalog.test.ts src/demo/session.test.ts src/demo/data.test.ts src/demo/patientAppData.test.ts src/copy/neutralTerminologySource.test.ts
```

结果：`5 passed` 测试文件、`8 passed` 测试。

全量小程序测试命令：

```bash
cd miniapp
npx vitest run
```

结果：`32 passed` 测试文件、`384 passed` 测试，包含全部现有 game-session 单元测试。

微信小程序构建命令：

```bash
cd miniapp
npm run build:weapp
```

结果：最终复验 Webpack `Compiled successfully in 1.87s`。

### 修复自审

- 共享 `GAME_CATALOG` 的六项顺序、代码、名称、kind 与 introAudioKey 均保持原值；来源映射函数对已知、未知和空来源的契约由测试覆盖。
- 演示数据仅依赖主包共享目录，边界测试会扫描 `src/demo` 全部生产 TypeScript 文件并拒绝运行时相对导入至 `app.config.ts` 声明的分包根目录；纯类型导入不会误报。
- 分包游戏页依赖方向改为分包到主包共享目录，符合微信小程序分包边界；原分包目录文件已删除，无残留 `gameCatalog` 引用。
- `git diff --check` 通过；未修改绑定页、App、首页、运动计划页或其他游戏行为实现。

### 修复关注点

- 全仓架构扫描暴露 3 条本任务前已存在的主包到游戏分包 `retryUpload` 运行时依赖：`app.ts`、`pages/home/index.tsx`、`pages/prescription/index.tsx`。它们不属于本轮游戏目录修复，并涉及明确禁止修改的文件，因此未在本提交处理；建议另立任务迁移 `retryUpload` 到主包共享目录。
