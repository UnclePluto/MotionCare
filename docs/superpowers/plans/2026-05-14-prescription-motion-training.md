# 运动训练处方与模拟跟练 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建医生端固定运动动作库、项目患者处方立即生效流程，以及 Web 患者端模拟跟练和训练记录提交闭环。

**Architecture:** 后端以 `ActionLibraryItem` 作为固定只读动作库，以 `Prescription` / `PrescriptionAction` 保存版本化处方和动作快照，以 `TrainingRecord` 保存单动作跟练结果。医生端通过项目患者维度开具/调整处方，患者端模拟页只读取当前 active 处方并调用同一套训练校验服务。

**Tech Stack:** Django 5 + DRF + pytest-django；React 18 + TypeScript + Vite + Ant Design 5 + TanStack Query v5 + Vitest。

---

## Scope Check

本计划覆盖单一业务闭环：固定动作库 -> 医生开处方 -> 当前处方展示 -> 患者模拟跟练 -> 训练记录。它跨后端和前端，但不拆成多个独立 spec，因为每一层都依赖同一套处方动作快照契约，拆开会导致无法独立验收。

本计划不实现真实患者账号、微信小程序、视频上传、AI 动作识别、处方草稿、待生效处方、旧处方补录。

## File Structure

### 后端

- Modify: `backend/apps/prescriptions/models.py`
  - 调整动作库字段：`source_key`、`instruction_text`、`suggested_repetitions`、`video_url`、`has_ai_supervision`。
  - 调整处方动作快照字段：`action_instruction_snapshot`、`video_url_snapshot`、`has_ai_supervision_snapshot`、`weekly_frequency`、`repetitions`。
  - 删除旧字段：`execution_description`、`key_points`、`execution_description_snapshot`、`frequency`。
- Create: `backend/apps/prescriptions/migrations/0003_motion_prescription_fields.py`
  - 字段迁移和旧字段数据合并。
- Create: `backend/apps/prescriptions/migrations/0004_seed_motion_actions.py`
  - 幂等预置 5 个运动训练动作。
- Modify: `backend/apps/prescriptions/serializers.py`
  - 动作库只读序列化、处方读取序列化、立即生效请求序列化。
- Modify: `backend/apps/prescriptions/services.py`
  - 创建 `create_active_prescription_now`，负责版本号、快照、归档、并发校验。
- Modify: `backend/apps/prescriptions/views.py`
  - 动作库改只读；处方列表支持 `project_patient`；增加 `current`。
- Modify: `backend/apps/studies/views.py`
  - 在 `ProjectPatientViewSet` 增加 `prescriptions/activate-now` action。
- Modify: `backend/apps/training/services.py`
  - 保证训练记录只能基于当前 active 处方动作创建。
- Modify: `backend/apps/training/serializers.py`
  - 支持训练记录创建输入和读取输出分离。
- Modify: `backend/apps/training/views.py`
  - 普通训练创建也走服务层校验。
- Create: `backend/apps/training/patient_sim_views.py`
  - 患者端模拟当前处方读取与训练提交 API。
- Create: `backend/apps/training/patient_sim_urls.py`
  - `/api/patient-sim/` 子路由。
- Modify: `backend/config/urls.py`
  - 挂载 `api/patient-sim/`。
- Modify: `backend/conftest.py`
  - 更新处方 fixture 使用新字段。
- Modify: `backend/apps/common/management/commands/seed_demo.py`
  - demo 数据使用新字段和内置动作。
- Test: `backend/apps/prescriptions/tests/test_motion_action_library.py`
- Test: `backend/apps/prescriptions/tests/test_activate_now_api.py`
- Test: `backend/apps/prescriptions/tests/test_prescription_versioning.py`
- Test: `backend/apps/training/tests/test_training_current_prescription.py`
- Test: `backend/apps/training/tests/test_patient_sim_api.py`

### 前端

- Create: `frontend/src/pages/prescriptions/types.ts`
  - 处方、动作、训练提交类型。
- Create: `frontend/src/pages/prescriptions/prescriptionUtils.ts`
  - `getActionParameterMode(actionType)`，基于动作类型返回 `duration` 或 `count`。
- Modify: `frontend/src/pages/prescriptions/PrescriptionPanel.tsx`
  - 变成项目患者维度处方管理页面，包含处方管理 Tab 和固定动作库 Tab。
- Create: `frontend/src/pages/prescriptions/PrescriptionDrawer.tsx`
  - 开具/调整处方抽屉表单。
- Create: `frontend/src/pages/prescriptions/FixedActionLibraryTab.tsx`
  - 固定动作库只读展示。
- Create: `frontend/src/pages/patient-sim/PatientSimTrainingPage.tsx`
  - Web 患者端模拟跟练页。
- Modify: `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx`
  - 增加“处方”入口。
- Modify: `frontend/src/app/App.tsx`
  - 增加处方页和模拟跟练页路由。
- Test: `frontend/src/pages/prescriptions/prescriptionUtils.test.ts`
- Test: `frontend/src/pages/prescriptions/PrescriptionPanel.test.tsx`
- Test: `frontend/src/pages/patient-sim/PatientSimTrainingPage.test.tsx`
- Modify: `frontend/src/app/App.test.tsx`
  - 补充新增路由 mock 或避免新增路由破坏现有测试。

---

### Task 1: 后端处方模型字段与预置动作迁移

**Files:**
- Modify: `backend/apps/prescriptions/models.py`
- Create: `backend/apps/prescriptions/migrations/0003_motion_prescription_fields.py`
- Create: `backend/apps/prescriptions/migrations/0004_seed_motion_actions.py`
- Modify: `backend/conftest.py`
- Modify: `backend/apps/prescriptions/tests/test_prescription_versioning.py`
- Modify: `backend/apps/common/management/commands/seed_demo.py`
- Test: `backend/apps/prescriptions/tests/test_motion_action_library.py`

- [ ] **Step 1: 写动作库字段和预置数据失败测试**

Create `backend/apps/prescriptions/tests/test_motion_action_library.py`:

```python
import pytest

from apps.prescriptions.models import ActionLibraryItem


@pytest.mark.django_db
def test_motion_actions_are_seeded_by_migration():
    actions = ActionLibraryItem.objects.filter(training_type="运动训练").order_by("source_key")

    assert actions.count() == 5
    assert list(actions.values_list("source_key", flat=True)) == [
        "motion-aerobic-high-knee",
        "motion-balance-sit-stand",
        "motion-resistance-leg-kickback",
        "motion-resistance-row",
        "motion-resistance-shoulder-press",
    ]

    sit_stand = ActionLibraryItem.objects.get(source_key="motion-balance-sit-stand")
    assert sit_stand.name == "坐站转移训练"
    assert sit_stand.internal_type == ActionLibraryItem.InternalType.MOTION
    assert sit_stand.action_type == "平衡训练"
    assert "找一把高度45CM的椅子" in sit_stand.instruction_text
    assert "起身时重心充分前移" in sit_stand.instruction_text
    assert sit_stand.suggested_frequency == "2 次/周"
    assert sit_stand.suggested_duration_minutes == 15
    assert sit_stand.has_ai_supervision is True


@pytest.mark.django_db
def test_action_snapshot_keeps_merged_instruction_and_video(project_patient, doctor):
    action = ActionLibraryItem.objects.create(
        source_key="custom-motion-test",
        name="测试动作",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="有氧训练",
        instruction_text="步骤一。\\n\\n要点：保持躯干稳定。",
        suggested_frequency="3 次/周",
        suggested_duration_minutes=20,
        video_url="https://example.com/video.mp4",
        has_ai_supervision=True,
    )
    prescription = project_patient.prescriptions.create(version=1, opened_by=doctor)

    snapshot = prescription.add_action_snapshot(
        action,
        weekly_frequency="3 次/周",
        duration_minutes=20,
        repetitions=None,
    )

    action.name = "动作库已改名"
    action.instruction_text = "动作库新文案"
    action.video_url = "https://example.com/new.mp4"
    action.save()

    snapshot.refresh_from_db()
    assert snapshot.action_name_snapshot == "测试动作"
    assert snapshot.action_instruction_snapshot == "步骤一。\\n\\n要点：保持躯干稳定。"
    assert snapshot.video_url_snapshot == "https://example.com/video.mp4"
    assert snapshot.has_ai_supervision_snapshot is True
    assert snapshot.weekly_frequency == "3 次/周"
```

- [ ] **Step 2: 运行失败测试确认字段缺失**

Run:

```bash
cd backend && pytest apps/prescriptions/tests/test_motion_action_library.py -v
```

Expected: FAIL，错误包含 `FieldError`、`AttributeError` 或 `no such column`，说明新字段和预置数据尚未实现。

- [ ] **Step 3: 更新处方模型字段**

Modify `backend/apps/prescriptions/models.py`:

```python
class ActionLibraryItem(UserStampedModel):
    class InternalType(models.TextChoices):
        VIDEO = "video", "视频类"
        GAME = "game", "游戏互动类"
        MOTION = "motion", "运动类"

    source_key = models.CharField("动作编码", max_length=120, unique=True, null=True, blank=True)
    name = models.CharField("动作名称", max_length=120)
    training_type = models.CharField("训练类型", max_length=80)
    internal_type = models.CharField("内部类型", max_length=20, choices=InternalType.choices)
    action_type = models.CharField("动作类型", max_length=80)
    instruction_text = models.TextField("动作说明文案", blank=True)
    suggested_frequency = models.CharField("建议频次", max_length=80, blank=True)
    suggested_duration_minutes = models.PositiveIntegerField("建议时长", null=True, blank=True)
    suggested_sets = models.PositiveIntegerField("建议组数", null=True, blank=True)
    suggested_repetitions = models.PositiveIntegerField("建议次数", null=True, blank=True)
    default_difficulty = models.CharField("默认难度", max_length=40, blank=True)
    video_url = models.URLField("视频URL", max_length=500, blank=True)
    has_ai_supervision = models.BooleanField("是否支持AI监督", default=False)
    is_active = models.BooleanField("是否启用", default=True)
```

Update `Prescription.add_action_snapshot` signature and create call:

```python
    def add_action_snapshot(
        self,
        action: ActionLibraryItem,
        *,
        weekly_frequency: str = "",
        duration_minutes: int | None = None,
        sets: int | None = None,
        repetitions: int | None = None,
        difficulty: str = "",
        notes: str = "",
        sort_order: int = 0,
    ):
        return PrescriptionAction.objects.create(
            prescription=self,
            action_library_item=action,
            action_name_snapshot=action.name,
            training_type_snapshot=action.training_type,
            internal_type_snapshot=action.internal_type,
            action_type_snapshot=action.action_type,
            action_instruction_snapshot=action.instruction_text,
            video_url_snapshot=action.video_url,
            has_ai_supervision_snapshot=action.has_ai_supervision,
            weekly_frequency=weekly_frequency,
            duration_minutes=duration_minutes,
            sets=sets,
            repetitions=repetitions,
            difficulty=difficulty,
            notes=notes,
            sort_order=sort_order,
        )
```

Replace `PrescriptionAction` fields:

```python
class PrescriptionAction(UserStampedModel):
    prescription = models.ForeignKey(
        Prescription, on_delete=models.CASCADE, related_name="actions"
    )
    action_library_item = models.ForeignKey(ActionLibraryItem, on_delete=models.PROTECT)
    action_name_snapshot = models.CharField("动作名称快照", max_length=120)
    training_type_snapshot = models.CharField("训练类型快照", max_length=80)
    internal_type_snapshot = models.CharField("内部类型快照", max_length=20)
    action_type_snapshot = models.CharField("动作类型快照", max_length=80)
    action_instruction_snapshot = models.TextField("动作说明文案快照", blank=True)
    video_url_snapshot = models.URLField("视频URL快照", max_length=500, blank=True)
    has_ai_supervision_snapshot = models.BooleanField("是否支持AI监督快照", default=False)
    weekly_frequency = models.CharField("每周频次", max_length=80, blank=True)
    duration_minutes = models.PositiveIntegerField("时长", null=True, blank=True)
    sets = models.PositiveIntegerField("组数", null=True, blank=True)
    repetitions = models.PositiveIntegerField("次数", null=True, blank=True)
    difficulty = models.CharField("难度", max_length=40, blank=True)
    notes = models.TextField("注意事项", blank=True)
    sort_order = models.PositiveIntegerField("排序", default=0)
```

- [ ] **Step 4: 创建字段迁移**

Create `backend/apps/prescriptions/migrations/0003_motion_prescription_fields.py`:

```python
# Generated manually for motion prescription fields.

from django.db import migrations, models


def forwards(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    PrescriptionAction = apps.get_model("prescriptions", "PrescriptionAction")

    for action in ActionLibraryItem.objects.all():
        parts = []
        if getattr(action, "execution_description", ""):
            parts.append(action.execution_description)
        if getattr(action, "key_points", ""):
            parts.append(f"动作要点：{action.key_points}")
        action.instruction_text = "\n\n".join(parts)
        action.save(update_fields=["instruction_text"])

    for snapshot in PrescriptionAction.objects.all():
        snapshot.action_instruction_snapshot = getattr(snapshot, "execution_description_snapshot", "")
        snapshot.weekly_frequency = getattr(snapshot, "frequency", "")
        snapshot.save(update_fields=["action_instruction_snapshot", "weekly_frequency"])


def backwards(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    PrescriptionAction = apps.get_model("prescriptions", "PrescriptionAction")

    for action in ActionLibraryItem.objects.all():
        action.execution_description = action.instruction_text
        action.key_points = ""
        action.save(update_fields=["execution_description", "key_points"])

    for snapshot in PrescriptionAction.objects.all():
        snapshot.execution_description_snapshot = snapshot.action_instruction_snapshot
        snapshot.frequency = snapshot.weekly_frequency
        snapshot.save(update_fields=["execution_description_snapshot", "frequency"])


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0002_prescription_project_patient_set_null"),
    ]

    operations = [
        migrations.AddField(
            model_name="actionlibraryitem",
            name="source_key",
            field=models.CharField(blank=True, max_length=120, null=True, unique=True, verbose_name="动作编码"),
        ),
        migrations.AddField(
            model_name="actionlibraryitem",
            name="instruction_text",
            field=models.TextField(blank=True, verbose_name="动作说明文案"),
        ),
        migrations.AddField(
            model_name="actionlibraryitem",
            name="suggested_repetitions",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="建议次数"),
        ),
        migrations.AddField(
            model_name="actionlibraryitem",
            name="video_url",
            field=models.URLField(blank=True, max_length=500, verbose_name="视频URL"),
        ),
        migrations.AddField(
            model_name="actionlibraryitem",
            name="has_ai_supervision",
            field=models.BooleanField(default=False, verbose_name="是否支持AI监督"),
        ),
        migrations.AddField(
            model_name="prescriptionaction",
            name="action_instruction_snapshot",
            field=models.TextField(blank=True, verbose_name="动作说明文案快照"),
        ),
        migrations.AddField(
            model_name="prescriptionaction",
            name="video_url_snapshot",
            field=models.URLField(blank=True, max_length=500, verbose_name="视频URL快照"),
        ),
        migrations.AddField(
            model_name="prescriptionaction",
            name="has_ai_supervision_snapshot",
            field=models.BooleanField(default=False, verbose_name="是否支持AI监督快照"),
        ),
        migrations.AddField(
            model_name="prescriptionaction",
            name="weekly_frequency",
            field=models.CharField(blank=True, max_length=80, verbose_name="每周频次"),
        ),
        migrations.AddField(
            model_name="prescriptionaction",
            name="repetitions",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="次数"),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(model_name="actionlibraryitem", name="execution_description"),
        migrations.RemoveField(model_name="actionlibraryitem", name="key_points"),
        migrations.RemoveField(model_name="prescriptionaction", name="execution_description_snapshot"),
        migrations.RemoveField(model_name="prescriptionaction", name="frequency"),
    ]
```

- [ ] **Step 5: 创建预置动作数据迁移**

Create `backend/apps/prescriptions/migrations/0004_seed_motion_actions.py`:

```python
from django.db import migrations


MOTION_ACTIONS = [
    {
        "source_key": "motion-aerobic-high-knee",
        "name": "椰林步道模拟（原地高抬腿+摆臂）",
        "action_type": "有氧训练",
        "instruction_text": (
            "双脚与肩同宽站立，躯干直立，双手自然垂于身体两侧。\n"
            "左侧大腿屈膝上抬，大腿平行地面，右侧手臂屈肘向前摆动。\n"
            "左腿放下，右侧大腿抬至水平高度，左手向前摆。\n"
            "双腿交替高抬腿，双臂协同前后摆动。\n\n"
            "动作要点：骨盆中立，不塌腰不驼背，抬腿髋部发力。"
        ),
        "suggested_frequency": "3 次/周",
        "suggested_duration_minutes": 20,
        "has_ai_supervision": True,
    },
    {
        "source_key": "motion-balance-sit-stand",
        "name": "坐站转移训练",
        "action_type": "平衡训练",
        "instruction_text": (
            "找一把高度45CM的椅子，坐稳；双脚平放与肩同宽，脚尖位于膝盖正下方。\n"
            "躯干前倾，重心前移，臀部缓慢抬离椅面。\n"
            "双腿发力站直，髋关节膝关节充分伸展。\n"
            "缓慢屈髋屈膝，轻缓坐下。\n\n"
            "动作要点：起身时重心充分前移，禁止用手臂撑椅子发力。"
        ),
        "suggested_frequency": "2 次/周",
        "suggested_duration_minutes": 15,
        "has_ai_supervision": True,
    },
    {
        "source_key": "motion-resistance-row",
        "name": "坐姿划船",
        "action_type": "抗阻训练",
        "instruction_text": (
            "用红/黄两档阻力，坐姿挺直，弹力带踩于双脚，双手握带。\n"
            "双手绕带，绕道手臂伸直，弹力带有阻力为止，拳心朝内。\n"
            "腰背挺直，沉肩，手臂加紧身体，屈肘后拉夹背。\n"
            "顶点处停顿 2 秒，缓慢回放至起始位。\n\n"
            "动作要点：躯干固定，用背部肌群发力，肩胛骨后缩，不耸肩不弯腰。"
        ),
        "suggested_frequency": "2 次/周",
        "suggested_duration_minutes": 10,
        "has_ai_supervision": True,
    },
    {
        "source_key": "motion-resistance-leg-kickback",
        "name": "腿部后踢",
        "action_type": "抗阻训练",
        "instruction_text": (
            "将弹力带一端固定在单侧脚踝处，另一端绑定在固定物体上。\n"
            "躯干直立，双腿自然站立，支撑腿站稳不动。\n"
            "绑有弹力带的发力侧，大腿向后缓慢后踢，感受大腿后侧收紧。\n"
            "顶峰处稍停顿，再缓慢控制回放至起始位，重复次数训练后，换腿练另一侧。\n\n"
            "动作要点：躯干固定不塌腰不晃胯，大腿后侧肌群发力，不是腰部代偿。"
        ),
        "suggested_frequency": "2 次/周",
        "suggested_duration_minutes": 10,
        "has_ai_supervision": False,
    },
    {
        "source_key": "motion-resistance-shoulder-press",
        "name": "肩部推举",
        "action_type": "抗阻训练",
        "instruction_text": (
            "双脚与肩同宽，踩住弹力带中间位置，踩实防滑。\n"
            "双手分别抓握弹力带两端，屈肘小臂抬起，手置于肩侧耳旁。\n"
            "核心收紧、腰背挺直，双手发力垂直向上推举，手臂接近伸直不锁肘。\n"
            "顶点稍停，控制速度缓慢下放回到肩侧，循环重复。\n\n"
            "动作要点：全程收腹立腰，身体不后仰、不挺肚子，避免斜方肌代偿。"
        ),
        "suggested_frequency": "2 次/周",
        "suggested_duration_minutes": 10,
        "has_ai_supervision": False,
    },
]


def seed_motion_actions(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    for item in MOTION_ACTIONS:
        ActionLibraryItem.objects.update_or_create(
            source_key=item["source_key"],
            defaults={
                **item,
                "training_type": "运动训练",
                "internal_type": "motion",
                "is_active": True,
            },
        )


def unseed_motion_actions(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    ActionLibraryItem.objects.filter(
        source_key__in=[item["source_key"] for item in MOTION_ACTIONS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0003_motion_prescription_fields"),
    ]

    operations = [
        migrations.RunPython(seed_motion_actions, unseed_motion_actions),
    ]
```

- [ ] **Step 6: 更新测试 fixture 和旧测试字段**

Modify `backend/conftest.py` fixture action:

```python
    action = ActionLibraryItem.objects.create(
        name="坐立训练",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="平衡训练",
        instruction_text="从椅子坐下后站起。\n\n动作要点：保持躯干稳定。",
    )
    return active_prescription.add_action_snapshot(
        action,
        weekly_frequency="2 次/周",
        duration_minutes=10,
        sets=2,
    )
```

Modify `backend/apps/prescriptions/tests/test_prescription_versioning.py` action setup and assertions:

```python
    action = ActionLibraryItem.objects.create(
        name="坐立训练",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="平衡训练",
        instruction_text="从椅子坐下后站起。\n\n动作要点：保持躯干稳定。",
    )
```

Use:

```python
    snapshot = prescription.add_action_snapshot(action, duration_minutes=10, sets=2)
    assert snapshot.action_instruction_snapshot == "从椅子坐下后站起。\n\n动作要点：保持躯干稳定。"
```

- [ ] **Step 7: 更新 demo seed**

Modify `backend/apps/common/management/commands/seed_demo.py` action block:

```python
        action, _ = ActionLibraryItem.objects.get_or_create(
            source_key="motion-balance-sit-stand",
            defaults={
                "name": "坐站转移训练",
                "training_type": "运动训练",
                "internal_type": ActionLibraryItem.InternalType.MOTION,
                "action_type": "平衡训练",
                "instruction_text": "找一把高度45CM的椅子，坐稳；双腿发力站直，缓慢坐下。",
                "suggested_frequency": "2 次/周",
                "suggested_duration_minutes": 15,
                "has_ai_supervision": True,
            },
        )
```

Change snapshot creation:

```python
            prescription.add_action_snapshot(
                action,
                weekly_frequency="2 次/周",
                duration_minutes=15,
                sets=2,
            )
```

- [ ] **Step 8: 运行迁移和后端处方测试**

Run:

```bash
cd backend && python manage.py migrate
cd backend && pytest apps/prescriptions/tests/test_motion_action_library.py apps/prescriptions/tests/test_prescription_versioning.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 9: 提交模型和预置动作变更**

Run:

```bash
git add backend/apps/prescriptions backend/conftest.py backend/apps/common/management/commands/seed_demo.py
git commit -m "feat(prescriptions): 调整运动动作库字段并预置动作"
```

### Task 2: 后端处方立即生效 API

**Files:**
- Modify: `backend/apps/prescriptions/serializers.py`
- Modify: `backend/apps/prescriptions/services.py`
- Modify: `backend/apps/prescriptions/views.py`
- Modify: `backend/apps/studies/views.py`
- Test: `backend/apps/prescriptions/tests/test_activate_now_api.py`

- [ ] **Step 1: 写立即生效 API 失败测试**

Create `backend/apps/prescriptions/tests/test_activate_now_api.py`:

```python
import pytest
from django.utils import timezone

from apps.prescriptions.models import ActionLibraryItem, Prescription


@pytest.fixture
def motion_action(db):
    return ActionLibraryItem.objects.create(
        source_key="motion-api-test",
        name="接口测试动作",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="有氧训练",
        instruction_text="接口测试动作说明",
        suggested_frequency="3 次/周",
        suggested_duration_minutes=20,
        video_url="https://example.com/motion.mp4",
        has_ai_supervision=True,
    )


@pytest.mark.django_db
def test_activate_now_creates_active_prescription_and_snapshots(client, doctor, project_patient, motion_action):
    client.force_login(doctor)

    response = client.post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        {
            "expected_active_version": None,
            "note": "初始处方",
            "actions": [
                {
                    "action_library_item": motion_action.id,
                    "weekly_frequency": "3 次/周",
                    "duration_minutes": 20,
                    "sets": None,
                    "repetitions": None,
                    "difficulty": "低",
                    "notes": "注意扶稳",
                    "sort_order": 1,
                }
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 1
    assert body["status"] == "active"
    assert body["actions"][0]["action_name_snapshot"] == "接口测试动作"
    assert body["actions"][0]["action_instruction_snapshot"] == "接口测试动作说明"
    assert body["actions"][0]["weekly_frequency"] == "3 次/周"
    assert body["actions"][0]["video_url_snapshot"] == "https://example.com/motion.mp4"


@pytest.mark.django_db
def test_activate_now_archives_previous_active(client, doctor, project_patient, motion_action):
    client.force_login(doctor)
    old = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    old.add_action_snapshot(motion_action, weekly_frequency="1 次/周", duration_minutes=10)

    response = client.post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        {
            "expected_active_version": 1,
            "actions": [
                {
                    "action_library_item": motion_action.id,
                    "weekly_frequency": "2 次/周",
                    "duration_minutes": 15,
                    "sets": None,
                    "repetitions": None,
                    "difficulty": "中",
                    "notes": "",
                    "sort_order": 1,
                }
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    old.refresh_from_db()
    assert old.status == Prescription.Status.ARCHIVED
    assert Prescription.objects.get(project_patient=project_patient, version=2).status == Prescription.Status.ACTIVE


@pytest.mark.django_db
def test_activate_now_rejects_duplicate_actions(client, doctor, project_patient, motion_action):
    client.force_login(doctor)

    response = client.post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        {
            "expected_active_version": None,
            "actions": [
                {"action_library_item": motion_action.id, "weekly_frequency": "2 次/周", "duration_minutes": 10},
                {"action_library_item": motion_action.id, "weekly_frequency": "2 次/周", "duration_minutes": 10},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "重复动作" in str(response.json())


@pytest.mark.django_db
def test_activate_now_rejects_stale_active_version(client, doctor, project_patient, motion_action):
    client.force_login(doctor)
    Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )

    response = client.post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        {
            "expected_active_version": None,
            "actions": [
                {"action_library_item": motion_action.id, "weekly_frequency": "2 次/周", "duration_minutes": 10}
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "当前处方已变化，请刷新后重试。"
```

- [ ] **Step 2: 运行失败测试确认接口不存在**

Run:

```bash
cd backend && pytest apps/prescriptions/tests/test_activate_now_api.py -v
```

Expected: FAIL，`404` 或 serializer 字段缺失。

- [ ] **Step 3: 实现处方读取和创建 serializer**

Modify `backend/apps/prescriptions/serializers.py`:

```python
from rest_framework import serializers

from .models import ActionLibraryItem, Prescription, PrescriptionAction


class ActionLibraryItemSerializer(serializers.ModelSerializer):
    parameter_mode = serializers.SerializerMethodField()

    class Meta:
        model = ActionLibraryItem
        fields = [
            "id",
            "source_key",
            "name",
            "training_type",
            "internal_type",
            "action_type",
            "instruction_text",
            "suggested_frequency",
            "suggested_duration_minutes",
            "suggested_sets",
            "suggested_repetitions",
            "default_difficulty",
            "video_url",
            "has_ai_supervision",
            "is_active",
            "parameter_mode",
        ]
        read_only_fields = fields

    def get_parameter_mode(self, obj):
        return "duration" if obj.action_type == "有氧训练" else "count"


class PrescriptionActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionAction
        fields = [
            "id",
            "prescription",
            "action_library_item",
            "action_name_snapshot",
            "training_type_snapshot",
            "internal_type_snapshot",
            "action_type_snapshot",
            "action_instruction_snapshot",
            "video_url_snapshot",
            "has_ai_supervision_snapshot",
            "weekly_frequency",
            "duration_minutes",
            "sets",
            "repetitions",
            "difficulty",
            "notes",
            "sort_order",
        ]
        read_only_fields = fields


class PrescriptionSerializer(serializers.ModelSerializer):
    actions = PrescriptionActionSerializer(many=True, read_only=True)
    opened_by_name = serializers.CharField(source="opened_by.name", read_only=True)

    class Meta:
        model = Prescription
        fields = [
            "id",
            "project_patient",
            "version",
            "opened_by",
            "opened_by_name",
            "opened_at",
            "effective_at",
            "status",
            "note",
            "actions",
        ]
        read_only_fields = fields


class ActivateNowActionSerializer(serializers.Serializer):
    action_library_item = serializers.PrimaryKeyRelatedField(
        queryset=ActionLibraryItem.objects.filter(is_active=True)
    )
    weekly_frequency = serializers.CharField(required=False, allow_blank=True, max_length=80)
    duration_minutes = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    sets = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    repetitions = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    difficulty = serializers.CharField(required=False, allow_blank=True, max_length=40)
    notes = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.IntegerField(required=False, min_value=0)


class ActivateNowPrescriptionSerializer(serializers.Serializer):
    expected_active_version = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    note = serializers.CharField(required=False, allow_blank=True)
    actions = ActivateNowActionSerializer(many=True)

    def validate_actions(self, value):
        if not value:
            raise serializers.ValidationError("至少选择一个动作")
        action_ids = [item["action_library_item"].id for item in value]
        if len(action_ids) != len(set(action_ids)):
            raise serializers.ValidationError("重复动作")
        return value
```

- [ ] **Step 4: 实现立即生效服务**

Modify `backend/apps/prescriptions/services.py`:

```python
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import Prescription


@transaction.atomic
def activate_prescription(prescription: Prescription, effective_at=None) -> Prescription:
    now = timezone.now()
    effective_at = effective_at or now
    Prescription.objects.filter(
        project_patient=prescription.project_patient,
        status=Prescription.Status.ACTIVE,
    ).exclude(id=prescription.id).update(status=Prescription.Status.ARCHIVED)

    prescription.effective_at = effective_at
    prescription.status = (
        Prescription.Status.ACTIVE if effective_at <= now else Prescription.Status.PENDING
    )
    prescription.save(update_fields=["effective_at", "status", "updated_at"])
    return prescription


@transaction.atomic
def create_active_prescription_now(*, project_patient, opened_by, actions, expected_active_version=None, note=""):
    active = (
        Prescription.objects.select_for_update(of=("self",))
        .filter(project_patient=project_patient, status=Prescription.Status.ACTIVE)
        .order_by("-version", "-id")
        .first()
    )
    actual_active_version = active.version if active else None
    if actual_active_version != expected_active_version:
        raise ValidationError("当前处方已变化，请刷新后重试。")

    max_version = (
        Prescription.objects.select_for_update(of=("self",))
        .filter(project_patient=project_patient)
        .aggregate(max_version=Max("version"))["max_version"]
        or 0
    )
    prescription = Prescription.objects.create(
        project_patient=project_patient,
        version=max_version + 1,
        opened_by=opened_by,
        effective_at=timezone.now(),
        status=Prescription.Status.ACTIVE,
        note=note,
    )

    for index, item in enumerate(actions):
        prescription.add_action_snapshot(
            item["action_library_item"],
            weekly_frequency=item.get("weekly_frequency", ""),
            duration_minutes=item.get("duration_minutes"),
            sets=item.get("sets"),
            repetitions=item.get("repetitions"),
            difficulty=item.get("difficulty", ""),
            notes=item.get("notes", ""),
            sort_order=item.get("sort_order", index),
        )

    if active:
        active.status = Prescription.Status.ARCHIVED
        active.save(update_fields=["status", "updated_at"])

    return prescription
```

- [ ] **Step 5: 更新处方 views**

Modify imports and view classes in `backend/apps/prescriptions/views.py`:

```python
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from .serializers import (
    ActionLibraryItemSerializer,
    PrescriptionSerializer,
)
```

Replace `ActionLibraryItemViewSet`:

```python
class ActionLibraryItemViewSet(ReadOnlyModelViewSet):
    queryset = ActionLibraryItem.objects.order_by("action_type", "id")
    serializer_class = ActionLibraryItemSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        qs = super().get_queryset()
        training_type = self.request.query_params.get("training_type")
        if training_type:
            qs = qs.filter(training_type=training_type)
        internal_type = self.request.query_params.get("internal_type")
        if internal_type:
            qs = qs.filter(internal_type=internal_type)
        return qs
```

Replace `PrescriptionViewSet.get_queryset` and add `current`:

```python
    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .prefetch_related("actions")
            .exclude(status=Prescription.Status.TERMINATED)
        )
        project_patient_id = self.request.query_params.get("project_patient")
        if project_patient_id:
            qs = qs.filter(project_patient_id=project_patient_id)
        return qs

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):
        project_patient_id = request.query_params.get("project_patient")
        if not project_patient_id:
            return Response({"detail": "缺少 project_patient"}, status=status.HTTP_400_BAD_REQUEST)
        prescription = (
            self.get_queryset()
            .filter(project_patient_id=project_patient_id, status=Prescription.Status.ACTIVE)
            .order_by("-effective_at", "-id")
            .first()
        )
        if not prescription:
            return Response(None)
        return Response(self.get_serializer(prescription).data)
```

- [ ] **Step 6: 在 ProjectPatientViewSet 增加 activate-now action**

Modify `backend/apps/studies/views.py` imports:

```python
from django.core.exceptions import ValidationError as DjangoValidationError
from apps.prescriptions.serializers import ActivateNowPrescriptionSerializer, PrescriptionSerializer
from apps.prescriptions.services import create_active_prescription_now
```

Add method inside `ProjectPatientViewSet`:

```python
    @action(detail=True, methods=["post"], url_path="prescriptions/activate-now")
    @transaction.atomic
    def activate_prescription_now(self, request, pk=None):
        project_patient = self.get_object()
        serializer = ActivateNowPrescriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            prescription = create_active_prescription_now(
                project_patient=project_patient,
                opened_by=request.user,
                expected_active_version=serializer.validated_data.get("expected_active_version"),
                note=serializer.validated_data.get("note", ""),
                actions=serializer.validated_data["actions"],
            )
        except DjangoValidationError as exc:
            detail = exc.messages[0] if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PrescriptionSerializer(prescription).data, status=status.HTTP_201_CREATED)
```

- [ ] **Step 7: 运行处方 API 测试**

Run:

```bash
cd backend && pytest apps/prescriptions/tests/test_activate_now_api.py apps/prescriptions/tests/test_motion_action_library.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 8: 提交处方立即生效 API**

Run:

```bash
git add backend/apps/prescriptions backend/apps/studies/views.py
git commit -m "feat(prescriptions): 新增项目患者处方立即生效接口"
```

### Task 3: 后端患者端模拟跟练 API 与训练服务校验

**Files:**
- Modify: `backend/apps/training/services.py`
- Modify: `backend/apps/training/serializers.py`
- Modify: `backend/apps/training/views.py`
- Create: `backend/apps/training/patient_sim_views.py`
- Create: `backend/apps/training/patient_sim_urls.py`
- Modify: `backend/config/urls.py`
- Test: `backend/apps/training/tests/test_training_current_prescription.py`
- Test: `backend/apps/training/tests/test_patient_sim_api.py`

- [ ] **Step 1: 写训练服务和 patient-sim 失败测试**

Append to `backend/apps/training/tests/test_training_current_prescription.py`:

```python
@pytest.mark.django_db
def test_training_rejects_action_from_archived_prescription(active_prescription, prescription_action, doctor):
    from django.utils import timezone
    from apps.prescriptions.models import Prescription

    newer = Prescription.objects.create(
        project_patient=active_prescription.project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    active_prescription.status = Prescription.Status.ARCHIVED
    active_prescription.save(update_fields=["status"])

    with pytest.raises(ValidationError, match="只能录入当前生效处方下的动作"):
        create_training_record(
            project_patient=active_prescription.project_patient,
            training_date="2026-05-06",
            prescription_action=prescription_action,
            status="completed",
        )

    assert newer.status == Prescription.Status.ACTIVE
```

Create `backend/apps/training/tests/test_patient_sim_api.py`:

```python
import pytest


@pytest.mark.django_db
def test_patient_sim_current_prescription_returns_active_actions(client, doctor, active_prescription, prescription_action):
    client.force_login(doctor)

    response = client.get(
        f"/api/patient-sim/project-patients/{active_prescription.project_patient_id}/current-prescription/"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == active_prescription.id
    assert body["actions"][0]["id"] == prescription_action.id
    assert body["actions"][0]["action_name_snapshot"] == prescription_action.action_name_snapshot


@pytest.mark.django_db
def test_patient_sim_current_prescription_empty_without_active(client, doctor, project_patient):
    client.force_login(doctor)

    response = client.get(f"/api/patient-sim/project-patients/{project_patient.id}/current-prescription/")

    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.django_db
def test_patient_sim_training_submit_creates_record(client, doctor, active_prescription, prescription_action):
    client.force_login(doctor)

    response = client.post(
        f"/api/patient-sim/project-patients/{active_prescription.project_patient_id}/training-records/",
        {
            "prescription_action": prescription_action.id,
            "training_date": "2026-05-06",
            "status": "completed",
            "actual_duration_minutes": 15,
            "form_data": {
                "completed_sets": 2,
                "completed_repetitions": 12,
                "perceived_difficulty": "中",
                "discomfort": "无",
            },
            "note": "完成顺利",
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["project_patient"] == active_prescription.project_patient_id
    assert body["prescription"] == active_prescription.id
    assert body["prescription_action"] == prescription_action.id
    assert body["form_data"]["completed_sets"] == 2


@pytest.mark.django_db
def test_patient_sim_training_submit_requires_active_prescription(client, doctor, project_patient):
    client.force_login(doctor)

    response = client.post(
        f"/api/patient-sim/project-patients/{project_patient.id}/training-records/",
        {
            "prescription_action": 999,
            "training_date": "2026-05-06",
            "status": "completed",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "当前无生效处方" in str(response.json())
```

- [ ] **Step 2: 运行失败测试确认 patient-sim 不存在**

Run:

```bash
cd backend && pytest apps/training/tests/test_training_current_prescription.py apps/training/tests/test_patient_sim_api.py -v
```

Expected: FAIL，patient-sim API 返回 404 或训练 serializer 未走服务层。

- [ ] **Step 3: 收紧训练服务**

Modify `backend/apps/training/services.py`:

```python
def create_training_record(*, project_patient, training_date, prescription_action=None, **fields):
    active = (
        Prescription.objects.filter(
            project_patient=project_patient,
            status=Prescription.Status.ACTIVE,
        )
        .order_by("-effective_at", "-id")
        .first()
    )
    if not active:
        raise ValidationError("当前无生效处方，不能录入训练")
    if prescription_action is None:
        raise ValidationError("必须选择当前处方动作")
    if prescription_action.prescription_id != active.id:
        raise ValidationError("只能录入当前生效处方下的动作")
    return TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active,
        prescription_action=prescription_action,
        training_date=training_date,
        **fields,
    )
```

This function already mostly exists. Keep this exact behavior after model field updates; do not allow caller-provided `prescription` to override active.

- [ ] **Step 4: 更新训练 serializer**

Modify `backend/apps/training/serializers.py`:

```python
from rest_framework import serializers

from apps.prescriptions.models import PrescriptionAction
from apps.studies.models import ProjectPatient

from .models import TrainingRecord


class TrainingRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingRecord
        fields = [
            "id",
            "project_patient",
            "prescription",
            "prescription_action",
            "training_date",
            "status",
            "actual_duration_minutes",
            "score",
            "form_data",
            "note",
        ]
        read_only_fields = ["id", "prescription"]


class TrainingRecordCreateSerializer(serializers.Serializer):
    project_patient = serializers.PrimaryKeyRelatedField(queryset=ProjectPatient.objects.all())
    prescription_action = serializers.PrimaryKeyRelatedField(queryset=PrescriptionAction.objects.all())
    training_date = serializers.DateField()
    status = serializers.ChoiceField(choices=TrainingRecord.Status.choices)
    actual_duration_minutes = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    score = serializers.DecimalField(required=False, allow_null=True, max_digits=6, decimal_places=2)
    form_data = serializers.JSONField(required=False)
    note = serializers.CharField(required=False, allow_blank=True)
```

- [ ] **Step 5: 让普通训练创建走服务层**

Modify `backend/apps/training/views.py`:

```python
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import TrainingRecord
from .serializers import TrainingRecordCreateSerializer, TrainingRecordSerializer
from .services import create_training_record


class TrainingRecordViewSet(ModelViewSet):
    queryset = TrainingRecord.objects.select_related(
        "project_patient", "prescription", "prescription_action"
    ).order_by("-id")
    serializer_class = TrainingRecordSerializer
    permission_classes = [IsAdminOrDoctor]

    def create(self, request, *args, **kwargs):
        serializer = TrainingRecordCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_training_record(**serializer.validated_data)
        except DjangoValidationError as exc:
            detail = exc.messages[0] if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TrainingRecordSerializer(record).data, status=status.HTTP_201_CREATED)
```

- [ ] **Step 6: 新增 patient-sim views**

Create `backend/apps/training/patient_sim_views.py`:

```python
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOrDoctor
from apps.prescriptions.models import Prescription
from apps.prescriptions.serializers import PrescriptionSerializer
from apps.studies.models import ProjectPatient

from .serializers import TrainingRecordCreateSerializer, TrainingRecordSerializer
from .services import create_training_record


class PatientSimCurrentPrescriptionView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, project_patient_id):
        project_patient = ProjectPatient.objects.get(pk=project_patient_id)
        prescription = (
            Prescription.objects.filter(
                project_patient=project_patient,
                status=Prescription.Status.ACTIVE,
            )
            .prefetch_related("actions")
            .order_by("-effective_at", "-id")
            .first()
        )
        if not prescription:
            return Response(None)
        return Response(PrescriptionSerializer(prescription).data)


class PatientSimTrainingRecordView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def post(self, request, project_patient_id):
        data = {**request.data, "project_patient": project_patient_id}
        serializer = TrainingRecordCreateSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_training_record(**serializer.validated_data)
        except DjangoValidationError as exc:
            detail = exc.messages[0] if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TrainingRecordSerializer(record).data, status=status.HTTP_201_CREATED)
```

- [ ] **Step 7: 新增 patient-sim URLs**

Create `backend/apps/training/patient_sim_urls.py`:

```python
from django.urls import path

from .patient_sim_views import PatientSimCurrentPrescriptionView, PatientSimTrainingRecordView

urlpatterns = [
    path(
        "project-patients/<int:project_patient_id>/current-prescription/",
        PatientSimCurrentPrescriptionView.as_view(),
        name="patient-sim-current-prescription",
    ),
    path(
        "project-patients/<int:project_patient_id>/training-records/",
        PatientSimTrainingRecordView.as_view(),
        name="patient-sim-training-records",
    ),
]
```

Modify `backend/config/urls.py`:

```python
    path("api/patient-sim/", include("apps.training.patient_sim_urls")),
```

- [ ] **Step 8: 运行 patient-sim 和训练测试**

Run:

```bash
cd backend && pytest apps/training/tests/test_training_current_prescription.py apps/training/tests/test_patient_sim_api.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 9: 提交训练和模拟 API**

Run:

```bash
git add backend/apps/training backend/config/urls.py
git commit -m "feat(training): 新增患者端模拟跟练接口"
```

### Task 4: 前端处方类型、参数模式和医生端处方管理 UI

**Files:**
- Create: `frontend/src/pages/prescriptions/types.ts`
- Create: `frontend/src/pages/prescriptions/prescriptionUtils.ts`
- Create: `frontend/src/pages/prescriptions/prescriptionUtils.test.ts`
- Create: `frontend/src/pages/prescriptions/FixedActionLibraryTab.tsx`
- Create: `frontend/src/pages/prescriptions/PrescriptionDrawer.tsx`
- Modify: `frontend/src/pages/prescriptions/PrescriptionPanel.tsx`
- Test: `frontend/src/pages/prescriptions/PrescriptionPanel.test.tsx`

- [ ] **Step 1: 写参数模式工具测试**

Create `frontend/src/pages/prescriptions/prescriptionUtils.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { getActionParameterMode } from "./prescriptionUtils";

describe("getActionParameterMode", () => {
  it("uses duration mode for aerobic actions", () => {
    expect(getActionParameterMode("有氧训练")).toBe("duration");
  });

  it("uses count mode for balance and resistance actions", () => {
    expect(getActionParameterMode("平衡训练")).toBe("count");
    expect(getActionParameterMode("抗阻训练")).toBe("count");
  });
});
```

- [ ] **Step 2: 运行工具测试确认失败**

Run:

```bash
cd frontend && npm run test -- src/pages/prescriptions/prescriptionUtils.test.ts
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: 创建前端处方类型**

Create `frontend/src/pages/prescriptions/types.ts`:

```ts
export type ActionParameterMode = "duration" | "count";

export type ActionLibraryItem = {
  id: number;
  source_key: string | null;
  name: string;
  training_type: string;
  internal_type: "video" | "game" | "motion";
  action_type: string;
  instruction_text: string;
  suggested_frequency: string;
  suggested_duration_minutes: number | null;
  suggested_sets: number | null;
  suggested_repetitions: number | null;
  default_difficulty: string;
  video_url: string;
  has_ai_supervision: boolean;
  is_active: boolean;
  parameter_mode?: ActionParameterMode;
};

export type PrescriptionAction = {
  id: number;
  prescription: number;
  action_library_item: number;
  action_name_snapshot: string;
  training_type_snapshot: string;
  internal_type_snapshot: string;
  action_type_snapshot: string;
  action_instruction_snapshot: string;
  video_url_snapshot: string;
  has_ai_supervision_snapshot: boolean;
  weekly_frequency: string;
  duration_minutes: number | null;
  sets: number | null;
  repetitions: number | null;
  difficulty: string;
  notes: string;
  sort_order: number;
};

export type Prescription = {
  id: number;
  project_patient: number;
  version: number;
  opened_by: number;
  opened_by_name: string;
  opened_at: string;
  effective_at: string | null;
  status: "draft" | "active" | "pending" | "archived" | "terminated";
  note: string;
  actions: PrescriptionAction[];
};

export type ActivateNowActionPayload = {
  action_library_item: number;
  weekly_frequency?: string;
  duration_minutes?: number | null;
  sets?: number | null;
  repetitions?: number | null;
  difficulty?: string;
  notes?: string;
  sort_order?: number;
};
```

- [ ] **Step 4: 创建参数模式工具**

Create `frontend/src/pages/prescriptions/prescriptionUtils.ts`:

```ts
import type { ActionParameterMode } from "./types";

export function getActionParameterMode(actionType: string): ActionParameterMode {
  return actionType === "有氧训练" ? "duration" : "count";
}
```

- [ ] **Step 5: 运行工具测试确认通过**

Run:

```bash
cd frontend && npm run test -- src/pages/prescriptions/prescriptionUtils.test.ts
```

Expected: PASS.

- [ ] **Step 6: 写医生端处方面板失败测试**

Create `frontend/src/pages/prescriptions/PrescriptionPanel.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PrescriptionPanel } from "./PrescriptionPanel";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PrescriptionPanel projectPatientId={9001} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const action = {
  id: 101,
  source_key: "motion-aerobic-high-knee",
  name: "椰林步道模拟（原地高抬腿+摆臂）",
  training_type: "运动训练",
  internal_type: "motion",
  action_type: "有氧训练",
  instruction_text: "动作说明",
  suggested_frequency: "3 次/周",
  suggested_duration_minutes: 20,
  suggested_sets: null,
  suggested_repetitions: null,
  default_difficulty: "低",
  video_url: "https://example.com/video.mp4",
  has_ai_supervision: true,
  is_active: true,
  parameter_mode: "duration",
};

const activePrescription = {
  id: 1,
  project_patient: 9001,
  version: 1,
  opened_by: 1,
  opened_by_name: "测试医生",
  opened_at: "2026-05-14T10:00:00+08:00",
  effective_at: "2026-05-14T10:00:00+08:00",
  status: "active",
  note: "",
  actions: [
    {
      id: 11,
      prescription: 1,
      action_library_item: 101,
      action_name_snapshot: "椰林步道模拟（原地高抬腿+摆臂）",
      training_type_snapshot: "运动训练",
      internal_type_snapshot: "motion",
      action_type_snapshot: "有氧训练",
      action_instruction_snapshot: "动作说明",
      video_url_snapshot: "https://example.com/video.mp4",
      has_ai_supervision_snapshot: true,
      weekly_frequency: "3 次/周",
      duration_minutes: 20,
      sets: null,
      repetitions: null,
      difficulty: "低",
      notes: "",
      sort_order: 0,
    },
  ],
};

describe("PrescriptionPanel", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params = typeof config === "object" && config ? (config as { params?: Record<string, unknown> }).params : {};
      if (url === "/prescriptions/current/") return Promise.resolve({ data: null });
      if (url === "/prescriptions/") return Promise.resolve({ data: [] });
      if (url === "/prescriptions/actions/" && params?.training_type === "运动训练") {
        return Promise.resolve({ data: [action] });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    mockPost.mockResolvedValue({
      data: {
        id: 1,
        project_patient: 9001,
        version: 1,
        opened_by: 1,
        opened_by_name: "测试医生",
        opened_at: "2026-05-14T10:00:00+08:00",
        effective_at: "2026-05-14T10:00:00+08:00",
        status: "active",
        note: "",
        actions: [],
      },
    });
  });

  afterEach(() => cleanup());

  it("shows fixed action library as read-only", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("tab", { name: "固定动作库" }));
    expect(await screen.findByText("椰林步道模拟（原地高抬腿+摆臂）")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新增动作" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编辑" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除" })).not.toBeInTheDocument();
  });

  it("creates an active prescription from selected action", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "开具处方" }));
    fireEvent.click(await screen.findByLabelText("椰林步道模拟（原地高抬腿+摆臂）"));
    fireEvent.click(screen.getByRole("button", { name: "保存并立即生效" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/studies/project-patients/9001/prescriptions/activate-now/",
        expect.objectContaining({
          expected_active_version: null,
          actions: [
            expect.objectContaining({
              action_library_item: 101,
              weekly_frequency: "3 次/周",
              duration_minutes: 20,
            }),
          ],
        }),
      );
    });
  });

  it("terminates active prescription after confirmation", async () => {
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params = typeof config === "object" && config ? (config as { params?: Record<string, unknown> }).params : {};
      if (url === "/prescriptions/current/") return Promise.resolve({ data: activePrescription });
      if (url === "/prescriptions/") return Promise.resolve({ data: [activePrescription] });
      if (url === "/prescriptions/actions/" && params?.training_type === "运动训练") {
        return Promise.resolve({ data: [action] });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "终止处方" }));
    expect(await screen.findByText("确认终止当前处方？")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认终止" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/prescriptions/1/terminate/");
    });
  });
});
```

- [ ] **Step 7: 运行处方面板测试确认失败**

Run:

```bash
cd frontend && npm run test -- src/pages/prescriptions/PrescriptionPanel.test.tsx
```

Expected: FAIL，`PrescriptionPanel` 缺少 `projectPatientId` prop 或 UI 不存在。

- [ ] **Step 8: 创建固定动作库 Tab**

Create `frontend/src/pages/prescriptions/FixedActionLibraryTab.tsx`:

```tsx
import { Badge, Card, List, Space, Tag, Typography } from "antd";

import type { ActionLibraryItem } from "./types";

type Props = {
  actions: ActionLibraryItem[];
};

export function FixedActionLibraryTab({ actions }: Props) {
  return (
    <List
      grid={{ gutter: 12, column: 2 }}
      dataSource={actions}
      renderItem={(action) => (
        <List.Item>
          <Card size="small" title={action.name}>
            <Space direction="vertical" size={8} style={{ width: "100%" }}>
              <Space wrap>
                <Tag>{action.action_type}</Tag>
                <Tag>{action.suggested_frequency || "未配置频次"}</Tag>
                <Tag>{action.suggested_duration_minutes ? `${action.suggested_duration_minutes} 分钟` : "未配置时长"}</Tag>
                <Badge status={action.video_url ? "success" : "default"} text={action.video_url ? "已配置视频" : "视频待配置"} />
                {action.has_ai_supervision ? <Tag color="blue">支持 AI 监督</Tag> : <Tag>无 AI 监督</Tag>}
              </Space>
              <Typography.Paragraph style={{ marginBottom: 0 }}>
                {action.instruction_text || "暂无动作说明"}
              </Typography.Paragraph>
            </Space>
          </Card>
        </List.Item>
      )}
    />
  );
}
```

- [ ] **Step 9: 创建处方抽屉表单**

Create `frontend/src/pages/prescriptions/PrescriptionDrawer.tsx`:

```tsx
import { Button, Checkbox, Drawer, Form, Input, InputNumber, Space } from "antd";
import { useMemo } from "react";

import { getActionParameterMode } from "./prescriptionUtils";
import type { ActionLibraryItem, ActivateNowActionPayload, Prescription } from "./types";

type Props = {
  open: boolean;
  actions: ActionLibraryItem[];
  currentPrescription: Prescription | null;
  submitting: boolean;
  onClose: () => void;
  onSubmit: (payload: { expected_active_version: number | null; actions: ActivateNowActionPayload[] }) => void;
};

type FormValues = {
  selectedActionIds?: number[];
};

export function PrescriptionDrawer({ open, actions, currentPrescription, submitting, onClose, onSubmit }: Props) {
  const [form] = Form.useForm<FormValues>();
  const initialSelected = useMemo(
    () => currentPrescription?.actions.map((item) => item.action_library_item) ?? [],
    [currentPrescription],
  );

  const submit = () => {
    const selected = form.getFieldValue("selectedActionIds") ?? initialSelected;
    const selectedActions = actions.filter((action) => selected.includes(action.id));
    onSubmit({
      expected_active_version: currentPrescription?.version ?? null,
      actions: selectedActions.map((action, index) => {
        const mode = getActionParameterMode(action.action_type);
        return {
          action_library_item: action.id,
          weekly_frequency: action.suggested_frequency,
          duration_minutes: action.suggested_duration_minutes,
          sets: mode === "count" ? action.suggested_sets : null,
          repetitions: mode === "count" ? action.suggested_repetitions : null,
          difficulty: action.default_difficulty,
          notes: "",
          sort_order: index,
        };
      }),
    });
  };

  return (
    <Drawer
      title={currentPrescription ? "调整处方" : "开具处方"}
      open={open}
      onClose={onClose}
      width={720}
      extra={
        <Button type="primary" loading={submitting} onClick={submit}>
          保存并立即生效
        </Button>
      }
    >
      <Form form={form} layout="vertical" initialValues={{ selectedActionIds: initialSelected }}>
        <Form.Item name="selectedActionIds" label="选择动作" rules={[{ required: true, message: "至少选择一个动作" }]}>
          <Checkbox.Group style={{ width: "100%" }}>
            <Space direction="vertical" style={{ width: "100%" }}>
              {actions.map((action) => (
                <Checkbox key={action.id} value={action.id} aria-label={action.name}>
                  {action.name}
                </Checkbox>
              ))}
            </Space>
          </Checkbox.Group>
        </Form.Item>
        <Form.Item label="处方参数">
          <Input.TextArea
            readOnly
            autoSize={{ minRows: 4 }}
            value="本期参数默认使用动作库建议值；时长型动作以频次和时长为主，计数型动作以频次、组数、次数为主。"
          />
        </Form.Item>
        <Form.Item label="预计单次时长预览">
          <InputNumber disabled value={actions[0]?.suggested_duration_minutes ?? undefined} addonAfter="分钟" />
        </Form.Item>
      </Form>
    </Drawer>
  );
}
```

- [ ] **Step 10: 重写 PrescriptionPanel**

Modify `frontend/src/pages/prescriptions/PrescriptionPanel.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Popconfirm, Space, Table, Tabs, Tag, message } from "antd";
import { useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";
import { FixedActionLibraryTab } from "./FixedActionLibraryTab";
import { PrescriptionDrawer } from "./PrescriptionDrawer";
import type { ActionLibraryItem, Prescription } from "./types";

type Props = {
  projectPatientId: number;
};

export function PrescriptionPanel({ projectPatientId }: Props) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const qc = useQueryClient();

  const currentQuery = useQuery({
    queryKey: ["current-prescription", projectPatientId],
    queryFn: async () => {
      const r = await apiClient.get<Prescription | null>("/prescriptions/current/", {
        params: { project_patient: projectPatientId },
      });
      return r.data;
    },
  });

  const historyQuery = useQuery({
    queryKey: ["prescription-history", projectPatientId],
    queryFn: async () => {
      const r = await apiClient.get<Prescription[]>("/prescriptions/", {
        params: { project_patient: projectPatientId },
      });
      return r.data;
    },
  });

  const actionsQuery = useQuery({
    queryKey: ["motion-actions"],
    queryFn: async () => {
      const r = await apiClient.get<ActionLibraryItem[]>("/prescriptions/actions/", {
        params: { training_type: "运动训练", internal_type: "motion" },
      });
      return r.data;
    },
  });

  const activateMutation = useMutation({
    mutationFn: async (payload: unknown) => {
      const r = await apiClient.post<Prescription>(
        `/studies/project-patients/${projectPatientId}/prescriptions/activate-now/`,
        payload,
      );
      return r.data;
    },
    onSuccess: async () => {
      message.success("处方已生效");
      setDrawerOpen(false);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["current-prescription", projectPatientId] }),
        qc.invalidateQueries({ queryKey: ["prescription-history", projectPatientId] }),
      ]);
    },
  });

  const terminateMutation = useMutation({
    mutationFn: async (prescriptionId: number) => {
      const r = await apiClient.post<Prescription>(`/prescriptions/${prescriptionId}/terminate/`);
      return r.data;
    },
    onSuccess: async () => {
      message.success("处方已终止");
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["current-prescription", projectPatientId] }),
        qc.invalidateQueries({ queryKey: ["prescription-history", projectPatientId] }),
      ]);
    },
  });

  const current = currentQuery.data ?? null;
  const actions = actionsQuery.data ?? [];

  return (
    <Card
      title="处方管理"
      extra={
        <Space>
          <Link to={`/patient-sim/project-patients/${projectPatientId}`}>打开跟练模拟</Link>
          {current ? (
            <Popconfirm
              title="确认终止当前处方？"
              description="终止后患者端将无法继续按该处方提交训练。"
              okText="确认终止"
              cancelText="取消"
              onConfirm={() => terminateMutation.mutate(current.id)}
            >
              <Button danger loading={terminateMutation.isPending}>
                终止处方
              </Button>
            </Popconfirm>
          ) : null}
          <Button type="primary" onClick={() => setDrawerOpen(true)}>
            {current ? "调整处方" : "开具处方"}
          </Button>
        </Space>
      }
    >
      <Tabs
        items={[
          {
            key: "prescription",
            label: "处方管理",
            children: (
              <Space direction="vertical" style={{ width: "100%" }}>
                {!current ? (
                  <Alert type="info" showIcon message="当前暂无生效处方。" />
                ) : (
                  <Alert type="success" showIcon message={`当前生效处方 v${current.version}`} />
                )}
                <Table
                  rowKey="id"
                  loading={historyQuery.isLoading}
                  dataSource={historyQuery.data ?? []}
                  columns={[
                    { title: "版本", dataIndex: "version", render: (v) => `v${v}` },
                    { title: "状态", dataIndex: "status", render: (v) => <Tag>{v}</Tag> },
                    { title: "开设医生", dataIndex: "opened_by_name" },
                    { title: "生效时间", dataIndex: "effective_at" },
                  ]}
                  expandable={{
                    expandedRowRender: (record) => (
                      <Table
                        rowKey="id"
                        pagination={false}
                        dataSource={record.actions}
                        columns={[
                          { title: "动作", dataIndex: "action_name_snapshot" },
                          { title: "类型", dataIndex: "action_type_snapshot" },
                          { title: "频次", dataIndex: "weekly_frequency" },
                          { title: "时长", dataIndex: "duration_minutes", render: (v) => (v ? `${v} 分钟` : "—") },
                          { title: "组数", dataIndex: "sets", render: (v) => v ?? "—" },
                          { title: "次数", dataIndex: "repetitions", render: (v) => v ?? "—" },
                          { title: "视频", dataIndex: "video_url_snapshot", render: (v) => (v ? "已配置" : "待配置") },
                        ]}
                      />
                    ),
                  }}
                />
              </Space>
            ),
          },
          {
            key: "actions",
            label: "固定动作库",
            children: <FixedActionLibraryTab actions={actions} />,
          },
        ]}
      />
      <PrescriptionDrawer
        open={drawerOpen}
        actions={actions}
        currentPrescription={current}
        submitting={activateMutation.isPending}
        onClose={() => setDrawerOpen(false)}
        onSubmit={(payload) => activateMutation.mutate(payload)}
      />
    </Card>
  );
}
```

- [ ] **Step 11: 运行处方前端测试**

Run:

```bash
cd frontend && npm run test -- src/pages/prescriptions/prescriptionUtils.test.ts src/pages/prescriptions/PrescriptionPanel.test.tsx
```

Expected: PASS.

- [ ] **Step 12: 提交医生端处方 UI**

Run:

```bash
git add frontend/src/pages/prescriptions
git commit -m "feat(frontend): 新增项目患者处方管理界面"
```

### Task 5: 前端路由集成与患者端模拟跟练页

**Files:**
- Create: `frontend/src/pages/patient-sim/PatientSimTrainingPage.tsx`
- Create: `frontend/src/pages/patient-sim/PatientSimTrainingPage.test.tsx`
- Modify: `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: 写患者端模拟页失败测试**

Create `frontend/src/pages/patient-sim/PatientSimTrainingPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PatientSimTrainingPage } from "./PatientSimTrainingPage";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/patient-sim/project-patients/:projectPatientId" element={<PatientSimTrainingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const prescription = {
  id: 1,
  project_patient: 9001,
  version: 1,
  opened_by: 1,
  opened_by_name: "测试医生",
  opened_at: "2026-05-14T10:00:00+08:00",
  effective_at: "2026-05-14T10:00:00+08:00",
  status: "active",
  note: "",
  actions: [
    {
      id: 11,
      prescription: 1,
      action_library_item: 101,
      action_name_snapshot: "坐站转移训练",
      training_type_snapshot: "运动训练",
      internal_type_snapshot: "motion",
      action_type_snapshot: "平衡训练",
      action_instruction_snapshot: "坐稳后起身，再缓慢坐下。",
      video_url_snapshot: "",
      has_ai_supervision_snapshot: true,
      weekly_frequency: "2 次/周",
      duration_minutes: 15,
      sets: 2,
      repetitions: 10,
      difficulty: "中",
      notes: "",
      sort_order: 0,
    },
  ],
};

describe("PatientSimTrainingPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockResolvedValue({ data: prescription });
    mockPost.mockResolvedValue({ data: { id: 99 } });
  });

  afterEach(() => cleanup());

  it("shows only current prescription actions and submits one training record", async () => {
    renderAt("/patient-sim/project-patients/9001");

    expect(await screen.findByText("当前处方 v1")).toBeInTheDocument();
    fireEvent.click(screen.getByText("坐站转移训练"));
    expect(screen.getByText("坐稳后起身，再缓慢坐下。")).toBeInTheDocument();
    expect(screen.getByText("视频待配置")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "提交训练记录" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/patient-sim/project-patients/9001/training-records/",
        expect.objectContaining({
          prescription_action: 11,
          status: "completed",
        }),
      );
    });
  });

  it("shows empty state without active prescription", async () => {
    mockGet.mockResolvedValue({ data: null });

    renderAt("/patient-sim/project-patients/9001");

    expect(await screen.findByText("暂无可执行处方")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 运行患者端模拟页测试确认失败**

Run:

```bash
cd frontend && npm run test -- src/pages/patient-sim/PatientSimTrainingPage.test.tsx
```

Expected: FAIL，组件不存在。

- [ ] **Step 3: 实现患者端模拟页**

Create `frontend/src/pages/patient-sim/PatientSimTrainingPage.tsx`:

```tsx
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Empty, Form, Input, InputNumber, List, Space, Tag, message } from "antd";
import dayjs from "dayjs";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import type { Prescription, PrescriptionAction } from "../prescriptions/types";

export function PatientSimTrainingPage() {
  const { projectPatientId } = useParams<{ projectPatientId: string }>();
  const id = Number(projectPatientId);
  const [selected, setSelected] = useState<PrescriptionAction | null>(null);

  const { data, isError, isLoading } = useQuery({
    queryKey: ["patient-sim-current-prescription", id],
    queryFn: async () => {
      const r = await apiClient.get<Prescription | null>(`/patient-sim/project-patients/${id}/current-prescription/`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  const submitMutation = useMutation({
    mutationFn: async (action: PrescriptionAction) => {
      const r = await apiClient.post(`/patient-sim/project-patients/${id}/training-records/`, {
        prescription_action: action.id,
        training_date: dayjs().format("YYYY-MM-DD"),
        status: "completed",
        actual_duration_minutes: action.duration_minutes ?? 1,
        form_data: {
          completed_sets: action.sets,
          completed_repetitions: action.repetitions,
          perceived_difficulty: action.difficulty,
          discomfort: "无",
        },
        note: "",
      });
      return r.data;
    },
    onSuccess: () => message.success("训练记录已提交"),
  });

  if (!Number.isFinite(id)) return <Alert type="error" message="无效的项目患者 ID" />;
  if (isError) return <Alert type="error" message="无法读取当前处方" />;
  if (!isLoading && !data) return <Empty description="暂无可执行处方" />;

  return (
    <Card loading={isLoading} title={data ? `当前处方 v${data.version}` : "患者跟练模拟"}>
      {data && (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Descriptions size="small" bordered column={2}>
            <Descriptions.Item label="生效时间">{data.effective_at ?? "—"}</Descriptions.Item>
            <Descriptions.Item label="动作数量">{data.actions.length}</Descriptions.Item>
          </Descriptions>
          <List
            dataSource={data.actions}
            renderItem={(action) => (
              <List.Item onClick={() => setSelected(action)} style={{ cursor: "pointer" }}>
                <List.Item.Meta
                  title={action.action_name_snapshot}
                  description={
                    <Space wrap>
                      <Tag>{action.action_type_snapshot}</Tag>
                      <Tag>{action.weekly_frequency || "未配置频次"}</Tag>
                      <Tag>{action.duration_minutes ? `${action.duration_minutes} 分钟` : "未配置时长"}</Tag>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
          {selected && (
            <Card type="inner" title={selected.action_name_snapshot}>
              <Space direction="vertical" style={{ width: "100%" }}>
                {selected.video_url_snapshot ? (
                  <video src={selected.video_url_snapshot} controls style={{ width: "100%", maxHeight: 320 }} />
                ) : (
                  <Alert type="info" message="视频待配置" />
                )}
                <p>{selected.action_instruction_snapshot || "暂无动作说明"}</p>
                <Descriptions size="small" bordered column={2}>
                  <Descriptions.Item label="频次">{selected.weekly_frequency || "—"}</Descriptions.Item>
                  <Descriptions.Item label="时长">{selected.duration_minutes ? `${selected.duration_minutes} 分钟` : "—"}</Descriptions.Item>
                  <Descriptions.Item label="组数">{selected.sets ?? "—"}</Descriptions.Item>
                  <Descriptions.Item label="次数">{selected.repetitions ?? "—"}</Descriptions.Item>
                </Descriptions>
                <Form layout="vertical">
                  <Form.Item label="实际时长">
                    <InputNumber value={selected.duration_minutes ?? 1} min={1} addonAfter="分钟" />
                  </Form.Item>
                  <Form.Item label="备注">
                    <Input.TextArea placeholder="可记录本次跟练情况" />
                  </Form.Item>
                </Form>
                <Button type="primary" loading={submitMutation.isPending} onClick={() => submitMutation.mutate(selected)}>
                  提交训练记录
                </Button>
              </Space>
            </Card>
          )}
        </Space>
      )}
    </Card>
  );
}
```

- [ ] **Step 4: 集成处方入口和路由**

Modify imports in `frontend/src/app/App.tsx`:

```tsx
import { PrescriptionPanel } from "../pages/prescriptions/PrescriptionPanel";
import { PatientSimTrainingPage } from "../pages/patient-sim/PatientSimTrainingPage";
```

Add routes inside `AdminLayout`:

```tsx
<Route
  path="/research-entry/project-patients/:projectPatientId/prescriptions"
  element={<PrescriptionRouteWrapper />}
/>
<Route path="/patient-sim/project-patients/:projectPatientId" element={<PatientSimTrainingPage />} />
```

Add wrapper in same file above `App`:

```tsx
function PrescriptionRouteWrapper() {
  const { projectPatientId } = useParams<{ projectPatientId: string }>();
  const id = Number(projectPatientId);
  return <PrescriptionPanel projectPatientId={id} />;
}
```

Add `useParams` to App import:

```tsx
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
```

- [ ] **Step 5: Add prescription link in research entry page**

Modify `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx` extra links:

```tsx
<Link to={`/research-entry/project-patients/${data.id}/prescriptions`}>处方</Link>
<Link to={`/patients/${data.patient}/crf-baseline`}>基线资料</Link>
<Link to={`/crf?projectPatientId=${data.id}`}>打开 CRF</Link>
```

- [ ] **Step 6: Update App test mocks for new routes**

Add these mock branches to `frontend/src/app/App.test.tsx` `mockGet.mockImplementation` so new route imports cannot trigger unmocked endpoint failures:

```ts
if (url === "/prescriptions/current/") return Promise.resolve({ data: null });
if (url === "/prescriptions/") return Promise.resolve({ data: [] });
if (url === "/prescriptions/actions/") return Promise.resolve({ data: [] });
if (url === "/patient-sim/project-patients/9001/current-prescription/") return Promise.resolve({ data: null });
```

- [ ] **Step 7: Run patient sim and route-related frontend tests**

Run:

```bash
cd frontend && npm run test -- src/pages/patient-sim/PatientSimTrainingPage.test.tsx src/pages/research-entry/ProjectPatientResearchEntryPage.test.tsx src/app/App.test.tsx
```

Expected: all selected tests PASS.

- [ ] **Step 8: 提交患者端模拟页和路由集成**

Run:

```bash
git add frontend/src/app/App.tsx frontend/src/app/App.test.tsx frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx frontend/src/pages/patient-sim
git commit -m "feat(frontend): 新增患者端模拟跟练页"
```

### Task 6: 全量验证与计划收口

**Files:**
- Modify: `docs/superpowers/plans/2026-05-14-prescription-motion-training.md`

- [ ] **Step 1: 运行后端处方与训练测试**

Run:

```bash
cd backend && pytest apps/prescriptions/tests apps/training/tests -v
```

Expected: all selected tests PASS.

- [ ] **Step 2: 运行后端全量测试**

Run:

```bash
cd backend && pytest
```

Expected: all tests PASS.

- [ ] **Step 3: 运行前端相关测试**

Run:

```bash
cd frontend && npm run test -- src/pages/prescriptions src/pages/patient-sim src/pages/research-entry/ProjectPatientResearchEntryPage.test.tsx src/app/App.test.tsx
```

Expected: all selected tests PASS.

- [ ] **Step 4: 运行前端全量测试、lint、build**

Run:

```bash
cd frontend && npm run test
cd frontend && npm run lint
cd frontend && npm run build
```

Expected: all commands PASS.

- [ ] **Step 5: 标记计划执行记录**

At top of `docs/superpowers/plans/2026-05-14-prescription-motion-training.md`, add an execution record after the header block:

```markdown
执行记录（2026-05-14, codex）：Task 1-6 已落地于 commit <short-sha>
```

Replace `<short-sha>` with the final implementation commit short SHA returned by:

```bash
git rev-parse --short HEAD
```

- [ ] **Step 6: 提交计划收口记录**

Run:

```bash
git add docs/superpowers/plans/2026-05-14-prescription-motion-training.md
git commit -m "docs(plan): 标记运动训练处方实施完成"
```

---

## Self-Review

### Spec Coverage

- 固定动作库预置 5 个运动训练动作：Task 1。
- 医生只能只读查看动作库：Task 2 后端 `ReadOnlyModelViewSet`，Task 4 前端只读 Tab。
- 动作字段调整：Task 1。
- `action_type` 驱动时长型/计数型表单：Task 1 后端字段，Task 4 前端工具和表单。
- 处方立即生效并归档旧 active：Task 2。
- 处方动作快照：Task 1 和 Task 2。
- 患者端模拟页只显示 current active 处方动作：Task 3 和 Task 5。
- 单动作训练提交：Task 3 和 Task 5。
- 旧处方动作不能提交训练：Task 3。
- 终止处方保留既有接口和二次确认前端入口：Task 4 的 `PrescriptionPanel` 增加 `Popconfirm` 和 `POST /api/prescriptions/<id>/terminate/` mutation。

### Placeholder Scan

未发现占位式任务描述。所有新增文件均给出具体路径、测试、命令和核心代码。

### Type Consistency

- 后端动作字段统一使用 `instruction_text`、`has_ai_supervision`。
- 后端处方动作快照统一使用 `action_instruction_snapshot`、`video_url_snapshot`、`has_ai_supervision_snapshot`、`weekly_frequency`、`repetitions`。
- 前端类型与后端 serializer 字段一致。
- API 路径统一使用当前项目实际前缀 `/api/studies/project-patients/`，前端 `apiClient` 内调用省略 `/api`。
