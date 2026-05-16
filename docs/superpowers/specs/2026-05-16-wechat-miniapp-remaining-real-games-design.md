> 状态：review
> 日期：2026-05-16
> 范围：微信小程序补齐剩余 4 个官方真实认知游戏；图案顺序记忆、分类转换任务、声音辨别、拼图；沿用现有 Game Session、上传与补传闭环。
> 关联：`docs/superpowers/specs/2026-05-16-wechat-miniapp-real-games-design.md`、`docs/superpowers/specs/2026-05-15-game-prescription-tracking-design.md`
> 实施基线 commit：0f59995

# 微信小程序剩余真实游戏设计

## 背景

上一阶段已经把小程序游戏占位页升级为两款真实游戏：

- `game-memory-color-sequence`：颜色顺序记忆。
- `game-executive-inhibition`：反应抑制能力训练。

同时已经建立通用 Game Session 壳，覆盖处方动作校验、难度调整、语音引导、音效、倒计时、暂停/继续、提前结束、结果上传和失败补传。本设计在不改变处方、训练记录和医生端训练追踪主链路的前提下，补齐剩余 4 个官方游戏。

## 已确认决策

1. 本期补齐剩余 4 个官方 `source_key`，使 6 个官方游戏都能从小程序当前处方进入真实玩法。
2. 采用图片资源增强方案：图案顺序记忆、分类转换任务和拼图使用小程序静态图片资源，不只用纯文字或编号占位。
3. 声音辨别使用 `docs/other/sounds` 中已有 `.m4a` 声音源，不重新生成这些目标声音。
4. 声音辨别不是单纯按钮试听选择，而是“翻卡试听 -> 全部盖回 -> 播放目标声音 -> 选择背面卡片”的流程。
5. 声音辨别每轮必须有混淆项，至少成对出现，例如“小鸟1/小鸟2”、“电话铃声1/电话铃声2”。
6. 声音辨别需要精确匹配具体声音文件；如果目标是 `小鸟2.m4a`，选择 `小鸟1.m4a` 即使图片相同也算错误。
7. 同一声音类别的多个变体使用同一张图片，例如 `小鸟1/2/3` 都显示同一张小鸟图，患者只能依赖声音记忆辨别。
8. 其他语音引导和通用音效沿用上一阶段方式：项目内生成 intro 语音，正确/错误/完成/点击音效复用。
9. 拼图手机端先采用点击两块交换位置的交互，不做拖拽，优先保证微信端可靠。
10. 不新增后端模型、API 或医生端专属列；新游戏继续使用 `TrainingRecord.form_data.raw_detail` 和现有训练追踪摘要。

## 目标

- 小程序支持剩余 4 个官方游戏：
  - `game-memory-pattern-sequence`：图案顺序记忆。
  - `game-executive-category-switch`：分类转换任务。
  - `game-audiovisual-sound-discrimination`：声音辨别。
  - `game-audiovisual-puzzle`：拼图。
- 4 个新游戏复用已有 Game Session 的难度、计时、暂停、提前结束、上传和补传能力。
- 每个游戏至少实现简单、中等、困难 3 档难度。
- 声音辨别使用现有声音源，且玩法符合“成对混淆 + 翻卡试听 + 目标音选择”的训练流程。
- 小程序微信构建通过，适合继续用微信开发者工具调试。

## 非目标

- 不新增 `GameSession`、`GameRound`、游戏资源版本等后端模型。
- 不做每轮题目、反应时间、卡片翻开顺序的医生端明细分析。
- 不在医生端新增 4 个游戏的专属统计列。
- 不做拖拽拼图、复杂物理动画或高成本图片编辑器。
- 不做完整离线训练队列；继续沿用当前一条待补传训练记录的机制。

## 总体架构

继续使用当前小程序页面：

```text
miniapp/src/pages/game-session/index.tsx
```

新增 4 个纯玩法模块，页面壳负责 session 状态和上传，玩法模块负责出题与判定：

```text
game-session/
  patternSequence.ts
  patternSequence.test.ts
  categorySwitch.ts
  categorySwitch.test.ts
  soundDiscrimination.ts
  soundDiscrimination.test.ts
  puzzle.ts
  puzzle.test.ts
```

现有模块扩展：

- `gameTypes.ts`：`GameCode` 扩展为全部 6 个官方游戏。
- `gameAudio.ts`：新增 4 个游戏 intro key，并集中维护声音辨别目标音频清单。
- `scoring.ts`：继续提供统一训练结果构造，不按游戏拆专属结果结构。
- `index.tsx`：扩展 `source_key -> gameCode` 映射和玩法渲染分支。

如果 `index.tsx` 膨胀明显，实施时允许拆出轻量 `gameCatalog.ts` 或渲染 helper，但不得做无关页面重构。

## 资源设计

### 图片资源

图案顺序记忆、分类转换任务和拼图使用小程序静态图片资源：

```text
miniapp/src/assets/images/game-session/
```

图片资源要求：

- 文件名使用 ASCII 稳定编码。
- 每张图片可独立作为游戏选项或拼图片源。
- 图片加载失败时页面显示文字或符号 fallback，游戏仍可继续。
- 视觉延续海南康复主题，成人化、清晰、高对比，不做儿童化包装。

### 声音资源

声音辨别目标音频来自：

```text
docs/other/sounds/
```

当前声音源包括：

- `小鸟1.m4a`、`小鸟2.m4a`、`小鸟3.m4a`
- `火车汽笛声1.m4a`、`火车汽笛声2.m4a`
- `电话铃声1.m4a`、`电话铃声2.m4a`、`电话铃声3.m4a`
- `笑声1.m4a`、`笑声2.m4a`、`笑声3.m4a`
- `鼓1.m4a`、`鼓2.m4a`、`鼓3.m4a`

实施时复制到小程序静态目录，并改为 ASCII 文件名：

```text
miniapp/src/assets/audio/sound-discrimination/
  bird_1.m4a
  bird_2.m4a
  train_1.m4a
  phone_1.m4a
  laugh_1.m4a
  drum_1.m4a
  ...
```

同一类别共享图片，例如所有 bird 音频都显示同一张小鸟图；正确性由音频文件精确匹配决定。

## 游戏三：图案顺序记忆

流程：

1. 播放玩法说明和倒计时。
2. 系统依次展示图片序列。
3. 展示结束后隐藏序列。
4. 患者从候选图片中按相同顺序点击。
5. 答完立即反馈，进入下一轮。

难度建议：

| 难度 | 候选图片数 | 序列长度 | 节奏 |
| --- | --- | --- | --- |
| 简单 | 3 | 3 | 慢 |
| 中等 | 4 | 4-5 | 标准 |
| 困难 | 5 | 5-7 | 快 |

判定：患者输入序列必须与目标序列长度和顺序完全一致才算正确。

## 游戏四：分类转换任务

流程：

1. 播放玩法说明和倒计时。
2. 每轮展示一张图片和当前分类规则。
3. 患者从分类按钮中选择答案。
4. 答完立即反馈，进入下一轮。

难度建议：

| 难度 | 分类规则 | 选项数 | 节奏 |
| --- | --- | --- | --- |
| 简单 | 固定按物体类别 | 3 | 慢 |
| 中等 | 物体类别/颜色间切换 | 3-4 | 标准 |
| 困难 | 物体类别/颜色/场景间切换 | 4 | 快 |

题目资源需给每张图片配置可判定元数据，例如：

- `kind`：水果、动物、交通、乐器等。
- `color`：红、黄、绿、蓝等。
- `scene`：海边、室内、户外等。

判定：根据本轮规则取图片对应字段，与患者选择比较。

## 游戏五：声音辨别

流程：

1. 播放玩法说明和倒计时。
2. 每轮生成多张背面卡片。
3. 患者逐张翻开卡片；每翻开一张，播放该卡片对应的声音。
4. 全部卡片试听完成后，所有卡片自动盖回背面。
5. 系统播放目标声音。
6. 患者从背面卡片中选择对应卡片。
7. 答完立即反馈，进入下一轮。

回合生成规则：

- 卡片必须包含混淆项，至少成对出现。
- 简单：4 张卡，2 组声音，每组 2 个变体。
- 中等：6 张卡，3 组声音，每组 2 个变体。
- 困难：8-10 张卡，从多组声音中抽取成对变体。
- 目标声音一定来自本轮卡片之一。
- 同类别变体显示相同图片，但内部 `soundId` 不同。

示例：

```text
卡片：小鸟1、小鸟2、电话铃声1、电话铃声2
试听阶段：每张卡翻开后播放自己的声音。
选择阶段：全部盖回，播放目标“小鸟2”，患者需要选择刚才对应“小鸟2”的卡片。
```

判定：选中卡片的 `soundId` 必须等于目标 `soundId`。

播放失败处理：

- 试听阶段播放失败，保留该卡可重新点击试听。
- 目标声音播放失败，允许患者点击“重播目标声音”。
- 如果播放能力不可用，不自动判错，也不阻塞整个 session；页面提示声音异常并允许结束或重试本轮。

暂停处理：

- 暂停时不继续自动播放声音。
- 恢复后保留当前阶段：试听未完成则继续试听；选择阶段则继续选择。

## 游戏六：拼图

流程：

1. 播放玩法说明和倒计时。
2. 展示完整图片短暂预览。
3. 将图片切成网格并打乱。
4. 患者点击两块拼图进行交换。
5. 拼图恢复正确顺序即完成一轮。
6. 进入下一轮或到时结束。

难度建议：

| 难度 | 网格 | 预览时长 | 节奏 |
| --- | --- | --- | --- |
| 简单 | 2x2 | 较长 | 慢 |
| 中等 | 2x3 | 标准 | 标准 |
| 困难 | 3x3 | 较短 | 快 |

判定：当前 tile 顺序与目标顺序完全一致即正确完成本轮。每轮完成后进入下一轮；未完成但到时结束，不额外记错，只按已完成轮次计分。

## 统一训练结果

4 个新游戏继续使用统一指标：

- `score`
- `accuracy_rate`
- `error_count`
- `actual_duration_minutes`
- `status`
- `form_data.difficulty`
- `form_data.raw_detail`

`raw_detail.game_code` 必须等于处方动作 `source_key`，例如：

```json
{
  "game_code": "game-audiovisual-sound-discrimination",
  "ended_by": "timer",
  "ended_early": false,
  "prescribed_difficulty": "中等",
  "difficulty_adjusted": false,
  "difficulty_adjust_reason": "",
  "upload_mode": "direct",
  "retry_count": 0,
  "total_retry_count": 0,
  "session_duration_seconds": 600,
  "suggested_duration_minutes": 10,
  "completed_units": 8,
  "correct_units": 6
}
```

不向后端提交每轮声音文件名、图片路径或卡片顺序。医生端仍只展示汇总摘要、调难原因、提前结束和补传信息。

## 错误处理

- 处方动作不是官方游戏：仍显示“该游戏暂未上线”或无效动作提示，不做兜底映射。
- 图片加载失败：显示文字/符号 fallback，游戏继续。
- 声音辨别音频播放失败：提示声音播放异常，允许重试本轮或重播目标音，不让患者被迫盲选。
- 暂停：冻结当前轮倒计时和自动进程。
- 提前结束：上传 `partial` 训练记录。
- 网络失败：继续使用现有待补传机制，单次打开周期最多 10 次退避重试，超过后下次打开重新尝试。

## 测试设计

小程序：

- `patternSequence.test.ts`
  - 不同难度生成候选图案数和序列长度。
  - 完整顺序正确，错序错误。
- `categorySwitch.test.ts`
  - 简单难度固定规则。
  - 中高难度规则切换。
  - 按当前规则判定正确/错误。
- `soundDiscrimination.test.ts`
  - 每轮生成成对混淆项。
  - 目标声音来自本轮卡片。
  - 同类不同变体图片相同但 `soundId` 不同。
  - 必须精确匹配具体声音文件。
- `puzzle.test.ts`
  - 不同难度网格尺寸。
  - 打乱后不是完成态。
  - 点击两块交换。
  - 交换回正确顺序后完成。
- `gameAudio.test.ts`
  - 新 intro key 存在。
  - 声音辨别 manifest 中每个音频都有稳定路径。

后端：

- 补充训练记录创建测试，覆盖 4 个新 `game_code` 与处方动作 `source_key` 匹配时可提交。
- 继续复用已有 raw_detail 字段校验。

前端：

- 医生端训练追踪不新增 UI 行为；可补充测试确认新游戏记录同样展示现有游戏摘要字段。

验证命令：

```bash
cd miniapp && npm run test
cd miniapp && npx tsc --noEmit --skipLibCheck
cd miniapp && npm run build:weapp
cd backend && pytest apps/training/tests/test_training_current_prescription.py apps/training/tests/test_tracking_api.py -q
cd frontend && npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
```

完成前还需按仓库规则跑更广验证：

```bash
cd backend && pytest
cd frontend && npm run test
cd frontend && npm run lint
cd frontend && npm run build
```

## 验收标准

- 医生给任意 6 个官方游戏开方，小程序都能从当前处方进入真实游戏。
- 4 个新增游戏都能完成至少一轮，并能到时结束或提前结束。
- 声音辨别符合“背面卡片 -> 翻卡试听 -> 全部盖回 -> 播放目标声音 -> 选择背面卡片”的流程。
- 声音辨别同类变体图片相同，正确性按具体声音文件精确匹配。
- 新游戏结果能上传，网络失败能进入现有待补传链路。
- `npm run build:weapp` 通过。
