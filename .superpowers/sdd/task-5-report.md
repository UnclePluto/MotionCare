# Task 5 报告：重写小程序分段会话、API 和上传队列

日期：2026-07-11
基线：9810139

## 实现

- `miniapp/src/api/client.ts`：导出 `apiUrl`、`patientAuthorizationHeader`、统一 401/403 清患者 token 并跳 `/pages/bind/index`，错误文本过滤 Authorization/Bearer/token/secret。
- `miniapp/src/pages/shoulder-press/api.ts`：替换为患者端服务端分段上传 API：
  - `POST /api/patient-app/training-video-sessions/`
  - `POST /api/patient-app/training-video-sessions/{video_id}/segments/{index}/`
  - `POST /api/patient-app/training-video-sessions/{video_id}/finalize/`
  - `GET /api/patient-app/training-video-sessions/{video_id}/status/`
- `miniapp/src/pages/shoulder-press/session.ts`：新增 `PendingShoulderPressSession` / `PendingShoulderPressSegment`，`getVideoInfo.size` 按 kB `*1024` 转 bytes，冷恢复校验 RFC4122 v4、连续 index、损坏 segment、状态枚举。
- `miniapp/src/pages/shoulder-press/workflow.ts`：实现 `runPendingSegmentUploads`，服务端已上传 index 合并恢复，逐段单并发上传，每次状态变化先 `saveSession`，成功后先持久化 `uploaded/sha256` 再 best-effort 删除本地文件，失败停在当前片段。
- `miniapp/src/pages/shoulder-press/recorder.ts`：新增无 React Recorder 控制器，timeout 自动续录，pause/finish 禁止自动续录，generation/path 去重处理 timeout 和 stop 回调竞争，小于 2 秒 pause 片段丢弃。
- 保留页面编译所需兼容导出，但 Task5 未改页面组件、样式或真机 `saveFile` 流程。

## 文件

- 修改：`miniapp/src/api/client.ts`
- 替换：`miniapp/src/pages/shoulder-press/api.ts`
- 替换：`miniapp/src/pages/shoulder-press/session.ts`
- 替换：`miniapp/src/pages/shoulder-press/workflow.ts`
- 新增：`miniapp/src/pages/shoulder-press/recorder.ts`
- 替换测试：`miniapp/src/pages/shoulder-press/api.test.ts`
- 替换测试：`miniapp/src/pages/shoulder-press/session.test.ts`
- 替换测试：`miniapp/src/pages/shoulder-press/workflow.test.ts`
- 新增测试：`miniapp/src/pages/shoulder-press/recorder.test.ts`

## RED

命令：

```bash
cd miniapp && npm run test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/api.test.ts src/pages/shoulder-press/workflow.test.ts src/pages/shoulder-press/recorder.test.ts
```

结果：失败，4 个测试文件失败。

准确失败摘要：

- `session.test.ts`：`createPendingShoulderPressSession`、`loadPendingShoulderPressSession`、`clearPendingShoulderPressSession` 等新 session API 不存在。
- `api.test.ts`：`createVideoSession`、`uploadVideoSegment`、`finalizeVideoSession`、`getVideoSessionStatus` 不存在。
- `recorder.test.ts`：`Cannot find module './recorder'`。
- `workflow.test.ts`：旧 workflow 加载 Taro 运行时，出现 `ReferenceError: ENABLE_INNER_HTML is not defined`。

## GREEN / 验证

- 聚焦测试：
  - 命令：`cd miniapp && npm run test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/api.test.ts src/pages/shoulder-press/workflow.test.ts src/pages/shoulder-press/recorder.test.ts`
  - 结果：4 文件、21 测试通过。
- Weapp 构建：
  - 命令：`cd miniapp && npm run build:weapp`
  - 结果：成功，Webpack compiled successfully。
- 全量测试：
  - 命令：`cd miniapp && npm run test`
  - 结果：17 文件、135 测试通过。
- H5 构建：
  - 命令：`cd miniapp && npm run build:h5`
  - 结果：成功；有 Webpack asset/entrypoint size warnings。
- 旧七牛凭证字段扫描：
  - 命令：`rg -n "upload_token|uploadToken|upload_host|uploadHost|bucket" miniapp/src miniapp/dist`
  - 结果：无命中。

## 自审

- cold recovery：`loadPendingShoulderPressSession` 对基础字段、RFC4122 v4、训练日期、连续 index、segment 字段、状态枚举做严格校验；损坏 manifest 返回 `null`。
- 损坏 manifest：空路径、非连续 index、非法 sha256、非法状态均无法恢复为有效 session。
- 连续 index：按数组位置强制 `segment.index === expectedIndex`。
- RFC4122 v4：`createPendingShoulderPressSession` 和恢复逻辑都校验 v4 形状；生成值仅用于幂等，不作为安全凭证。
- 文件删除顺序：workflow 在 upload resolve 后先持久化 `uploadState: uploaded` 与 `sha256`，再调用 `deleteSavedFile`；删除失败被吞掉，不回 pending。
- 错误脱敏：JSON request 与 multipart upload 的 401/403 都清 token 并跳绑定页；错误消息过滤 Authorization/Bearer/token/secret。
- 上传并发：workflow `for...of + await`，测试用受控 Promise 断言下一段不会在当前 upload Promise resolve 前启动。
- 服务端已上传 index：`getVideoSessionStatus` 的 `uploaded_segments` 合并到本地状态，恢复时跳过已确认 index。

## concerns

- Task5 按要求未改页面组件；因此页面仍通过旧兼容导出名调用上传流程，Task6 接页面和真机 `saveFile` 时应移除这些兼容导出。
- `build:h5` 仍有既有资源体积 warning，与本任务无关。

## 审查阻断项修复（2026-07-11, Codex）

### RED

命令：

```bash
cd miniapp && npm run test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/api.test.ts src/pages/shoulder-press/workflow.test.ts src/pages/shoulder-press/recorder.test.ts
```

结果：失败，4 个测试文件中 13 个测试失败，Vitest 同时捕获 2 个 Recorder 未处理 rejection。

准确失败摘要：

- `session.test.ts`：finalized 但仍有 pending segment 的 manifest 被恢复；`actualDurationMs` 与 segment duration 总和不一致的 manifest 被恢复。
- `api.test.ts`：JSON / multipart 的 `{ error: "..." }` 字段未作为可恢复业务错误展示；multipart success 后的 late 401/fail 仍触发清 token/跳转副作用。
- `workflow.test.ts`：远端 `uploaded_segments` 越界、非前缀、重复时 workflow 仍继续上传并 finalize；旧页面 wrapper 仍调用旧 `uploadVideo` 链路。
- `recorder.test.ts`：timeout 下一段 start fail 会丢上一段；timeout `onSegment` reject 未由后续 `finish()` 观察；旧 start fail 回调会污染当前 mode；pause/finish 并发时 `finish()` 不等待同一 stop。

### 修复

- `recorder.ts`：每个 generation 持有独立 `startedAt/state`；start/timeout/stop 回调均校验 generation；timeout 先发起下一段 start，再以受控 Promise 交付上一段；跟踪 pending delivery 与 stopping Promise，`finish()` 会等待并收敛错误。
- `api.ts` / `client.ts`：支持 string `error` 字段并继续脱敏；multipart upload 增加显式 settled guard；兼容 upload 导出不再使用 `videoId=0`、`durationMs=1`、`sizeBytes=1` 占位。
- `session.ts`：冷恢复拒绝 finalized+pending/uploading manifest；要求 `actualDurationMs` 等于所有 segment duration 总和；保留重复 sha 合法、sha 可选。
- `workflow.ts`：远端 `uploaded_segments` 必须是本地范围内从 0 开始的连续前缀，越界/重复/非前缀先持久化 `lastError` 再停止；旧页面 wrapper 使用真实 `createVideoSession` 返回的 `videoId` 与 pending 中原始 `trainingDate/duration/size/path` 构造单段 session，并复用 `runPendingSegmentUploads` 与 finalize。

### GREEN / 验证

- 聚焦测试：
  - 命令：`cd miniapp && npm run test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/api.test.ts src/pages/shoulder-press/workflow.test.ts src/pages/shoulder-press/recorder.test.ts`
  - 结果：4 文件、37 测试通过。
- Weapp 构建：
  - 命令：`cd miniapp && npm run build:weapp`
  - 结果：成功，Webpack compiled successfully。
- 全量测试：
  - 命令：`cd miniapp && npm run test`
  - 结果：17 文件、151 测试通过。
- Diff 检查：
  - 命令：`git diff --check`
  - 结果：通过，无输出。
- 旧七牛凭证字段扫描：
  - 命令：`rg -n "upload_token|uploadToken|upload_host|uploadHost|bucket" miniapp/src miniapp/dist`
  - 结果：无命中。

### concerns

- report 仅追加本修复记录，按要求不纳入提交。
- Task6 仍应移除页面对旧兼容导出名的依赖；本次未改页面、样式或 Task6 `saveFile` 流程。

## JSON runtime shape 与 network 安全收敛修复（2026-07-11, Codex）

### RED

命令：

```bash
cd miniapp && npm run test -- src/pages/shoulder-press/api.test.ts
```

结果：失败，1 个测试文件中 20 个测试失败。

准确失败摘要：

- create/status/finalize 的 2xx malformed body 被 `request<T>` 原样 resolve，没有校验 body 是否为对象、`video_id` 是否为正整数、`status` 是否属于后端 `TrainingVideo.Status`。
- status 的 `uploaded_segments` 缺失、非数组、包含小数或负数时仍被放行。
- finalize 的 `assembly_job_id` 为字符串或非正整数时仍被放行。
- `Taro.request` reject 会把原始错误消息透出，测试中的 `Authorization Bearer patient-token secret request header leaked` 未被收敛为中文安全错误。

### 修复

- `client.ts`：`request` 只在 `Taro.request` 网络 reject 边界统一抛出 `请求失败，请检查网络后重试`，保留后续 401/403 清 token 并跳绑定页、非 2xx `safeApiErrorMessage` 处理。
- `api.ts`：为 create/status/finalize 增加 runtime parser；`status` 只接受后端 `TrainingVideo.Status` 真实集合：`recording`、`uploading_segments`、`queued`、`assembling`、`uploading_qiniu`、`attached`、`failed`、`expired`。
- `api.ts`：status 响应要求 `uploaded_segments` 为非负整数数组；前缀/范围继续由 workflow 结合本地 session 校验。
- `api.ts`：finalize 校验 `video_id/status/assembly_job_id` shape；`assembly_job_id` 接受正整数或后端兼容空值，不接受字符串、小数、0 或负数。

### GREEN / 验证

- RED 后单文件 GREEN：
  - 命令：`cd miniapp && npm run test -- src/pages/shoulder-press/api.test.ts`
  - 结果：1 文件、30 测试通过。
- 用户指定聚焦测试：
  - 命令：`cd miniapp && npm run test -- src/pages/shoulder-press/api.test.ts src/pages/shoulder-press/workflow.test.ts`
  - 结果：2 文件、40 测试通过。
- 全量测试：
  - 命令：`cd miniapp && npm run test`
  - 结果：17 文件、172 测试通过。
- Weapp 构建：
  - 命令：`cd miniapp && npm run build:weapp`
  - 结果：成功，Webpack compiled successfully。
- Diff 检查：
  - 命令：`git diff --check`
  - 结果：通过，无输出。

### concerns

- report 仅追加本修复记录，按要求不纳入提交。
- 本次未改 multipart、workflow、session 或 Recorder。

## JSON runtime contract 最后三项收紧（2026-07-11, Codex）

### RED

命令：

```bash
cd miniapp && npm run test -- src/pages/shoulder-press/api.test.ts
```

结果：失败，1 个测试文件中 5 个测试失败。

准确失败摘要：

- create 成功响应缺失 `uploaded_segments` 时仍被接受。
- status 成功响应的 `video_id` 与请求路径 `videoId` 不一致时仍被接受。
- finalize 成功响应的 `video_id` 与 input `videoId` 不一致时仍被接受。
- finalize 成功响应缺失 `assembly_job_id` 或 `assembly_job_id: null` 时仍被接受。

### 修复

- `api.ts`：`parseVideoSessionStatus` 改为显式 options：`requireUploadedSegments`、`requireAssemblyJobId`、`expectedVideoId`。
- `api.ts`：create 调用要求 `uploaded_segments` 必须存在且为非负整数数组。
- `api.ts`：status 调用要求 `uploaded_segments`，并要求 body `video_id` 等于请求路径 `videoId`。
- `api.ts`：finalize 调用要求 body `video_id` 等于 input `videoId`，且 `assembly_job_id` 必须是正整数，不能缺失或为 `null`。

### GREEN / 验证

- RED 后单文件 GREEN：
  - 命令：`cd miniapp && npm run test -- src/pages/shoulder-press/api.test.ts`
  - 结果：1 文件、38 测试通过。
- 用户指定聚焦测试：
  - 命令：`cd miniapp && npm run test -- src/pages/shoulder-press/api.test.ts src/pages/shoulder-press/workflow.test.ts`
  - 结果：2 文件、48 测试通过。
- 全量测试：
  - 命令：`cd miniapp && npm run test`
  - 结果：17 文件、180 测试通过。
- Weapp 构建：
  - 命令：`cd miniapp && npm run build:weapp`
  - 结果：成功，Webpack compiled successfully。
- Diff 检查：
  - 命令：`git diff --check`
  - 结果：通过，无输出。

### concerns

- report 仅追加本修复记录，按要求不纳入提交。
- 本次未改 `client.ts`、workflow、session、recorder 或 multipart。
