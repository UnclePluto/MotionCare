# 游戏逐题数据与长期统计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为六款认知游戏建立可靠的逐题有效作答数据、幂等整场上传、历史数据迁移，以及医生端单场明细和长期趋势统计。

**Architecture:** `TrainingRecord` 继续代表一次游戏会话，新增 `GameQuestionResult` 保存标准化逐题结果；小程序只在整场结束时批量上传，后端通过客户端 UUID 与语义指纹实现幂等事务写入。医生端通过独立统计与分页明细接口读取数据，不把逐题数组塞进现有训练追踪详情响应。

**Tech Stack:** Django 5、Django REST Framework、PostgreSQL、pytest-django、Taro 4、React 18、TypeScript、Vitest、Ant Design 5、TanStack Query v5、Ant Design Charts。

**Spec:** `docs/superpowers/specs/2026-08-21-game-question-analytics-design.md`

> 状态：review
> 日期：2026-08-21
> 范围：六款认知游戏逐题采集、幂等写入、历史迁移、长期统计和单场明细。
> 关联：`docs/superpowers/specs/2026-08-21-game-question-analytics-design.md`

## Global Constraints

- 覆盖六个现有游戏编码：`game-memory-color-sequence`、`game-memory-pattern-sequence`、`game-executive-inhibition`、`game-executive-category-switch`、`game-audiovisual-sound-discrimination`、`game-audiovisual-puzzle`。
- `TrainingRecord` 是唯一整场会话模型；禁止新增独立 `GameSession`。
- 未完成题直接丢弃；只有已答题和单题超时题进入 `GameQuestionResult`。
- 有效作答时长排除展示、语音、暂停和答后反馈；单位统一为整数毫秒。
- 拼图只统计实际交换次数，不统计普通点击；拼图不进入综合正确率。
- 单次最多接收 2,000 条逐题结果；单题最多 3,600,000 毫秒；逐题时长总和不得超过整场秒数换算值加 1,000 毫秒。
- 新逐题请求的题号必须从 1 连续递增。
- `raw_detail.upload_mode`、`retry_count`、`total_retry_count` 不参与幂等语义指纹。
- 新版写入先发布后端，再发布医生端，最后发布小程序。
- 所有后端读取必须复用现有医生/管理员权限和 `ProjectPatient` 行级范围。
- 不修改处方版本、当前 active 处方校验、游戏玩法、整场计分公式或 CRF。
- 所有 Git 提交信息使用中文；每个任务只提交该任务明确列出的文件。

---

## 文件结构与职责

### 后端

- `backend/apps/training/models.py`：定义 `TrainingRecord` 幂等字段与 `GameQuestionResult` 持久化模型。
- `backend/apps/training/game_questions.py`：逐题输入标准化、跨字段校验、会话汇总重算、语义指纹和旧 `rounds` 解析；不访问 HTTP。
- `backend/apps/training/services.py`：当前处方校验、事务创建、并发幂等收口。
- `backend/apps/training/game_question_tracking.py`：日期筛选、聚合统计和单场分页序列化；不处理写入。
- `backend/apps/training/serializers.py`：医生端训练写入使用的共享逐题输入 serializer。
- `backend/apps/patient_app/serializers.py`：患者端请求字段定义。
- `backend/apps/patient_app/views.py`、`backend/apps/training/views.py`：调用幂等服务并区分 `200/201/409`。
- `backend/apps/training/tracking_views.py`、`backend/apps/training/urls.py`：逐题统计和单场明细只读接口。
- `backend/apps/training/migrations/0014_game_question_results.py`：Schema migration。
- `backend/apps/training/migrations/0015_backfill_game_question_results.py`：自包含历史数据迁移。

### 小程序

- `miniapp/src/pages/game-session/questionCapture.ts`：可注入时钟的有效时间状态机、题号分配、暂停/恢复、超时、丢弃和拼图交换累计。
- `miniapp/src/pages/game-session/gameTypes.ts`：逐题请求与整场 payload 类型。
- `miniapp/src/pages/game-session/index.tsx`：在六款游戏的准确可操作节点调用采集状态机。
- `miniapp/src/pages/game-session/retryUpload.ts`：校验、缓存和补传包含 UUID 与逐题数组的完整 payload。
- `miniapp/src/utils/clientSessionId.ts`：通用 UUID v4 创建与校验；录像训练和游戏共同复用。

### 医生 Web

- `frontend/src/pages/training-tracking/types.ts`：统计、趋势和分页明细 API 类型。
- `frontend/src/pages/training-tracking/gameQuestionAnalyticsChartConfig.ts`：纯函数生成正确率/中位时长双轴图配置。
- `frontend/src/pages/training-tracking/GameQuestionAnalyticsPanel.tsx`：日期、游戏、难度筛选以及汇总、分游戏表、趋势图。
- `frontend/src/pages/training-tracking/GameQuestionDetailDrawer.tsx`：按训练记录分页加载逐题明细。
- `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`：传入当前患者/项目关系，并在游戏记录行打开逐题抽屉。

---

### Task 1: 建立逐题模型与数据库约束

**Files:**
- Modify: `backend/apps/training/models.py`
- Create: `backend/apps/training/migrations/0014_game_question_results.py`
- Create: `backend/apps/training/tests/test_game_question_models.py`

**Interfaces:**
- Consumes: 现有 `TrainingRecord`、`PrescriptionAction` 和 Django ORM。
- Produces: `TrainingRecord.client_session_id`、`TrainingRecord.client_payload_fingerprint`、`GameQuestionResult`、`GameQuestionResult.ResultType`、`GameQuestionResult.CaptureVersion`。

- [ ] **Step 1: 写模型行为失败测试**

在 `test_game_question_models.py` 创建游戏训练记录，覆盖字段持久化、同场题号唯一、UUID 唯一和超时正确性约束：

```python
import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.training.models import GameQuestionResult, TrainingRecord


@pytest.mark.django_db
def test_game_question_result_persists_core_metrics(training_record):
    question = GameQuestionResult.objects.create(
        training_record=training_record,
        question_index=1,
        game_code="game-executive-inhibition",
        difficulty="中等",
        response_duration_ms=2380,
        is_correct=True,
        result_type=GameQuestionResult.ResultType.ANSWERED,
        capture_version=GameQuestionResult.CaptureVersion.ACTIVE_RESPONSE_V1,
    )

    assert question.response_duration_ms == 2380
    assert question.swap_count is None


@pytest.mark.django_db
def test_timeout_question_cannot_be_correct(training_record):
    with pytest.raises(IntegrityError), transaction.atomic():
        GameQuestionResult.objects.create(
            training_record=training_record,
            question_index=1,
            game_code="game-executive-inhibition",
            difficulty="中等",
            response_duration_ms=4000,
            is_correct=True,
            result_type=GameQuestionResult.ResultType.TIMEOUT,
            capture_version=GameQuestionResult.CaptureVersion.ACTIVE_RESPONSE_V1,
        )


@pytest.mark.django_db
def test_training_client_session_id_is_unique(training_record, second_training_record):
    session_id = uuid.uuid4()
    training_record.client_session_id = session_id
    training_record.save(update_fields=["client_session_id"])
    second_training_record.client_session_id = session_id

    with pytest.raises(IntegrityError), transaction.atomic():
        second_training_record.save(update_fields=["client_session_id"])
```

- [ ] **Step 2: 运行测试确认缺少模型**

Run: `cd backend && pytest apps/training/tests/test_game_question_models.py -q`

Expected: FAIL，提示 `GameQuestionResult` 无法导入或 `TrainingRecord` 缺少新字段。

- [ ] **Step 3: 实现模型和迁移**

在 `models.py` 为 `TrainingRecord` 增加：

```python
client_session_id = models.UUIDField("游戏客户端会话 ID", null=True, blank=True, unique=True)
client_payload_fingerprint = models.CharField(
    "游戏客户端语义指纹",
    max_length=64,
    null=True,
    blank=True,
)
```

定义逐题模型：

```python
class GameQuestionResult(models.Model):
    class ResultType(models.TextChoices):
        ANSWERED = "answered", "已作答"
        TIMEOUT = "timeout", "答题超时"

    class CaptureVersion(models.TextChoices):
        LEGACY_WALL_CLOCK_V0 = "legacy_wall_clock_v0", "历史墙上时钟"
        ACTIVE_RESPONSE_V1 = "active_response_v1", "有效作答时间"

    training_record = models.ForeignKey(
        TrainingRecord,
        on_delete=models.CASCADE,
        related_name="game_question_results",
    )
    question_index = models.PositiveIntegerField("题号")
    game_code = models.CharField("游戏编码快照", max_length=80)
    difficulty = models.CharField("实际难度", max_length=40)
    response_duration_ms = models.PositiveIntegerField("有效作答时长毫秒")
    is_correct = models.BooleanField("是否正确")
    result_type = models.CharField("结果类型", max_length=20, choices=ResultType.choices)
    swap_count = models.PositiveIntegerField("拼图交换次数", null=True, blank=True)
    capture_version = models.CharField(
        "采集版本",
        max_length=32,
        choices=CaptureVersion.choices,
    )

    class Meta:
        ordering = ["question_index", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["training_record", "question_index"],
                name="uniq_game_question_index_per_training",
            ),
            models.CheckConstraint(
                condition=models.Q(question_index__gt=0),
                name="game_question_index_gt_0",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(result_type="answered")
                    | models.Q(is_correct=False)
                ),
                name="game_question_timeout_not_correct",
            ),
        ]
        indexes = [
            models.Index(fields=["game_code", "difficulty"], name="game_q_code_diff_idx"),
        ]
```

用 `python manage.py makemigrations training` 生成 `0014_game_question_results.py`，确认 migration 只包含上述字段、模型、索引和约束，不夹带其他 schema 变化。

- [ ] **Step 4: 运行模型测试和迁移漂移检查**

Run: `cd backend && pytest apps/training/tests/test_game_question_models.py -q && python manage.py makemigrations --check`

Expected: 全部 PASS；输出 `No changes detected`。

- [ ] **Step 5: 提交模型任务**

```bash
git add backend/apps/training/models.py backend/apps/training/migrations/0014_game_question_results.py backend/apps/training/tests/test_game_question_models.py
git commit -m "feat(游戏统计): 建立逐题结果模型"
```

---

### Task 2: 实现逐题标准化、汇总重算与语义指纹

**Files:**
- Create: `backend/apps/training/game_questions.py`
- Create: `backend/apps/training/tests/test_game_questions.py`

**Interfaces:**
- Consumes: `PrescriptionAction.action_library_item.source_key`、`TrainingRecord` 字段值、未经信任的逐题数组和 `form_data`。
- Produces: `normalize_new_question_results(prescription_action, raw_results, form_data) -> NormalizedGameQuestions`、`semantic_game_payload_fingerprint(project_patient_id, prescription_action_id, training_date, status, actual_duration_minutes, score, form_data, note, question_results) -> str`、常量 `PUZZLE_GAME_CODE`、`MAX_QUESTION_RESULTS=2000`。

- [ ] **Step 1: 写标准化和指纹失败测试**

测试必须覆盖连续题号、超时、拼图字段、2,000 条上限、单题时长、整场时长、后端汇总和重试元数据排除：

```python
import pytest
from django.core.exceptions import ValidationError

from apps.training.game_questions import (
    normalize_new_question_results,
    semantic_game_payload_fingerprint,
)


def question(index=1, **overrides):
    value = {
        "question_index": index,
        "game_code": "game-executive-inhibition",
        "difficulty": "中等",
        "response_duration_ms": 2380,
        "is_correct": True,
        "result_type": "answered",
        "swap_count": None,
    }
    value.update(overrides)
    return value


def test_normalize_recomputes_session_summary(game_action):
    normalized = normalize_new_question_results(
        prescription_action=game_action,
        raw_results=[question(), question(2, is_correct=False)],
        form_data={
            "accuracy_rate": 99,
            "error_count": 99,
            "difficulty": "中等",
            "raw_detail": {"session_duration_seconds": 10},
        },
    )

    assert normalized.form_data["accuracy_rate"] == 50
    assert normalized.form_data["error_count"] == 1
    assert normalized.form_data["raw_detail"]["completed_units"] == 2
    assert normalized.form_data["raw_detail"]["correct_units"] == 1


def test_question_indexes_must_be_contiguous(game_action):
    with pytest.raises(ValidationError, match="题号必须从 1 连续递增"):
        normalize_new_question_results(
            prescription_action=game_action,
            raw_results=[question(2)],
            form_data={"raw_detail": {"session_duration_seconds": 10}},
        )


def test_retry_metadata_does_not_change_fingerprint(valid_fingerprint_input):
    direct = semantic_game_payload_fingerprint(**valid_fingerprint_input)
    valid_fingerprint_input["form_data"]["raw_detail"].update(
        upload_mode="retry",
        retry_count=3,
        total_retry_count=8,
    )
    retried = semantic_game_payload_fingerprint(**valid_fingerprint_input)

    assert retried == direct
```

- [ ] **Step 2: 运行测试确认领域模块不存在**

Run: `cd backend && pytest apps/training/tests/test_game_questions.py -q`

Expected: FAIL，提示 `apps.training.game_questions` 不存在。

- [ ] **Step 3: 实现纯领域模块**

使用不可变返回对象锁定接口：

```python
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Any


PUZZLE_GAME_CODE = "game-audiovisual-puzzle"
MAX_QUESTION_RESULTS = 2000
MAX_QUESTION_DURATION_MS = 3_600_000
SESSION_DURATION_ROUNDING_TOLERANCE_MS = 1000
TRANSPORT_ONLY_RAW_DETAIL_KEYS = {
    "upload_mode",
    "retry_count",
    "total_retry_count",
}


@dataclass(frozen=True)
class NormalizedGameQuestions:
    rows: Sequence[dict[str, Any]]
    form_data: dict[str, Any]
```

`normalize_new_question_results` 必须：

1. 复制 `form_data`，不得就地修改 serializer 输入。
2. 验证 `game_code` 与处方动作 `source_key` 一致。
3. 非游戏动作只要出现顶层逐题字段就拒绝；游戏动作验证题号为 `1..N`、逐题数量和时长上限。
4. 验证 `timeout => is_correct=False`。
5. 新拼图要求 `answered + is_correct=True + swap_count>=0`；其他游戏要求 `swap_count is None`。
6. 验证逐题时长总和不超过 `session_duration_seconds * 1000 + 1000`。
7. 把每行 `capture_version` 固定为 `active_response_v1`。
8. 从逐题结果重算 `accuracy_rate`、`error_count`、`completed_units` 和 `correct_units`。

`semantic_game_payload_fingerprint` 使用 `json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` 生成稳定 JSON，再返回 `hashlib.sha256(serialized.encode("utf-8")).hexdigest()`。指纹输入包含项目患者、处方动作、训练日期、状态、实际时长、得分、备注、去除派生汇总与三个传输字段后的 `form_data`、标准化逐题行；不得包含数据库 ID、创建时间或传输重试次数。

- [ ] **Step 4: 运行领域测试**

Run: `cd backend && pytest apps/training/tests/test_game_questions.py -q`

Expected: 全部 PASS。

- [ ] **Step 5: 提交领域规则任务**

```bash
git add backend/apps/training/game_questions.py backend/apps/training/tests/test_game_questions.py
git commit -m "feat(游戏统计): 校验逐题数据与语义指纹"
```

---

### Task 3: 事务保存、幂等重传与两个训练写入入口

**Files:**
- Modify: `backend/apps/training/services.py`
- Modify: `backend/apps/training/serializers.py`
- Modify: `backend/apps/training/views.py`
- Modify: `backend/apps/patient_app/serializers.py`
- Modify: `backend/apps/patient_app/views.py`
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py`
- Modify: `backend/apps/training/tests/test_training_current_prescription.py`

**Interfaces:**
- Consumes: Task 1 模型、Task 2 `normalize_new_question_results` 与 `semantic_game_payload_fingerprint`。
- Produces: `TrainingRecordCreateResult(record: TrainingRecord, created: bool)`、`create_training_record_with_result(project_patient, training_date, prescription_action, client_session_id, question_results, **fields)`；患者端和医生端首次创建返回 `201`，幂等命中返回 `200`。

- [ ] **Step 1: 写患者端失败测试**

在 `test_patient_app_api.py` 增加：

```python
@pytest.mark.django_db
def test_patient_app_creates_game_questions_atomically(
    project_patient,
    doctor,
    active_prescription,
):
    action = active_prescription.actions.get(
        action_library_item__source_key="game-executive-inhibition"
    )
    payload = valid_game_payload(action)
    payload["client_session_id"] = "8cf99c30-9b03-4bda-b4d3-b492f3a2db12"
    payload["question_results"] = [
        {
            "question_index": 1,
            "game_code": "game-executive-inhibition",
            "difficulty": "中等",
            "response_duration_ms": 2380,
            "is_correct": True,
            "result_type": "answered",
            "swap_count": None,
        }
    ]

    response = _auth_client(project_patient, doctor).post(
        "/api/patient-app/training-records/",
        payload,
        format="json",
    )

    assert response.status_code == 201
    record = TrainingRecord.objects.get(pk=response.data["id"])
    assert record.game_question_results.get().response_duration_ms == 2380
```

再增加五个独立测试：相同 UUID 同内容返回 `200` 且只有一条记录；仅改变重试元数据仍返回 `200`；改变逐题正确性返回 `409`；第二题非法时训练记录与第一题都不存在；两个并发请求使用同一 UUID 和相同内容时最终只创建一条训练记录并都取得同一记录 ID。并发测试沿用仓库现有 `TransactionTestCase + threading.Barrier + close_old_connections()` 模式。

- [ ] **Step 2: 运行写入测试确认失败**

Run: `cd backend && pytest apps/patient_app/tests/test_patient_app_api.py -q -k "game_questions or client_session"`

Expected: FAIL，serializer 忽略新字段或接口仍重复创建记录。

- [ ] **Step 3: 增加共享逐题 serializer**

在 `backend/apps/training/serializers.py` 定义：

```python
class GameQuestionResultInputSerializer(serializers.Serializer):
    question_index = serializers.IntegerField(min_value=1)
    game_code = serializers.CharField(max_length=80)
    difficulty = serializers.CharField(max_length=40)
    response_duration_ms = serializers.IntegerField(min_value=0, max_value=3_600_000)
    is_correct = serializers.BooleanField()
    result_type = serializers.ChoiceField(choices=["answered", "timeout"])
    swap_count = serializers.IntegerField(required=False, allow_null=True, min_value=0)
```

在两个 create serializer 中增加可选 `client_session_id = serializers.UUIDField(required=False, allow_null=True)` 和 `question_results = GameQuestionResultInputSerializer(many=True, required=False, max_length=2000)`。`TrainingRecordSerializer` 只返回 `client_session_id`，不要嵌套返回所有逐题数据。

- [ ] **Step 4: 实现事务服务与并发幂等收口**

在 `services.py` 增加：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TrainingRecordCreateResult:
    record: TrainingRecord
    created: bool
```

实现 `create_training_record_with_result(project_patient, training_date, prescription_action=None, client_session_id=None, question_results=None, **fields) -> TrainingRecordCreateResult`：

1. 保留现有项目开放、active 处方和动作归属校验。
2. 新逐题字段存在时调用 Task 2 标准化并重算 `form_data`。
3. 计算语义指纹。
4. UUID 已存在时比较 `client_payload_fingerprint`；相同返回 `created=False`，不同抛出专用 `GameSessionConflict`。
5. 新建路径使用 `transaction.atomic()` 创建 `TrainingRecord`，再 `bulk_create([GameQuestionResult(training_record=record, **row) for row in normalized.rows])`。
6. 唯一约束并发冲突使用内层 savepoint 捕获 `IntegrityError`，随后重新读取 UUID 并执行同样指纹判断。
7. 现有 `create_training_record(project_patient, training_date, prescription_action=None, **fields)` 继续返回 `.record`，保证旧调用方签名不变。

- [ ] **Step 5: 更新两个 View 的响应状态和冲突码**

患者端和医生端调用 `create_training_record_with_result`；响应规则统一：

```python
result = create_training_record_with_result(**serializer.validated_data)
return Response(
    TrainingRecordSerializer(result.record).data,
    status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
)
```

捕获 `GameSessionConflict` 时返回 `{"detail": "游戏会话标识已用于不同训练内容"}` 和 `409`。原有 Django/DRF validation 仍返回 `400`。

- [ ] **Step 6: 运行写入和现有处方测试**

Run: `cd backend && pytest apps/patient_app/tests/test_patient_app_api.py apps/training/tests/test_training_current_prescription.py -q`

Expected: 全部 PASS，原有多次同日训练测试仍允许无 UUID 的旧 payload 创建多条记录。

- [ ] **Step 7: 提交写入任务**

```bash
git add backend/apps/training/services.py backend/apps/training/serializers.py backend/apps/training/views.py backend/apps/patient_app/serializers.py backend/apps/patient_app/views.py backend/apps/patient_app/tests/test_patient_app_api.py backend/apps/training/tests/test_training_current_prescription.py
git commit -m "feat(游戏统计): 幂等保存整场逐题结果"
```

---

### Task 4: 兼容旧 `raw_detail.rounds` 并迁移历史数据

**Files:**
- Modify: `backend/apps/training/game_questions.py`
- Modify: `backend/apps/training/services.py`
- Create: `backend/apps/training/migrations/0015_backfill_game_question_results.py`
- Create: `backend/apps/training/tests/test_game_question_backfill_migration.py`
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py`

**Interfaces:**
- Consumes: 旧 `TrainingRecord.form_data.raw_detail.rounds`。
- Produces: `parse_legacy_rounds(prescription_action, form_data) -> Sequence[dict[str, object]]`；旧客户端写入和 migration 使用相同字段口径，但 migration 内保留自包含解析代码。

- [ ] **Step 1: 写旧客户端和 migration 失败测试**

旧客户端 API 测试提交没有顶层 `question_results` 的合法 `rounds`，断言整场 `201` 且创建 `capture_version=legacy_wall_clock_v0` 的题目；非法题目不阻塞整场创建且不产生对应子记录。

MigrationExecutor 测试从 `0014_game_question_results` 迁到 `0015_backfill_game_question_results`：

```python
@pytest.mark.django_db(transaction=True)
def test_backfill_converts_valid_rounds_and_preserves_form_data(migrator):
    old_apps = migrator.migrate(("training", "0014_game_question_results"))
    record = create_historical_game_record(
        old_apps,
        rounds=[
            {"round_index": 1, "response_ms": 2100, "correct": True},
            {"round_index": 2, "response_ms": 5000, "correct": False, "result": "timeout"},
            {"round_index": 3, "response_ms": "bad", "correct": True},
        ],
    )

    new_apps = migrator.migrate(("training", "0015_backfill_game_question_results"))
    TrainingRecord = new_apps.get_model("training", "TrainingRecord")
    GameQuestionResult = new_apps.get_model("training", "GameQuestionResult")

    assert GameQuestionResult.objects.filter(training_record_id=record.id).count() == 2
    assert TrainingRecord.objects.get(pk=record.id).form_data["raw_detail"]["rounds"][2]["response_ms"] == "bad"
```

- [ ] **Step 2: 运行兼容测试确认失败**

Run: `cd backend && pytest apps/training/tests/test_game_question_backfill_migration.py apps/patient_app/tests/test_patient_app_api.py -q -k "legacy_rounds or backfill"`

Expected: FAIL，历史迁移不存在且旧写入没有子记录。

- [ ] **Step 3: 实现运行时旧 rounds 解析**

`parse_legacy_rounds` 只接受：正整数且唯一的 `round_index`、非负整数 `response_ms`、布尔 `correct`。游戏编码依次取题目 `game_code`、整场 `raw_detail.game_code`、处方动作 `source_key`；难度依次取题目 `difficulty` 和整场 `form_data.difficulty`。`result == "timeout"` 映射为 timeout，其余映射 answered；历史拼图 `swap_count` 固定为空；所有行标记 `legacy_wall_clock_v0`。

当顶层 `question_results` 缺失时，`services.py` 调用旧解析器。旧题异常只跳过该题，不让整场失败；顶层字段存在时禁止同时解析旧 `rounds`。

- [ ] **Step 4: 实现自包含数据 migration**

`0015_backfill_game_question_results.py` 必须使用 `apps.get_model`，不得导入运行时代码。按主键分块迭代游戏记录，为没有任何逐题子记录的训练批量创建合法历史题；每批 `bulk_create`，`reverse_code=migrations.RunPython.noop`。原 `form_data` 不执行 save。

- [ ] **Step 5: 运行 migration、兼容和漂移测试**

Run: `cd backend && pytest apps/training/tests/test_game_question_backfill_migration.py apps/patient_app/tests/test_patient_app_api.py -q -k "legacy_rounds or backfill" && python manage.py makemigrations --check`

Expected: 全部 PASS；`No changes detected`。

- [ ] **Step 6: 提交兼容迁移任务**

```bash
git add backend/apps/training/game_questions.py backend/apps/training/services.py backend/apps/training/migrations/0015_backfill_game_question_results.py backend/apps/training/tests/test_game_question_backfill_migration.py backend/apps/patient_app/tests/test_patient_app_api.py
git commit -m "feat(游戏统计): 迁移历史逐题明细"
```

---

### Task 5: 提供长期统计和单场分页接口

**Files:**
- Create: `backend/apps/training/game_question_tracking.py`
- Modify: `backend/apps/training/tracking_views.py`
- Modify: `backend/apps/training/urls.py`
- Modify: `backend/apps/training/tests/test_tracking_api.py`

**Interfaces:**
- Consumes: `GameQuestionResult`、`accessible_project_patients(user)`、患者 ID、项目患者 ID、日期和筛选参数。
- Produces: `game_question_statistics(user, patient_id, project_patient_id, range_value, start_date, end_date, game_code, difficulty) -> dict`、`game_question_page(user, training_record_id, page, page_size) -> dict`；GET 统计接口和 GET 单场明细接口。

- [ ] **Step 1: 写统计与权限失败测试**

在 `test_tracking_api.py` 建立两个非拼图游戏和一个拼图的逐题夹具，断言：

```python
response = _client(doctor).get(
    f"/api/training/tracking/patients/{project_patient.patient_id}/game-questions/",
    {"project_patient": project_patient.id, "range": "30d"},
)

assert response.status_code == 200
assert response.data["summary"] == {
    "completed_question_count": 4,
    "accuracy_rate": 66.67,
    "average_response_duration_ms": 3000.0,
    "median_response_duration_ms": 3000.0,
    "legacy_question_count": 1,
}
assert response.data["puzzle_summary"]["completed_puzzle_count"] == 1
assert response.data["puzzle_summary"]["average_swap_count"] == 4.0
```

同时覆盖：近 7 天、近 30 天、自定义 `start_date/end_date`、开始晚于结束返回 `400`、游戏/难度筛选、拼图不进入综合正确率、单场分页默认 50/最大 200、不可访问患者返回 `404`、非游戏记录明细返回 `404`。

- [ ] **Step 2: 运行统计测试确认路由不存在**

Run: `cd backend && pytest apps/training/tests/test_tracking_api.py -q -k "game_question"`

Expected: FAIL，接口返回 `404`。

- [ ] **Step 3: 实现统计服务**

`game_question_tracking.py` 定义两个公开函数：

- `game_question_statistics(user, *, patient_id: int, project_patient_id: int, range_value: str | None = None, start_date: date | None = None, end_date: date | None = None, game_code: str = "", difficulty: str = "") -> dict`
- `game_question_page(user, *, training_record_id: int, page: int = 1, page_size: int = 50) -> dict`

实现时先用 `accessible_project_patients(user)` 锁定患者与 `project_patient_id`，再查询逐题。日期解释固定为：`7d` 包含今天共 7 个自然日，`30d` 包含今天共 30 个自然日，自定义范围两端均包含。平均值保留两位小数；中位数使用 `statistics.median` 后保留两位小数；正确率分母排除拼图，超时题保留在分母且算错误。

返回结构固定为：

```python
{
    "filters": {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "game_code": "", "difficulty": ""},
    "options": {
        "games": [
            {"game_code": "game-executive-inhibition", "game_name": "反应抑制能力训练"}
        ],
        "difficulties": ["简单", "中等", "困难"],
    },
    "summary": {
        "completed_question_count": 0,
        "accuracy_rate": None,
        "average_response_duration_ms": None,
        "median_response_duration_ms": None,
        "legacy_question_count": 0,
    },
    "by_game": [
        {
            "game_code": "game-executive-inhibition",
            "game_name": "反应抑制能力训练",
            "training_record_count": 0,
            "completed_question_count": 0,
            "accuracy_rate": None,
            "average_response_duration_ms": None,
            "median_response_duration_ms": None,
            "average_swap_count": None,
        }
    ],
    "trend": [
        {
            "date": "YYYY-MM-DD",
            "completed_question_count": 0,
            "accuracy_rate": None,
            "median_response_duration_ms": None,
            "median_swap_count": None,
        }
    ],
    "puzzle_summary": {
        "completed_puzzle_count": 0,
        "average_response_duration_ms": None,
        "median_response_duration_ms": None,
        "average_swap_count": None,
    },
}
```

`options` 只受项目患者和日期范围影响，不受当前游戏/难度筛选影响，确保用户切换筛选后选项不会消失。`trend` 仅在指定 `game_code` 时按 `training_date` 返回；未指定时为空数组。拼图趋势的 `accuracy_rate` 为 `None`，额外返回 `median_swap_count`。

- [ ] **Step 4: 实现 APIView 与路由**

新增：

```text
GET /api/training/tracking/patients/{patient_id}/game-questions/
GET /api/training/tracking/records/{training_record_id}/game-questions/
```

两个 View 使用 `IsAdminOrDoctor`。统计 View 校验 `project_patient` 必填正整数，以及 `range` 与自定义日期二选一；明细 View 把 `page/page_size` 转换为正整数并把 `page_size` 限制到 200。参数错误统一返回 `400`，越权和不存在统一返回 `404`。

- [ ] **Step 5: 运行统计接口和完整 tracking 测试**

Run: `cd backend && pytest apps/training/tests/test_tracking_api.py -q`

Expected: 全部 PASS，现有训练追踪详情响应结构未被破坏。

- [ ] **Step 6: 提交查询任务**

```bash
git add backend/apps/training/game_question_tracking.py backend/apps/training/tracking_views.py backend/apps/training/urls.py backend/apps/training/tests/test_tracking_api.py
git commit -m "feat(游戏统计): 提供逐题趋势与明细接口"
```

---

### Task 6: 建立小程序有效作答计时与逐题采集状态机

**Files:**
- Create: `miniapp/src/pages/game-session/questionCapture.ts`
- Create: `miniapp/src/pages/game-session/questionCapture.test.ts`
- Modify: `miniapp/src/pages/game-session/gameTypes.ts`

**Interfaces:**
- Consumes: 六个 `GameCode`、`GameDifficulty` 和注入的 `now: () => number`。
- Produces: `GameQuestionResult`、`createQuestionCapture(now?) -> QuestionCapture`；页面只通过该状态机管理当前题和已完成列表。

- [ ] **Step 1: 写计时与六游戏失败测试**

核心测试：

```typescript
it('excludes paused time and numbers only completed questions', () => {
  let now = 1_000
  const capture = createQuestionCapture(() => now)

  capture.begin('game-executive-inhibition', '中等')
  now = 2_000
  capture.pause()
  now = 12_000
  capture.resume()
  now = 13_500
  capture.complete(true)

  expect(capture.results()).toEqual([
    {
      question_index: 1,
      game_code: 'game-executive-inhibition',
      difficulty: '中等',
      response_duration_ms: 2_500,
      is_correct: true,
      result_type: 'answered',
      swap_count: null,
    },
  ])
})

it.each(ALL_GAME_CODES)('captures a completed unit for %s', (gameCode) => {
  const capture = createQuestionCapture(() => 100)
  capture.begin(gameCode, '简单')
  if (gameCode === 'game-audiovisual-puzzle') capture.recordPuzzleSwap()
  capture.complete(true)
  expect(capture.results()).toHaveLength(1)
})
```

另测：`timeout()` 生成错误题、`discard()` 不生成题且下一题仍编号 1、重复 finish 无效、暂停期间不能累计交换、同方块无交换由页面不调用状态机、拼图保存准确 `swap_count`、非拼图交换调用抛出错误。

- [ ] **Step 2: 运行计时测试确认模块不存在**

Run: `cd miniapp && npm run test -- src/pages/game-session/questionCapture.test.ts`

Expected: FAIL，找不到 `questionCapture`。

- [ ] **Step 3: 定义 payload 类型**

在 `gameTypes.ts` 增加：

```typescript
export type GameQuestionResultType = 'answered' | 'timeout'

export type GameQuestionResult = {
  question_index: number
  game_code: GameCode
  difficulty: GameDifficulty
  response_duration_ms: number
  is_correct: boolean
  result_type: GameQuestionResultType
  swap_count: number | null
}
```

`GameTrainingPayload` 增加必填 `client_session_id: string` 和 `question_results: GameQuestionResult[]`。新版类型移除 `raw_detail.rounds`；整场摘要字段保留。

- [ ] **Step 4: 实现纯状态机**

`QuestionCapture` 公共接口固定为：

```typescript
export type QuestionCapture = {
  begin: (gameCode: GameCode, difficulty: GameDifficulty) => void
  pause: () => void
  resume: () => void
  recordPuzzleSwap: () => void
  complete: (isCorrect: boolean) => void
  timeout: () => void
  discard: () => void
  resetSession: () => void
  results: () => GameQuestionResult[]
}
```

内部只在 `complete/timeout` 时分配 `question_index = results.length + 1`。`pause` 把本段 `now - activeStartedAt` 加入累计值；`resume` 重新设置 active 起点；`discard` 清除当前题；返回结果时复制数组，禁止调用方修改内部状态。

- [ ] **Step 5: 运行状态机测试**

Run: `cd miniapp && npm run test -- src/pages/game-session/questionCapture.test.ts`

Expected: 全部 PASS。

- [ ] **Step 6: 提交状态机任务**

```bash
git add miniapp/src/pages/game-session/questionCapture.ts miniapp/src/pages/game-session/questionCapture.test.ts miniapp/src/pages/game-session/gameTypes.ts
git commit -m "feat(小程序): 建立游戏逐题有效计时"
```

---

### Task 7: 将六款游戏和拼图交换接入逐题采集

**Files:**
- Modify: `miniapp/src/pages/game-session/index.tsx`
- Modify: `miniapp/src/pages/game-session/puzzle.ts`
- Modify: `miniapp/src/pages/game-session/puzzle.test.ts`
- Create: `miniapp/src/pages/game-session/questionCaptureIntegration.test.ts`

**Interfaces:**
- Consumes: Task 6 `createQuestionCapture`。
- Produces: 六个明确计时起点、暂停/恢复、完成/超时/丢弃调用；拼图 `swapPuzzleTiles` 返回是否实际交换的信息。

- [ ] **Step 1: 写拼图交换和接入映射失败测试**

把拼图交换函数改为可判定真实交换：

```typescript
expect(swapPuzzleTiles(tiles, 'puzzle-tile-0', 'puzzle-tile-1')).toMatchObject({
  swapped: true,
})
expect(swapPuzzleTiles(tiles, 'puzzle-tile-0', 'puzzle-tile-0')).toEqual({
  tiles,
  swapped: false,
})
```

`questionCaptureIntegration.test.ts` 用导出的纯映射 helper 断言六款游戏计时起点：颜色/图案为 `reveal-complete`，抑制/分类为 `round-rendered`，声音为 `target-audio-complete`，拼图为 `preview-complete`。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd miniapp && npm run test -- src/pages/game-session/puzzle.test.ts src/pages/game-session/questionCaptureIntegration.test.ts`

Expected: FAIL，交换函数仍只返回数组且计时节点 helper 不存在。

- [ ] **Step 3: 接入准确的题目生命周期**

在页面创建单一 `questionCaptureRef`，删除 `roundStartedAtRef` 和 `responseMs()`。以下节点调用 `begin`：

- `startColorRevealTimer` 完成回调。
- `startPatternRevealTimer` 完成回调。
- `startInhibitionRound` 设置当前题后、启动 timeout 前。
- `startCategoryRound` 设置当前题后、启动 timeout 前。
- `autoPreviewSoundRound` 的目标声音 `await playAudioSrc(latestRound.target.audioSrc)` 完成且 run 仍有效后。
- `startPuzzlePreviewTimer` 完成回调。

所有正确/错误选择分支调用 `complete(attempt.correct)`；`handleRoundTimeout` 调用 `timeout()`；`pauseGame/resumeGame` 调用 `pause()/resume()`；`endSession` 在读取结果前调用 `discard()`；`resetSessionState` 调用 `resetSession()`。

- [ ] **Step 4: 接入拼图实际交换次数**

将 `swapPuzzleTiles` 返回值改为：

```typescript
export type PuzzleSwapResult = {
  tiles: PuzzleTile[]
  swapped: boolean
}
```

只有 `swapped === true` 时页面调用 `questionCaptureRef.current.recordPuzzleSwap()`。拼图完成时调用 `complete(true)`，整场结束未完成时只 discard。

- [ ] **Step 5: 运行游戏页相关测试**

Run: `cd miniapp && npm run test -- src/pages/game-session`

Expected: 全部 PASS，六个现有玩法单测不因交换返回类型变化而失败。

- [ ] **Step 6: 提交游戏接入任务**

```bash
git add miniapp/src/pages/game-session/index.tsx miniapp/src/pages/game-session/puzzle.ts miniapp/src/pages/game-session/puzzle.test.ts miniapp/src/pages/game-session/questionCaptureIntegration.test.ts
git commit -m "feat(小程序): 采集六款游戏逐题表现"
```

---

### Task 8: 加入会话 UUID、整场 payload 和补传兼容

**Files:**
- Create: `miniapp/src/utils/clientSessionId.ts`
- Create: `miniapp/src/utils/clientSessionId.test.ts`
- Modify: `miniapp/src/features/motion-training/session.ts`
- Modify: `miniapp/src/pages/game-session/index.tsx`
- Modify: `miniapp/src/pages/game-session/retryUpload.ts`
- Modify: `miniapp/src/pages/game-session/retryUpload.test.ts`
- Modify: `miniapp/src/pages/game-session/scoring.test.ts`

**Interfaces:**
- Consumes: Task 6 `GameTrainingPayload`、Task 7 页面采集结果。
- Produces: `createClientSessionId(random?) -> string`、完整缓存与重传 payload；录像训练继续通过原导出名使用相同 UUID helper。

- [ ] **Step 1: 写 UUID 和补传失败测试**

```typescript
it('creates a stable UUID v4 from injected random values', () => {
  const id = createClientSessionId(() => 0)
  expect(id).toBe('00000000-0000-4000-8000-000000000000')
  expect(isClientSessionId(id)).toBe(true)
})

it('preserves client session and questions while adding retry metadata', async () => {
  const pending = savePendingGameUpload(storage, payloadWithQuestions, 1000)
  await tryUploadPendingGameRecord(storage, 1000, uploader)
  expect(uploader).toHaveBeenCalledWith(expect.objectContaining({
    client_session_id: payloadWithQuestions.client_session_id,
    question_results: payloadWithQuestions.question_results,
  }))
})
```

再增加旧缓存安全处理测试：缺少 UUID 或 `question_results` 的旧待补传结构仍按现有类型守卫判为无效并返回 `null`，不得发送不满足新版契约的半升级 payload。

- [ ] **Step 2: 运行 UUID/补传测试确认失败**

Run: `cd miniapp && npm run test -- src/utils/clientSessionId.test.ts src/pages/game-session/retryUpload.test.ts src/pages/game-session/scoring.test.ts`

Expected: FAIL，通用 helper 不存在且 payload 类型缺字段。

- [ ] **Step 3: 抽取通用 UUID helper并保留录像兼容导出**

`clientSessionId.ts` 导出：

```typescript
export const CLIENT_SESSION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export function isClientSessionId(value: unknown): value is string {
  return typeof value === 'string' && CLIENT_SESSION_ID_PATTERN.test(value)
}

export function createClientSessionId(random: () => number = Math.random): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (marker) => {
    const value = marker === 'x' ? Math.floor(random() * 16) : Math.floor(random() * 4) + 8
    return value.toString(16)
  })
}
```

`motion-training/session.ts` 改为导入并 `export { createClientSessionId }`，保持现有测试和调用方的公开 API 不变。

- [ ] **Step 4: 在整场开始时生成一次 UUID并构建新版 payload**

页面在每次 `resetSessionState` 后、真正开始新 intro 前生成一个 UUID 存入 ref；暂停、恢复和补传期间不重新生成。`endSession` 顶层写入 `client_session_id` 和 `question_results: questionCapture.results()`，停止向 `raw_detail.rounds` 写逐题数组。

- [ ] **Step 5: 扩展缓存类型守卫和补传**

`retryUpload.ts` 必须验证 UUID v4、逐题数组、连续题号和核心字段基本类型。`payloadForRetry` 只能修改三个 `raw_detail` 传输字段，必须保持 UUID 和逐题数组原样。HTTP `200` 和 `201` 均视为成功。

- [ ] **Step 6: 运行小程序游戏与录像相关测试**

Run: `cd miniapp && npm run test -- src/utils/clientSessionId.test.ts src/pages/game-session src/features/motion-training/session.test.ts`

Expected: 全部 PASS，录像训练现有 UUID 行为不变。

- [ ] **Step 7: 提交上传任务**

```bash
git add miniapp/src/utils/clientSessionId.ts miniapp/src/utils/clientSessionId.test.ts miniapp/src/features/motion-training/session.ts miniapp/src/pages/game-session/index.tsx miniapp/src/pages/game-session/retryUpload.ts miniapp/src/pages/game-session/retryUpload.test.ts miniapp/src/pages/game-session/scoring.test.ts
git commit -m "feat(小程序): 幂等上传游戏逐题结果"
```

---

### Task 9: 实现医生端长期统计面板

**Files:**
- Modify: `frontend/src/pages/training-tracking/types.ts`
- Create: `frontend/src/pages/training-tracking/gameQuestionAnalyticsChartConfig.ts`
- Create: `frontend/src/pages/training-tracking/gameQuestionAnalyticsChartConfig.test.ts`
- Create: `frontend/src/pages/training-tracking/GameQuestionAnalyticsPanel.tsx`
- Create: `frontend/src/pages/training-tracking/GameQuestionAnalyticsPanel.test.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`

**Interfaces:**
- Consumes: Task 5 统计接口、当前 `patientId` 和 `selectedProjectPatientId`。
- Produces: `<GameQuestionAnalyticsPanel patientId projectPatientId />`；不改变现有详情 queryKey。

- [ ] **Step 1: 定义 API 类型并写图表纯函数失败测试**

在 `types.ts` 增加 `GameQuestionStatisticsResponse`、`GameQuestionByGameRow`、`GameQuestionTrendPoint`、`PuzzleQuestionSummary`。图表测试断言：正确率使用左轴百分比，中位时长转换为秒并使用右轴，拼图正确率为 null 时不伪造 0%。

```typescript
expect(buildGameQuestionTrendData([
  { date: '2026-08-20', completed_question_count: 4, accuracy_rate: 75, median_response_duration_ms: 2500, median_swap_count: null },
])).toEqual([
  { date: '08-20', accuracy_rate: 75, median_response_seconds: 2.5 },
])
```

- [ ] **Step 2: 运行图表测试确认失败**

Run: `cd frontend && npm run test -- src/pages/training-tracking/gameQuestionAnalyticsChartConfig.test.ts`

Expected: FAIL，模块和类型不存在。

- [ ] **Step 3: 实现统计面板组件测试**

组件测试 mock 独立接口并覆盖：默认请求 `range=30d`；点击近 7 天发送 `range=7d`；选择自定义日期发送 `start_date/end_date` 且不发送 range；游戏与难度筛选进入 queryKey；展示完成题数、正确率、平均/中位时长；拼图显示交换次数和“无需统计”；`legacy_question_count > 0` 时显示“部分历史时长为估算值”；接口失败显示局部重试，不影响页面其他文本。

- [ ] **Step 4: 实现统计面板**

组件 props：

```typescript
type GameQuestionAnalyticsPanelProps = {
  patientId: number
  projectPatientId: number
}
```

使用独立 queryKey：

```typescript
[
  'training-tracking',
  'game-questions',
  patientId,
  projectPatientId,
  filters,
]
```

游戏和难度下拉选项只读取响应的 `options.games/options.difficulties`，不得从当前已筛选的 `by_game` 反推。UI 使用 `Segmented`（7 天/30 天/自定义）、`DatePicker.RangePicker`、游戏 `Select`、难度 `Select`、四个 `Statistic`、分游戏 `Table` 和 `DualAxes`。选择“全部游戏”时不展示趋势图并提示“选择一个游戏查看逐日趋势”；选择具体游戏后用接口 `trend` 渲染。只要 `summary.legacy_question_count > 0`，汇总区下方显示“部分历史时长为估算值，可能包含旧版暂停时间”。

- [ ] **Step 5: 在训练追踪页替换旧游戏摘要卡**

保留现有详情返回的 `game_summary` 兼容字段，但页面的“游戏表现统计”区域改渲染 `GameQuestionAnalyticsPanel`。只有 `selected_project_patient` 存在时启用查询；切换患者或项目时组件 queryKey 必须隔离旧响应。

- [ ] **Step 6: 运行统计组件和详情页测试**

Run: `cd frontend && npm run test -- src/pages/training-tracking/gameQuestionAnalyticsChartConfig.test.ts src/pages/training-tracking/GameQuestionAnalyticsPanel.test.tsx src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`

Expected: 全部 PASS；更新详情页旧“平均得分/总错误次数”断言为新版逐题指标断言。

- [ ] **Step 7: 提交长期统计面板**

```bash
git add frontend/src/pages/training-tracking/types.ts frontend/src/pages/training-tracking/gameQuestionAnalyticsChartConfig.ts frontend/src/pages/training-tracking/gameQuestionAnalyticsChartConfig.test.ts frontend/src/pages/training-tracking/GameQuestionAnalyticsPanel.tsx frontend/src/pages/training-tracking/GameQuestionAnalyticsPanel.test.tsx frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
git commit -m "feat(医生端): 展示游戏逐题长期趋势"
```

---

### Task 10: 实现单场逐题明细抽屉

**Files:**
- Modify: `frontend/src/pages/training-tracking/types.ts`
- Create: `frontend/src/pages/training-tracking/GameQuestionDetailDrawer.tsx`
- Create: `frontend/src/pages/training-tracking/GameQuestionDetailDrawer.test.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`

**Interfaces:**
- Consumes: Task 5 单场分页接口、`TrackingRecentRecord`。
- Produces: `<GameQuestionDetailDrawer record onClose />`，仅在打开时请求当前训练记录的题目页。

- [ ] **Step 1: 写抽屉失败测试**

测试覆盖：关闭状态不请求；打开游戏记录请求第一页；正确/错误/超时标签；毫秒格式化为秒；拼图显示交换次数；历史 `capture_version` 显示“历史估算”；空结果显示“该场训练暂无逐题明细”；错误状态提供重试；翻页发送 `page/page_size`。

```typescript
fireEvent.click(screen.getByRole('button', { name: '查看逐题' }))
expect(await screen.findByText('第 1 题')).toBeInTheDocument()
expect(screen.getByText('2.38 秒')).toBeInTheDocument()
expect(screen.getByText('历史估算')).toBeInTheDocument()
```

- [ ] **Step 2: 运行抽屉测试确认失败**

Run: `cd frontend && npm run test -- src/pages/training-tracking/GameQuestionDetailDrawer.test.tsx`

Expected: FAIL，组件不存在。

- [ ] **Step 3: 实现分页类型和抽屉**

类型固定为：

```typescript
export type GameQuestionDetailRow = {
  id: number
  question_index: number
  game_code: string
  difficulty: string
  response_duration_ms: number
  is_correct: boolean
  result_type: 'answered' | 'timeout'
  swap_count: number | null
  capture_version: 'legacy_wall_clock_v0' | 'active_response_v1'
}

export type GameQuestionDetailPage = {
  count: number
  page: number
  page_size: number
  results: GameQuestionDetailRow[]
}
```

抽屉 queryKey 为 `['training-record', record.id, 'game-questions', page, pageSize]`，`enabled` 只在 `record !== null`。关闭时把页码重置为 1。表格题号显示“第 N 题”，`timeout` 优先显示“超时”，其余按正确布尔值显示；交换次数为空显示 `—`。

- [ ] **Step 4: 在最近训练记录增加操作入口**

新增独立“逐题明细”列。只有 `internal_type === 'game'` 时显示 aria-label 为“查看逐题”的按钮；运动记录显示 `—`。逐题抽屉状态与现有视频抽屉使用不同 state，互不复用下载和分析逻辑。

- [ ] **Step 5: 运行抽屉与详情页测试**

Run: `cd frontend && npm run test -- src/pages/training-tracking/GameQuestionDetailDrawer.test.tsx src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`

Expected: 全部 PASS；运动记录没有“查看逐题”按钮，游戏记录可以打开抽屉。

- [ ] **Step 6: 提交单场明细任务**

```bash
git add frontend/src/pages/training-tracking/types.ts frontend/src/pages/training-tracking/GameQuestionDetailDrawer.tsx frontend/src/pages/training-tracking/GameQuestionDetailDrawer.test.tsx frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
git commit -m "feat(医生端): 查看单场游戏逐题明细"
```

---

### Task 11: 全量验证、迁移演练与计划收口

**Files:**
- Modify: `docs/superpowers/plans/2026-08-21-game-question-analytics.md`
- Modify: `docs/superpowers/specs/2026-08-21-game-question-analytics-design.md`
- Modify: `docs/superpowers/README.md`

**Interfaces:**
- Consumes: Task 1-10 的全部实现和测试。
- Produces: 可发布验证证据、已实施 spec/plan 状态和执行记录。

- [ ] **Step 1: 运行后端全量测试与 schema 检查**

Run: `cd backend && pytest && python manage.py makemigrations --check`

Expected: 全部 PASS；`No changes detected`。

- [ ] **Step 2: 在迁移前后核对历史数据数量**

在测试/预发布数据库先执行只读统计：

```bash
cd backend
python manage.py shell -c "from apps.training.models import TrainingRecord; print(TrainingRecord.objects.filter(prescription_action__internal_type_snapshot='game', form_data__raw_detail__has_key='rounds').count())"
python manage.py migrate
python manage.py shell -c "from apps.training.models import GameQuestionResult; print(GameQuestionResult.objects.filter(capture_version='legacy_wall_clock_v0').count())"
```

Expected: migration 成功；第二个数量大于等于 0。人工抽查至少一条合法历史记录的题号、耗时和正确性，确认原 `form_data.raw_detail.rounds` 未改变。

- [ ] **Step 3: 运行小程序全量测试与微信构建**

Run: `cd miniapp && npm run test && npm run build:weapp`

Expected: 全部 PASS；Taro 微信构建成功，无 TypeScript 错误。

- [ ] **Step 4: 运行医生端全量测试、lint 和构建**

Run: `cd frontend && npm run test && npm run lint && npm run build`

Expected: 全部 PASS，无 ESLint 或 TypeScript 错误。

- [ ] **Step 5: 按发布顺序完成手工烟测**

依次验证：

1. 旧版 payload 没有 UUID 和顶层逐题数组仍能创建训练。
2. 新版 payload 首次返回 `201`，同 UUID 补传返回 `200` 且数据库只一场。
3. 六款游戏各完成至少一题，暂停 5 秒后逐题有效时长不增加 5 秒。
4. 拼图完成后交换次数等于实际交换操作数。
5. 医生端近 7 天、近 30 天、自定义日期、游戏、难度筛选返回正确数据。
6. 单场抽屉显示逐题结果；无明细旧场次显示空状态。
7. 无权限医生无法通过猜测训练记录 ID 读取明细。

- [ ] **Step 6: 更新 spec、plan 和索引状态**

全部验证通过后：

- spec 状态从 `approved` 改为 `implemented`，写入实施基线 commit。
- plan 顶部增加 `执行记录（2026-08-21, codex）：Task 1-11 已落地于 commit <short-sha>`，并勾选所有任务步骤。
- `docs/superpowers/README.md` 中 spec 和 plan 状态改为 `implemented`。

- [ ] **Step 7: 提交验证收口**

```bash
git add docs/superpowers/plans/2026-08-21-game-question-analytics.md docs/superpowers/specs/2026-08-21-game-question-analytics-design.md docs/superpowers/README.md
git commit -m "docs(游戏统计): 回填逐题统计实施检查点"
```

---

## 执行依赖顺序

```text
Task 1 模型
  -> Task 2 领域规则
  -> Task 3 事务写入
  -> Task 4 历史兼容迁移
  -> Task 5 查询接口
  -> Task 6 小程序状态机
  -> Task 7 六游戏接入
  -> Task 8 UUID 与补传
  -> Task 9 长期统计面板
  -> Task 10 单场明细抽屉
  -> Task 11 全量验证与收口
```

后端 Task 1-5 必须先于小程序 Task 8 发布。Task 6-8 可以在后端稳定后连续执行；医生端 Task 9-10 依赖 Task 5 的接口契约。执行时每个任务完成后都要先做该任务的测试与代码审查，再进入下一任务。
