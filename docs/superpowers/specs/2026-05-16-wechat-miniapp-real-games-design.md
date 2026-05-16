> 状态：review
> 日期：2026-05-16
> 范围：微信小程序首批真实认知游戏；颜色顺序记忆 + 反应抑制能力训练；患者真实使用体验、语音音效、自动回传和失败补传。
> 关联：`docs/superpowers/specs/2026-05-15-game-prescription-tracking-design.md`、`docs/superpowers/specs/2026-05-14-wechat-miniapp-patient-daily-workbench-design.md`、`specs/patient-rehab-system/prd.md` §6.7-§6.10 / §12.3
> 决策更新：本 spec 覆盖旧决策“真实游戏后置”；本里程碑开始在小程序落地两款真实小游戏，但不改变处方、项目患者、训练记录主链路。

# 微信小程序真实游戏一期设计

## 背景

MotionCare 已经完成游戏处方闭环一期：医生可将认知游戏动作加入当前生效处方，小程序可从处方动作进入游戏占位页，并通过 `/api/patient-app/training-records/` 回传游戏结果。该闭环仍以 `ActionLibraryItem -> PrescriptionAction -> TrainingRecord` 为主链路，训练记录只能基于当前 active 处方动作创建。

本设计把“游戏占位/模拟完成页”升级为两款患者可真实使用的微信小程序小游戏：

- `game-memory-color-sequence`：颜色顺序记忆。
- `game-executive-inhibition`：反应抑制能力训练。

这是对 PRD 中“真实游戏后置”的阶段性覆盖：本里程碑只前置上述两款真实小游戏，不一次性实现 6 个游戏，不引入游戏版本管理、资源包管理或独立游戏会话模型。

## 已确认决策

1. 本期采用“两款真实游戏 + 轻量 Game Session 壳”方案。
2. 首批游戏为“颜色顺序记忆”和“反应抑制能力训练”。
3. 游戏体验按“患者真实使用可用”设计，不只是研究演示：包含适老化界面、语音引导、音效、暂停/继续、提前结束、结果展示和失败补传。
4. 视觉方向采用“海南康复主题”：使用海岛、椰林、灯塔等温和元素，但保持成人化、医疗可信和高对比，不做儿童化包装。
5. 训练以处方动作建议时长为主，到时自动结束并提交 `completed`。
6. 患者可提前结束并上传一条记录；提前结束一律提交 `partial`。
7. 医生开方难度作为默认值，小程序允许患者调整难度；患者调整难度时必须填写原因，医生端可见。
8. 语音引导使用项目内生成的预置音频文件，另配正确、错误、完成、按钮反馈等音效；所有音频资源应可替换。
9. 训练结束采用“自动提交 + 结果页展示”：结束后先尝试上传，再展示结果和上传状态。
10. 网络失败时缓存本次训练结果，并在小程序前台做退避式重试；单次打开周期最多自动重试 10 次。
11. 超过 10 次后不丢记录，下次打开小程序时重新启动一轮最多 10 次的退避重试；患者也可手动立即重试。
12. 后端不新增 `GameSession` 模型，继续使用 `TrainingRecord.form_data` 与 `raw_detail` 存游戏会话摘要。
13. 医生端只展示汇总指标、调难原因、提前结束标记和补传标记；不做每轮明细页面。

## 目标

- 将两个处方游戏动作升级为真实可玩的 Taro 小程序游戏。
- 建立复用的 Game Session 壳，统一处理处方动作校验、难度选择、计时、暂停、结束、音频、结果、上传和补传。
- 为两款游戏分别实现出题、交互、判分和结果汇总。
- 保持现有训练记录 API 形态，训练结果仍落到 `TrainingRecord`。
- 医生端训练追踪能识别实际难度、调难原因、提前结束和补传信息。
- 测试覆盖玩法核心逻辑、上传失败缓存、退避重试和后端字段校验。

## 非目标

- 不实现其余 4 个游戏：图案顺序记忆、分类转换任务、声音辨别、拼图。
- 不新增游戏独立后台、游戏发布管理、游戏版本管理或资源包管理。
- 不新增 `GameSession`、`GameRound` 等后端模型。
- 不做每轮题目、答案、反应时间的医生端明细分析。
- 不做完整离线训练队列；本期只缓存一条待上传训练记录及其重试状态。
- 不改变处方版本化规则、当前 active 处方校验规则或训练记录只能基于当前处方动作创建的规则。

## 总体架构

小程序侧新增一个共用 Game Session 壳，两个游戏作为独立玩法模块接入。

```text
当前处方页
  -> game-session 路由
      -> 读取 current-prescription
      -> 校验 prescription_action 是当前处方内的 game 动作
      -> Game Session 壳
          -> 难度/调难原因
          -> 语音说明和倒计时
          -> 处方建议时长计时
          -> 暂停/继续/提前结束
          -> 调用具体玩法模块
          -> 计算结果
          -> 上传 TrainingRecord
          -> 失败缓存 + 退避重试
      -> 结果页
```

建议模块边界：

- `game-session/index.tsx`：页面壳和路由入口。
- `games/session/`：通用状态机、计时、结束、上传、补传、音频开关。
- `games/audio/`：音频资源清单、播放封装、静音兜底。
- `games/color-sequence/`：颜色顺序记忆玩法。
- `games/inhibition/`：反应抑制玩法。
- `games/retry/`：本地缓存、退避重试和手动重试。

如果实现时文件数量需要收敛，可先保持在 `miniapp/src/pages/game-session/` 下分文件，避免一次性重构小程序目录。

## 游戏一：颜色顺序记忆

流程：

1. 播放玩法说明语音，并显示同等文字说明。
2. 进入 3 秒倒计时。
3. 系统生成颜色序列并依次高亮。
4. 患者按顺序点击颜色块。
5. 每轮答完立即给出正确/错误反馈，并进入下一轮。
6. 持续到处方建议时长结束，或患者提前结束。

难度建议：

| 难度 | 颜色数量 | 序列长度 | 节奏 |
| --- | --- | --- | --- |
| 简单 | 3 | 3 步 | 高亮和点击等待较长 |
| 中等 | 4 | 4-5 步 | 标准节奏 |
| 困难 | 4-5 | 5-7 步 | 高亮和点击等待更短 |

反馈：

- 正确：高亮成功状态，播放正确音效和鼓励语音。
- 错误：标出正确顺序或给出简短提示，播放温和鼓励语音，不使用负向文案。
- 暂停：冻结序列和计时，恢复后重新显示当前轮提示。

## 游戏二：反应抑制能力训练

流程：

1. 播放玩法说明语音，并显示同等文字说明。
2. 进入 3 秒倒计时。
3. 每题展示一组数字，其中只有一个数字与其他不同。
4. 患者点击“不同的数字”。
5. 每题答完立即反馈，继续下一题。
6. 持续到处方建议时长结束，或患者提前结束。

难度建议：

| 难度 | 数字数量 | 干扰强度 | 节奏 |
| --- | --- | --- | --- |
| 简单 | 4 个 | 差异明显 | 答题等待较长 |
| 中等 | 6 个 | 差异中等 | 标准节奏 |
| 困难 | 9 个 | 差异更接近 | 答题等待更短 |

反馈：

- 正确：播放正确音效和鼓励语音。
- 错误：播放温和鼓励语音，并短暂标出正确选项。
- 超时：记为错误或未答，继续下一题，文案避免挫败感。

## 计分与训练结果

两款游戏使用统一指标：

- `score`：0-100，按正确率为主，结合有效完成轮次/题数给轻微加成。
- `accuracy_rate`：正确轮次或正确题数 / 总轮次或总题数，范围 0-100。
- `error_count`：错误次数，非负整数。
- `actual_duration_minutes`：按实际训练时长向上取整为非负整数分钟，匹配后端现有 `PositiveIntegerField`。
- `status`：到时自动结束为 `completed`，提前结束为 `partial`。

建议第一版计分：

```text
accuracy_score = accuracy_rate
volume_bonus = min(10, completed_units / expected_units * 10)
early_penalty = ended_early ? 10 : 0
score = clamp(round(accuracy_score * 0.9 + volume_bonus - early_penalty), 0, 100)
```

其中 `expected_units` 由游戏和难度给出估算值，只用于分数轻微修正，不替代医生端的真实完成状态。

## 难度与调难原因

处方动作中的 `difficulty` 作为进入游戏时的默认难度。患者可在开始前调整为简单、中等或困难，但必须填写调难原因。

调难原因可以先用选项 + 自由文本：

- 太难，先降低难度。
- 太简单，想提高难度。
- 今天状态不佳。
- 其他。

提交记录时：

- `form_data.difficulty` 保存实际游戏难度。
- `raw_detail.prescribed_difficulty` 保存处方默认难度。
- `raw_detail.difficulty_adjusted` 表示是否调整。
- `raw_detail.difficulty_adjust_reason` 保存患者填写原因。

医生端训练追踪展示实际难度和调难原因。

## 语音与音效

音频采用项目内生成的预置资源。实现上以资源清单管理，不把音频路径散落在页面代码中。

每个游戏至少需要：

- 玩法说明。
- 3、2、1 倒计时。
- 开始。
- 正确提示。
- 错误鼓励。
- 完成鼓励。
- 提前结束确认提示。

通用音效至少需要：

- 点击反馈。
- 正确。
- 错误。
- 完成。

要求：

- 提供静音开关，并记住患者本地偏好。
- 音频加载失败不能阻塞游戏；页面必须显示同等文字提示。
- 所有音频资源路径集中配置，后续正式录音可直接替换。
- 语音文案保持成人化、温和、明确，避免儿童化措辞。

## 上传与补传

训练结束后先计算结果并自动调用：

```text
POST /api/patient-app/training-records/
```

成功后结果页展示“已上传”。失败时：

1. 将完整 payload、本地会话摘要和错误信息写入本地缓存。
2. 结果页展示“待上传”，并允许手动立即重试。
3. 如果小程序仍在前台，启动退避式重试。

单次打开周期的自动重试上限为 10 次。建议间隔：

```text
5s -> 10s -> 20s -> 40s -> 80s -> 160s -> 300s -> 300s -> 300s -> 300s
```

缓存字段建议：

- `payload`：待提交训练记录请求体。
- `retry_count`：当前打开周期内已自动重试次数，0-10。
- `total_retry_count`：该记录累计重试次数。
- `next_retry_at`：下一次重试时间。
- `last_error`：最近一次错误信息。
- `created_at`：缓存创建时间。
- `retry_paused_until_next_launch`：当前打开周期已达 10 次，等待下次打开后重启一轮重试。

超过 10 次后不丢弃记录，只暂停当前打开周期的自动轮询。下次小程序 `onShow`、进入首页、进入处方页或进入游戏页时，如果发现仍有待上传记录，则把 `retry_count` 重置为 0，并重新开始最多 10 次的退避式重试。

成功补传时：

- `raw_detail.upload_mode = "retry"`。
- `raw_detail.retry_count` 保存本次打开周期重试次数。
- `raw_detail.total_retry_count` 保存累计重试次数。

工程边界：小程序进入后台或被微信挂起后，不承诺继续常驻轮询；补传能力以“前台自动重试 + 下次打开恢复重试”为准。

## 后端数据约定

不新增模型。`TrainingRecord.form_data` 继续保存通用游戏指标：

```json
{
  "accuracy_rate": 85,
  "error_count": 3,
  "difficulty": "中等",
  "raw_detail": {
    "game_code": "game-memory-color-sequence",
    "ended_by": "timer",
    "ended_early": false,
    "prescribed_difficulty": "简单",
    "difficulty_adjusted": true,
    "difficulty_adjust_reason": "太简单，想提高难度",
    "upload_mode": "retry",
    "retry_count": 2,
    "total_retry_count": 2,
    "session_duration_seconds": 600,
    "completed_units": 18,
    "correct_units": 15
  }
}
```

后端校验：

- `form_data` 必须是对象。
- `accuracy_rate` 非空时必须在 0 到 100。
- `error_count` 非空时必须为非负整数。
- `difficulty` 非空时必须是文本。
- `raw_detail` 非空时必须是对象。
- `raw_detail.game_code` 若提交，必须与当前处方动作 source key 或前端映射一致。
- `raw_detail.ended_by` 限制为 `timer`、`manual`。
- `raw_detail.ended_early` 必须为布尔值。
- `raw_detail.retry_count`、`raw_detail.total_retry_count` 必须为非负整数。

若处方已调整导致 `prescription_action` 不属于当前 active 处方，接口继续返回明确错误：“处方已更新，请返回当前处方重新进入”。

## 医生端展示

医生端训练追踪在游戏表现和最近训练记录中补充：

- 实际难度。
- 调难原因。
- 完成状态：完成 / 提前结束。
- 上传方式：实时上传 / 补传。
- 补传次数。
- 得分、正确率、错误次数、实际时长。

本期不新增每轮明细页面，不展示题目和点击轨迹。

## 错误处理

- 无当前处方：返回处方页空状态，不允许开始游戏。
- 非游戏动作：提示“游戏动作无效，请返回当前处方重新进入”。
- 处方已更新：提交失败后提示返回当前处方页刷新。
- 音频失败：静默降级为文字提示。
- 网络失败：缓存本次记录并进入补传流程。
- 缓存中已有待上传记录：结果页和首页提示先上传旧记录；第一版不允许覆盖旧记录。

## 测试验收

小程序：

- 颜色顺序记忆出题和判分单测。
- 反应抑制出题和判分单测。
- 难度默认值、患者调难和原因必填。
- 到时结束提交 `completed`，提前结束提交 `partial`。
- 暂停/继续不会错误累计训练时长。
- 音频静音开关和音频失败文字兜底。
- 上传失败写入缓存。
- 前台退避式重试最多 10 次。
- 超过 10 次后下次 `onShow` 重启一轮 10 次重试。
- 手动立即重试成功后清理缓存。
- 小程序构建和 TypeScript 检查通过。

后端：

- 游戏 `form_data` 合法 payload 可创建训练记录。
- 非法 `accuracy_rate`、`error_count`、`difficulty`、`raw_detail` 被拒绝。
- 处方动作不属于当前 active 处方时拒绝。
- 补传字段 `upload_mode`、`retry_count`、`total_retry_count` 校验正确。

医生 Web：

- 最近训练记录展示实际难度、调难原因、提前结束、上传方式和补传次数。
- 游戏表现聚合不被补传字段破坏。

## 参考

- 微信小程序 App 生命周期：`https://developers.weixin.qq.com/miniprogram/dev/reference/api/App.html`
- 微信小程序网络请求：`https://developers.weixin.qq.com/miniprogram/dev/api/network/request/wx.request.html`
- 微信小程序本地缓存：`https://developers.weixin.qq.com/miniprogram/dev/api/storage/wx.setStorageSync.html`
