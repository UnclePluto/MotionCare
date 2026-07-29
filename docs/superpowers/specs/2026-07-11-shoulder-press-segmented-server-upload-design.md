> 状态：approved
> 日期：2026-07-11
> 范围：肩部推举 30 秒分段录制、业务服务器断点上传、FFmpeg 合并、最终视频上传七牛、医生审阅与 PP-TinyPose 分析。
> 关联：`docs/superpowers/specs/2026-07-08-shoulder-press-video-analysis-design.md`、`docs/superpowers/plans/2026-07-10-shoulder-press-video-analysis.md`
> 实施基线 commit：d2fe616（已有单文件直传实现，需按本设计替换患者上传链路）
>
> 审批记录（2026-07-11）：用户已确认书面设计，可进入实施计划阶段。
> 实施记录（2026-07-11, codex）：本地代码、PostgreSQL、真实 FFmpeg、后端/小程序/医生端自动验证与最终代码审查已完成；真实七牛、iOS/Android 真机、生产部署及真实 PP-TinyPose E2E 待验收，状态保持 approved。

# 肩部推举分段录制、服务端合并与动作分析设计

## 背景

肩部推举继续沿用 `ActionLibraryItem -> PrescriptionAction -> TrainingRecord` 主链路。医生端视频审阅、PP-TinyPose 关键点推理和肩部推举规则层已经具备基础实现，但微信小程序 `CameraContext.startRecord` 单段录制存在约 30 秒上限，原有“录制一个完整文件后直传七牛”的设计无法覆盖最长 10 分钟的训练。

本设计替代七牛 Kodo 单文件直传方案。小程序把录像切成约 30 秒片段，在训练过程中逐段上传 MotionCare 单台业务服务器；服务器使用 FFmpeg 合并为一个 MP4，只把最终文件上传一次七牛。系统不调用七牛 `avconcat` 或其它多媒体处理能力，避免额外的七牛媒体处理费用。

## 已确认决策

1. **本期只升级肩部推举**：其它运动动作继续走普通训练记录页。
2. **分段只影响上传链路**：医生播放和动作分析始终面对一个完整 MP4，不展示分段。
3. **约 30 秒自动分段**：小程序连续录制，片段数量可以超过 20；FFmpeg 不依赖七牛 21 段限制。
4. **训练中后台上传**：每段持久化后进入单并发上传队列，降低训练结束后的等待时长。
5. **上传到业务服务器**：小程序不再获取七牛上传凭证，也不直接访问七牛上传域名。
6. **单机临时存储**：一期按 Django Web 与 Celery/FFmpeg Worker 共享本机临时磁盘设计，不引入 NAS 或临时对象存储。
7. **服务器本地合并**：优先无损转封装；不兼容时最多执行一次完整转码。
8. **最终文件只上传一次七牛**：七牛仅保存医生端最终视频，不保存录像分段和中间文件。
9. **强制页等待分段安全上传**：所有分段到达服务器并成功提交合并任务后，患者即可离开；FFmpeg、七牛上传和训练记录创建异步完成。
10. **成功立即清理**：七牛对象校验和训练记录创建成功后立即删除服务器本地文件；清理失败异步重试。
11. **失败保留 24 小时**：中断、合并失败或上传失败的临时文件最多保留 24 小时，之后标记过期并删除。
12. **处理中不创建训练记录**：只有最终七牛对象校验成功后才创建唯一 `TrainingRecord` 并绑定视频。
13. **医生手动触发分析**：PP-TinyPose 仍由医生触发，分析失败不影响已经创建的训练记录。
14. **不做分段边界识别**：FFmpeg 合并后按普通连续视频分析，不向规则层传递分段边界或增加边界状态机。

## 目标

- 小程序默认开启前置摄像头，同屏播放示例视频并录制患者训练。
- 自动生成、持久化和后台上传多个短片段，支持断网重试与冷启动恢复。
- 训练完成后进入不可绕过的上传等待页，确认所有片段安全到达业务服务器。
- 服务器可靠地合并任意合理数量的片段，并把最终 MP4 上传七牛私有空间。
- 成功后创建训练记录、删除本地视频，医生端可以播放完整视频并执行动作分析。
- 对磁盘耗尽、进程崩溃、重复请求和清理失败提供可恢复机制。

## 非目标

- 不做实时动作纠错或患者端分析结果展示。
- 不做小程序本地 FFmpeg/WASM 合并。
- 不调用七牛音视频拼接、转码、审核或其它 DORA 多媒体处理服务。
- 不设计多台业务服务器之间的共享临时存储。
- 不为其它运动动作泛化录像入口。
- 不做临时文件管理后台或七牛生命周期配置界面。
- 不把“不标准”结果解释为医学诊断。

## 总体架构

```text
前置摄像头 + 示例视频
        |
        v
小程序约 30 秒录像片段
        |
        +--> 本地持久化 --> 单并发后台上传 --> 业务服务器临时目录
        |                                           |
        +--> 训练结束强制页补传剩余片段               v
                                            VideoAssemblyJob
                                                    |
                                                    v
                                              FFmpeg 合并
                                                    |
                                                    v
                                            最终 MP4 上传七牛
                                                    |
                                                    v
                                      七牛 stat 校验 + 创建 TrainingRecord
                                                    |
                                                    +--> 删除本地临时文件
                                                    +--> 医生播放/手动分析
```

一期部署约束：Django Web、Celery Worker 和 Celery Beat 位于同一台服务器，且都能访问 `TRAINING_VIDEO_STAGING_ROOT`。临时目录不得通过 Django、Nginx 或其它静态文件服务暴露。

## 数据模型

### TrainingVideo

`TrainingVideo` 代表一次患者录像会话和最终七牛视频，保留既有处方、患者与训练记录关系，并调整为会话状态模型：

```text
TrainingVideo
- id
- client_session_id UUID
- project_patient
- prescription
- prescription_action
- training_record nullable unique
- training_date
- note
- expected_duration_seconds
- actual_duration_seconds
- expected_segment_count nullable
- uploaded_segment_count
- status:
    recording
    uploading_segments
    queued
    assembling
    uploading_qiniu
    attached
    failed
    expired
- storage_backend: qiniu_kodo
- bucket
- object_key
- object_hash
- content_type
- size_bytes
- duration_seconds
- failure_reason
- finalized_at
- uploaded_at
- created_at / updated_at
```

约束：

- `client_session_id` 在同一 `ProjectPatient` 下唯一，用于小程序重试和冷启动恢复。
- `training_record` 仍保持一对一，重复任务不能创建重复训练记录。
- `object_key` 由后端生成，患者端不能指定 bucket、key 或服务器路径。
- `uploaded_segment_count` 可以缓存，但最终完成条件必须查询真实已完成分段，不能只信任计数器。

### TrainingVideoSegment

```text
TrainingVideoSegment
- training_video
- index
- duration_ms
- size_bytes
- sha256
- relative_path
- status: uploading | uploaded | deleted | failed
- uploaded_at
- failure_reason
- created_at / updated_at
```

约束：

- `(training_video, index)` 唯一。
- `index` 从 0 开始且必须小于配置的最大分段数。
- 只保存相对 `TRAINING_VIDEO_STAGING_ROOT` 的路径；任何文件操作都必须安全解析并确认仍位于会话目录内。
- 服务端计算实际大小和 SHA-256，不信任客户端声明。

### VideoAssemblyJob

```text
VideoAssemblyJob
- training_video one-to-one
- status: pending | running | succeeded | failed
- attempt_count
- output_relative_path
- qiniu_object_key
- qiniu_object_hash
- cleanup_status: pending | succeeded | failed
- cleanup_attempt_count
- failure_reason
- cleanup_error
- started_at
- finished_at
- heartbeat_at
- created_at / updated_at
```

`VideoAssemblyJob` 负责 FFmpeg、最终七牛上传和本地清理的生命周期。任务状态与医生触发的 `MotionAnalysisJob` 相互独立。

## 本地目录与原子写入

建议目录：

```text
<TRAINING_VIDEO_STAGING_ROOT>/<training_video_id>-<client_session_uuid>/
├── segments/
│   ├── 000000.mp4
│   ├── 000001.mp4
│   └── ...
└── working/
    ├── concat.txt
    ├── final.tmp.mp4
    └── final.mp4
```

规则：

- 上传先写入服务器生成的 `.part` 临时文件，流式计算大小和 SHA-256；成功后使用同文件系统原子重命名为分段文件。
- 会话目录同时包含后端生成且全局唯一的 `TrainingVideo.id` 与客户端会话 UUID；不允许仅使用患者可控、只在患者内唯一的 `client_session_id`。不使用客户端文件名构造目录或文件名。
- FFmpeg 先输出 `final.tmp.mp4`，验证成功后原子重命名为 `final.mp4`。
- 临时根目录使用仅服务账号可读写权限，不进入服务器备份。
- 删除逻辑不得跟随符号链接；清理前再次确认目标位于该会话目录内。

## 患者端 API

### 创建或恢复会话

```text
POST /api/patient-app/training-video-sessions/
```

请求示例：

```json
{
  "client_session_id": "8cf99c30-9b03-4bda-b4d3-b492f3a2db12",
  "prescription_action": 123,
  "training_date": "2026-07-11",
  "expected_duration_seconds": 180
}
```

后端从患者 token 推导 `ProjectPatient`，校验当前 active 处方及肩部推举动作。相同患者和 `client_session_id` 重复请求返回原会话及已上传分段，不创建新会话。

### 上传单个片段

```text
POST /api/patient-app/training-video-sessions/{video_id}/segments/{index}/
Content-Type: multipart/form-data
```

表单字段：

```text
file=<本地 mp4>
duration_ms=<实际片段时长>
size_bytes=<小程序读取的大小，仅作提前校验>
```

后端行为：

- 校验会话归属、状态、序号、内容类型、单段大小、总大小和总时长。
- 使用 Django 临时文件上传机制，避免把视频整体读入 Python 内存。
- 计算实际大小和 SHA-256，并原子落盘。
- 同一序号已经成功上传时返回现有结果；元数据冲突则返回 409，不静默覆盖。
- 响应包含服务端大小、SHA-256、时长和当前已上传分段数。

### 提交录像完成

```text
POST /api/patient-app/training-video-sessions/{video_id}/finalize/
```

请求示例：

```json
{
  "segment_count": 23,
  "actual_duration_seconds": 598,
  "note": ""
}
```

后端在数据库事务中锁定 `TrainingVideo` 和当前 `ProjectPatient`，并校验：

- 会话仍属于当前患者与原处方动作。
- `0..segment_count-1` 全部分段存在且状态为 `uploaded`。
- 分段总大小、总时长、数量均未超过配置上限。
- 客户端总时长与服务端分段时长和在允许误差内。

成功后把状态置为 `queued`，创建或返回唯一 `VideoAssemblyJob`，并通过 `transaction.on_commit` 入队。重复 `finalize` 返回相同任务状态。

强制上传页收到成功响应后，即可显示“视频已上传，正在后台处理”并允许患者离开；不等待 FFmpeg、七牛上传或 PP-TinyPose。

### 查询状态

```text
GET /api/patient-app/training-video-sessions/{video_id}/status/
```

返回：

- 会话状态与已上传分段索引。
- FFmpeg/七牛后台处理阶段。
- 成功后的训练记录 ID。
- 可安全展示给患者的失败原因与是否可重试。

该接口用于强制页轮询和冷启动恢复，不返回服务器路径、七牛密钥或内部 FFmpeg 命令。

## 小程序录制与上传

### 路由约束

- 当前处方动作 `source_key = motion-resistance-shoulder-press` 时只能进入专用跟练页。
- 禁止通过首页或普通患者训练记录接口直接完成肩部推举。
- 完成训练后使用路由栈重置进入强制上传页，上传完成前不能返回录像页或跳过。

### 连续分段

- 默认请求前置摄像头权限；未授权时不允许开始。
- 摄像头预览与示例视频同屏，示例视频在训练期间循环播放。
- 每次 `startRecord` 到达约 30 秒上限后，立即开始下一段；上一段异步持久化并加入上传队列。
- 小程序必须使用 `saveFile` 或等价持久化能力保存片段，不能把临时 `wxfile://` 路径作为冷启动恢复依据。
- `getVideoInfo.size` 按小程序 API 的 kB 单位换算为字节；服务端仍以实际读取字节数为准。
- 上传队列默认单并发，优先保证相机录制稳定。
- 服务端确认片段落盘后才删除小程序本地文件。

### 中断与恢复

- 来电、锁屏、切后台或页面隐藏导致提前结束录像时自动暂停训练。
- 超过 2 秒的当前片段正常保存和上传；更短片段丢弃。
- 返回页面后由患者点击继续，只累计实际录像时间。
- 患者主动退出时二次确认；确认退出后不创建训练记录，服务器临时文件按 24 小时规则清理。
- 训练日期、处方动作和 `client_session_id` 在首次开始时固定，次日补传仍属于原训练日期。
- 小程序冷启动优先恢复待上传的肩部推举会话，再允许开始新的同类训练。

### 强制上传页

- 展示总分段数、已上传数、当前片段进度和重试状态。
- 补传训练中尚未送达服务器的片段。
- 全部分段成功后调用 `finalize`。
- `finalize` 成功前不允许离开；成功后不等待服务器合并。
- 网络错误只重试失败片段，不重传已确认片段。

## FFmpeg 合并

### 预检

Worker 获取会话锁并把状态置为 `assembling`，随后使用 `ffprobe` 逐段检查：

- 文件存在且位于会话目录。
- 容器可读取，至少存在一个视频流。
- 时长、分辨率、编码格式和音频流信息可解析。
- 分段序号连续，总时长与 `finalize` 数据在允许误差内。

任何 FFmpeg/FFprobe 调用都使用参数数组，不通过 shell 拼接命令；设置整体超时、输出长度限制和可控工作目录。

### 首选：无损转封装

片段参数兼容时使用 concat demuxer：

```text
ffmpeg -f concat -safe 0 -i concat.txt -c copy -movflags +faststart final.tmp.mp4
```

`concat.txt` 只引用服务器生成的安全路径。完成后再次 `ffprobe`，验证视频可解码、至少包含视频流、总时长在允许误差内且文件大小合法。

### 降级：单次完整转码

无损合并失败、时间戳异常或输出校验失败时，允许执行一次 H.264/AAC 转码：

```text
ffmpeg -f concat -safe 0 -i concat.txt \
  -c:v libx264 -pix_fmt yuv420p -c:a aac \
  -movflags +faststart final.tmp.mp4
```

转码仍失败则任务进入 `failed`，保留本地文件供 24 小时内后台重试。系统不得在多次重试中反复转码已经生成的中间视频；每次重试都从原始片段生成唯一最终文件。

FFmpeg 本身不限制 21 个片段。系统只应用配置化的业务上限：默认总时长不超过 600 秒、总大小不超过 200 MB、单段不超过 32 MB、单次训练不超过 120 个片段。

## 最终文件上传七牛

合并验证成功后，Worker 把状态置为 `uploading_qiniu`，使用只存在于后端的七牛 AK/SK 和官方 SDK 上传 `final.mp4`。

对象 key 由后端确定：

```text
training-videos/{project_patient_id}/{yyyy}/{mm}/{dd}/{training_video_uuid}.mp4
```

规则：

- 不调用七牛 `avconcat`、转码或其它 DORA 多媒体处理接口。
- 上传前若目标 key 已存在，必须通过七牛 `stat` 比对大小和 hash；一致则视为前次上传已成功，不一致则进入失败状态，禁止覆盖未知对象。
- 新上传完成后再次 `stat`，以七牛返回结果作为最终对象校验依据。
- 只有对象校验成功后，才在数据库事务中创建唯一 `TrainingRecord`、绑定 `TrainingVideo.training_record` 并置为 `attached`。
- 数据库事务失败时保留本地文件；重试可识别已存在且一致的七牛对象，不重复上传。
- 七牛空间保持私有，医生端继续使用后端生成的短有效期下载 URL。

## 本地文件清理

### 成功清理

七牛对象校验和训练记录事务成功后，通过 `transaction.on_commit` 调度清理任务：

1. 锁定 `VideoAssemblyJob`，确认 `TrainingVideo.status = attached`。
2. 删除所有 `.part`、原始分段、`concat.txt`、临时输出和最终本地文件。
3. 删除空会话目录。
4. 把分段状态置为 `deleted`，任务 `cleanup_status` 置为 `succeeded`。

删除操作幂等。清理失败不回滚训练记录或删除七牛对象，任务进入 `cleanup_status = failed` 并指数退避重试。

### 过期清理

Celery Beat 定期扫描：

- 超过 24 小时仍未 `finalize` 的录像会话。
- 超过 24 小时仍处于 `failed` 的合并或七牛上传任务。
- 无数据库归属且超过 TTL 的遗留 `.part` 文件和临时目录。

扫描任务必须跳过仍有新心跳或最近更新时间的活跃任务。清理后将会话标记为 `expired`，不得再接受新分段；患者端提示重新训练。

### 磁盘保护

- 创建新会话前检查临时分区剩余空间；低于 `TRAINING_VIDEO_MIN_FREE_BYTES` 时拒绝开始新录像。
- 已开始会话仍允许补传，避免患者已有录像无法完成上传。
- 单段大小、单会话总大小、总时长和最大分段数均由服务端强制执行。
- 监控临时目录占用、磁盘剩余空间、失败清理数和最老未完成任务。

## 医生端与动作分析

医生端保持“一次训练对应一个完整视频”：

- tracking API 单独返回尚未创建训练记录的 `pending_training_videos`，供医生查看合并、七牛上传和失败状态；最终绑定后该条目移入正常训练记录列表。
- `queued`、`assembling`、`uploading_qiniu` 显示“视频处理中”。
- `attached` 后显示“查看视频”和“动作分析”。
- `failed` 显示安全的处理失败状态，不暴露服务器路径和 FFmpeg 原始输出。
- 医生端不展示、下载或单独分析原始分段。

动作分析继续使用既有流程：

```text
POST /api/training/videos/{video_id}/analysis-jobs/
GET  /api/training/videos/{video_id}/analysis-jobs/latest/
```

Worker 从七牛私有 URL 下载最终 MP4 到独立分析临时文件，调用 PaddleX `create_model("PP-TinyPose_128x96")` 获取人体关键点，再由肩部推举规则层计算总次数、标准次数和不标准次数。下载文件必须在 `finally` 中删除。

FFmpeg 合并后的视频按普通连续 MP4 分析，不记录或传递 30 秒分段边界。短暂卡顿造成的极少量计数误差属于第一版可接受范围。

## 肩部推举规则层

计数状态保持既有设计：

```text
down -> up -> down
```

- `down`：手腕接近肩部高度，肘部弯曲。
- `up`：手腕明显高于肩部，肘部接近伸直。
- 状态需要持续若干帧或毫秒才确认，视频首尾不完整半次动作不计数。
- `range_too_small`：没有达到明确上举范围。
- `tempo_abnormal`：单次动作过快或过慢。
- `low_confidence`：动作关键帧置信度不足。

PP-TinyPose 只负责关键点检测；业务规则不得宣称医学诊断能力。阈值继续通过样例视频校准并按规则版本记录。

## 失败恢复

- **摄像头未授权**：不创建会话，不开始训练。
- **片段上传中断**：保留小程序持久化文件，按序号重试。
- **响应丢失**：重复上传或 `finalize` 返回已存在结果，不创建重复数据。
- **小程序关闭**：冷启动读取本地会话清单并调用状态接口恢复。
- **Web/Worker 重启**：长时间停留在 `assembling` 或 `uploading_qiniu` 且无心跳的任务重新入队。
- **FFmpeg 失败**：保留原始分段，在 24 小时内有限次数重试。
- **七牛上传失败**：保留最终本地文件和分段，重试上传；不重新合并已验证的最终文件。
- **七牛成功但数据库失败**：重试先 stat 已存在对象，再完成训练记录事务。
- **清理失败**：训练记录保持成功，独立重试清理。
- **处方在录像期间更新**：`finalize` 仍按会话开始时锁定的处方动作验证；若患者已从项目解绑或关系失效，则不创建训练记录并按失败 TTL 清理。

所有后台任务使用有限重试、指数退避和可恢复状态，不在进程内递归调用自身。

## 权限与安全

- 患者接口只从患者 token 推导 `ProjectPatient`，不信任患者、项目、处方或服务器路径参数。
- 分段只能写入所属会话目录；拒绝路径穿越、符号链接和非预期文件类型。
- 上传端点使用流式临时文件，避免大文件进入进程内存。
- 医生每次获取七牛下载 URL 前都执行接口级和行级权限校验。
- 七牛 AK/SK 仅存在后端环境变量，不下发小程序。
- 日志记录会话 ID、任务 ID、状态和错误分类，不记录患者姓名、原始本地路径或签名 URL。
- FFmpeg 原始 stderr 只进入受控服务日志；数据库和患者端只保存截断、脱敏后的失败摘要。

## 配置与部署

新增或调整配置：

```text
TRAINING_VIDEO_STAGING_ROOT=/var/lib/motioncare/training-video-staging
TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES=33554432
TRAINING_VIDEO_MAX_SIZE_BYTES=209715200
TRAINING_VIDEO_MAX_DURATION_SECONDS=600
TRAINING_VIDEO_MAX_SEGMENTS=120
TRAINING_VIDEO_STAGING_TTL_SECONDS=86400
TRAINING_VIDEO_MIN_FREE_BYTES=5368709120
VIDEO_ASSEMBLY_TIMEOUT_SECONDS=1800
VIDEO_ASSEMBLY_MAX_CONCURRENCY=1
VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS=3600
FFMPEG_PATH=/usr/bin/ffmpeg
FFPROBE_PATH=/usr/bin/ffprobe

QINIU_ACCESS_KEY
QINIU_SECRET_KEY
QINIU_BUCKET
QINIU_DOWNLOAD_DOMAIN
QINIU_DOWNLOAD_TOKEN_TTL_SECONDS
```

部署要求：

- 安装受控版本的 `ffmpeg` 与 `ffprobe`，并包含 H.264/AAC 编解码能力。
- Web 与 Worker 启动健康检查必须验证二进制可执行；不可用时拒绝创建新录像会话。
- FFmpeg 合并使用独立 Celery 队列，一期并发数固定为 1，避免多次转码同时耗尽单机 CPU 和磁盘 IO。
- Nginx 单请求限制按单个 30 秒片段设置，不放开到整个 200 MB 视频；上传超时与代理缓冲策略需要按部署环境验证。
- 临时目录使用独立、可监控的磁盘路径，不对外提供静态访问。
- 多机部署不在一期范围；扩容前必须先把临时存储替换成共享卷或独立媒体处理节点。

## 测试与验收

### 后端自动化测试

- 会话创建校验患者权限、当前处方、肩部推举动作及 `client_session_id` 幂等。
- 分段上传覆盖实际大小、哈希、序号、冲突、总量限制、原子落盘和路径穿越防护。
- 缺少任一分段时 `finalize` 被拒绝；完整会话重复提交只创建一个任务。
- FFprobe 预检、无损合并、单次转码降级、超时和输出时长校验。
- 超过 20 个片段仍能合并为一个可解码 MP4。
- 七牛上传失败重试、已存在对象一致/冲突校验和训练记录幂等创建。
- 成功立即清理、清理失败重试、24 小时过期清理和活跃任务跳过。
- 磁盘低水位拒绝新会话，但允许已有会话补传。
- 陈旧 FFmpeg/七牛任务恢复不会覆盖新 Worker 的结果。
- 医生无权访问、处理中、已绑定和分析任务状态正确。

### 小程序自动化测试

- 约 30 秒自动停止后立即开始下一段。
- 片段先持久化，再进入单并发上传队列；服务端确认后才删除。
- 上传失败只重试对应分段，冷启动恢复已上传索引。
- 切后台暂停，返回后继续累计有效录像时长。
- 强制页路由不可返回，全部分段和 `finalize` 成功后才可离开。
- 次日补传保持原训练日期和会话 UUID。
- 肩部推举不能经普通训练记录 API 绕过录像。
- 小程序视频大小单位正确换算，上传进度不会把 kB 当作字节。

### 真机与集成验收

- 至少一台 iOS 和一台 Android 连续训练 10 分钟。
- 验证弱网、断网恢复、来电、锁屏、切后台和小程序重启。
- 构造超过 20 个片段，确认 FFmpeg 输出可完整播放、时长合理。
- 确认最终七牛空间只有一个 MP4，不产生分段对象或 `avconcat` 任务。
- 确认成功后服务器会话目录被删除；失败文件在 24 小时后被清理。
- 医生端完整播放最终视频，并成功得到 PP-TinyPose 总数、标准数和不标准数。

## 风险与后续

- 视频流量改为经过业务服务器，部署时需要评估出口带宽、临时磁盘和并发 FFmpeg 任务数。
- FFmpeg 无损拼接依赖片段编码参数一致；真机矩阵必须验证降级转码比例。
- 单台服务器故障会影响正在上传的临时视频；一期接受该部署约束，扩容时再引入共享暂存能力。
- 肩部推举阈值仍需要真实样例视频校准，PP-TinyPose 真实模型和真机视频的端到端验收不可由单元测试替代。
- 后续其它动作需要录像时，可以复用会话、分段、合并和清理基础设施，但每个动作仍需独立规则层和产品确认。
