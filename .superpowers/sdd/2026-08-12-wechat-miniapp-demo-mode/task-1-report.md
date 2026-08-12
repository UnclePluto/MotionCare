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
