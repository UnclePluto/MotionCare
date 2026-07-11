> 状态：superseded
> 日期：2026-07-08
> 范围：肩部推举专项升级；小程序录像跟练、七牛 Kodo 直传、医生端视频审阅、PP-TinyPose 手动分析。
> 关联：`docs/superpowers/specs/2026-05-14-prescription-motion-training-design.md`、`docs/superpowers/specs/2026-05-14-wechat-miniapp-patient-daily-workbench-design.md`、`docs/superpowers/specs/2026-05-15-game-prescription-tracking-design.md`
> 实施基线 commit：c72d8ce
>
> 修订（2026-07-11, codex）：七牛直传单文件方案已由 `docs/superpowers/specs/2026-07-11-shoulder-press-segmented-server-upload-design.md` 替代；本文件保留为历史记录。

# 肩部推举录像跟练与动作分析设计

## 背景

MotionCare 已经有运动训练处方闭环：肩部推举作为固定动作库中的 `motion-resistance-shoulder-press`，通过 `ActionLibraryItem -> PrescriptionAction -> TrainingRecord` 进入患者端处方、本周进度和医生端训练追踪。

此前设计把运动类训练定义为表单模拟，不做摄像头采集、视频上传和 AI 动作识别。本设计覆盖该后置决策：仅将肩部推举升级为真实录像跟练和医生端手动分析，不把所有运动动作一次性泛化。

## 已确认决策

1. **本期只升级肩部推举**：其它运动动作继续走现有普通训练记录页。
2. **继续使用既有训练主链路**：不新建独立运动训练体系，训练完成后仍创建 `TrainingRecord`。
3. **上传后再创建训练记录**：小程序完成录像后进入强制上传页，上传和后端绑定成功后才创建训练记录。
4. **上传采用七牛云 Kodo 直传**：后端生成上传凭证，小程序直传七牛，后端不承载视频大文件流量。
5. **医生端手动触发分析**：患者上传完成后，医生在后台查看视频并点击动作分析。
6. **PP-TinyPose 只负责关键点检测**：肩部推举计数和标准/不标准判定由 MotionCare 业务规则层完成。
7. **分析不阻塞训练记录**：视频上传成功即可形成训练记录；分析失败不删除训练记录或视频。

## 目标

- 小程序肩部推举页默认请求前置摄像头，展示示例视频或动作说明，并录制患者训练视频。
- 训练完成后进入强制上传等待页，要求用户等待七牛上传和后端保存完成。
- 后端生成七牛 Kodo 上传凭证，并记录训练视频对象。
- 上传完成后后端创建 `TrainingRecord`，并将视频绑定到该记录。
- 医生端训练追踪可以查看肩部推举视频，并手动触发 PP-TinyPose 分析任务。
- 分析结果展示总次数、标准次数、不标准次数、任务状态和基础异常标记。

## 非目标

- 不做实时动作纠错。
- 不做所有运动动作的视频化。
- 不做医学诊断级动作评分。
- 不做患者端分析结果实时反馈。
- 不做七牛空间创建、账号管理或计费管理。
- 不做视频转码、内容审核、生命周期清理的完整后台配置界面。

## 总体架构

肩部推举仍基于当前 active 处方动作执行。小程序通过患者端 token 获取当前处方；当动作 `source_key` 为 `motion-resistance-shoulder-press` 时，进入专用跟练页。

新增两个核心后端模型：

```text
TrainingVideo
- project_patient
- prescription
- prescription_action
- training_record nullable
- storage_backend: qiniu_kodo
- bucket
- object_key
- object_hash
- original_filename
- content_type
- size_bytes
- duration_seconds
- status: uploading | uploaded | attached | failed | expired
- upload_token_expires_at
- uploaded_at
- failure_reason
- created_at / updated_at
```

```text
MotionAnalysisJob
- training_video
- training_record
- project_patient
- prescription_action
- status: pending | running | succeeded | failed
- algorithm_name: pp-tiny-pose
- algorithm_version
- rule_version
- total_count
- standard_count
- nonstandard_count
- result_payload
- failure_reason
- requested_by
- started_at
- finished_at
- created_at / updated_at
```

`TrainingRecord` 不直接新增视频字段，通过 `TrainingVideo.training_record` 反查视频。这样后续其它动作需要录像时可以复用视频模型。

## 七牛 Kodo 上传设计

后端使用七牛 Kodo 原生上传凭证，不把七牛 AK/SK 下发给小程序。根据七牛文档，客户端上传前需要从服务端获取上传凭证，上传时将凭证作为请求内容的一部分；不带凭证或凭证非法会返回 401。直传文件接口使用表单上传，返回资源 `hash` 和 `key`。

MotionCare 后端配置：

```text
QINIU_ACCESS_KEY
QINIU_SECRET_KEY
QINIU_BUCKET
QINIU_UPLOAD_HOST
QINIU_DOWNLOAD_DOMAIN
QINIU_PRIVATE_BUCKET=true
QINIU_UPLOAD_TOKEN_TTL_SECONDS
QINIU_DOWNLOAD_TOKEN_TTL_SECONDS
```

后端生成上传凭证时，scope 固定到单个对象：

```text
scope = "<bucket>:<object_key>"
```

对象 key 由后端生成，建议格式：

```text
training-videos/{project_patient_id}/{yyyy}/{mm}/{dd}/{uuid}.mp4
```

这样小程序只能上传到指定 key，不能自行决定覆盖其它对象。

相关七牛文档：

- 快速入门：`https://developer.qiniu.com/kodo/1233/console-quickstart`
- 上传凭证：`https://developer.qiniu.com/kodo/1208/upload-token`
- 直传文件：`https://developer.qiniu.com/kodo/1312/upload`
- 下载凭证：`https://developer.qiniu.com/kodo/1202/download-token`

## API 设计

### 小程序患者端

```text
POST /api/patient-app/training-videos/upload-intent/
```

请求：

```json
{
  "prescription_action": 123,
  "content_type": "video/mp4",
  "size_bytes": 10485760,
  "duration_seconds": 180
}
```

响应：

```json
{
  "video_id": 456,
  "bucket": "motioncare-training",
  "key": "training-videos/89/2026/07/08/uuid.mp4",
  "upload_token": "<qiniu-upload-token>",
  "upload_host": "https://upload.qiniup.com",
  "expires_at": "2026-07-08T10:15:00+08:00"
}
```

后端校验：

- 患者端 token 有效。
- `prescription_action` 属于 token 绑定的 `ProjectPatient` 当前 active 处方。
- 动作编码是 `motion-resistance-shoulder-press`。
- 文件类型和大小在允许范围内。

```text
POST <Qiniu Upload Host>/
```

小程序使用七牛直传表单：

```text
key=<object_key>
token=<upload_token>
file=<video_file>
```

```text
POST /api/patient-app/training-videos/{video_id}/complete/
```

请求：

```json
{
  "key": "training-videos/89/2026/07/08/uuid.mp4",
  "hash": "<qiniu-etag>",
  "training_date": "2026-07-08",
  "actual_duration_minutes": 3,
  "note": ""
}
```

后端校验对象 key、七牛 hash、当前处方动作仍有效后，创建 `TrainingRecord(status=completed)`，绑定 `TrainingVideo.training_record`，并将视频状态置为 `attached`。complete 接口需要幂等：同一 `video_id` 重复提交时返回已创建的训练记录，避免重复记录。

### 医生端

```text
GET /api/training/videos/{video_id}/download-url/
```

后端校验医生对该 `ProjectPatient` 有权限后，生成短有效期七牛私有下载 URL。私有空间不向前端暴露永久公开地址。

```text
POST /api/training/videos/{video_id}/analysis-jobs/
```

后端校验：

- 医生有权限访问该训练记录。
- 视频状态为 `attached`。
- 动作是 `motion-resistance-shoulder-press`。
- 当前没有 `pending` 或 `running` 分析任务。

成功后创建 `MotionAnalysisJob(status=pending)`，交给 Celery 或后台 worker。

```text
GET /api/training/videos/{video_id}/analysis-jobs/latest/
```

返回最近一次分析任务状态和结果，供医生端轮询或刷新。

## 小程序页面

当前处方页识别肩部推举：

- `source_key = motion-resistance-shoulder-press` 时按钮文案为“开始跟练”。
- 其它 `motion` 动作仍显示“开始训练”，走现有训练记录页。

肩部推举跟练页：

- 默认请求前置摄像头。
- 同屏展示摄像头预览和示例视频或动作说明。
- 未授权摄像头时不允许开始训练。
- 训练开始后录像，展示计时、处方建议和结束按钮。
- 达到最长录制时长后自动停止；系统硬上限建议为 10 分钟。

强制上传页：

- 停止录像后必须进入。
- 显示“正在上传训练视频，请保持小程序打开”。
- 展示步骤：申请上传凭证、上传视频、保存训练记录。
- 不提供“跳过上传并完成”。
- 上传失败时停留本页，展示失败原因和“重试上传”。
- 小程序关闭或返回时，本地保留待上传视频路径和 `video_id`，下次进入优先提示继续上传。

结果页：

- 只有 complete 接口成功后才进入。
- 展示训练已保存、训练时长和返回处方页入口。
- 不展示 PP-TinyPose 分析结果；分析结果属于医生端。

## 医生端页面

训练追踪详情页扩展现有“最近训练记录”：

- 肩部推举记录展示视频状态。
- 已上传视频显示“查看视频”。
- 可分析视频显示“动作分析”。
- 有最新分析结果时展示总次数、标准次数、不标准次数和分析状态。

视频抽屉：

- 调用后端获取短有效期下载 URL。
- 使用浏览器视频播放器播放。
- 展示训练日期、动作名称、处方版本、患者、项目、上传时间。
- 展示最新分析结果或失败原因。

分析任务：

- 医生点击“动作分析”后立即创建任务。
- 前端可以轮询最新任务，也可以提示医生稍后刷新。
- 失败任务允许重试；重试创建新任务，历史任务保留用于审计。

## PP-TinyPose 分析规则

PP-TinyPose 用于输出人体关键点。肩部推举规则层使用肩、肘、腕、髋等关键点和置信度做基础计数。

计数状态：

- `down`：手腕接近肩部高度，肘部弯曲。
- `up`：手腕明显高于肩部，肘部接近伸直。
- `transition`：上下之间过渡。

一次候选重复为：

```text
down -> up -> down
```

去抖规则：

- 状态需要持续若干帧或若干毫秒才确认。
- 视频开头和结尾不完整的半次动作不计入总次数。
- 左右关键点可优先选择置信度更稳定的一侧，或使用双侧平均。

第一版标准判定：

- `range_too_small`：没有达到明确 `up` 状态。
- `tempo_abnormal`：单次动作过快或过慢。
- `low_confidence`：该次动作关键帧置信度不足。

结果结构：

```json
{
  "total_count": 8,
  "standard_count": 6,
  "nonstandard_count": 2,
  "rep_details": [
    {
      "index": 1,
      "start_ms": 1200,
      "end_ms": 4100,
      "is_standard": true,
      "flags": []
    },
    {
      "index": 2,
      "start_ms": 4300,
      "end_ms": 5900,
      "is_standard": false,
      "flags": ["range_too_small"]
    }
  ],
  "quality_flags": ["camera_angle_unverified"]
}
```

限制：

- 只做训练后分析，不做实时纠错。
- 第一版仅支持正面或近正面坐姿/站姿肩部推举。
- 摄像头角度太偏或遮挡严重时，结果标记低可信。
- 不把不标准动作解释为医学诊断。

## 失败处理

- 摄像头权限失败：不开始训练，不创建后端记录。
- 上传凭证过期：重新申请上传意图或刷新上传凭证；旧视频记录标记 `expired` 或 `failed`。
- 七牛上传失败：保留本地视频，允许重试。
- 上传成功但 complete 失败：用同一个 `video_id` 重试 complete，避免重复创建训练记录。
- complete 时处方已更新：不创建训练记录，提示返回当前处方重新开始；已上传对象标记为孤儿视频，后续清理。
- 医生分析失败：不影响训练记录和视频，任务记录失败原因，允许重试。

## 权限与安全

- 患者端所有视频上传接口都从患者 token 推导 `ProjectPatient`，不信任前端传入患者或项目 ID。
- 后端生成七牛上传凭证时固定 bucket 和 key。
- 医生端下载 URL 必须短有效期，且每次访问前校验医生权限。
- 七牛 AK/SK 只保存在后端环境变量中。
- 视频对象默认按私有资源处理。

## 测试与验收

### 后端

- 非肩部推举动作不能申请训练视频上传意图。
- 非当前 active 处方动作不能申请上传意图。
- 上传意图生成固定 key 的七牛上传凭证。
- complete 成功后创建一条 `TrainingRecord` 并绑定 `TrainingVideo`。
- complete 重复提交不创建重复训练记录。
- 处方更新后 complete 被拒绝。
- 医生无权限时不能获取视频下载 URL 或创建分析任务。
- 同一视频已有运行中任务时不能重复创建新任务。
- 分析任务成功写入总次数、标准次数、不标准次数。
- 分析失败保存失败原因，且不影响训练记录。

### 小程序

- 肩部推举进入专用录像跟练页。
- 默认请求前置摄像头，未授权时不能开始。
- 录像结束后进入强制上传页。
- 上传完成前不跳转结果页。
- 上传失败后可以在强制上传页重试。
- complete 成功后返回处方页并刷新本周进度。

### 医生端

- 训练追踪最近记录中肩部推举展示视频状态。
- 医生可以打开视频抽屉播放七牛私有下载 URL。
- 医生可以手动触发动作分析。
- 分析中、成功、失败三种状态均有明确展示。
- 成功结果展示总次数、标准次数、不标准次数。

## 风险与后续

- 七牛上传域名、空间区域和跨域策略需要在部署前确认。
- 小程序录像 API 在不同机型上可能有兼容差异，实施时需要真机验证。
- PP-TinyPose 推理环境可能需要独立 Python 依赖和模型文件，建议与 Django Web 进程隔离。
- 肩部推举标准判定阈值需要通过样例视频校准；第一版应允许通过配置调整。
- 后续可以把 `TrainingVideo` 复用到其它运动动作，但需要为每个动作单独设计规则层。
