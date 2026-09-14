# 单患者训练明细导出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

执行记录（2026-09-09, Codex）：Task 1–8 独立双轴审查通过；整体审查发现 FR-1 数值置信度兼容遗漏，修复后限定复核通过。最终后端1448项、Web336项、小程序1035项测试通过，相关构建、迁移演练、五表样本与浏览器下载验收通过。实施基线：当前隔离区未提交改动；本轮未提交、推送、部署或上传。样本与界面证据随本轮交付。

调整记录（2026-09-09）：用户要求导出仅展示有效逐题耗时与判定；删除历史耗时列及历史计时题数，过滤无可用有效耗时的旧题目，保留旧原始存储与合法整场/运动/健康数据。以下八任务作为原实施历史保留；其中历史耗时分列的导出要求由现行spec §3.2/§5覆盖。本次调整94项相关测试通过，独立审查及限定复核通过；新版12条有效题样本已验收，未发布。

**Goal:** 医生在单患者“训练与健康”页按项目和日期导出五表 Excel，并补齐六款游戏可追溯的逐题有效耗时和安全补传。

**Architecture:** 先建立独立逐题关系表、历史兼容与游戏会话幂等，再接入六游戏统一采集。导出在同一只读数据库快照中将已授权数据分批写入私有行暂存文件，随后用 openpyxl write-only 生成五表文件；审计位于快照事务外，Web 只负责筛选和文件下载。

**Tech Stack:** Django 5、DRF、PostgreSQL、openpyxl 3.1、React 18、Ant Design 5、TanStack Query v5、Taro 4.2、TypeScript、pytest-django、Vitest。

**Spec:** `docs/superpowers/specs/2026-09-09-patient-training-detail-export-design.md`（approved）；必须同时阅读。沿用 `2026-08-21-game-question-analytics-design.md` 的采集规则，范围以本次 spec 为准。

## Global Constraints

- 状态：implemented；日期：2026-09-09；八任务与最终审查通过，未发布。
- 工作目录：`/Users/nick/my_dev/workout/MotionCare/.worktrees/game-difficulty-704`；实施基线 HEAD `c58d7aa` 加本会话已知未提交改动。不要修改原根的其他会话改动，不重建或清空现有工作区。
- 仅单患者、单项目；默认近 30 天，支持 `7d/30d/custom/all`，按训练日期含首尾筛选全部历史处方。
- 五表名称固定：`训练场次`、`游戏逐题`、`运动明细`、`训练期间生理数据`、`字段说明`；格式版本 `training_detail_v1`；时区 `Asia/Shanghai`。
- 规范与历史毫秒分列；缺失为空，真实 0/false 保留；拼图正确率为空且说明不适用。
- 固定健康窗口：首次录像开始＋处方秒数＋300 秒，闭区间；本期不新增游戏绝对时间或游戏健康窗口。
- 每场最多 2000 题，单题最多 3600000 毫秒；总逐题有效时间不超过整场秒数×1000＋1000。
- 只采集最终判定题；不新增普通点击事件流、长期统计图或逐题抽屉。
- 患者开始前可自由选择三档难度，新版调整原因为空；保留 2 秒展示、分类文案/语音、签名素材、媒体生命周期与运动录像行为。
- 椰林步道模拟不支持 AI；仍允许录像和医生结果。保留已经修正的处方迁移 `0013_disable_high_knee_ai_supervision.py`。
- 后台不外显项目状态，已完结项目允许只读导出，现有写入门禁继续有效。
- 单文件最多 10000 场，各数据表最多 200000 行，总数据行最多 500000，最长生成 60 秒；超限失败，不截断返回。
- 文件字符串显式文本，日期为 Excel 日期，数值为数值；非法 XML 字符替换计数，长 JSON 分列，不输出视频链接/对象键/原始设备载荷。
- 不主动提交、推送、部署或上传小程序。历史 7.0.5 上传授权不扩展到本功能，执行阶段不自行修改版本号。
- 每任务先失败测试再实现、定向验证、独立审查；保留当前已有改动，禁止用放宽断言掩盖行为回归。旧逐题计划仅被本轮承接数据基础，不标全部完成。

## 文件职责与执行顺序

以下路径均相对上述隔离工作区，修改位置以符号名定位，避免历史行号漂移。

| 任务 | 文件 | 职责 |
| --- | --- | --- |
| 1 | `backend/apps/training/models.py`、`game_question_legacy.py`、training 新迁移 | 逐题关系表、冻结旧数据解析、历史迁移 |
| 2 | `game_questions.py`、`game_record_service.py`、现有 services/serializers/views | 规范校验、指纹、事务写入、幂等与旧写入兼容 |
| 3 | `miniapp/src/pages/game-session/questionCapture.ts`、`capturePlatform.ts` | 可注入单调时钟、逐题状态、UUID |
| 4 | `miniapp/src/pages/game-session/index.tsx`、`gameTypes.ts`、`scoring.ts` | 六游戏采集节点、整场上传与补传 |
| 5 | `backend/apps/training/export_scope.py`、`export_rows.py`、`export_schema.py` | 过滤契约、授权查询、五表字段和快照行流 |
| 6 | `export_workbook.py`、`export_views.py`、models/urls/迁移/pyproject | XLSX、临时文件、超时、审计与下载接口 |
| 7 | `frontend/src/pages/training-tracking/TrainingDetailExportModal.tsx`、`trainingDetailExport.ts`、详情页 | 筛选弹窗、二进制下载、错误反馈 |
| 8 | 各端验收测试与现有 spec/plan/changelog | 跨端样本、实际工作簿检查、全量验证与交付记录 |

依赖顺序：1 → 2 → 3 → 4 → 5 → 6 → 7 → 8。不要同时修改同一个文件；若用户选择子代理，每任务完成后先规范审查再质量审查。

## 验证环境约定

后端 Python 使用 `/Users/nick/my_dev/workout/MotionCare/backend/.venv/bin/python`。为避免并行会话竞争共享测试数据库，执行者在 `/private/tmp/motioncare-training-export-pytest.py` 写入以下临时测试入口（非产品代码）：

```python
import os
import sys
import django
import pytest
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
settings.DATABASES["default"].setdefault("TEST", {})["NAME"] = (
    "test_motioncare_export_" + str(os.getpid())
)
raise SystemExit(pytest.main(sys.argv[1:]))
```

下文 `后端测试 <参数>` 表示在 `backend/` 执行：

```bash
QINIU_BUCKET=motioncare-training PYTHONPATH=.:../packages/motion_analysis_contract/src /Users/nick/my_dev/workout/MotionCare/backend/.venv/bin/python /private/tmp/motioncare-training-export-pytest.py <参数>
```

`<参数>` 是命令记法，执行时替换为每一步给出的测试文件/选择器，不能原样传入。访问本地 PostgreSQL 和 macOS Taro 生产构建如被沙箱限制，通过正常工具提权运行，不更改应用配置绕过。不得打印 `.env`。

---

### Task 1: 逐题模型与历史数据兼容

**Files:**
- Modify: `backend/apps/training/models.py`（TrainingRecord 与新增 GameQuestionResult）
- Create: `backend/apps/training/game_question_legacy.py`
- Create: `backend/apps/training/migrations/0016_game_question_results.py`
- Create: `backend/apps/training/migrations/0017_backfill_game_question_results.py`
- Create: `backend/apps/training/tests/test_game_question_models.py`
- Create: `backend/apps/training/tests/test_game_question_legacy.py`
- Create: `backend/apps/training/tests/test_game_question_migration.py`

**Interfaces:**
- Consumes: `TrainingRecord.form_data`、`prescription_action.action_library_item.source_key`、处方动作 `difficulty`。
- Produces: `GameQuestionResult` 模型：`training_record`（related_name=`question_results`）、`question_index`、`game_code`、`difficulty`、`response_duration_ms`、`is_correct`、`result_type`、`swap_count`、`capture_version`。
- Produces: TrainingRecord `client_session_id: UUID | None`（unique）、`client_payload_fingerprint: str`（max_length=64, blank）。
- Produces: `parse_legacy_rounds(*, form_data: dict, source_key: str, prescribed_difficulty: str) -> LegacyParseResult`；返回 `.rows: list[dict]`、`.skipped_count: int`。迁移中冻结同签名纯函数，不从在线业务模块导入。

- [x] **Step 1: 写解析失败测试及模型约束测试。** 使用以下最小例子；另外参数化拒绝 bool 充整数、负数、重复题号、非布尔正确性，保留合法非连续题号。

```python
from apps.training.game_question_legacy import parse_legacy_rounds

def test_legacy_keeps_zero_and_gaps_without_inventing_swaps():
    result = parse_legacy_rounds(
        form_data={"difficulty": "中等", "raw_detail": {"rounds": [
            {"round_index": 1, "response_ms": 0, "correct": True},
            {"round_index": 3, "response_ms": 2400, "correct": False},
            {"round_index": 3, "response_ms": 2, "correct": True},
            {"round_index": 4, "response_ms": "bad", "correct": True},
        ]}},
        source_key="game-audiovisual-puzzle", prescribed_difficulty="简单",
    )
    assert [row["question_index"] for row in result.rows] == [1, 3]
    assert result.rows[0]["response_duration_ms"] == 0
    assert result.rows[0]["swap_count"] is None
    assert {row["capture_version"] for row in result.rows} == {"legacy_wall_clock_v0"}
    assert result.skipped_count == 2
```

- [x] **Step 2: 运行红灯。** `后端测试 apps/training/tests/test_game_question_legacy.py -q`，预期新模块不存在；模型测试应因缺少新模型失败。
- [x] **Step 3: 增加模型字段和数据库约束，生成 schema migration。** 沿用项目 models.TextChoices；关键声明如下，其他字段按 Interfaces 和旧 spec 字段表实现。

```python
client_session_id = models.UUIDField(null=True, blank=True, unique=True)
client_payload_fingerprint = models.CharField(max_length=64, blank=True)

# GameQuestionResult.Meta.constraints 中：
models.UniqueConstraint(fields=["training_record", "question_index"], name="game_question_record_index_uniq")
models.CheckConstraint(condition=models.Q(question_index__gt=0), name="game_question_index_positive")
models.CheckConstraint(condition=models.Q(response_duration_ms__gte=0), name="game_question_duration_nonnegative")
models.CheckConstraint(
    condition=~models.Q(result_type="timeout") | models.Q(is_correct=False),
    name="game_question_timeout_incorrect",
)
```

`swap_count` 使用 nullable PositiveIntegerField；为 game_code、difficulty 建索引，FK 默认索引。新/旧版本的拼图交换规则在 Task 2 校验，不把历史非法外形误升级成新版。先确认 training 当前叶节点仍为 `0015_motion_analysis_current_stage`，有并发新增迁移时顺延新编号，不覆盖他人迁移。执行 `python manage.py makemigrations training --name game_question_results`；将生成内容审查为本任务 schema migration，不手写漏字段的 schema。

- [x] **Step 4: 实现冻结旧解析。** 对不是 dict/list 的载荷安全返回空；按输入顺序处理，首个合法题号优先。游戏编码依次取 round.game_code、raw_detail.game_code、source_key，必须属于六游戏且与处方 source_key 匹配；难度依次取 round.difficulty、form_data.difficulty、prescribed_difficulty，必须三档之一。只接受整数非 bool 的 0<index<=2147483647、0<=response_ms<=2147483647 与布尔 correct；超出数据库整数范围视为非法历史项跳过，历史时间不套新版一小时上限。合法 timeout 且 correct=false 才保留 timeout；timeout=true 的矛盾项跳过。历史 swap_count 始终空，不推算。构造结果核心：

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class LegacyParseResult:
    rows: list[dict]
    skipped_count: int

# 已通过上述检查的单行映射：
row = {
    "question_index": index, "game_code": game_code, "difficulty": difficulty,
    "response_duration_ms": response_ms, "is_correct": correct,
    "result_type": "timeout" if item.get("result") == "timeout" else "answered",
    "swap_count": None, "capture_version": "legacy_wall_clock_v0",
}
```

- [x] **Step 5: 创建数据迁移与迁移测试。** 冻结 Step 4 解析到 `0017`，通过 historical apps 模型、schema_editor.connection.alias 读取；`iterator(chunk_size=500)`，每批题目 bulk_create；已有正式题目场次全部跳过，原 JSON 不改。计数仅打印 scanned/created/skipped，不输出患者原文。逆向 noop，不能倒迁移时删除未知新版题目。

```python
Record = apps.get_model("training", "TrainingRecord")
Question = apps.get_model("training", "GameQuestionResult")
alias = schema_editor.connection.alias
records = Record.objects.using(alias).filter(
    prescription_action__internal_type_snapshot="game",
).select_related("prescription_action__action_library_item")
# 每个 record 先检查已有题目，再调用迁移文件内冻结解析。
# 测试分别调用冻结函数与在线函数，以相同样本断言 rows 和 skipped_count 完全相等。
```

迁移测试使用 MigrationExecutor 从0016迁移至0017，覆盖合法、混合异常、重复执行、原JSON原样保留、已有正式题目不重复。每个迁移测试最终恢复当前叶节点，避免污染其他测试。

- [x] **Step 6: 运行绿灯及模型检查。** `后端测试 apps/training/tests/test_game_question_models.py apps/training/tests/test_game_question_legacy.py apps/training/tests/test_game_question_migration.py -q`，预期全部通过；`python manage.py makemigrations --check --dry-run` 预期无缺失迁移。记录数量证据，不提交。

### Task 2: 规范写入、权威摘要与 UUID 幂等

**Files:**
- Create: `backend/apps/training/game_questions.py`
- Create: `backend/apps/training/game_record_service.py`
- Modify: `backend/apps/training/services.py`（create_training_record）
- Modify: `backend/apps/patient_app/serializers.py`（PatientAppTrainingRecordCreateSerializer）
- Modify: `backend/apps/patient_app/views.py`（PatientAppTrainingRecordView.post）
- Create: `backend/apps/training/tests/test_game_questions.py`
- Create: `backend/apps/patient_app/tests/test_game_record_idempotency.py`
- Modify: `backend/apps/training/tests/test_training_current_prescription.py`

**Interfaces:**
- Consumes: Task 1 模型、`parse_legacy_rounds`；现有 `create_training_record(*, project_patient, training_date, prescription_action=None, **fields) -> TrainingRecord` 返回值保持兼容所有运动调用者。
- Produces: `normalize_new_question_results(*, prescription_action: PrescriptionAction, raw_results: list[dict], form_data: dict) -> NormalizedGameQuestions`，含 `.rows: list[dict]`、`.form_data: dict`。
- Produces: `semantic_game_payload_fingerprint(*, project_patient_id: int, prescription_action_id: int, training_date: date, fields: dict, questions: NormalizedGameQuestions) -> str`。
- Produces: `create_game_training_record(*, project_patient: ProjectPatient, prescription_action: PrescriptionAction, training_date: date, client_session_id: UUID, question_results: list[dict], **fields) -> GameRecordWriteResult`，含 `.record: TrainingRecord`、`.created: bool`。
- Produces: `GameSessionConflict(APIException)`，status_code=409，统一 detail=`游戏会话内容与已保存记录不一致`。

- [x] **Step 1: 写规范校验和重传失败测试。** 新测试使用当前 backend/conftest.py 的 active_prescription，通过新增局部 fixture 创建 source_key=`game-executive-inhibition`、internal_type=game 的动作快照。固定 UUID 和 payload，不依赖演示患者。

```python
q = {
    "question_index": 1, "game_code": "game-executive-inhibition",
    "difficulty": "困难", "response_duration_ms": 2300,
    "is_correct": True, "result_type": "answered", "swap_count": None,
}
# 在测试中以 game_action 和该载荷调用 normalize_new_question_results。
form_data = {"difficulty": "困难", "accuracy_rate": 7, "error_count": 88,
             "raw_detail": {"session_duration_seconds": 10}}
normalized = normalize_new_question_results(
    prescription_action=game_action, raw_results=[q], form_data=form_data,
)
assert normalized.form_data["accuracy_rate"] == 100
assert normalized.form_data["error_count"] == 0
assert normalized.form_data["raw_detail"]["completed_units"] == 1
assert normalized.form_data["raw_detail"]["difficulty_adjust_reason"] == ""
```

API 测试按现有 patient-app 测试的登录 fixture 建真实身份；断言首次201、同UUID补传200且一record一question、改语义409、别的患者不返回原record、处方更新后成功会话200、新UUID旧动作400、非法任一题整体零写入；用 `transaction=True` 和两个连接验证并发相同UUID只写一场。

- [x] **Step 2: 运行红灯。** `后端测试 apps/training/tests/test_game_questions.py apps/patient_app/tests/test_game_record_idempotency.py -q`，预期模块/字段缺失失败。
- [x] **Step 3: 实现输入规范和权威摘要。** serializer 成对接收 UUID/question_results，允许空数组但不允许仅一个字段；旧载荷两者都缺失保持兼容。整数用严格检查排除bool，布尔不接受字符串；拒绝非游戏、未知游戏、题号不连续、时长/条数越界、难度非三档或不等于本场实际难度、非法timeout/puzzle/swap。source_key匹配动作，canonical form_data 用 deep copy，不修改 request。汇总如下：

```python
rows = normalized_rows
completed = len(rows)
correct = sum(row["is_correct"] for row in rows)
form["error_count"] = completed - correct
form["accuracy_rate"] = round(correct * 100 / completed, 1) if completed else 0
raw = form.setdefault("raw_detail", {})
raw.update(completed_units=completed, correct_units=correct,
           prescribed_difficulty=prescription_action.difficulty,
           difficulty_adjusted=form["difficulty"] != prescription_action.difficulty,
           difficulty_adjust_reason="")
```

`normalized_rows` 是本函数完成逐项校验后的局部列表，`form` 是入参深复制。保留旧得分算法，本次权威重算四个约定汇总；拼图文件正确率留空由 Task 5 映射实现。每行 capture_version 固定active_response_v1，客户端不得伪造历史版本。

- [x] **Step 4: 实现语义指纹。** 明确 whitelist：project_patient、prescription_action、training_date、status、actual_duration_minutes、score、note、清理后的form_data、规范题目行。日期ISO、Decimal固定字符串；递归JSON禁止NaN/Infinity。排除form_data accuracy_rate/error_count，raw_detail completed_units/correct_units，以及 upload_mode/retry_count/total_retry_count；规范题目存在时去掉冗余rounds，不能让原始rounds覆盖规范题目。

```python
serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False, allow_nan=False)
return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
```

`canonical` 为以上 whitelist 字典。分别测试派生摘要/补传元数据变化指纹不变，题目耗时/难度/动作/备注变化指纹改变。

- [x] **Step 5: 实现兼容事务服务。** 为原 create_training_record 增加 `@transaction.atomic`，仍完成当前处方/项目门禁后创建Record；对游戏原始rounds立即写legacy子行。新服务在一个外层事务中先按当前project_patient与原action约束查UUID；有记录校验指纹后直接返回created=false，无记录才调用原create_training_record。新调用给原服务传去掉rounds的form_data，正式题目 bulk_create 后保存UUID/hash；不要递归调用新服务。

```python
@dataclass(frozen=True)
class GameRecordWriteResult:
    record: TrainingRecord
    created: bool

class GameSessionConflict(APIException):
    status_code = 409
    default_detail = "游戏会话内容与已保存记录不一致"
```

唯一约束冲突必须在内部 `transaction.atomic()` savepoint 外捕获 IntegrityError，重新查询已授权UUID并比较指纹；若UUID属于其他患者/动作，统一409且没有原记录序列化。没有UUID的旧普通/游戏仍非幂等。不要把原运动模型的TrainingVideo.client_session_id与新游戏UUID混用。

- [x] **Step 6: 接入患者 API 并移除过早的当前处方拦截。** 查询action必须先限制 `prescription__project_patient=project_patient`；新版游戏交给新服务处理幂等顺序，旧路径继续现有检查，官方运动仍只能录像上传。响应核心：

```python
result = create_game_training_record(
    project_patient=project_patient, prescription_action=action, **data,
)
return Response(TrainingRecordSerializer(result.record).data,
                status=201 if result.created else 200)
```

新函数只在serializer验证成对新字段且动作是game时调用。不要把 `.current_prescription_for()` 放在此调用前；首次创建的当前处方校验由原服务保留。原医生 create API 无需增加新版顶层字段，但其旧rounds通过共享服务生成legacy行。

- [x] **Step 7: 绿灯与现有写入回归。** `后端测试 apps/training/tests/test_game_questions.py apps/patient_app/tests/test_game_record_idempotency.py apps/training/tests/test_training_current_prescription.py apps/training/tests/test_training_video_api.py -q`；验证归属、处方切换、并发和事务失败均通过。

### Task 3: 独立有效计时与逐题采集模块

**Files:**
- Create: `miniapp/src/pages/game-session/questionCapture.ts`
- Create: `miniapp/src/pages/game-session/questionCapture.test.ts`
- Create: `miniapp/src/pages/game-session/capturePlatform.ts`
- Create: `miniapp/src/pages/game-session/capturePlatform.test.ts`

**Interfaces:**
- Consumes: `GameCode`、`GameDifficulty`（gameTypes.ts）；平台单调毫秒函数注入。
- Produces: `GameQuestionPayload`：Task 2 逐题JSON字段，不由客户端传capture_version。
- Produces: `createQuestionCapture(now: () => number): QuestionCapture`，方法 `begin(gameCode, difficulty): void`、`pause(): void`、`resume(): void`、`finish(isCorrect, resultType): GameQuestionPayload | null`、`recordSwap(): void`、`discard(): void`、`reset(): void`、`results(): GameQuestionPayload[]`。
- Produces: `createCaptureNow(): () => number`、`createGameClientSessionId(): string`。UUID格式v4；只作幂等标识，不作身份凭证。

- [x] **Step 1: 写纯采集测试。** 同时覆盖重复pause/resume、未begin finish为空、discard不占题号、返回副本不可篡改、拼图swap、时间回拨输入拒绝。

```typescript
it('只累计可作答区间并丢弃未判定题', () => {
  let now = 0
  const capture = createQuestionCapture(() => now)
  capture.begin('game-executive-inhibition', '中等')
  now = 1200
  capture.pause()
  now = 9200
  capture.resume()
  now = 10500
  expect(capture.finish(true, 'answered')?.response_duration_ms).toBe(2500)
  capture.begin('game-executive-inhibition', '中等')
  capture.discard()
  expect(capture.results()).toHaveLength(1)
  expect(capture.results()[0].question_index).toBe(1)
})
```

- [x] **Step 2: 运行红灯。** `cd miniapp && npm test -- src/pages/game-session/questionCapture.test.ts src/pages/game-session/capturePlatform.test.ts`；预期模块缺失。
- [x] **Step 3: 实现采集状态机。** `begin`重置当前题累计值并开始；pause只结算一次，resume只恢复已有题；finish冻结并分配results.length+1；finished题重复finish返回null，discard不追加。核心结算如下：

```typescript
let activeStartedAt: number | null = null
let elapsedMs = 0
function pause() {
  if (activeStartedAt === null) return
  const current = now()
  if (!Number.isFinite(current) || current < activeStartedAt) throw new Error('作答时钟无效')
  elapsedMs += current - activeStartedAt
  activeStartedAt = null
}
```

finish取 `Math.round(elapsedMs)`；只有puzzle返回swap_count数字，其他null；结果逐项复制。单场2000题/单题一小时上限在页面安全结束与后端校验共同保障，不静默丢弃已判定题。

- [x] **Step 4: 实现平台时钟适配与 UUID。** H5用global performance.now，微信优先平台性能时钟可用的now；调用需要bind原对象。当前Taro类型声明只有getPerformance、未声明now，执行时用能力检测和窄类型guard，不用any强行假设。核心选择：

```typescript
type Clock = { now: () => number }
function isClock(value: unknown): value is Clock {
  return typeof value === 'object' && value !== null &&
    'now' in value && typeof value.now === 'function'
}
```

测试模拟H5、微信、缺失接口。**执行本任务必须在微信开发者工具/实际运行环境验证选中时钟存在且单位为毫秒；缺失时不得用Date.now假装active_response_v1，先报告兼容阻塞。** 不擅自给用户新最低基础库要求。UUID可使用独立小函数按现有运动会话v4实现，避免从运动大模块引入整个游戏分包；验证1000次格式与集合无重复，这不是密码学强度断言。

```typescript
export function createGameClientSessionId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, marker => {
    const value = marker === 'x' ? Math.floor(Math.random() * 16) : Math.floor(Math.random() * 4) + 8
    return value.toString(16)
  })
}
```

- [x] **Step 5: 绿灯。** 重跑本任务两文件，所有纯计时、平台选择、UUID用例通过；记录微信运行时能力验证证据后再进入集成。

### Task 4: 六游戏接入、上传与补传

**Files:**
- Modify: `miniapp/src/pages/game-session/index.tsx`
- Modify: `miniapp/src/pages/game-session/gameTypes.ts`
- Modify: `miniapp/src/pages/game-session/scoring.ts`
- Modify: `miniapp/src/pages/game-session/index.integration.test.tsx`
- Modify: `miniapp/src/pages/game-session/retryUpload.test.ts`
- Modify: `miniapp/src/pages/game-session/scoring.test.ts`

**Interfaces:**
- Consumes: Task 3 `QuestionCapture`、`GameQuestionPayload`、时钟/UUID；现有 `postGameTrainingRecord` 和补传缓存流程。
- Produces: 新版 `GameTrainingPayload` 增加 `client_session_id` 与 `question_results`；旧缓存载荷仍可读取。使用optional兼容旧缓存，页面构造新版时以交叉类型确保两个字段必填。
- Produces: `buildGameTrainingResult` 仍仅生成摘要；其Omit返回类型新增排除client_session_id/question_results，避免摘要函数负责UUID。

- [x] **Step 1: 扩展现有页面 harness 的行为测试。** 注入可控平台时钟，不用真实等待。在已有六游戏成功路径里核对上传payload，额外覆盖暂停、隐藏、声音重播、反馈期间主动结束、拼图重复方块。断言形状：

```typescript
expect(payload.client_session_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
expect(payload.question_results).toEqual([
  expect.objectContaining({question_index: 1, response_duration_ms: 2500, result_type: 'answered'}),
])
expect(payload.form_data.raw_detail.difficulty_adjust_reason).toBe('')
expect(payload.form_data.raw_detail.rounds).toBeUndefined()
```

`payload`从现有postGameTrainingRecord mock捕获；2.5秒由测试推动两段1200/1300毫秒作答，中间推进8秒暂停得到。序列测试先等待全部2秒展示结束才启动有效时钟，不把预览时长混入。

- [x] **Step 2: 运行红灯。** `cd miniapp && npm test -- src/pages/game-session/index.integration.test.tsx src/pages/game-session/retryUpload.test.ts`，预期新字段和排除暂停断言失败。
- [x] **Step 3: 接入每题开始和暂停节点。** 删除roundStartedAtRef/responseMs的权威计时用途；UnitResult仅保留游戏当前反馈所需字段，新payload不再上传题干/答案/点击轨迹。节点映射：

| 游戏/节点 | 操作 |
| --- | --- |
| 颜色/图案 scheduler.onComplete | 已切换可输入后begin |
| startInhibitionRound/startCategoryRound | 题目可点击时begin |
| startPuzzlePreviewTimer完成 | 预览结束后begin |
| autoPreviewSoundRound | 目标声音播放完成且run仍有效才begin |
| suspend/pauseGame/useDidHide | 同步capture.pause，不等React effect |
| resumeGame/useDidShow | 仅题目处于可作答且没有语音/反馈时resume |
| replayTargetSound | 播放前pause，完成且原题仍有效才resume |
| appendUnitResult/timeout | 在反馈与tap音影响前finish一次 |
| endSession/unmount/reset | discard当前未判定题；reset仅新会话 |

```typescript
const captureRef = useRef<QuestionCapture | null>(null)
const clientSessionIdRef = useRef<string | null>(null)
// 在用户正式开始新游戏时初始化，重复渲染和重试不执行：
captureRef.current = createQuestionCapture(createCaptureNow())
clientSessionIdRef.current = createGameClientSessionId()
```

声音首次播放/重播期间禁用最终选择并冻结单题倒计时，结束后恢复剩余思考时间；失败也需明确恢复或允许用户重播，不产生一段静默计时。通过原runId＋当前题对象＋phase判定隔离过期音频回调，后台/结束后不能resume。多种暂停原因同时存在时以统一 `canAnswerCurrentQuestion` 条件恢复，不能只凭一个音频finally恢复。

- [x] **Step 4: 统一题目完成与拼图交换。** 在appendUnitResult内部先调用finish，若null不重复追加；withBaseRoundDetail不再计算时钟。timeout传false/timeout；拼图只有两个不同有效方块实际交换才recordSwap，且在完成判定前累计最后一次交换。

```typescript
if (selectedPuzzleTileId !== tile.id) captureRef.current?.recordSwap()
const row = captureRef.current?.finish(correct, detail?.result === 'timeout' ? 'timeout' : 'answered')
if (!row) return
```

两个片段分别位于现有swap成功处和appendUnitResult，不要把finish放在每次拼图交换处。达到2000个已判定题后调用现有结束入口保存结果，不再生成第2001题；自动结束仍保留原ended_by枚举和说明，不扩充玩法参数。

- [x] **Step 5: 整场载荷使用规范列表。** endSession先discard，然后读取results。摘要completed/correct使用同一列表，保持score现有算法；新版raw_detail不写rounds。实现核心：

```typescript
captureRef.current?.discard()
const questions = captureRef.current?.results() ?? []
const sessionId = clientSessionIdRef.current
if (!sessionId) throw new Error('游戏会话尚未开始')
const payload: GameTrainingPayload & {client_session_id: string; question_results: GameQuestionPayload[]} = {
  ...base,
  prescription_action: currentAction.id,
  training_date: todayLocalDate(),
  note: reason === 'manual' ? '用户提前结束本次游戏训练' : '',
  client_session_id: sessionId,
  question_results: questions,
}
```

当前整场计时若受setInterval节拍漂移影响而小于有效题时长总和，调整**整场已用时间计算**使用同一单调来源累计playing区间，保留显示/结束阈值与暂停语义；不得通过缩短题目毫秒或扩大后端容差“修复”。游戏intro不进入整场训练秒数，展示/反馈可计整场秒数。

- [x] **Step 6: 验证补传与所有游戏回归。** retry只更新三个传输字段，UUID与question_results不变；旧缓存无新字段仍可上传，409不可自动无限重试。`cd miniapp && npm test -- src/pages/game-session`；六游戏各有一条带明确时间证据的页面用例，另跑scoring/retry既有用例，无2秒展示、三档难度、媒体隐藏回归。

### Task 5: 授权范围、快照查询与五表行数据

**Files:**
- Create: `backend/apps/training/export_scope.py`
- Create: `backend/apps/training/export_schema.py`
- Create: `backend/apps/training/export_rows.py`
- Modify: `backend/apps/wearables/services/training_windows.py`（公开纯窗口函数，原图表调用保持相同）
- Create: `backend/apps/training/tests/test_export_scope.py`
- Create: `backend/apps/training/tests/test_export_rows.py`
- Modify: `backend/apps/training/tests/test_training_video_wearable_api.py`

**Interfaces:**
- Consumes: `accessible_project_patients(user)`、TrainingRecord、Task 1 question_results、TrainingVideo reverse relation `video`、WearableMeasurement 和现有 motion job 状态。
- Produces: `ExportFilter` dataclass：`project_patient_id:int, range_value:str, start_date:date|None, end_date:date|None`。
- Produces: `TrainingDetailExportSerializer(serializers.Serializer)`；`resolve_export_filter(data: dict, *, today: date) -> ExportFilter`；`authorize_export(user: User, *, patient_id:int, project_patient_id:int) -> ProjectPatient`，越权404。
- Produces: `training_video_health_window(video: TrainingVideo) -> tuple[datetime, datetime] | None`，公开原_health_window的纯计算；保留旧私有函数别名兼容旧引用。
- Produces: `ExportRows` context manager，`.metadata:dict`、`.row_counts:dict[str,int]`、`.quality_chunk_count:int`、`.text_chunk_counts:dict[str,dict[str,int]]`（按表/文本字段记录拆分列数）、`.iter_rows(sheet_name:str) -> Iterator[dict[str, CellValue]]`，`.close()->None`删除全部行暂存文件。
- Produces: `prepare_export_rows(*, project_patient: ProjectPatient, filters: ExportFilter, deadline: float) -> ExportRows`；调用者已在只读快照事务内并二次确认权限。
- Produces: `CellValue = str | int | float | Decimal | bool | date | datetime | None`，`SHEET_HEADERS: dict[str, tuple[str,...]]`、`FIELD_DEFINITIONS: dict[str, str]`；行dict直接用中文表头为key，未知key测试报错。
- Produces: `ExportLimitError`、`ExportDeadlineError`，供 Task 6 转明确JSON；使用time.monotonic检查绝对deadline。

- [x] **Step 1: 写筛选与授权测试。** 以明确日期测试范围，不依赖机器本地时区。

```python
from datetime import date
from apps.training.export_scope import resolve_export_filter

def test_last_seven_days_are_inclusive():
    value = resolve_export_filter(
        {"project_patient": 8, "range": "7d"}, today=date(2026, 9, 9),
    )
    assert value.start_date == date(2026, 9, 3)
    assert value.end_date == date(2026, 9, 9)
```

参数化custom缺日期、非custom夹带日期、格式错误、未来结束、反向日期、未知range；均400。authorize_export通过accessible_project_patients过滤 pk和patient_id；不调用ensure_project_open，测试已完结项目和行范围feature flag保持一致。

- [x] **Step 2: 运行红灯并实现筛选。** `后端测试 apps/training/tests/test_export_scope.py -q`，先缺模块失败，再实现下列边界并跑绿：

```python
start = today - timedelta(days=6 if range_value == "7d" else 29)
# all -> start_date/end_date 均 None；custom 使用serializer验证后的两个date。
return get_object_or_404(accessible_project_patients(user),
                         pk=project_patient_id, patient_id=patient_id)
```

Serializer.project_patient IntegerField(min_value=1)，range ChoiceField四枚举且默认30d，start/end DateField optional；显式核验请求键，不能把客户端任意video/record/device参数带入查询。

- [x] **Step 3: 写数据行语义测试与完整样本 fixture。** 在新test_export_rows.py局部定义 `export_sample` fixture，基于现有doctor/project_patient/active_prescription：创建历史和当前处方、一个规范游戏两题（0ms正确和超时错误）、一个legacy游戏、一场医生修订运动、一场无结果运动，以及第二项目/第二患者排除项；扩展生理样本覆盖窗口端点与重叠。

```python
# export_sample 提供已授权 project_patient、filters、record_id；在该fixture创建的两题为active。
with prepare_export_rows(project_patient=export_sample.project_patient,
                         filters=export_sample.filters,
                         deadline=time.monotonic() + 60) as rows:
    questions = list(rows.iter_rows("游戏逐题"))
    own = [row for row in questions if row["训练记录编号"] == export_sample.record_id]
    assert own[0]["有效作答时间（毫秒）"] == 0
    assert own[0]["历史作答时间（毫秒）"] is None
    assert own[1]["判定"] == "超时"
```

模型fixture可返回SimpleNamespace，不跨import其他测试的私有helper。生理测试断言同一measurement_id在两个窗口恰好两行、边界±1微秒的纳入/排除、wrong patient/ambiguous排除、BP缺半对排除、actual_end变化不影响；摘要与导出明细自己计算的均值一致。

- [x] **Step 4: 定义完整列契约。** export_schema.py存五表有序表头与逐字段定义，Task 6只负责写值。以下是逐题和生理的完整表头；场次、运动字段按随后映射清单逐项登记，测试断言每个表头都有FIELD_DEFINITIONS且不会漏列。

```python
SHEET_HEADERS = {
    "游戏逐题": ("训练记录编号", "训练日期", "游戏编码", "游戏名称", "题号", "实际难度",
                "有效作答时间（毫秒）", "历史作答时间（毫秒）", "判定", "实际交换次数", "采集版本", "数据口径说明"),
    "训练期间生理数据": ("训练记录编号", "录像编号", "测量记录编号", "测量时间", "指标类型",
                        "心率（次/分）", "收缩压（mmHg）", "舒张压（mmHg）", "血氧（%）",
                        "窗口开始", "窗口结束", "窗口口径"),
    "字段说明": ("分类", "字段或项目", "说明或值"),
}
```

场次表按顺序加入：患者编号/姓名/脱敏手机号、项目编号/名称、项目患者编号/当前分组名称、训练记录编号/训练日期/提交时间、处方编号/版本/动作编号/动作编码/动作名称/训练类型、完成状态、计划时长（秒）/实际训练时长（秒）/时长来源与精度、训练开始时间/实际结束时间/起止时间可用性、游戏得分/实际难度/处方难度/是否调整难度/完成题数/正确题数/错误题数/正确率（%）/是否提前结束/结束方式、逐题记录数/规范计时题数/历史计时题数/逐题完整性/备注、窗口开始/结束/口径，最后三个指标各自可用性与count/mean/min/max（血压一份配对count和两组均值/最小/最大）。

运动表按顺序加入：训练记录编号/训练日期/动作编码/动作名称/处方时长（秒）/首次录像开始/实际结束/实际训练秒数/视频文件秒数、动作总次数/标准次数/非标准次数/结果来源/结果更新时间/修订医生编号/姓名、分析状态/分析失败说明、动作质量详情1至N、录像编号/录像处理状态/备注。动态N由行暂存最大JSON长度提前计算，至少1列；每段最多32767字符，禁止事后向write-only表头追加列。

- [x] **Step 5: 实现记录和题目分批查询及字段映射。** 从授权ProjectPatient过滤TrainingRecord.training_date，按training_date,id排序，不限当前处方。每批100records预载patient/project/group/prescription/action/video/修订医生；最新job仅用于分析状态与失败原因，以Subquery或每批一次query读取，结果次数/quality必须读record。失败说明使用现有追踪接口的脱敏口径，不直接写异常堆栈；质量JSON只输出动作质量及医生说明业务字段，不能透出对象键、签名URL或原始推理载荷。逐题每批一次查询并按record,index稳定排序，正式行存在就不再解析rounds；有新版UUID且正式列表为空表示真实0题，不能fallback到rounds。

```python
active = question.capture_version == "active_response_v1"
question_row = {
    "有效作答时间（毫秒）": question.response_duration_ms if active else None,
    "历史作答时间（毫秒）": None if active else question.response_duration_ms,
}
```

行完整字段由Step4契约逐一赋值；预载模型变换为局部可序列化dict，避免迭代时隐式SQL。日期time不可用为空；游戏时长raw_detail秒优先，再分钟换算标精度；运动video.actual_duration_seconds优先再分钟，绝不拿video.duration_seconds代替实际训练。动作名称/参数用处方快照，source_key采用已有动作关联编码。历史摘要保留原值；有规范题目根据正式表汇总，puzzle正确率None。

- [x] **Step 6: 实现固定窗口与测量关联流。** 将原_health_window公开为training_video_health_window且旧函数代理；现有图表仍使用同公式。每批授权record的100个窗口组成参数化VALUES CTE，经recordid/videoid/windowstart/end JOIN WearableMeasurement；所有值用数据库参数，不拼接来自请求的SQL。按训练记录顺序、measured_at、measurementid返回；用服务器游标fetchmany(500)处理并生成生理行，同时累计各场count/sum/min/max，不保存全量测量列表。关键关联必须同时满足：

```sql
m.patient_id = %s
AND m.attribution_status = 'attributed'
AND m.measured_at >= w.started_at
AND m.measured_at <= w.ended_at
AND ((m.metric_type = 'heart_rate' AND m.heart_rate IS NOT NULL)
 OR (m.metric_type = 'blood_pressure' AND m.systolic IS NOT NULL AND m.diastolic IS NOT NULL)
 OR (m.metric_type = 'blood_oxygen' AND m.blood_oxygen IS NOT NULL))
```

SQL表名从模型_meta.db_table经connection.ops.quote_name得到，窗口只能来自本批已授权record；使用明确列清单，不SELECT raw_payload。闭区间重叠保持多条关联。Decimal均值quantize(0.1, ROUND_HALF_UP)，空count可0但摘要数值None且标原因。运动没有窗口/有窗口无测量分别说明；game不创建window。大查询有statement timeout，整批前后检查deadline。

- [x] **Step 7: 实现私有行暂存和资源限额。** 使用TemporaryDirectory默认0700、每表0600 JSONL；只写允许的CellValue，date/datetime/Decimal用带类型标记编码并由iter_rows还原，不能把日期/数值丢成字符串。每append检查各表和总行数，10001场/200001单表/500001总数据行抛ExportLimitError；说明表不计业务数据行。写每行前检查deadline，异常关闭上下文删目录。metadata保留实际日期范围、计数、当前分组口径、快照点；每个自由文本字段在暂存时更新text_chunk_counts，以原始字符数计算所需32767字符分段上界。quality_chunk_count从运动质量字段的同一计数读取。原始生理载荷与患者视频对象键永不落暂存。

```python
if sheet_count > 200_000 or total_count > 500_000:
    raise ExportLimitError("导出数据过多，请缩小日期范围")
if time.monotonic() >= deadline:
    raise ExportDeadlineError("导出生成超时，请缩小日期范围")
```

超限测试通过monkeypatch模块常量为小值覆盖，而非每次造50万数据；另在Task8做接近真实量样本验证。行暂存完成后Task6可结束数据库快照事务再压缩XLSX。

- [x] **Step 8: 绿灯与查询规模验证。** `后端测试 apps/training/tests/test_export_scope.py apps/training/tests/test_export_rows.py apps/training/tests/test_training_video_wearable_api.py -q`；测试1/100record处于同一批时查询次数有固定上界，101record只增加一批成本，不能每场一个测量/逐题SQL。只读一致性在Task6用真实事务验证。

### Task 6: 五表 Excel、审计和下载接口

**Files:**
- Create: `backend/apps/training/export_workbook.py`
- Create: `backend/apps/training/export_views.py`
- Modify: `backend/apps/training/models.py`（TrainingDetailExportLog）
- Create: `backend/apps/training/migrations/0018_training_detail_export_log.py`
- Modify: `backend/apps/training/urls.py`
- Modify: `backend/pyproject.toml`（openpyxl依赖）
- Create: `backend/apps/training/tests/test_export_workbook.py`
- Create: `backend/apps/training/tests/test_training_detail_export_api.py`

**Interfaces:**
- Consumes: Task5完整接口与schema；现有IsAdminOrDoctor/Session/CSRF。
- Produces: `build_training_detail_workbook(rows: ExportRows, *, deadline:float) -> BinaryIO`；成功返回已seek(0)的TemporaryFile，异常自行close。
- Produces: `TrainingDetailExportLog`：operator可空SET_NULL、patient_id_snapshot/project_id_snapshot/project_patient_id_snapshot整数、filters JSON、started_at/finished_at、status generating/succeeded/failed、format_version、row_counts JSON、error_code（固定枚举文本）。无强制保留源实体FK，无文件列。
- Produces: `TrackingPatientExportView.post(request, patient_id)` → FileResponse或DRF JSON；路由 `tracking/patients/<int:patient_id>/export/`。

- [x] **Step 1: 增加依赖并写可读工作簿失败测试。** pyproject runtime添加 `openpyxl>=3.1,<4.0`，在后端环境安装项目依赖后创建测试。sample使用Task5样本数据，含`=HYPERLINK(...)`备注、0数值、换行、60000字质量JSON、XML控制字符和中文。

```python
with build_training_detail_workbook(rows, deadline=time.monotonic() + 60) as handle:
    workbook = openpyxl.load_workbook(handle, data_only=False)
    assert workbook.sheetnames == ["训练场次", "游戏逐题", "运动明细", "训练期间生理数据", "字段说明"]
    for sheet in workbook:
        assert sheet.freeze_panes == "A2"
        assert sheet.auto_filter.ref is not None
        assert not sheet.merged_cells.ranges
    notes = [cell for row in workbook["训练场次"] for cell in row if cell.value == '=HYPERLINK("x")']
    assert notes and notes[0].data_type == "s"
    assert notes[0].hyperlink is None
```

- [x] **Step 2: 运行红灯并实现单元格编码。** `后端测试 apps/training/tests/test_export_workbook.py -q`先失败。用WriteOnlyCell显式字符串，禁止让openpyxl自行把等号识别公式；清理非法XML C0字符并累计替换数，必须在写“字段说明”最后一表时纳入总数。

```python
cell = WriteOnlyCell(sheet, value=cleaned_value)
if isinstance(cleaned_value, str):
    cell.data_type = "s"
    cell.hyperlink = None
    cell.alignment = Alignment(vertical="top", wrap_text=True)
elif isinstance(cleaned_value, datetime):
    cell.value = cleaned_value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    cell.number_format = "yyyy-mm-dd hh:mm:ss"
```

date不走datetime分支，格式yyyy-mm-dd；bool保留bool；Decimal转Excel兼容数值并按字段固定格式。无外部链接、不创建宏。临时工作簿使用 `TemporaryFile(mode="w+b")` 权限0600，成功返回，异常关闭。

- [x] **Step 3: 实现write-only五表布局和说明。** 创建所有表，先设freeze/filter/列宽再append；从schema读取有序header，动态质量列N和其他长文本字段的text_chunk_counts提前已知，拼接恢复测试与经过明确XML字符替换的原JSON精确相等。默认数字列12–18宽、名称18–24、说明/JSON36–48、日期20，首行字体加粗浅底色、换行。长文本不限于质量JSON：任意超过32767字符的自由文本同样连续分列并标注，不静默截断。说明表含操作者、范围、实际起止日期、生成时间/快照点、五表行数、替换字符数、每字段单位和解释；空业务表保留header和筛选A1至最后表头。

```python
sheet.freeze_panes = "A2"
sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(1, count + 1)}"
sheet.append([WriteOnlyCell(sheet, value=header) for header in headers])
```

工作簿压缩最后save前后也检查deadline。实现一个deadline检查的文件包装器（代理write/seek/tell/flush给TemporaryFile，每次write先检查），让zip写入超过60秒能中止；不要只检查数据库查询而遗漏压缩阶段。

- [x] **Step 4: 增加审计模型和migration。** 按Interfaces建字段，status generating开始、succeeded生成完成、failed已分类失败；源id整数快照不加PROTECT，operator SET_NULL。执行makemigrations training --name training_detail_export_log，核对依赖最新叶节点。单测删除ProjectPatient后日志仍在且解绑流程不阻塞；不改解绑清理代码来迁就审计。

- [x] **Step 5: 写API失败测试及快照并发测试。** 用真实Session CSRF测试未登录/患者角色/缺CSRF/跨患者/跨项目/医生行范围；合法已完结项目200，空结果200且五表。固定日期范围覆盖历史处方。两个数据库连接在导出第一表生成后更改motionresult并插入measurement；文件中五表仍反映同一旧快照，下一次导出才含新值。

```python
response = client.post(
    f"/api/training/tracking/patients/{patient.id}/export/",
    {"project_patient": project_patient.id, "range": "30d"}, format="json",
)
assert response.status_code == 200
assert response["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
assert response["Cache-Control"] == "no-store"
assert patient.name not in response["Content-Disposition"]
response.close()
```

这里client由本测试以doctor身份初始化，patient/project_patient来自fixture。权限拒绝不创建含别的患者身份的审计行，不泄漏别的患者是否存在。

- [x] **Step 6: 实现API协调与快照。** serializer→authorize→审计generating→deadline→只读transaction→二次authorize→prepare行数据→退出事务→build文件→audit success→FileResponse。快照事务的**第一条SQL**设置事务级别，所有本次读取均在其后；不要在事务内部先查权限再设隔离级别。

```python
with transaction.atomic():
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", ["60000"])
    project_patient = authorize_export(request.user, patient_id=patient_id,
                                      project_patient_id=filters.project_patient_id)
    rows = prepare_export_rows(project_patient=project_patient, filters=filters, deadline=deadline)
```

每次新查询前把statement_timeout设为**剩余预算毫秒**，避免第59秒新query再跑60秒。生成时间在开始时固定；snapshot metadata由同事务SELECT transaction_timestamp()获取。审计save在只读事务外。FileResponse直接接临时file对象，响应close自动关闭；rows在finally.close；如果response构造失败也close workbook。audit失败不得返回未审计的成功文件，清理文件并标准500。

- [x] **Step 7: 映射明确错误、检查超时配置。** ExportLimitError→400/detail缩小范围；ExportDeadlineError或SQL查询超时→503/detail缩小范围；其他异常→500固定“导出失败，请重试”，日志error_code不记录载荷/SQL/存储URL。filename用patient/project数字编号、range日期label、上海生成time，Django FileResponse filename自动编码Disposition。

```python
response = FileResponse(handle, as_attachment=True, filename=filename,
    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
response["Cache-Control"] = "no-store"
return response
```

当前仓库后端Dockerfile gunicorn timeout=180、deploy/openresty/motioncare.conf API proxy_read_timeout=300，均大于60秒；只核对实际部署准备配置，无需为了本功能修改现有超时。测试成功/超时/限额/写文件异常/客户端close路径的所有句柄和临时目录均释放。

- [x] **Step 8: 绿灯。** `后端测试 apps/training/tests/test_export_workbook.py apps/training/tests/test_training_detail_export_api.py -q`；加 `makemigrations --check --dry-run`。权限、快照、审计和临时清理用例必须真实通过，不用mock掉核心事务。

### Task 7: 患者详情导出弹窗与下载

**Files:**
- Create: `frontend/src/pages/training-tracking/trainingDetailExport.ts`
- Create: `frontend/src/pages/training-tracking/trainingDetailExport.test.ts`
- Create: `frontend/src/pages/training-tracking/TrainingDetailExportModal.tsx`
- Create: `frontend/src/pages/training-tracking/TrainingDetailExportModal.test.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`

**Interfaces:**
- Consumes: `TrackingPatient`、`TrackingProjectPatient[]`、详情页 `currentProjectPatientId`、现有apiClient CSRF拦截器。
- Produces: `TrainingExportRequest = {project_patient:number; range:'7d'|'30d'|'custom'|'all'; start_date?:string; end_date?:string}`。
- Produces: `downloadTrainingDetail(patientId:number, request:TrainingExportRequest):Promise<void>`，成功触发浏览器下载，失败throw已脱敏中文Error。
- Produces: `TrainingDetailExportModal({open,onClose,patient,projects,defaultProjectPatientId})`；patient:TrackingPatient、projects:TrackingProjectPatient[]、onClose:()=>void、默认项目number|undefined。

- [x] **Step 1: 写下载行为失败测试。** mock axios返回blob和headers，mock URL.createObjectURL/revokeObjectURL、anchor.click。错误blob为JSON时应展示detail而非下载。

```typescript
it('JSON错误不会被保存为Excel', async () => {
  vi.mocked(apiClient.post).mockRejectedValue({response: {
    headers: {'content-type': 'application/json'},
    data: new Blob([JSON.stringify({detail: '导出数据过多，请缩小日期范围'})], {type: 'application/json'}),
  }})
  await expect(downloadTrainingDetail(3, {project_patient: 8, range: 'all'}))
    .rejects.toThrow('导出数据过多，请缩小日期范围')
  expect(URL.createObjectURL).not.toHaveBeenCalled()
})
```

- [x] **Step 2: 红灯并实现请求下载。** `cd frontend && npm run test -- src/pages/training-tracking/trainingDetailExport.test.ts`，先缺模块失败；核心请求如下：

```typescript
const response = await apiClient.post<Blob>(
  `/training/tracking/patients/${patientId}/export/`, request,
  {responseType: 'blob', timeout: 75_000},
)
```

只在xlsx MIME且body非空时createObjectURL。解析Content-Disposition filename*优先，decode失败用`患者编号_训练明细.xlsx`；去掉路径分隔符/控制字符，不能从任意header拼网页。创建临时anchor设download触发，下载后下一任务清理URL和anchor，异常也清理。JSON错误按Content-Type＋Blob.text解析detail；网络/超时/未知格式用固定中文，拒绝把含URL、token、secret的后端异常原文展示给用户。不在console写导出内容。

- [x] **Step 3: 写弹窗与详情入口测试。** 组件初次打开默认当前项目＋30d，切换custom显示日期范围；自定义缺失/未来/反向禁导出，生成中一次请求、不允许切项目/关闭后状态错乱，失败保留筛选，成功关弹窗。无项目详情分支仍展示禁用入口与原因；不展示project_status。

```typescript
expect(screen.getByRole('button', {name: '导出 Excel'})).toBeEnabled()
await user.click(screen.getByRole('button', {name: '导出 Excel'}))
expect(downloadTrainingDetail).toHaveBeenCalledWith(3, {project_patient: 8, range: '30d'})
expect(screen.queryByText('已完结')).not.toBeInTheDocument()
```

以上patient=3/projectpatient=8由render传props；使用现有TestingLibrary/QueryClient/router测试模式，不重写全局harness。

- [x] **Step 4: 实现AntD轻量弹窗。** 使用Form、Select、Radio.Group、DatePicker.RangePicker、Alert、Modal；width=600且maxWidth适应小屏。项目选项仅project_name，范围四个文字“近7天/近30天/自定义/全部历史”，确认按钮“导出 Excel”。组件状态独立于详情页现有weekly筛选。

```tsx
<Modal title="导出训练明细" open={open} onCancel={onClose}
  onOk={() => void form.submit()} okText="导出 Excel" confirmLoading={loading}
  cancelButtonProps={{disabled: loading}} closable={!loading} maskClosable={!loading}>
  <Typography.Paragraph>{patient.name}（{patient.phone_masked}）</Typography.Paragraph>
  <Form form={form} layout="vertical" onFinish={handleExport}>
    <Form.Item name="project_patient" label="项目" rules={[{required: true, message: '请选择项目'}]}>
      <Select disabled={loading} options={projects.map(p => ({value: p.id, label: p.project_name}))} />
    </Form.Item>
  </Form>
</Modal>
```

`handleExport(values)`本组件内定义，先验证range/dates，设置loading，await downloadTrainingDetail，成功onClose，catch setError，finally清loading；用同步ref锁防同一帧重复提交。打开时用defaultProjectPatientId若存在于projects，否则第一个；同一次打开失败不resetFields。日期以YYYY-MM-DD发送，未来比较上海当天字符串，不用浏览器UTC Date.toISOString截日期。

弹窗帮助文字分三句：包含游戏逐题、运动结果和生理读数；“历史数据可能缺失。游戏暂无可用生理观察窗口，运动生理窗口包含处方时长后5分钟。”；“单次最多10000场，每个数据表200000行，总计500000行；超限请缩小日期范围。”不显示存储、版本内部实现细节。

- [x] **Step 5: 接入详情页顶部与无项目分支。** 在“患者训练与健康”Descriptions.extra加入导出按钮，使用currentProjectPatientId传默认值；组件放在稳定父级，避免更换趋势range导致弹窗卸载。无项目分支禁用同名按钮并给“暂无可导出的项目”说明，权限和未登录仍走现有页面边界。

```tsx
<Button onClick={() => setExportOpen(true)} disabled={!currentProjectDataReady}>
  导出训练明细
</Button>
```

不要依赖`recent_records`生成文件或判断是否可导出，空记录也可生成；项目切换加载期间防默认ID与患者错配。页面路由患者变化时关闭弹窗、清旧患者引用。

- [x] **Step 6: 绿灯和视觉验收。** `cd frontend && npm run test -- src/pages/training-tracking`，然后npm run lint与npm run build。用本地合成患者API样本打开弹窗，验证600px桌面/375px窄屏不截按钮；截图入口、custom、loading/error各状态。不得用真实患者资料制作交付截图。

### Task 8: 跨端样本、工作簿验收与收口

**Files:**
- Create: `backend/apps/training/tests/test_training_detail_export_acceptance.py`
- Modify: 本计划及已确认设计头部（仅真实执行状态）
- Modify: `docs/superpowers/README.md`
- Modify: `specs/patient-rehab-system/changelog.md`（只追加）
- Local artifacts: `output/training-detail-export/`（合成样本XLSX和截图，不纳入业务数据目录）

**Interfaces:**
- Consumes: Task1–7真实API、模型、页面、工作簿；不增加新运行时接口。
- Produces: 可由Excel兼容读取器打开的合成样本文件、字段值核对结果、全量测试/构建记录、发布顺序清单。没有发布授权时只交付可审查产物。

- [x] **Step 1: 写跨端契约验收。** fixture创建两项目、每款游戏至少一场、三档难度、历史处方、legacy混合数据、AI/医生运动结果、无AI高抬腿、三类测量。先经患者API提交规范question_results，再以医生API导出；不能直接建Question模型代替写入链路。使用openpyxl按header找列核对值：

```python
headers = [cell.value for cell in workbook["游戏逐题"][1]]
records = [dict(zip(headers, values)) for values in workbook["游戏逐题"].iter_rows(min_row=2, values_only=True)]
assert {row["游戏编码"] for row in records} == set(game_codes)
assert sum(row["采集版本"] == "active_response_v1" for row in records) == expected_active_count
assert all(row["历史作答时间（毫秒）"] is None for row in records if row["采集版本"] == "active_response_v1")
```

`game_codes`为fixture六个实际catalog编码列表，expected_active_count由提交列表长度汇总；期望不能从生成文件倒算。再测试空数据仍五表、跨午夜上海日期、同日多场、质量JSON恢复与公式字符串、未完成题未导出。接近容量的合成数据测试限额计数和性能，在临时独立DB执行，不向患者业务库写测试样本。

- [x] **Step 2: 完成红绿验收。** `后端测试 apps/training/tests/test_training_detail_export_acceptance.py -q`。若用例红灯，按实际根因修改负责模块并回跑受影响定向测试，不通过去掉跨端断言绕过。
- [x] **Step 3: 保存实际样本并视觉检查。** 由验收fixture/实际导出服务生成合成XLSX到output/training-detail-export/sample.xlsx。此步骤应用spreadsheets技能并先读取该SKILL.md，再用可用渲染器或Excel兼容应用检查五张表。若选渲染，仅截可读关键列，并额外程序核对宽表所有列、冻结、筛选、Excel数值/日期、无公式/链接、长JSON全部片段；不能只拍第一屏说验收通过。
- [x] **Step 4: 全量后端验证与迁移演练。** `后端测试 -q`；预期完整通过，不复用先前1237条通过数字。独立测试库从现有叶节点升级，记录legacy scanned/created/skipped并核对来源JSON未变化，`makemigrations --check --dry-run`无漏迁移。旧数据恢复能力只说已有字段可还原，不声称历史有效耗时已补齐。
- [x] **Step 5: 全量Web验证。** `cd frontend && npm run test`，再依次 `npm run lint`、`npm run build`；记录测试总数与警告，既有5项lint警告与本次新增问题分开。
- [x] **Step 6: 全量小程序验证与构建。** `cd miniapp && npm test`；再依次 `npm run build:weapp:prod`、`npm run check:weapp-package-size`、`TARO_APP_CONFIG_ENV=production npm run build:h5`。构建可能覆写dist，微信包检查紧跟微信构建，不用H5产物验微信包。保留日志并检查静态签名素材没有重新打包进主包。
- [x] **Step 7: 更新真实执行记录并完成审查。** 每任务实际通过才勾选；未提交时实施基线写“当前隔离区未提交改动”，不编造提交编号。不将旧2026-08-21长期统计计划整体标完成，也不把新功能写成已上线。changelog追加模型/客户端/导出入口/历史限制与证据；保留既有难度、隐藏项目状态和高抬腿改动。
- [x] **Step 8: 交付用户可审查结果。** 说明入口、五表、有效与历史耗时区别、运动健康窗口口径、测试结果及发布前提；附合成样本和界面截图。发布顺序固定：后端兼容写入与迁移→核对历史迁移→Web入口→新版小程序。只有后续收到明确发布/上传授权和小程序版本号，才执行对应发布；本任务不执行发布。

## 主控自审与需求覆盖

- Spec §1–2：Task7入口与筛选、Task5历史处方范围；未纳入跨项目批量。
- Spec §3五表：Task5列契约与映射、Task6格式和安全、Task8实际文件验证。
- Spec §4数据基础：Task1–4；ID幂等在当前处方检查前，首次写入门禁仍由原服务保证。
- Spec §5历史兼容：Task1冻结解析/迁移、Task2旧在线写入、Task5正式优先与计时分列。
- Spec §6权限与审计：Task5授权、Task6Session/CSRF/审计/解绑兼容、Task7错误blob防误下载。
- Spec §7容量与一致性：Task5行限额/分批查询/暂存，Task6快照/剩余SQL预算/文件压缩deadline/清理。
- Spec §8–9验收与发布：Task8；无自动提交或发布。Game绝对时间不在本期，UI和说明表标清。
- 当前已核对迁移叶节点0015、实际API前缀、当前处方检查位置、Taro性能类型声明、gunicorn180秒与代理300秒。微信单调时钟的运行时能力为Task3必须验证的技术条件，未把它当作已验证事实。
- 自审记录（2026-09-09, Codex）：已核对八任务接口衔接、原服务返回类型兼容、旧缓存、新题0条不回退rounds、只读事务外审计、动态长文本列和输出清理。所有实施复选框保持未勾选；此文档是实施计划，不能当作代码已完成证明。
