# 训练视频固定健康观察窗口设计

> 状态：implemented
> 日期：2026-08-07
> 范围：以首次录像开始时间和处方时长快照计算医生端健康数据观察窗口，取消健康图表对实际训练结束时间的依赖。
> 关联：`docs/superpowers/specs/2026-08-06-training-video-wearable-window-design.md`
> 回滚基线：`3b85ce1`

修订（2026-08-07, codex）：根据用户批准将状态更新为 `approved`；同时对齐关联设计的一期边界，明确步数仅有日总量，不进入训练时段趋势。

修订（2026-08-07, codex）：Task 1-4 已分别落地于 `1f624a1`、`12b8e4e`、`1f75ab0`、`036cf79`；后端、医生端和小程序全量测试及构建验证通过，状态更新为 `implemented`。

## 1. 背景

现有训练视频健康图表使用 `training_started_at` 至 `training_ended_at`
作为查询范围。为了保证实际结束时间准确、可恢复且只能提交一次，小程序录像、
分段落盘、上传重试、页面恢复与服务端 finalize 被逐步绑定到同一套复杂状态逻辑。

本项目尚未上线，不需要兼容旧本地 mock 数据。新的产品决策是把“健康观察窗口”
与“视频上传生命周期”彻底分开：

- 健康观察窗口使用首次录像开始时间和本次处方时长快照计算。
- 实际完成时间仍可上传和保存，但允许缺失，不参与图表查询。
- 视频暂停、实际录像时长、上传时间和处理状态均不得修改健康观察窗口。

本设计替代关联设计中以下规则：

- `training_ended_at` 必填。
- 健康数据以 `training_started_at <= measured_at <= training_ended_at` 查询。
- 实际录像时长必须与开始至结束的墙钟跨度耦合校验。

关联设计中的健康指标、趋势图、统计表和医生端展示规则继续保留。

## 2. 目标与非目标

### 2.1 目标

- 记录第一次录像真正启动成功时的手机端时间。
- 使用视频会话保存的处方时长快照计算固定健康观察窗口。
- 正常完成时尽力上传实际完成时间，意外退出时允许缺失。
- 让视频上传失败、延迟或重试不影响健康数据时间范围。
- 保留医生端心率、血压、血氧趋势及心率、血压统计展示。
- 删除为保证实际结束时间而引入的复杂录像状态机。

### 2.2 非目标

- 不恢复或迁移旧 Manifest、本地上传清单或 mock 数据。
- 不根据实际录像时长动态缩短或延长健康观察窗口。
- 不在医生端展示实际完成时间。
- 不新增后台任务补写缺失的 `training_ended_at`。
- 不改变穿戴设备数据采集和同步逻辑。

## 3. 核心时间语义

### 3.1 首次录像开始时间

继续使用 `TrainingVideo.training_started_at`，语义固定为：

> 本次训练第一次调用摄像头录像并收到启动成功结果时的手机端时间。

规则：

- 手机端生成带时区偏移的 ISO 8601 时间。
- 暂停和继续录像不得修改该值。
- 相同 `client_session_id` 重试创建视频会话时必须提交相同值。
- 该值不是服务器收到请求的时间，也不是首个分段上传完成时间。

### 3.2 实际完成时间

继续保留 `TrainingVideo.training_ended_at`，语义固定为：

> 用户正常点击“完成训练”时的手机端时间。

规则：

- 字段允许为空。
- 正常完成时，小程序随 finalize 请求上传该值。
- 意外退出、崩溃或没有进入正常完成流程时，不推算、不补写。
- 有值时只校验晚于 `training_started_at`。
- 不参与健康图表查询，不参与实际录像时长校验，医生端暂不展示。

### 3.3 固定健康观察窗口

视频会话继续保存 `expected_duration_seconds`，它是创建会话时处方动作时长的快照。
健康观察窗口固定为：

```text
window_started_at = training_started_at
window_ended_at = training_started_at
                  + expected_duration_seconds
                  + 300 秒
```

示例：

- 第一次录像开始：09:00。
- 处方动作时长：15 分钟。
- 固定缓冲：5 分钟。
- 医生端健康观察窗口：09:00–09:20。

该窗口一经视频会话创建即保持稳定。之后修改处方、暂停训练、继续录像、提前完成、
延迟上传或视频处理失败均不得改变窗口。

## 4. 组件边界

### 4.1 小程序录像页

小程序使用回滚基线中的简单待上传会话结构，不引入 Manifest V2 phase 状态机。

职责：

- 第一次录像启动成功时生成并保存 `training_started_at`。
- 暂停或继续时复用原值。
- 正常点击完成时生成可选 `training_ended_at`。
- 将两个时间随既有创建和 finalize 请求上传。

不负责：

- 根据视频分段时长计算健康窗口。
- 为补齐 `training_ended_at` 执行冷恢复或复杂补偿事务。
- 因上传结果修改训练开始或结束时间。

### 4.2 视频上传流程

视频上传继续负责：

- 创建或恢复 `client_session_id` 对应的服务端视频会话。
- 上传分段并执行 finalize。
- 按既有幂等规则重试。

上传流程与健康窗口只有两项输入关联：

- 创建会话时提交 `training_started_at`。
- 创建会话时提交 `expected_duration_seconds`。

`training_ended_at` 是 finalize 的可选审计字段。上传时间与服务端处理时间不参与窗口计算。

### 4.3 后端视频服务

后端继续保存：

- `training_started_at`
- `training_ended_at`（nullable）
- `expected_duration_seconds`
- `actual_duration_seconds`

创建视频会话：

- 新版小程序必须提交 `training_started_at`。
- 必须提交有效的 `expected_duration_seconds`。
- 相同 `client_session_id` 的重复创建必须保持两者一致。

完成视频会话：

- `training_ended_at` 改为可选。
- 有值时必须晚于开始时间。
- 删除“实际录像时长不得大于训练墙钟跨度”的耦合校验。
- 视频分段总时长与 `actual_duration_seconds` 的一致性校验继续保留。

### 4.4 健康观察窗口接口

`GET /api/training/videos/{video_id}/wearable-window/` 不再读取
`training_ended_at` 作为查询上界。

可用响应新增明确的窗口字段：

```json
{
  "available": true,
  "window_started_at": "2026-08-06T01:00:00Z",
  "window_ended_at": "2026-08-06T01:20:00Z",
  "expected_duration_seconds": 900,
  "buffer_seconds": 300
}
```

实际响应继续包含既有的心率、血压、血氧序列和统计结构。一期不查询、
不估算、不展示训练时段步数，因为当前厂商接口只提供自然日总步数。

不可用规则：

- `training_started_at` 缺失；或
- `expected_duration_seconds` 缺失或无效。

满足任一条件时返回 `available: false`，医生端不展示图表。

健康测量点仍按闭区间查询：

```text
window_started_at <= measured_at <= window_ended_at
```

### 4.5 医生 Web 端

医生端：

- 使用 `window_started_at` 和 `window_ended_at` 设置图表横轴。
- 展示固定观察窗口内的心率、血压、血氧趋势。
- 保留心率和血压的平均值、最高值、最低值统计。
- 不展示 `training_ended_at`。
- 接口 `available: false` 时不展示健康图表。

## 5. 异常与幂等

### 5.1 意外退出

- 已记录开始时间但没有正常完成时，`training_ended_at` 可以永久为空。
- 不启动后台补写，不推算实际完成时间。
- 只要视频会话存在有效的开始时间和处方时长，健康窗口仍可计算。

### 5.2 网络与上传失败

- 创建会话重试必须复用相同 `client_session_id`、开始时间和处方时长。
- 上传失败只影响视频上传状态，不改变健康窗口。
- finalize 重试有结束时间时复用同一值；没有结束时间时继续提交空值。
- 第一次成功 finalize 的 `training_ended_at`（包括空值）即为最终审计值；
  后续幂等重试必须保持相同，不支持在 finalize 完成后补写。
- 已保存的非空实际完成时间不得被其他值覆盖。

### 5.3 时间校验

- `training_started_at` 必须是带时区偏移的合法手机时间。
- 非空 `training_ended_at` 必须晚于开始时间。
- `expected_duration_seconds` 必须符合现有视频时长上限。
- 健康窗口由后端使用 aware datetime 加秒数计算，避免客户端版本产生差异。

## 6. 回滚与实施边界

实施前已创建备份分支：

```text
codex/backup-training-video-state-machine-20260807
```

当前工作分支回滚至：

```text
3b85ce1 docs(training): 记录训练时段穿戴趋势实施结果
```

因此以下内容不进入新实现：

- Manifest V2 及其 phase 状态机。
- 摄像页 lifecycle recovery。
- 后台上传与生命周期字段的复杂 CAS 合并。
- completed 清单所有权清理协议。
- 为保证实际结束时间完整而增加的录像回调补偿逻辑。

新实现只在回滚基线上完成本设计所需的最小修改。

## 7. 测试与验收

### 7.1 小程序

- 第一次录像启动成功只记录一次 `training_started_at`。
- 暂停和继续不修改开始时间。
- 正常完成上传 `training_ended_at`。
- 意外退出或缺少结束时间不阻断后续允许的上传恢复。
- 上传重试不修改开始时间和处方时长。

### 7.2 后端

- 创建会话保存手机开始时间和处方时长快照。
- 相同会话的冲突开始时间或处方时长被拒绝。
- finalize 接受缺失的 `training_ended_at`。
- 非空结束时间必须晚于开始时间。
- 实际录像时长不再与训练墙钟跨度耦合。
- 观察窗口严格等于开始时间加处方时长再加 300 秒。
- 缺失开始时间或处方时长时接口返回不可用。

### 7.3 Web

- 图表横轴使用 `window_started_at/window_ended_at`。
- 实际完成时间变化或缺失不改变图表范围。
- 无可用窗口时不展示健康图表。
- 既有趋势和统计展示保持不变。

### 7.4 完成门禁

完成前必须通过：

```bash
cd backend && pytest
cd frontend && npm run test
cd frontend && npm run lint
cd frontend && npm run build
cd miniapp && npm run test
cd miniapp && npm run build:weapp
```

同时扫描并确认新实现不存在 Manifest V2 状态机残留。
