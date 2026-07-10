# Task 5 接管报告：肩部推举录像与强制上传流

日期：2026-07-10

## 接管说明

本任务接管时，前一代理已经留下初始 RED 测试、小程序实现和扩展测试，但没有可读取的任务报告，也没有提交。因此本报告不推断或伪造前一代理的命令输出；以下仅记录本次接管实际新增的 RED/GREEN 和最终验证。

## 已审核并保留的实现

- 处方动作按 `source_key` 路由，肩部推举进入专用跟练页，其他训练/游戏维持既有入口。
- 跟练页在同一训练舞台固定展示前置 `Camera` 与 `video_url` 示例视频；缺少视频时显示动作说明，录像落盘前通过 `Taro.getVideoInfo` 获取真实时长和大小。
- 停止录像后保存 pending 状态并 `reLaunch` 到上传页；上传页自动恢复，凭证、七牛上传、保存训练记录三阶段都有状态和真实上传进度，运行中的操作由 ref 防重入。
- 工作流持久化凭证的 `expiresAt` 和七牛 hash；凭证到期时重取，hash 已保存时 complete 重试跳过上传；七牛返回 key 必须与申请 key 匹配；只有 complete 成功后才清除 pending 并离开上传页。

## 本次新增 RED/GREEN

1. RED：基础录像数据有效但上传凭证只有部分字段时，`loadPendingShoulderPressUpload` 返回 `null`，无法恢复。GREEN：剥离损坏的远端阶段数据，保留录像基座，上传工作流会重新申请凭证。
2. RED：完整凭证状态中混入非字符串 `lastError` 时，该未校验字段会原样返回。GREEN：加载逻辑只重建已校验字段，丢弃损坏诊断数据。

同时移除了 pending 基座缺失/损坏时上传页直接返回处方的入口，避免违反“仅 complete 成功后清除并离开”的强制流程约束。

## 最终验证

- `cd miniapp && npm run test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/api.test.ts src/pages/shoulder-press/workflow.test.ts src/pages/shoulder-press/pageState.test.ts src/pages/prescription/actionRouting.test.ts`：5 文件、29 测试通过。
- `cd miniapp && npm run test`：16 文件、137 测试通过。
- `cd miniapp && npm run build:weapp`：成功。
- `cd miniapp && npm run build:h5`：成功；仅有既有游戏资源导致的 Webpack 资源体积警告。按任务约束未启动浏览器或 Playwright。

已清理 `frontend/dist`、`miniapp/dist` 与 `.playwright-cli` 类临时产物（未发现后者）。
