# 游戏处方与患者训练追踪 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有处方体系上接入游戏处方闭环，并新增医生端患者训练追踪模块。

**Architecture:** 游戏作为 `ActionLibraryItem.internal_type = game` 的动作库项进入现有版本化处方；小程序游戏结果继续落到 `TrainingRecord`，用 `form_data` 保存通用游戏指标；医生端训练追踪通过 `apps.training` 聚合 API 按选中的 `ProjectPatient` 展示处方完成率、趋势图、游戏表现和最近记录。

**Tech Stack:** Django 5 + DRF + pytest-django；React 18 + TypeScript + Vite + Ant Design 5 + TanStack Query v5 + `@ant-design/charts`；Taro 4 + React + TypeScript。

---

执行记录（2026-05-15, codex）：游戏处方与训练追踪已落地，验证通过。实施 commit：38839e0, e7c4fcd, 55142b7, 17c18e8, 86b988e, 266150d, 321eb00, 3ef50a5, a8fd307, 2f28a9b, 1de66ea, a59d8eb, e440773, 65ff3d3, 0378892

## Execution Notes

- 当前工作区已有用户确认保留的未提交改动：`.gitignore`、`scripts/start_backend.sh`。执行本计划时不要回退、覆盖或顺手格式化这些文件。
- 本计划实现代码时需要按 TDD 执行：先写失败测试，再写实现。
- 所有提交描述使用中文。
- 如果执行过程中遇到已存在的未提交改动，先判断是否与本任务相关；无关则忽略，相关则保留并在现有代码基础上修改。

## File Structure

### Backend

- Create: `backend/apps/prescriptions/migrations/0010_seed_game_actions.py`
  - 幂等写入 6 个游戏动作。
- Create: `backend/apps/prescriptions/tests/test_game_action_library.py`
  - 覆盖游戏动作 seed、动作库过滤和快照字段。
- Create: `backend/apps/training/game_results.py`
  - 游戏类训练结果 `form_data` 基础校验。
- Modify: `backend/apps/patient_app/views.py`
  - 在患者端训练记录提交时处理旧处方动作提示，并调用游戏结果校验。
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py`
  - 覆盖游戏结果回传、非法指标、旧处方动作拒绝。
- Create: `backend/apps/training/tracking.py`
  - 患者训练追踪聚合服务。
- Create: `backend/apps/training/tracking_views.py`
  - 医生端训练追踪 API。
- Modify: `backend/apps/training/urls.py`
  - 挂载 tracking API。
- Create: `backend/apps/training/tests/test_tracking_api.py`
  - 覆盖患者搜索、默认项目、完成率、趋势、权限过滤。

### Doctor Web Frontend

- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
  - 新增 `@ant-design/charts`。
- Modify: `frontend/src/pages/prescriptions/types.ts`
  - 收紧 `internal_type` 类型并支持游戏动作。
- Modify: `frontend/src/pages/prescriptions/PrescriptionPanel.tsx`
  - 加载全部动作库，不再只取运动动作。
- Modify: `frontend/src/pages/prescriptions/PrescriptionDrawer.tsx`
  - 按运动/认知游戏分组展示和提交混合处方。
- Modify: `frontend/src/pages/prescriptions/FixedActionLibraryTab.tsx`
  - 展示训练类型、内部类型和游戏描述。
- Modify: `frontend/src/pages/prescriptions/PrescriptionPanel.test.tsx`
  - 覆盖游戏动作选择和混合处方 payload。
- Create: `frontend/src/pages/training-tracking/types.ts`
- Create: `frontend/src/pages/training-tracking/TrainingTrackingPage.tsx`
- Create: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Create: `frontend/src/pages/training-tracking/TrainingTrackingPage.test.tsx`
- Create: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/layout/AdminLayout.tsx`
- Modify: `frontend/src/app/App.test.tsx`
  - 新增训练追踪路由与侧边栏入口。

### Miniapp

- Modify: `miniapp/src/app.config.ts`
  - 新增 `pages/game-session/index`。
- Modify: `miniapp/src/types/patientApp.ts`
  - 将处方动作 `internal_type` 标明为 `motion | game | video`，保留游戏展示字段。
- Modify: `miniapp/src/pages/prescription/index.tsx`
  - 游戏动作显示“开始游戏”，跳转游戏占位页。
- Create: `miniapp/src/pages/game-session/index.tsx`
  - 游戏模拟完成表单。
- Modify: `miniapp/src/app.scss`
  - 补充游戏页表单样式。

---

### Task 1: Seed Game Action Library

**Files:**
- Create: `backend/apps/prescriptions/tests/test_game_action_library.py`
- Create: `backend/apps/prescriptions/migrations/0010_seed_game_actions.py`

- [x] **Step 1: 写游戏动作库失败测试**

Create `backend/apps/prescriptions/tests/test_game_action_library.py`:

```python
import pytest

from apps.prescriptions.models import ActionLibraryItem, Prescription


@pytest.mark.django_db
def test_game_actions_are_seeded_by_migration():
    actions = ActionLibraryItem.objects.filter(
        internal_type=ActionLibraryItem.InternalType.GAME
    ).order_by("source_key")

    assert actions.count() == 6
    assert list(actions.values_list("source_key", flat=True)) == [
        "game-audiovisual-puzzle",
        "game-audiovisual-sound-discrimination",
        "game-executive-category-switch",
        "game-executive-inhibition",
        "game-memory-color-sequence",
        "game-memory-pattern-sequence",
    ]

    color = ActionLibraryItem.objects.get(source_key="game-memory-color-sequence")
    assert color.name == "颜色顺序记忆"
    assert color.training_type == "认知训练"
    assert color.internal_type == ActionLibraryItem.InternalType.GAME
    assert color.action_type == "记忆力训练"
    assert color.instruction_text == "按顺序点击变色方块\n\n实现成本：可实现\n资源难度：低"
    assert color.suggested_frequency == "1 次/周"
    assert color.suggested_duration_minutes == 10
    assert color.has_ai_supervision is False
    assert color.is_active is True


@pytest.mark.django_db
def test_action_library_endpoint_filters_game_actions(client, doctor):
    client.force_login(doctor)

    response = client.get(
        "/api/prescriptions/actions/",
        {"internal_type": ActionLibraryItem.InternalType.GAME},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 6
    assert {row["internal_type"] for row in body} == {"game"}
    assert {row["training_type"] for row in body} == {"认知训练"}
    assert "颜色顺序记忆" in {row["name"] for row in body}


@pytest.mark.django_db
def test_game_action_snapshot_keeps_prescription_fields(project_patient, doctor):
    action = ActionLibraryItem.objects.get(source_key="game-memory-color-sequence")
    prescription = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
    )

    snapshot = prescription.add_action_snapshot(
        action,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=12,
        difficulty="中",
        notes="从简单难度开始",
    )

    action.name = "动作库已改名"
    action.instruction_text = "动作库新说明"
    action.save(update_fields=["name", "instruction_text", "updated_at"])

    snapshot.refresh_from_db()
    assert snapshot.action_name_snapshot == "颜色顺序记忆"
    assert snapshot.training_type_snapshot == "认知训练"
    assert snapshot.internal_type_snapshot == "game"
    assert snapshot.action_type_snapshot == "记忆力训练"
    assert "按顺序点击变色方块" in snapshot.action_instruction_snapshot
    assert snapshot.weekly_frequency == "2 次/周"
    assert snapshot.weekly_target_count == 2
    assert snapshot.duration_minutes == 12
    assert snapshot.difficulty == "中"
    assert snapshot.notes == "从简单难度开始"
```

- [x] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend && pytest apps/prescriptions/tests/test_game_action_library.py -q
```

Expected: FAIL，原因是 6 个游戏动作尚未 seed。

- [x] **Step 3: 新增游戏动作 seed migration**

Create `backend/apps/prescriptions/migrations/0010_seed_game_actions.py`:

```python
from django.db import migrations


GAME_ACTIONS = [
    {
        "source_key": "game-memory-color-sequence",
        "game_no": 1,
        "name": "颜色顺序记忆",
        "action_type": "记忆力训练",
        "description": "按顺序点击变色方块",
        "implementation_cost": "可实现",
        "resource_difficulty": "低",
    },
    {
        "source_key": "game-memory-pattern-sequence",
        "game_no": 2,
        "name": "图案顺序记忆",
        "action_type": "记忆力训练",
        "description": "展示图片，记忆后连续选择相同的图片",
        "implementation_cost": "可实现",
        "resource_difficulty": "低",
    },
    {
        "source_key": "game-executive-inhibition",
        "game_no": 5,
        "name": "反应抑制能力训练",
        "action_type": "执行力训练",
        "description": "出现多个数字，选择不同的数字",
        "implementation_cost": "可实现",
        "resource_difficulty": "低",
    },
    {
        "source_key": "game-executive-category-switch",
        "game_no": 6,
        "name": "分类转换任务",
        "action_type": "执行力训练",
        "description": "展示图片，选择图片内容对应的分类",
        "implementation_cost": "可实现",
        "resource_difficulty": "中等",
    },
    {
        "source_key": "game-audiovisual-sound-discrimination",
        "game_no": 9,
        "name": "声音辨别",
        "action_type": "视听力训练",
        "description": "播放选项对应音频，记忆后，播放声音，选择声音对应的选项",
        "implementation_cost": "可实现（稍晚）",
        "resource_difficulty": "较高",
    },
    {
        "source_key": "game-audiovisual-puzzle",
        "game_no": 10,
        "name": "拼图",
        "action_type": "视听力训练",
        "description": "展示拼图，乱序后要求恢复",
        "implementation_cost": "可实现，但不适合手机端",
        "resource_difficulty": "低",
    },
]


def instruction_text(item):
    return (
        f"{item['description']}\n\n"
        f"实现成本：{item['implementation_cost']}\n"
        f"资源难度：{item['resource_difficulty']}"
    )


def seed_game_actions(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    for item in GAME_ACTIONS:
        ActionLibraryItem.objects.update_or_create(
            source_key=item["source_key"],
            defaults={
                "name": item["name"],
                "training_type": "认知训练",
                "internal_type": "game",
                "action_type": item["action_type"],
                "instruction_text": instruction_text(item),
                "suggested_frequency": "1 次/周",
                "suggested_duration_minutes": 10,
                "default_difficulty": "",
                "video_url": "",
                "has_ai_supervision": False,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0009_prescriptionaction_weekly_target_count"),
    ]

    operations = [
        migrations.RunPython(seed_game_actions, migrations.RunPython.noop),
    ]
```

- [x] **Step 4: 运行游戏动作库测试**

Run:

```bash
cd backend && pytest apps/prescriptions/tests/test_game_action_library.py -q
```

Expected: PASS。

- [x] **Step 5: 提交游戏动作库 seed**

```bash
git add backend/apps/prescriptions/migrations/0010_seed_game_actions.py backend/apps/prescriptions/tests/test_game_action_library.py
git commit -m "feat(prescriptions): 预置认知游戏动作库"
```

---

### Task 2: Validate Patient-App Game Result Submission

**Files:**
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py`
- Create: `backend/apps/training/game_results.py`
- Modify: `backend/apps/patient_app/views.py`

- [x] **Step 1: 写患者端游戏结果回传失败测试**

Append to `backend/apps/patient_app/tests/test_patient_app_api.py`:

```python
from apps.prescriptions.models import ActionLibraryItem, Prescription


def _game_prescription_action(active_prescription):
    action = ActionLibraryItem.objects.get(source_key="game-memory-color-sequence")
    return active_prescription.add_action_snapshot(
        action,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=10,
        difficulty="简单",
    )


@pytest.mark.django_db
def test_patient_app_submits_game_result(
    project_patient,
    doctor,
    active_prescription,
):
    game_action = _game_prescription_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-records/",
        {
            "prescription_action": game_action.id,
            "training_date": str(timezone.localdate()),
            "status": TrainingRecord.Status.COMPLETED,
            "actual_duration_minutes": 8,
            "score": "86.50",
            "form_data": {
                "accuracy_rate": 92,
                "error_count": 3,
                "difficulty": "简单",
                "raw_detail": {"rounds": 6, "max_sequence": 5},
            },
            "note": "完成顺利",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    record = TrainingRecord.objects.get(pk=response.data["id"])
    assert record.prescription == active_prescription
    assert record.prescription_action == game_action
    assert str(record.score) == "86.50"
    assert record.form_data["accuracy_rate"] == 92
    assert record.form_data["error_count"] == 3
    assert record.form_data["difficulty"] == "简单"
    assert record.form_data["raw_detail"]["max_sequence"] == 5


@pytest.mark.django_db
@pytest.mark.parametrize(
    "form_data,error_text",
    [
        ([], "游戏结果明细必须是对象"),
        ({"accuracy_rate": 101}, "正确率必须在 0 到 100 之间"),
        ({"accuracy_rate": -1}, "正确率必须在 0 到 100 之间"),
        ({"error_count": -1}, "错误次数必须是非负整数"),
        ({"error_count": "很多"}, "错误次数必须是非负整数"),
    ],
)
def test_patient_app_rejects_invalid_game_result_metrics(
    project_patient,
    doctor,
    active_prescription,
    form_data,
    error_text,
):
    game_action = _game_prescription_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-records/",
        {
            "prescription_action": game_action.id,
            "training_date": str(timezone.localdate()),
            "status": TrainingRecord.Status.COMPLETED,
            "actual_duration_minutes": 8,
            "form_data": form_data,
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert error_text in str(response.data)
    assert not TrainingRecord.objects.filter(prescription_action=game_action).exists()


@pytest.mark.django_db
def test_patient_app_rejects_stale_game_prescription_action(
    project_patient,
    doctor,
    active_prescription,
):
    old_game_action = _game_prescription_action(active_prescription)
    active_prescription.status = Prescription.Status.ARCHIVED
    active_prescription.archived_at = timezone.now()
    active_prescription.save(update_fields=["status", "archived_at", "updated_at"])
    Prescription.objects.create(
        project_patient=project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-records/",
        {
            "prescription_action": old_game_action.id,
            "training_date": str(timezone.localdate()),
            "status": TrainingRecord.Status.COMPLETED,
            "actual_duration_minutes": 8,
            "form_data": {"accuracy_rate": 90, "error_count": 1},
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert response.data["detail"] == "处方已更新，请返回当前处方重新进入"
    assert not TrainingRecord.objects.filter(prescription_action=old_game_action).exists()
```

- [x] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend && pytest apps/patient_app/tests/test_patient_app_api.py -q
```

Expected: FAIL，原因是游戏指标校验和旧处方动作提示尚未实现。

- [x] **Step 3: 创建游戏结果校验工具**

Create `backend/apps/training/game_results.py`:

```python
from django.core.exceptions import ValidationError

from apps.prescriptions.models import ActionLibraryItem, PrescriptionAction


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_game_result_fields(
    prescription_action: PrescriptionAction,
    *,
    form_data,
) -> None:
    if prescription_action.internal_type_snapshot != ActionLibraryItem.InternalType.GAME:
        return
    if form_data in (None, ""):
        return
    if not isinstance(form_data, dict):
        raise ValidationError("游戏结果明细必须是对象")

    accuracy_rate = form_data.get("accuracy_rate")
    if accuracy_rate is not None:
        if not _is_number(accuracy_rate) or accuracy_rate < 0 or accuracy_rate > 100:
            raise ValidationError("正确率必须在 0 到 100 之间")

    error_count = form_data.get("error_count")
    if error_count is not None:
        if not isinstance(error_count, int) or isinstance(error_count, bool) or error_count < 0:
            raise ValidationError("错误次数必须是非负整数")

    difficulty = form_data.get("difficulty")
    if difficulty is not None and not isinstance(difficulty, str):
        raise ValidationError("游戏难度必须是文本")
```

- [x] **Step 4: 在患者端训练提交视图中调用校验**

Modify `backend/apps/patient_app/views.py`:

```python
# add import
from apps.training.game_results import validate_game_result_fields
```

Replace `PatientAppTrainingRecordView.post()` body after `data = serializer.validated_data` with:

```python
        project_patient = self.project_patient()
        try:
            action = PrescriptionAction.objects.get(pk=data.pop("prescription_action"))
            active_prescription = current_prescription_for(project_patient)
            if active_prescription is None or action.prescription_id != active_prescription.id:
                return Response(
                    {"detail": "处方已更新，请返回当前处方重新进入"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            validate_game_result_fields(
                action,
                form_data=data.get("form_data"),
            )
            record = create_training_record(
                project_patient=project_patient,
                prescription_action=action,
                **data,
            )
        except PrescriptionAction.DoesNotExist:
            return Response(
                {"detail": "动作不存在或不属于当前处方"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (DjangoValidationError, DrfValidationError) as exc:
            return Response(
                {"detail": validation_detail(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
```

- [x] **Step 5: 运行患者端 API 测试**

Run:

```bash
cd backend && pytest apps/patient_app/tests/test_patient_app_api.py -q
```

Expected: PASS。

- [x] **Step 6: 提交游戏结果回传校验**

```bash
git add backend/apps/training/game_results.py backend/apps/patient_app/views.py backend/apps/patient_app/tests/test_patient_app_api.py
git commit -m "feat(training): 支持患者端游戏结果回传校验"
```

---

### Task 3: Add Backend Training Tracking API

**Files:**
- Create: `backend/apps/training/tests/test_tracking_api.py`
- Create: `backend/apps/training/tracking.py`
- Create: `backend/apps/training/tracking_views.py`
- Modify: `backend/apps/training/urls.py`

- [x] **Step 1: 写训练追踪 API 失败测试**

Create `backend/apps/training/tests/test_tracking_api.py`:

```python
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.training.models import TrainingRecord


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _project_link(patient, doctor, name, enrolled_group="干预组"):
    project = StudyProject.objects.create(name=name, created_by=doctor)
    group = StudyGroup.objects.create(project=project, name=enrolled_group)
    return ProjectPatient.objects.create(project=project, patient=patient, group=group)


def _active_prescription(project_patient, doctor, version=1):
    return Prescription.objects.create(
        project_patient=project_patient,
        version=version,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )


def _action_snapshot(prescription, *, source_key, name, internal_type, action_type):
    action = ActionLibraryItem.objects.create(
        source_key=source_key,
        name=name,
        training_type="认知训练" if internal_type == "game" else "运动训练",
        internal_type=internal_type,
        action_type=action_type,
        instruction_text=f"{name}说明",
        suggested_frequency="2 次/周",
        suggested_duration_minutes=10,
    )
    return prescription.add_action_snapshot(
        action,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=10,
    )


@pytest.mark.django_db
def test_tracking_patient_search_returns_accessible_patient_summary(doctor):
    patient = Patient.objects.create(
        name="训练患者",
        gender=Patient.Gender.FEMALE,
        phone="13900009999",
        primary_doctor=doctor,
    )
    project_patient = _project_link(patient, doctor, "训练项目 A")
    prescription = _active_prescription(project_patient, doctor)
    action = _action_snapshot(
        prescription,
        source_key="game-search",
        name="颜色顺序记忆",
        internal_type="game",
        action_type="记忆力训练",
    )
    TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=prescription,
        prescription_action=action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=8,
        score=Decimal("88.00"),
        form_data={"accuracy_rate": 90, "error_count": 2},
    )

    response = _client(doctor).get("/api/training/tracking/patients/", {"q": "训练"})

    assert response.status_code == 200, response.data
    assert response.data == [
        {
            "patient": {
                "id": patient.id,
                "name": "训练患者",
                "phone_masked": "139****9999",
            },
            "project_count": 1,
            "last_training_at": str(timezone.localdate()),
            "last_30_days_completed_count": 1,
        }
    ]


@pytest.mark.django_db
def test_tracking_patient_detail_returns_completion_trend_and_game_summary(doctor):
    patient = Patient.objects.create(
        name="详情患者",
        gender=Patient.Gender.MALE,
        phone="13900008888",
        primary_doctor=doctor,
    )
    project_patient = _project_link(patient, doctor, "详情项目")
    prescription = _active_prescription(project_patient, doctor)
    game_action = _action_snapshot(
        prescription,
        source_key="game-detail",
        name="颜色顺序记忆",
        internal_type="game",
        action_type="记忆力训练",
    )
    motion_action = _action_snapshot(
        prescription,
        source_key="motion-detail",
        name="坐站转移训练",
        internal_type="motion",
        action_type="平衡训练",
    )
    today = timezone.localdate()
    TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=prescription,
        prescription_action=game_action,
        training_date=today,
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=8,
        score=Decimal("80.00"),
        form_data={"accuracy_rate": 90, "error_count": 2, "difficulty": "简单"},
    )
    TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=prescription,
        prescription_action=motion_action,
        training_date=today - timezone.timedelta(days=1),
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=12,
        form_data={},
    )

    response = _client(doctor).get(f"/api/training/tracking/patients/{patient.id}/")

    assert response.status_code == 200, response.data
    assert response.data["patient"]["id"] == patient.id
    assert response.data["selected_project_patient"]["id"] == project_patient.id
    assert response.data["current_prescription"]["version"] == 1
    completion = response.data["prescription_completion"]
    assert len(completion) == 2
    color_completion = next(item for item in completion if item["action_name"] == "颜色顺序记忆")
    assert color_completion["target_count"] == 2
    assert color_completion["completed_count"] == 1
    assert color_completion["completion_rate"] == 50.0
    trend = response.data["trend"]
    assert len(trend["daily"]) == 30
    assert trend["daily"][-1]["date"] == str(today)
    assert trend["daily"][-1]["completed_count"] == 1
    assert trend["daily"][-1]["duration_minutes"] == 8
    assert len(trend["moving_average"]) == 30
    assert trend["weekly"]
    assert response.data["game_summary"]["average_score"] == 80.0
    assert response.data["game_summary"]["average_accuracy_rate"] == 90.0
    assert response.data["game_summary"]["total_error_count"] == 2
    assert response.data["game_summary"]["by_game"][0]["action_name"] == "颜色顺序记忆"
    assert response.data["recent_records"][0]["game_accuracy_rate"] == 90
    assert response.data["recent_records"][0]["game_error_count"] == 2


@pytest.mark.django_db
def test_tracking_detail_can_switch_project_patient(doctor):
    patient = Patient.objects.create(
        name="多项目患者",
        gender=Patient.Gender.FEMALE,
        phone="13900007777",
        primary_doctor=doctor,
    )
    first = _project_link(patient, doctor, "项目一")
    second = _project_link(patient, doctor, "项目二")
    first_prescription = _active_prescription(first, doctor)
    second_prescription = _active_prescription(second, doctor)
    _action_snapshot(
        first_prescription,
        source_key="game-first",
        name="图案顺序记忆",
        internal_type="game",
        action_type="记忆力训练",
    )
    _action_snapshot(
        second_prescription,
        source_key="game-second",
        name="分类转换任务",
        internal_type="game",
        action_type="执行力训练",
    )

    response = _client(doctor).get(
        f"/api/training/tracking/patients/{patient.id}/",
        {"project_patient": second.id},
    )

    assert response.status_code == 200, response.data
    assert response.data["selected_project_patient"]["id"] == second.id
    assert response.data["selected_project_patient"]["project_name"] == "项目二"
    assert {row["id"] for row in response.data["project_patients"]} == {first.id, second.id}
    assert response.data["current_prescription"]["id"] == second_prescription.id


@pytest.mark.django_db
def test_tracking_patient_search_hides_inaccessible_patient(doctor):
    other_doctor = User.objects.create_user(
        phone="13800002222",
        password="pass123456",
        name="其他医生",
        role=User.Role.DOCTOR,
    )
    hidden_patient = Patient.objects.create(
        name="不可见患者",
        gender=Patient.Gender.MALE,
        phone="13900006666",
        primary_doctor=other_doctor,
    )
    _project_link(hidden_patient, other_doctor, "其他项目")

    response = _client(doctor).get("/api/training/tracking/patients/", {"q": "不可见"})

    assert response.status_code == 200, response.data
    assert response.data == []
```

- [x] **Step 2: 运行训练追踪测试确认失败**

Run:

```bash
cd backend && pytest apps/training/tests/test_tracking_api.py -q
```

Expected: FAIL，原因是 tracking API 尚未存在。

- [x] **Step 3: 创建训练追踪聚合服务**

Create `backend/apps/training/tracking.py`:

```python
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Max, Q
from django.utils import timezone

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.prescriptions.models import Prescription, PrescriptionAction
from apps.studies.models import ProjectPatient

from .models import TrainingRecord


def mask_phone(phone: str) -> str:
    if not phone or len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


def accessible_project_patients(user: User):
    qs = ProjectPatient.objects.select_related("patient", "project", "group").order_by("-enrolled_at", "-id")
    if user.role in {User.Role.SUPER_ADMIN, User.Role.ADMIN}:
        return qs
    return qs.filter(
        Q(patient__primary_doctor=user)
        | Q(project__created_by=user)
        | Q(created_by=user)
    ).distinct()


def current_week_bounds(today: date | None = None):
    today = today or timezone.localdate()
    start = today - timezone.timedelta(days=today.weekday())
    end = start + timezone.timedelta(days=6)
    return start, end


def date_range(start: date, end: date):
    days = (end - start).days
    return [start + timezone.timedelta(days=offset) for offset in range(days + 1)]


def as_float(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def numeric_form_value(form_data, key):
    if not isinstance(form_data, dict):
        return None
    value = form_data.get(key)
    return as_float(value)


def int_form_value(form_data, key):
    if not isinstance(form_data, dict):
        return None
    value = form_data.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def project_patient_payload(project_patient: ProjectPatient):
    return {
        "id": project_patient.id,
        "project": project_patient.project_id,
        "project_name": project_patient.project.name,
        "project_status": project_patient.project.status,
        "group": project_patient.group_id,
        "group_name": project_patient.group.name if project_patient.group_id else None,
        "enrolled_at": project_patient.enrolled_at.isoformat() if project_patient.enrolled_at else None,
    }


def current_prescription_for(project_patient: ProjectPatient):
    return (
        Prescription.objects.filter(
            project_patient=project_patient,
            status=Prescription.Status.ACTIVE,
        )
        .prefetch_related("actions")
        .order_by("-effective_at", "-id")
        .first()
    )


def patient_search_rows(user: User, q: str = ""):
    project_patients = accessible_project_patients(user)
    if q:
        normalized = q.strip()
        if normalized:
            project_patients = project_patients.filter(
                Q(patient__name__icontains=normalized)
                | Q(patient__phone__icontains=normalized)
            )

    patient_ids = list(project_patients.values_list("patient_id", flat=True).distinct())
    if not patient_ids:
        return []

    visible_links = list(project_patients.filter(patient_id__in=patient_ids))
    links_by_patient = defaultdict(list)
    for link in visible_links:
        links_by_patient[link.patient_id].append(link)

    today = timezone.localdate()
    last_30_start = today - timezone.timedelta(days=29)
    records = TrainingRecord.objects.filter(project_patient__in=visible_links)
    recent_by_patient = {
        row["project_patient__patient_id"]: row["last_training_at"]
        for row in records.values("project_patient__patient_id").annotate(
            last_training_at=Max("training_date")
        )
    }
    completed_30 = defaultdict(int)
    for row in (
        records.filter(
            training_date__gte=last_30_start,
            training_date__lte=today,
            status=TrainingRecord.Status.COMPLETED,
        )
        .values("project_patient__patient_id")
        .annotate(last_training_at=Max("training_date"))
    ):
        completed_30[row["project_patient__patient_id"]] += TrainingRecord.objects.filter(
            project_patient__patient_id=row["project_patient__patient_id"],
            project_patient__in=visible_links,
            training_date__gte=last_30_start,
            training_date__lte=today,
            status=TrainingRecord.Status.COMPLETED,
        ).count()

    patients = Patient.objects.filter(id__in=patient_ids).order_by("-id")
    return [
        {
            "patient": {
                "id": patient.id,
                "name": patient.name,
                "phone_masked": mask_phone(patient.phone),
            },
            "project_count": len(links_by_patient[patient.id]),
            "last_training_at": recent_by_patient.get(patient.id).isoformat()
            if recent_by_patient.get(patient.id)
            else None,
            "last_30_days_completed_count": completed_30.get(patient.id, 0),
        }
        for patient in patients
    ]


def choose_project_patient(project_patients, requested_id=None):
    if requested_id:
        for project_patient in project_patients:
            if project_patient.id == requested_id:
                return project_patient
        return None
    if not project_patients:
        return None
    latest_training = {
        row["project_patient_id"]: row["last_training_at"]
        for row in TrainingRecord.objects.filter(project_patient__in=project_patients)
        .values("project_patient_id")
        .annotate(last_training_at=Max("training_date"))
    }
    with_training = [item for item in project_patients if item.id in latest_training]
    if with_training:
        return sorted(
            with_training,
            key=lambda item: (latest_training[item.id], item.enrolled_at, item.id),
            reverse=True,
        )[0]
    return sorted(project_patients, key=lambda item: (item.enrolled_at, item.id), reverse=True)[0]


def completion_rows(project_patient: ProjectPatient, prescription: Prescription | None):
    if prescription is None:
        return []
    week_start, week_end = current_week_bounds()
    actions = list(prescription.actions.order_by("sort_order", "id"))
    completed_counts = defaultdict(int)
    recent_dates = {}
    records = TrainingRecord.objects.filter(
        project_patient=project_patient,
        prescription=prescription,
        prescription_action__in=actions,
    )
    for record in records:
        if record.status == TrainingRecord.Status.COMPLETED and week_start <= record.training_date <= week_end:
            completed_counts[record.prescription_action_id] += 1
        current_recent = recent_dates.get(record.prescription_action_id)
        if current_recent is None or record.training_date > current_recent:
            recent_dates[record.prescription_action_id] = record.training_date

    rows = []
    for action in actions:
        target_count = action.weekly_target_count
        completed_count = completed_counts[action.id]
        rows.append(
            {
                "prescription_action": action.id,
                "action_name": action.action_name_snapshot,
                "internal_type": action.internal_type_snapshot,
                "action_type": action.action_type_snapshot,
                "target_count": target_count,
                "completed_count": completed_count,
                "completion_rate": round(completed_count / target_count * 100, 2)
                if target_count
                else 0.0,
                "recent_record_at": recent_dates[action.id].isoformat()
                if action.id in recent_dates
                else None,
            }
        )
    return rows


def trend_payload(project_patient: ProjectPatient, range_key: str):
    today = timezone.localdate()
    days = 6 if range_key == "7d" else 29
    start = today - timezone.timedelta(days=days)
    records = list(
        TrainingRecord.objects.select_related("prescription_action")
        .filter(project_patient=project_patient, training_date__gte=start, training_date__lte=today)
        .order_by("training_date", "id")
    )
    by_day = {
        day: {"date": day.isoformat(), "completed_count": 0, "duration_minutes": 0, "game_scores": []}
        for day in date_range(start, today)
    }
    for record in records:
        row = by_day[record.training_date]
        if record.status == TrainingRecord.Status.COMPLETED:
            row["completed_count"] += 1
        row["duration_minutes"] += record.actual_duration_minutes or 0
        if record.prescription_action.internal_type_snapshot == "game":
            score = as_float(record.score)
            if score is not None:
                row["game_scores"].append(score)

    daily = []
    for day in date_range(start, today):
        row = by_day[day]
        scores = row.pop("game_scores")
        row["game_average_score"] = round(sum(scores) / len(scores), 2) if scores else None
        daily.append(row)

    moving_average = []
    for index, row in enumerate(daily):
        window = daily[max(0, index - 6) : index + 1]
        moving_average.append(
            {
                "date": row["date"],
                "completed_count_avg": round(
                    sum(item["completed_count"] for item in window) / len(window),
                    2,
                ),
                "duration_minutes_avg": round(
                    sum(item["duration_minutes"] for item in window) / len(window),
                    2,
                ),
            }
        )

    week_rows = {}
    for row in daily:
        day = date.fromisoformat(row["date"])
        week_start = day - timezone.timedelta(days=day.weekday())
        key = week_start.isoformat()
        item = week_rows.setdefault(
            key,
            {
                "week_start": key,
                "week_end": (week_start + timezone.timedelta(days=6)).isoformat(),
                "completed_count": 0,
                "duration_minutes": 0,
                "game_scores": [],
            },
        )
        item["completed_count"] += row["completed_count"]
        item["duration_minutes"] += row["duration_minutes"]
        if row["game_average_score"] is not None:
            item["game_scores"].append(row["game_average_score"])
    weekly = []
    for item in week_rows.values():
        scores = item.pop("game_scores")
        item["game_average_score"] = round(sum(scores) / len(scores), 2) if scores else None
        weekly.append(item)

    return {"daily": daily, "moving_average": moving_average, "weekly": weekly}


def game_summary(project_patient: ProjectPatient, start: date, end: date):
    records = list(
        TrainingRecord.objects.select_related("prescription_action")
        .filter(
            project_patient=project_patient,
            training_date__gte=start,
            training_date__lte=end,
            prescription_action__internal_type_snapshot="game",
        )
        .order_by("-training_date", "-id")
    )
    scores = [as_float(record.score) for record in records if as_float(record.score) is not None]
    accuracy_values = [
        numeric_form_value(record.form_data, "accuracy_rate")
        for record in records
        if numeric_form_value(record.form_data, "accuracy_rate") is not None
    ]
    total_error_count = sum(
        int_form_value(record.form_data, "error_count") or 0 for record in records
    )
    by_game_data = {}
    for record in records:
        action = record.prescription_action
        item = by_game_data.setdefault(
            action.id,
            {
                "prescription_action": action.id,
                "action_name": action.action_name_snapshot,
                "record_count": 0,
                "scores": [],
                "accuracy_values": [],
                "recent_record_at": record.training_date,
            },
        )
        item["record_count"] += 1
        score = as_float(record.score)
        if score is not None:
            item["scores"].append(score)
        accuracy = numeric_form_value(record.form_data, "accuracy_rate")
        if accuracy is not None:
            item["accuracy_values"].append(accuracy)
        if record.training_date > item["recent_record_at"]:
            item["recent_record_at"] = record.training_date

    by_game = []
    for item in by_game_data.values():
        game_scores = item.pop("scores")
        game_accuracy_values = item.pop("accuracy_values")
        item["average_score"] = round(sum(game_scores) / len(game_scores), 2) if game_scores else None
        item["average_accuracy_rate"] = (
            round(sum(game_accuracy_values) / len(game_accuracy_values), 2)
            if game_accuracy_values
            else None
        )
        item["recent_record_at"] = item["recent_record_at"].isoformat()
        by_game.append(item)

    return {
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
        "average_accuracy_rate": round(sum(accuracy_values) / len(accuracy_values), 2)
        if accuracy_values
        else None,
        "total_error_count": total_error_count,
        "by_game": sorted(by_game, key=lambda item: item["recent_record_at"], reverse=True),
    }


def recent_records(project_patient: ProjectPatient, limit=30):
    records = (
        TrainingRecord.objects.select_related("prescription", "prescription_action")
        .filter(project_patient=project_patient)
        .order_by("-training_date", "-id")[:limit]
    )
    return [
        {
            "id": record.id,
            "training_date": record.training_date.isoformat(),
            "status": record.status,
            "prescription": record.prescription_id,
            "prescription_version": record.prescription.version,
            "prescription_action": record.prescription_action_id,
            "action_name": record.prescription_action.action_name_snapshot,
            "internal_type": record.prescription_action.internal_type_snapshot,
            "action_type": record.prescription_action.action_type_snapshot,
            "actual_duration_minutes": record.actual_duration_minutes,
            "score": as_float(record.score),
            "game_accuracy_rate": numeric_form_value(record.form_data, "accuracy_rate"),
            "game_error_count": int_form_value(record.form_data, "error_count"),
            "game_difficulty": record.form_data.get("difficulty")
            if isinstance(record.form_data, dict)
            else None,
            "note": record.note,
        }
        for record in records
    ]


def patient_tracking_detail(user: User, patient_id: int, project_patient_id=None, range_key="30d"):
    project_patients = list(accessible_project_patients(user).filter(patient_id=patient_id))
    if not project_patients:
        return None
    selected = choose_project_patient(project_patients, requested_id=project_patient_id)
    if selected is None:
        return None
    prescription = current_prescription_for(selected)
    today = timezone.localdate()
    start = today - timezone.timedelta(days=29)
    return {
        "patient": {
            "id": selected.patient_id,
            "name": selected.patient.name,
            "phone_masked": mask_phone(selected.patient.phone),
        },
        "project_patients": [project_patient_payload(item) for item in project_patients],
        "selected_project_patient": project_patient_payload(selected),
        "current_prescription": {
            "id": prescription.id,
            "version": prescription.version,
            "status": prescription.status,
            "effective_at": prescription.effective_at.isoformat()
            if prescription.effective_at
            else None,
        }
        if prescription
        else None,
        "prescription_completion": completion_rows(selected, prescription),
        "trend": trend_payload(selected, range_key),
        "game_summary": game_summary(selected, start, today),
        "recent_records": recent_records(selected),
    }
```

- [x] **Step 4: 创建训练追踪 API 视图**

Create `backend/apps/training/tracking_views.py`:

```python
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOrDoctor

from .tracking import patient_search_rows, patient_tracking_detail


class TrackingPatientListView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request):
        q = request.query_params.get("q", "")
        return Response(patient_search_rows(request.user, q=q))


class TrackingPatientDetailView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, patient_id):
        project_patient = request.query_params.get("project_patient")
        range_key = request.query_params.get("range", "30d")
        if range_key not in {"7d", "30d", "weekly"}:
            return Response(
                {"detail": "range 仅支持 7d、30d、weekly"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        project_patient_id = int(project_patient) if project_patient else None
        data = patient_tracking_detail(
            request.user,
            patient_id=patient_id,
            project_patient_id=project_patient_id,
            range_key=range_key,
        )
        if data is None:
            return Response({"detail": "患者不可访问或未参与项目"}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)
```

- [x] **Step 5: 挂载训练追踪 URL**

Modify `backend/apps/training/urls.py`:

```python
from django.urls import path
from rest_framework.routers import DefaultRouter

from .tracking_views import TrackingPatientDetailView, TrackingPatientListView
from .views import TrainingRecordViewSet

router = DefaultRouter()
router.register("", TrainingRecordViewSet, basename="training-record")

urlpatterns = [
    path("tracking/patients/", TrackingPatientListView.as_view(), name="training-tracking-patients"),
    path(
        "tracking/patients/<int:patient_id>/",
        TrackingPatientDetailView.as_view(),
        name="training-tracking-patient-detail",
    ),
] + router.urls
```

- [x] **Step 6: 运行训练追踪 API 测试**

Run:

```bash
cd backend && pytest apps/training/tests/test_tracking_api.py -q
```

Expected: PASS。

- [x] **Step 7: 提交训练追踪后端 API**

```bash
git add backend/apps/training/tracking.py backend/apps/training/tracking_views.py backend/apps/training/urls.py backend/apps/training/tests/test_tracking_api.py
git commit -m "feat(training): 新增患者训练追踪聚合接口"
```

---

### Task 4: Support Mixed Motion And Game Prescriptions In Doctor UI

**Files:**
- Modify: `frontend/src/pages/prescriptions/types.ts`
- Modify: `frontend/src/pages/prescriptions/PrescriptionPanel.tsx`
- Modify: `frontend/src/pages/prescriptions/PrescriptionDrawer.tsx`
- Modify: `frontend/src/pages/prescriptions/FixedActionLibraryTab.tsx`
- Modify: `frontend/src/pages/prescriptions/PrescriptionPanel.test.tsx`

- [x] **Step 1: 写混合处方前端失败测试**

Modify `frontend/src/pages/prescriptions/PrescriptionPanel.test.tsx`:

Add this action fixture after `legKickbackAction`:

```tsx
const gameAction = {
  id: 201,
  source_key: "game-memory-color-sequence",
  name: "颜色顺序记忆",
  training_type: "认知训练",
  internal_type: "game",
  action_type: "记忆力训练",
  instruction_text: "按顺序点击变色方块\n\n实现成本：可实现\n资源难度：低",
  suggested_frequency: "1 次/周",
  suggested_duration_minutes: 10,
  default_difficulty: "",
  video_url: "",
  has_ai_supervision: false,
  is_active: true,
};
```

Change the mock for `/prescriptions/actions/` to:

```tsx
      if (url === "/prescriptions/actions/") {
        return Promise.resolve({ data: [action, resistanceAction, legKickbackAction, gameAction] });
      }
```

Append this test:

```tsx
  it("creates mixed motion and game prescription actions", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "开具处方" }));
    fireEvent.click(await screen.findByLabelText("椰林步道模拟（原地高抬腿+摆臂）"));
    fireEvent.click(await screen.findByLabelText("颜色顺序记忆"));
    expect(await screen.findByText("认知游戏")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存并立即生效" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/studies/project-patients/9001/prescriptions/activate-now/",
        expect.objectContaining({
          expected_active_version: null,
          actions: expect.arrayContaining([
            expect.objectContaining({
              action_library_item: 101,
              weekly_target_count: 3,
              duration_minutes: 20,
            }),
            expect.objectContaining({
              action_library_item: 201,
              weekly_frequency: "1 次/周",
              weekly_target_count: 1,
              duration_minutes: 10,
            }),
          ]),
        }),
      );
    });
  });
```

- [x] **Step 2: 运行处方面板测试确认失败**

Run:

```bash
cd frontend && npm run test -- src/pages/prescriptions/PrescriptionPanel.test.tsx
```

Expected: FAIL，原因是处方面板目前只加载 `training_type=运动训练&internal_type=motion`。

- [x] **Step 3: 更新处方类型**

Modify `frontend/src/pages/prescriptions/types.ts`:

```ts
export type ActionInternalType = "video" | "game" | "motion";

export type ActionLibraryItem = {
  id: number;
  source_key: string | null;
  name: string;
  training_type: string;
  internal_type: ActionInternalType;
  action_type: string;
  instruction_text: string;
  suggested_frequency: string;
  suggested_duration_minutes: number | null;
  default_difficulty: string;
  video_url: string;
  has_ai_supervision: boolean;
  is_active: boolean;
};
```

Keep the rest of the file as-is, but update `PrescriptionAction.internal_type_snapshot` to:

```ts
  internal_type_snapshot: ActionInternalType;
```

- [x] **Step 4: 加载全部动作库**

Modify the `actionsQuery` in `frontend/src/pages/prescriptions/PrescriptionPanel.tsx`:

```tsx
  const actionsQuery = useQuery({
    queryKey: ["action-library"],
    queryFn: async () => {
      const response = await apiClient.get<ActionLibraryItem[]>("/prescriptions/actions/");
      return response.data;
    },
  });
```

- [x] **Step 5: 按内部类型分组动作抽屉**

Modify `frontend/src/pages/prescriptions/PrescriptionDrawer.tsx`:

Add helper functions above `PrescriptionDrawer`:

```tsx
function internalTypeLabel(type: ActionLibraryItem["internal_type"]) {
  if (type === "game") return "认知游戏";
  if (type === "motion") return "运动训练";
  return "视频训练";
}

function groupKeyForAction(action: ActionLibraryItem) {
  return `${action.internal_type}:${action.action_type}`;
}
```

Replace `groupedActions` with:

```tsx
  const groupedActions = useMemo(() => {
    const groups = new Map<string, ActionLibraryItem[]>();
    for (const action of actions) {
      const key = groupKeyForAction(action);
      const group = groups.get(key) ?? [];
      group.push(action);
      groups.set(key, group);
    }
    return [...groups.entries()].map(([key, groupActions]) => ({
      key,
      internalType: groupActions[0].internal_type,
      actionType: groupActions[0].action_type,
      actions: groupActions,
    }));
  }, [actions]);
```

Replace the `Collapse` `items` mapping with:

```tsx
              items={groupedActions.map((group) => ({
                key: group.key,
                label: (
                  <Space>
                    <span>{internalTypeLabel(group.internalType)}</span>
                    <Tag>{group.actionType}</Tag>
                    <Tag>{group.actions.length} 个动作</Tag>
                  </Space>
                ),
                children: (
                  <Space direction="vertical" size={8} style={{ width: "100%" }}>
                    {group.actions.map((action) => (
                      <Checkbox key={action.id} value={action.id} aria-label={action.name} disabled={!action.is_active}>
                        <Space wrap size={8}>
                          <span>{action.name}</span>
                          <Tag>{action.training_type}</Tag>
                          <Tag>{weeklyFrequencyLabel(action.suggested_frequency)}</Tag>
                          <Tag>{renderDuration(action)}</Tag>
                        </Space>
                      </Checkbox>
                    ))}
                  </Space>
                ),
              }))}
```

- [x] **Step 6: 固定动作库展示训练类型**

Modify the tag area in `frontend/src/pages/prescriptions/FixedActionLibraryTab.tsx`:

```tsx
              <Space wrap size={[8, 8]}>
                <Tag>{action.training_type}</Tag>
                <Tag>{action.internal_type === "game" ? "认知游戏" : action.internal_type === "motion" ? "运动训练" : "视频训练"}</Tag>
                <Tag>{action.action_type}</Tag>
                <Tag>{weeklyFrequencyLabel(action.suggested_frequency)}</Tag>
                <Tag>
                  {action.suggested_duration_minutes ? `${action.suggested_duration_minutes} 分钟` : "未配置时长"}
                </Tag>
                <Badge status={action.video_url ? "success" : "default"} text={action.video_url ? "已配置视频" : "无视频资源"} />
                {action.has_ai_supervision ? <Tag color="blue">支持 AI 监督</Tag> : <Tag>无 AI 监督</Tag>}
              </Space>
```

- [x] **Step 7: 运行处方前端测试**

Run:

```bash
cd frontend && npm run test -- src/pages/prescriptions/PrescriptionPanel.test.tsx
```

Expected: PASS。

- [x] **Step 8: 提交混合处方 UI**

```bash
git add frontend/src/pages/prescriptions
git commit -m "feat(frontend): 处方管理支持认知游戏动作"
```

---

### Task 5: Add Miniapp Game Placeholder Session

**Files:**
- Modify: `miniapp/src/app.config.ts`
- Modify: `miniapp/src/types/patientApp.ts`
- Modify: `miniapp/src/pages/prescription/index.tsx`
- Create: `miniapp/src/pages/game-session/index.tsx`
- Modify: `miniapp/src/app.scss`

- [x] **Step 1: 新增小程序游戏页面路由**

Modify `miniapp/src/app.config.ts`:

```ts
export default defineAppConfig({
  pages: [
    'pages/bind/index',
    'pages/home/index',
    'pages/prescription/index',
    'pages/training/index',
    'pages/game-session/index',
    'pages/action-history/index',
    'pages/daily-health/index'
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#ffffff',
    navigationBarTitleText: 'MotionCare',
    navigationBarTextStyle: 'black'
  }
})
```

- [x] **Step 2: 更新患者端处方动作类型**

Modify action item type in `miniapp/src/types/patientApp.ts`:

```ts
    internal_type: 'motion' | 'game' | 'video'
```

Keep other fields unchanged.

- [x] **Step 3: 当前处方页增加游戏入口**

Modify the button row in `miniapp/src/pages/prescription/index.tsx`:

```tsx
          <View className='button-row'>
            <Button
              className='primary-button'
              onClick={() =>
                Taro.navigateTo({
                  url:
                    action.internal_type === 'game'
                      ? `/pages/game-session/index?actionId=${action.id}`
                      : `/pages/training/index?actionId=${action.id}`
                })
              }
            >
              {action.internal_type === 'game' ? '开始游戏' : '开始训练'}
            </Button>
            <Button
              className='secondary-button'
              onClick={() => Taro.navigateTo({ url: `/pages/action-history/index?actionId=${action.id}` })}
            >
              训练历史
            </Button>
          </View>
```

- [x] **Step 4: 创建游戏占位页**

Create `miniapp/src/pages/game-session/index.tsx`:

```tsx
import { Button, Input, Picker, Text, View } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { useState } from 'react'

import { request } from '../../api/client'
import type { CurrentPrescription } from '../../types/patientApp'
import { todayLocalDate } from '../../utils/date'

const DIFFICULTY_OPTIONS = ['简单', '中等', '困难'] as const

export default function GameSessionPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [prescription, setPrescription] = useState<CurrentPrescription>(null)
  const [difficultyIndex, setDifficultyIndex] = useState(0)
  const [duration, setDuration] = useState('')
  const [score, setScore] = useState('')
  const [accuracyRate, setAccuracyRate] = useState('')
  const [errorCount, setErrorCount] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useDidShow(() => {
    setError('')
    request<CurrentPrescription>('/patient-app/current-prescription/')
      .then(setPrescription)
      .catch((err) => setError(err instanceof Error ? err.message : '加载失败'))
  })

  const action = prescription?.actions.find((item) => item.id === actionId)

  async function submit() {
    if (!action || action.internal_type !== 'game') {
      setError('游戏动作无效，请返回当前处方重新进入')
      return
    }
    setLoading(true)
    setError('')
    try {
      await request('/patient-app/training-records/', {
        method: 'POST',
        data: {
          prescription_action: action.id,
          training_date: todayLocalDate(),
          status: 'completed',
          actual_duration_minutes: duration ? Number(duration) : null,
          score: score || null,
          form_data: {
            accuracy_rate: accuracyRate ? Number(accuracyRate) : undefined,
            error_count: errorCount ? Number(errorCount) : undefined,
            difficulty: DIFFICULTY_OPTIONS[difficultyIndex],
            raw_detail: { source: 'miniapp-placeholder' }
          },
          note
        }
      })
      Taro.navigateBack()
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败')
    } finally {
      setLoading(false)
    }
  }

  if (!prescription) {
    return (
      <View className='page game-session-page'>
        <Text className='title'>游戏训练</Text>
        {error ? <Text className='error'>{error}</Text> : <Text className='muted'>加载中</Text>}
      </View>
    )
  }

  if (!action || action.internal_type !== 'game') {
    return (
      <View className='page game-session-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='error'>游戏动作无效，请返回当前处方重新进入</Text>
      </View>
    )
  }

  return (
    <View className='page game-session-page'>
      <Text className='title'>{action.action_name}</Text>
      <Text className='muted'>{action.action_type}</Text>
      <Text className='paragraph'>{action.action_instruction}</Text>
      <View className='panel'>
        <View className='row'>
          <Text className='label'>本周进度</Text>
          <Text className='value'>
            {action.weekly_completed_count}/{action.weekly_target_count} 次
          </Text>
        </View>
        <View className='row'>
          <Text className='label'>建议时长</Text>
          <Text className='value'>{action.duration_minutes ?? '-'} 分钟</Text>
        </View>
      </View>
      <View className='field-card'>
        <Text className='label'>难度</Text>
        <Picker
          mode='selector'
          range={DIFFICULTY_OPTIONS}
          value={difficultyIndex}
          onChange={(event) => setDifficultyIndex(Number(event.detail.value))}
        >
          <Text className='value'>{DIFFICULTY_OPTIONS[difficultyIndex]}</Text>
        </Picker>
      </View>
      <View className='field-card'>
        <Text className='label'>完成时长</Text>
        <Input className='input' type='number' value={duration} placeholder='分钟' onInput={(event) => setDuration(event.detail.value)} />
      </View>
      <View className='field-card'>
        <Text className='label'>得分</Text>
        <Input className='input' type='digit' value={score} placeholder='0-100' onInput={(event) => setScore(event.detail.value)} />
      </View>
      <View className='field-card'>
        <Text className='label'>正确率</Text>
        <Input className='input' type='digit' value={accuracyRate} placeholder='0-100' onInput={(event) => setAccuracyRate(event.detail.value)} />
      </View>
      <View className='field-card'>
        <Text className='label'>错误次数</Text>
        <Input className='input' type='number' value={errorCount} placeholder='0' onInput={(event) => setErrorCount(event.detail.value)} />
      </View>
      <View className='field-card'>
        <Text className='label'>备注</Text>
        <Input className='input' value={note} placeholder='可选' onInput={(event) => setNote(event.detail.value)} />
      </View>
      {error ? <Text className='error'>{error}</Text> : null}
      <Button className='primary-button' loading={loading} onClick={submit}>
        提交游戏结果
      </Button>
    </View>
  )
}
```

- [x] **Step 5: 补充游戏页面样式**

Append to `miniapp/src/app.scss`:

```scss
.game-session-page {
  .paragraph {
    display: block;
    margin: 16px 0;
    color: #394150;
    line-height: 1.6;
    white-space: pre-wrap;
  }
}
```

- [x] **Step 6: 运行小程序构建和类型检查**

Run:

```bash
cd miniapp && npm run build:weapp
cd miniapp && npx tsc --noEmit --skipLibCheck
```

Expected: both commands pass。

- [x] **Step 7: 提交小程序游戏占位页**

```bash
git add miniapp/src/app.config.ts miniapp/src/types/patientApp.ts miniapp/src/pages/prescription/index.tsx miniapp/src/pages/game-session/index.tsx miniapp/src/app.scss
git commit -m "feat(miniapp): 新增游戏处方占位提交页"
```

---

### Task 6: Add Doctor Web Training Tracking Module

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/src/pages/training-tracking/types.ts`
- Create: `frontend/src/pages/training-tracking/TrainingTrackingPage.tsx`
- Create: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Create: `frontend/src/pages/training-tracking/TrainingTrackingPage.test.tsx`
- Create: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/layout/AdminLayout.tsx`
- Modify: `frontend/src/app/App.test.tsx`

- [x] **Step 1: 安装 Web 图表依赖**

Run:

```bash
cd frontend && npm install @ant-design/charts
```

Expected: `frontend/package.json` and `frontend/package-lock.json` are updated。

- [x] **Step 2: 写训练追踪患者搜索页失败测试**

Create `frontend/src/pages/training-tracking/TrainingTrackingPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TrainingTrackingPage } from "./TrainingTrackingPage";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/training-tracking"]}>
        <Routes>
          <Route path="/training-tracking" element={<TrainingTrackingPage />} />
          <Route path="/training-tracking/patients/:patientId" element={<div>详情页</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TrainingTrackingPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockGet.mockResolvedValue({
      data: [
        {
          patient: { id: 201, name: "训练患者", phone_masked: "139****9999" },
          project_count: 2,
          last_training_at: "2026-05-15",
          last_30_days_completed_count: 8,
        },
      ],
    });
  });

  afterEach(() => cleanup());

  it("searches global patients and links to tracking detail", async () => {
    renderPage();

    expect(screen.getByText("患者训练追踪")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("患者姓名或手机号"), { target: { value: "训练" } });
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/training/tracking/patients/",
        expect.objectContaining({ params: { q: "训练" } }),
      );
    });
    expect(await screen.findByText("训练患者")).toBeInTheDocument();
    expect(screen.getByText("139****9999")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看追踪" })).toHaveAttribute(
      "href",
      "/training-tracking/patients/201",
    );
  });
});
```

- [x] **Step 3: 写训练追踪详情页失败测试**

Create `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TrainingTrackingDetailPage } from "./TrainingTrackingDetailPage";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("@ant-design/charts", () => ({
  DualAxes: ({ data }: { data: unknown }) => <div data-testid="trend-chart">{JSON.stringify(data)}</div>,
  Column: ({ data }: { data: unknown }) => <div data-testid="completion-chart">{JSON.stringify(data)}</div>,
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

const detail = {
  patient: { id: 201, name: "训练患者", phone_masked: "139****9999" },
  project_patients: [
    {
      id: 9001,
      project: 1,
      project_name: "研究项目 A",
      project_status: "active",
      group: 10,
      group_name: "干预组",
      enrolled_at: "2026-05-12T10:00:00+08:00",
    },
    {
      id: 9002,
      project: 2,
      project_name: "研究项目 B",
      project_status: "active",
      group: 20,
      group_name: "对照组",
      enrolled_at: "2026-05-13T10:00:00+08:00",
    },
  ],
  selected_project_patient: {
    id: 9001,
    project: 1,
    project_name: "研究项目 A",
    project_status: "active",
    group: 10,
    group_name: "干预组",
    enrolled_at: "2026-05-12T10:00:00+08:00",
  },
  current_prescription: { id: 1, version: 2, status: "active", effective_at: "2026-05-15T10:00:00+08:00" },
  prescription_completion: [
    {
      prescription_action: 11,
      action_name: "颜色顺序记忆",
      internal_type: "game",
      action_type: "记忆力训练",
      target_count: 2,
      completed_count: 1,
      completion_rate: 50,
      recent_record_at: "2026-05-15",
    },
  ],
  trend: {
    daily: [{ date: "2026-05-15", completed_count: 1, duration_minutes: 8, game_average_score: 80 }],
    moving_average: [{ date: "2026-05-15", completed_count_avg: 0.14, duration_minutes_avg: 1.14 }],
    weekly: [{ week_start: "2026-05-11", week_end: "2026-05-17", completed_count: 1, duration_minutes: 8, game_average_score: 80 }],
  },
  game_summary: {
    average_score: 80,
    average_accuracy_rate: 90,
    total_error_count: 2,
    by_game: [
      {
        prescription_action: 11,
        action_name: "颜色顺序记忆",
        record_count: 1,
        average_score: 80,
        average_accuracy_rate: 90,
        recent_record_at: "2026-05-15",
      },
    ],
  },
  recent_records: [
    {
      id: 501,
      training_date: "2026-05-15",
      status: "completed",
      prescription: 1,
      prescription_version: 2,
      prescription_action: 11,
      action_name: "颜色顺序记忆",
      internal_type: "game",
      action_type: "记忆力训练",
      actual_duration_minutes: 8,
      score: 80,
      game_accuracy_rate: 90,
      game_error_count: 2,
      game_difficulty: "简单",
      note: "完成顺利",
    },
  ],
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/training-tracking/patients/201"]}>
        <Routes>
          <Route path="/training-tracking/patients/:patientId" element={<TrainingTrackingDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TrainingTrackingDetailPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockGet.mockResolvedValue({ data: detail });
  });

  afterEach(() => cleanup());

  it("shows project switch, completion, trend and game summary", async () => {
    renderPage();

    expect(await screen.findByText("训练患者")).toBeInTheDocument();
    expect(screen.getByText("研究项目 A")).toBeInTheDocument();
    expect(screen.getByText("当前处方 v2")).toBeInTheDocument();
    expect(screen.getByText("颜色顺序记忆")).toBeInTheDocument();
    expect(screen.getByText("1/2")).toBeInTheDocument();
    expect(screen.getByText("平均得分")).toBeInTheDocument();
    expect(screen.getByText("80")).toBeInTheDocument();
    expect(screen.getByTestId("trend-chart")).toBeInTheDocument();
    expect(screen.getByText("完成顺利")).toBeInTheDocument();
  });

  it("switches project by query param", async () => {
    renderPage();

    await screen.findByText("训练患者");
    fireEvent.mouseDown(screen.getByLabelText("切换项目"));
    fireEvent.click(await screen.findByText("研究项目 B"));

    await waitFor(() => {
      expect(mockGet).toHaveBeenLastCalledWith(
        "/training/tracking/patients/201/",
        expect.objectContaining({ params: expect.objectContaining({ project_patient: 9002 }) }),
      );
    });
  });
});
```

- [x] **Step 4: 创建训练追踪类型**

Create `frontend/src/pages/training-tracking/types.ts`:

```ts
export type TrackingPatientRow = {
  patient: { id: number; name: string; phone_masked: string };
  project_count: number;
  last_training_at: string | null;
  last_30_days_completed_count: number;
};

export type TrackingProjectPatient = {
  id: number;
  project: number;
  project_name: string;
  project_status: string;
  group: number | null;
  group_name: string | null;
  enrolled_at: string | null;
};

export type TrackingDetail = {
  patient: { id: number; name: string; phone_masked: string };
  project_patients: TrackingProjectPatient[];
  selected_project_patient: TrackingProjectPatient;
  current_prescription: null | {
    id: number;
    version: number;
    status: string;
    effective_at: string | null;
  };
  prescription_completion: Array<{
    prescription_action: number;
    action_name: string;
    internal_type: "motion" | "game" | "video";
    action_type: string;
    target_count: number;
    completed_count: number;
    completion_rate: number;
    recent_record_at: string | null;
  }>;
  trend: {
    daily: Array<{ date: string; completed_count: number; duration_minutes: number; game_average_score: number | null }>;
    moving_average: Array<{ date: string; completed_count_avg: number; duration_minutes_avg: number }>;
    weekly: Array<{ week_start: string; week_end: string; completed_count: number; duration_minutes: number; game_average_score: number | null }>;
  };
  game_summary: {
    average_score: number | null;
    average_accuracy_rate: number | null;
    total_error_count: number;
    by_game: Array<{
      prescription_action: number;
      action_name: string;
      record_count: number;
      average_score: number | null;
      average_accuracy_rate: number | null;
      recent_record_at: string | null;
    }>;
  };
  recent_records: Array<{
    id: number;
    training_date: string;
    status: "completed" | "partial" | "missed";
    prescription_version: number;
    action_name: string;
    internal_type: "motion" | "game" | "video";
    action_type: string;
    actual_duration_minutes: number | null;
    score: number | null;
    game_accuracy_rate: number | null;
    game_error_count: number | null;
    game_difficulty: string | null;
    note: string;
  }>;
};
```

- [x] **Step 5: 创建患者搜索页**

Create `frontend/src/pages/training-tracking/TrainingTrackingPage.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Button, Card, Input, Space, Table } from "antd";
import { useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";
import type { TrackingPatientRow } from "./types";

export function TrainingTrackingPage() {
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const { data = [], isLoading } = useQuery({
    queryKey: ["training-tracking-patients", query],
    queryFn: async () => {
      const response = await apiClient.get<TrackingPatientRow[]>("/training/tracking/patients/", {
        params: { q: query },
      });
      return response.data;
    },
  });

  return (
    <Card title="患者训练追踪">
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          allowClear
          placeholder="患者姓名或手机号"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onPressEnter={() => setQuery(draft.trim())}
          style={{ width: 220 }}
        />
        <Button type="primary" onClick={() => setQuery(draft.trim())}>
          查询
        </Button>
      </Space>
      <Table<TrackingPatientRow>
        rowKey={(row) => row.patient.id}
        loading={isLoading}
        dataSource={data}
        columns={[
          { title: "患者", dataIndex: ["patient", "name"] },
          { title: "手机号", dataIndex: ["patient", "phone_masked"] },
          { title: "参与项目数", dataIndex: "project_count" },
          { title: "最近训练", dataIndex: "last_training_at", render: (value: string | null) => value ?? "—" },
          { title: "近 30 天完成次数", dataIndex: "last_30_days_completed_count" },
          {
            title: "操作",
            render: (_: unknown, row) => <Link to={`/training-tracking/patients/${row.patient.id}`}>查看追踪</Link>,
          },
        ]}
      />
    </Card>
  );
}
```

- [x] **Step 6: 创建患者训练追踪详情页**

Create `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`:

```tsx
import { Column, DualAxes } from "@ant-design/charts";
import { useQuery } from "@tanstack/react-query";
import { Card, Descriptions, Empty, Progress, Select, Space, Statistic, Table, Tabs, Tag } from "antd";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import type { TrackingDetail } from "./types";

const STATUS_LABEL = { completed: "已完成", partial: "部分完成", missed: "未完成" };
const TYPE_LABEL = { motion: "运动", game: "游戏", video: "视频" };

export function TrainingTrackingDetailPage() {
  const { patientId } = useParams<{ patientId: string }>();
  const [projectPatientId, setProjectPatientId] = useState<number | undefined>();
  const [range, setRange] = useState<"30d" | "7d" | "weekly">("30d");
  const id = Number(patientId);

  const { data, isLoading } = useQuery({
    queryKey: ["training-tracking-detail", id, projectPatientId, range],
    enabled: Number.isSafeInteger(id) && id > 0,
    queryFn: async () => {
      const response = await apiClient.get<TrackingDetail>(`/training/tracking/patients/${id}/`, {
        params: {
          ...(projectPatientId ? { project_patient: projectPatientId } : {}),
          range,
        },
      });
      return response.data;
    },
  });

  const completionChartData = data?.prescription_completion ?? [];
  const trendData = useMemo(() => {
    if (!data) return [[], []] as const;
    const raw = range === "weekly" ? data.trend.weekly.map((row) => ({
      date: row.week_start,
      completed_count: row.completed_count,
      duration_minutes: row.duration_minutes,
    })) : data.trend.daily;
    const average = range === "weekly" ? [] : data.trend.moving_average.map((row) => ({
      date: row.date,
      completed_count_avg: row.completed_count_avg,
    }));
    return [raw, average] as const;
  }, [data, range]);

  if (!Number.isSafeInteger(id) || id <= 0) {
    return <Card><Empty description="无效患者 ID" /></Card>;
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card loading={isLoading}>
        {data ? (
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <Space wrap>
              <Select
                aria-label="切换项目"
                value={data.selected_project_patient.id}
                style={{ width: 260 }}
                onChange={setProjectPatientId}
                options={data.project_patients.map((item) => ({
                  value: item.id,
                  label: item.project_name,
                }))}
              />
              <Tag>{data.selected_project_patient.group_name ?? "未分组"}</Tag>
              <Tag>{data.current_prescription ? `当前处方 v${data.current_prescription.version}` : "暂无生效处方"}</Tag>
            </Space>
            <Descriptions title={data.patient.name} bordered size="small" column={3}>
              <Descriptions.Item label="手机号">{data.patient.phone_masked}</Descriptions.Item>
              <Descriptions.Item label="当前项目">{data.selected_project_patient.project_name}</Descriptions.Item>
              <Descriptions.Item label="分组">{data.selected_project_patient.group_name ?? "—"}</Descriptions.Item>
            </Descriptions>
          </Space>
        ) : null}
      </Card>

      {data ? (
        <>
          <Card title="处方完成情况">
            <Table
              rowKey="prescription_action"
              dataSource={data.prescription_completion}
              pagination={false}
              columns={[
                { title: "动作", dataIndex: "action_name" },
                { title: "类型", dataIndex: "internal_type", render: (value: keyof typeof TYPE_LABEL) => TYPE_LABEL[value] },
                { title: "分类", dataIndex: "action_type" },
                { title: "完成", render: (_: unknown, row) => `${row.completed_count}/${row.target_count}` },
                { title: "完成率", dataIndex: "completion_rate", render: (value: number) => <Progress percent={Math.min(value, 100)} format={() => `${value}%`} /> },
                { title: "最近训练", dataIndex: "recent_record_at", render: (value: string | null) => value ?? "—" },
              ]}
            />
            <Column
              data={completionChartData}
              xField="action_name"
              yField="completion_rate"
              height={220}
              style={{ marginTop: 16 }}
            />
          </Card>

          <Card title="训练趋势" extra={<Tabs activeKey={range} onChange={(key) => setRange(key as typeof range)} items={[
            { key: "30d", label: "近 30 天" },
            { key: "7d", label: "近 7 天" },
            { key: "weekly", label: "按周" },
          ]} />}>
            <DualAxes
              data={trendData}
              xField="date"
              yField={["completed_count", "completed_count_avg"]}
              geometryOptions={[{ geometry: "column" }, { geometry: "line" }]}
              height={300}
            />
          </Card>

          <Card title="游戏表现">
            <Space wrap size={24}>
              <Statistic title="平均得分" value={data.game_summary.average_score ?? 0} />
              <Statistic title="平均正确率" value={data.game_summary.average_accuracy_rate ?? 0} suffix="%" />
              <Statistic title="总错误次数" value={data.game_summary.total_error_count} />
            </Space>
            <Table
              rowKey="prescription_action"
              dataSource={data.game_summary.by_game}
              pagination={false}
              style={{ marginTop: 16 }}
              columns={[
                { title: "游戏", dataIndex: "action_name" },
                { title: "记录数", dataIndex: "record_count" },
                { title: "平均得分", dataIndex: "average_score", render: (value: number | null) => value ?? "—" },
                { title: "平均正确率", dataIndex: "average_accuracy_rate", render: (value: number | null) => (value == null ? "—" : `${value}%`) },
                { title: "最近训练", dataIndex: "recent_record_at" },
              ]}
            />
          </Card>

          <Card title="最近训练记录">
            <Table
              rowKey="id"
              dataSource={data.recent_records}
              columns={[
                { title: "日期", dataIndex: "training_date" },
                { title: "动作", dataIndex: "action_name" },
                { title: "类型", dataIndex: "internal_type", render: (value: keyof typeof TYPE_LABEL) => TYPE_LABEL[value] },
                { title: "状态", dataIndex: "status", render: (value: keyof typeof STATUS_LABEL) => STATUS_LABEL[value] },
                { title: "时长", dataIndex: "actual_duration_minutes", render: (value: number | null) => (value == null ? "—" : `${value} 分钟`) },
                { title: "得分", dataIndex: "score", render: (value: number | null) => value ?? "—" },
                { title: "正确率", dataIndex: "game_accuracy_rate", render: (value: number | null) => (value == null ? "—" : `${value}%`) },
                { title: "备注", dataIndex: "note" },
              ]}
            />
          </Card>
        </>
      ) : (
        <Card loading={isLoading}>
          <Empty description="暂无训练追踪数据" />
        </Card>
      )}
    </Space>
  );
}
```

- [x] **Step 7: 加入路由和侧边栏**

Modify `frontend/src/app/App.tsx` imports:

```tsx
import { TrainingTrackingDetailPage } from "../pages/training-tracking/TrainingTrackingDetailPage";
import { TrainingTrackingPage } from "../pages/training-tracking/TrainingTrackingPage";
```

Add routes inside `AdminLayout` route:

```tsx
              <Route path="/training-tracking" element={<TrainingTrackingPage />} />
              <Route path="/training-tracking/patients/:patientId" element={<TrainingTrackingDetailPage />} />
```

Modify `frontend/src/app/layout/AdminLayout.tsx` imports:

```tsx
  LineChartOutlined,
```

Add menu item:

```tsx
            { key: "/training-tracking", icon: <LineChartOutlined />, label: "训练追踪" },
```

- [x] **Step 8: 更新 App 路由测试**

Modify `frontend/src/app/App.test.tsx` by adding a mock response for tracking list where the test mock dispatches `apiClient.get`:

```tsx
      if (url === "/training/tracking/patients/") return Promise.resolve({ data: [] });
```

Append a route smoke test:

```tsx
  it("renders training tracking route", async () => {
    window.history.pushState({}, "", "/training-tracking");
    renderApp();

    expect(await screen.findByText("患者训练追踪")).toBeInTheDocument();
  });
```

- [x] **Step 9: 运行训练追踪前端测试**

Run:

```bash
cd frontend && npm run test -- src/pages/training-tracking/TrainingTrackingPage.test.tsx src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx src/app/App.test.tsx
```

Expected: PASS。

- [x] **Step 10: 提交训练追踪 Web 模块**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/pages/training-tracking frontend/src/app/App.tsx frontend/src/app/layout/AdminLayout.tsx frontend/src/app/App.test.tsx
git commit -m "feat(frontend): 新增患者训练追踪模块"
```

---

### Task 7: Final Verification And Plan Closure

**Files:**
- Modify: `docs/superpowers/plans/2026-05-15-game-prescription-tracking.md`

- [x] **Step 1: 运行后端完整测试**

Run:

```bash
cd backend && pytest
```

Expected: PASS。

- [x] **Step 2: 运行前端测试、lint 和构建**

Run:

```bash
cd frontend && npm run test
cd frontend && npm run lint
cd frontend && npm run build
```

Expected: all commands pass。

- [x] **Step 3: 运行小程序构建和类型检查**

Run:

```bash
cd miniapp && npm run build:weapp
cd miniapp && npx tsc --noEmit --skipLibCheck
```

Expected: both commands pass。

- [x] **Step 4: 更新本计划执行记录**

At the top of this file after the header block, add one execution record using the actual completion date and actual implementation commit short SHAs. The line must use this shape:

```markdown
执行记录（实际完成日期, codex）：游戏处方与训练追踪已落地，验证通过。实施 commit：以逗号分隔的实际短 SHA 列表
```

Then change all completed task checkboxes from `- [ ]` to `- [x]`.

- [x] **Step 5: 提交计划收口记录**

```bash
git add docs/superpowers/plans/2026-05-15-game-prescription-tracking.md
git commit -m "docs(plan): 标记游戏处方与训练追踪实施完成"
```

---

## Self-Review

- Spec coverage: 游戏动作库、混合处方、小程序游戏入口、游戏结果回传、医生端训练追踪、图表平滑、权限过滤、测试验收均有对应任务。
- Placeholder scan: 本计划未发现占位标记或延迟补写式步骤。
- Type consistency: 后端统一使用 `internal_type = game`、`form_data.accuracy_rate`、`form_data.error_count`、`form_data.difficulty`；前端类型与 API 返回字段一致；小程序沿用 `prescription_action` 和 `/patient-app/training-records/`。
