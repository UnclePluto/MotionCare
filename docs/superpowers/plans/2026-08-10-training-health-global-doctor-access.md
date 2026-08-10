# 训练与健康全医生可见实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> 状态：implemented
> 日期：2026-08-10
> 关联：`docs/superpowers/specs/2026-08-10-training-health-global-doctor-access-design.md`
> 执行记录（2026-08-10, Codex）：Task 1 已落地于 `27db6dd`；Task 2 已落地并经审查强化于 `d160d89`、`ba5e52c`。Task 3 全量验证：后端 `693 passed`，Ruff 返回 `All checks passed!`，`makemigrations --check --dry-run` 返回 `No changes detected`；管理端 `256 passed`，lint 为 `0 errors, 5 warnings`，生产 build 成功；小程序 `354 passed`，开发配置及 `TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api` 生产 API 配置两次微信构建均成功。最终 `git diff --check` 通过；提交 `4f73864` 前工作树仅包含本计划执行记录，提交后 `git status --short` 为空。

**Goal:** 让所有医生和管理员默认查看全部已入组患者的训练、视频、分析与穿戴健康数据，同时通过配置开关保留原有医生行级过滤策略。

**Architecture:** 保持 `accessible_project_patients(user)` 为训练与健康读取链路的唯一数据范围入口，在其中根据 `TRAINING_HEALTH_ENFORCE_ROW_SCOPE` 选择“全部已入组患者”或既有三类医生行级过滤。列表、详情、视频和穿戴健康无需各自增加分支；测试分别固定默认开放和开关开启后的旧权限语义。

**Tech Stack:** Django 5、Django REST Framework、pytest-django、PostgreSQL、现有 React/Vitest 与 Taro/Vitest 验证链路。

## Global Constraints

- `TRAINING_HEALTH_ENFORCE_ROW_SCOPE` 默认必须为 `False`；生产环境未配置该变量时所有医生可见全部已入组患者。
- “全部患者”只包含至少存在一条 `ProjectPatient` 的患者；未入组患者不得进入训练与健康列表或详情。
- `IsAdminOrDoctor` 必须继续保护所有医生端训练与健康接口；不得开放匿名访问或患者端跨患者访问。
- 开关开启时必须完整恢复原规则：患者主治医生、项目创建人或入组创建人任一匹配即可访问；管理员始终全局可见。
- 训练列表、详情、视频下载、动作分析、训练视频健康时间窗、穿戴测量、日汇总、同步状态和项目汇总必须共享同一读取范围。
- 不修改患者小程序鉴权、设备管理权限、设备命令、绑定/解绑、处方或训练写入规则。
- 不新增模型、迁移、前端页面、依赖或权限管理界面。
- 不改写历史 spec/plan；只在本计划中记录实施进度。

---

### Task 1: 增加可切换的数据范围策略并改造训练追踪测试

**Files:**
- Modify: `backend/config/settings.py:23-26`
- Modify: `backend/apps/training/tracking.py:1-39`
- Modify: `backend/apps/training/tests/test_tracking_api.py:1-12,473-563,907-966`
- Modify: `deploy/env.production.example:7-12`

**Interfaces:**
- Consumes: `User.role`、`ProjectPatient.objects.select_related("patient", "project", "group")`、环境变量 `TRAINING_HEALTH_ENFORCE_ROW_SCOPE`。
- Produces: `accessible_project_patients(user) -> QuerySet[ProjectPatient]`，函数签名与调用方不变；默认返回全部项目患者，配置开启时返回既有行级过滤结果。

- [x] **Step 1: 为默认开放、未入组排除和权限恢复编写失败测试**

在 `test_tracking_api.py` 增加 `override_settings` 导入，并增加以下测试。使用现有 `_doctor`、`_patient`、`_project_patient` 和 `_client` helper，不创建新的测试工厂：

```python
from django.test import override_settings


@pytest.mark.django_db
def test_tracking_is_global_for_doctors_by_default_and_excludes_unenrolled_patient(doctor):
    other_doctor = _doctor(phone="13800008881", name="其他主管医生")
    enrolled_patient = _patient(
        other_doctor,
        name="跨医生可见患者",
        phone="13900008881",
    )
    other_pp = _project_patient(
        other_doctor,
        enrolled_patient,
        project_name="跨医生研究",
    )
    second_pp = _project_patient(
        other_doctor,
        enrolled_patient,
        project_name="跨医生第二研究",
    )
    unenrolled_patient = _patient(
        other_doctor,
        name="未入组患者",
        phone="13900008882",
    )

    list_response = _client(doctor).get(
        "/api/training/tracking/patients/",
        {"q": "跨医生可见患者"},
    )
    detail_response = _client(doctor).get(
        f"/api/training/tracking/patients/{enrolled_patient.id}/"
    )
    unenrolled_list = _client(doctor).get(
        "/api/training/tracking/patients/",
        {"q": "未入组患者"},
    )
    unenrolled_detail = _client(doctor).get(
        f"/api/training/tracking/patients/{unenrolled_patient.id}/"
    )

    assert list_response.status_code == 200
    assert [row["patient"]["id"] for row in list_response.data] == [enrolled_patient.id]
    assert list_response.data[0]["project_count"] == 2
    assert detail_response.status_code == 200
    assert {
        item["id"] for item in detail_response.data["project_patients"]
    } == {other_pp.id, second_pp.id}
    assert unenrolled_list.data == []
    assert unenrolled_detail.status_code == 404


@pytest.mark.django_db
@override_settings(TRAINING_HEALTH_ENFORCE_ROW_SCOPE=True)
def test_tracking_row_scope_can_be_reenabled_without_changing_callers(doctor):
    other_doctor = _doctor(phone="13800008883", name="受限主管医生")
    patient = _patient(other_doctor, name="恢复受限患者", phone="13900008883")
    project_patient = _project_patient(
        other_doctor,
        patient,
        project_name="恢复权限研究",
    )

    list_response = _client(doctor).get(
        "/api/training/tracking/patients/",
        {"q": "恢复受限患者"},
    )
    detail_response = _client(doctor).get(
        f"/api/training/tracking/patients/{patient.id}/"
    )
    admin_response = _client(_admin()).get(
        f"/api/training/tracking/patients/{patient.id}/",
        {"project_patient": project_patient.id},
    )

    assert list_response.data == []
    assert detail_response.status_code == 404
    assert admin_response.status_code == 200
```

同时给以下现有测试增加 `@override_settings(TRAINING_HEALTH_ENFORCE_ROW_SCOPE=True)`，保留它们对旧权限策略的验证：

- `test_tracking_list_query_count_is_constant_and_excludes_hidden_patient`
- `test_tracking_detail_hides_inaccessible_patient_and_rejects_invalid_project_patient`
- `test_tracking_allows_project_patient_creator_to_access_patient`

- [x] **Step 2: 运行训练追踪测试并确认默认开放用例失败**

Run:

```bash
cd backend
pytest apps/training/tests/test_tracking_api.py \
  -k "global_for_doctors or row_scope_can_be_reenabled or excludes_hidden_patient or hides_inaccessible or project_patient_creator" \
  -q
```

Expected: 新增默认开放用例失败，医生查询其他医生患者仍返回空列表或 404；所有标记为开关开启的旧权限测试继续通过。

- [x] **Step 3: 增加配置和最小权限策略实现**

在 `backend/config/settings.py` 的 Cookie/安全配置附近加入：

```python
TRAINING_HEALTH_ENFORCE_ROW_SCOPE = (
    os.getenv("TRAINING_HEALTH_ENFORCE_ROW_SCOPE", "false").lower() == "true"
)
```

在 `backend/apps/training/tracking.py` 导入 Django settings，并把现有函数改为：

```python
from django.conf import settings


def _doctor_scoped_project_patients(qs, user):
    return qs.filter(
        Q(patient__primary_doctor=user)
        | Q(project__created_by=user)
        | Q(created_by=user)
    )


def accessible_project_patients(user):
    qs = ProjectPatient.objects.select_related("patient", "project", "group")
    if _is_admin(user) or not settings.TRAINING_HEALTH_ENFORCE_ROW_SCOPE:
        return qs
    return _doctor_scoped_project_patients(qs, user)
```

不要改变 `accessible_project_patients` 的名称、参数、返回类型或任何调用方。

在 `deploy/env.production.example` 的 Django 配置区加入显式默认值：

```dotenv
TRAINING_HEALTH_ENFORCE_ROW_SCOPE=false
```

- [x] **Step 4: 运行训练追踪完整测试并确认通过**

Run:

```bash
cd backend
pytest apps/training/tests/test_tracking_api.py -q
```

Expected: 所有训练追踪测试通过；默认开放、未入组排除、旧权限恢复、管理员全局可见和恒定查询数均被覆盖。

- [x] **Step 5: 检查迁移和差异质量**

Run:

```bash
cd backend
python manage.py makemigrations --check --dry-run
ruff check config/settings.py apps/training/tracking.py apps/training/tests/test_tracking_api.py
cd ..
git diff --check
```

Expected: `No changes detected`；Ruff 和差异检查均返回 0。

- [x] **Step 6: 提交统一权限策略**

```bash
git add \
  backend/config/settings.py \
  backend/apps/training/tracking.py \
  backend/apps/training/tests/test_tracking_api.py \
  deploy/env.production.example
git commit -m "feat(training): 增加训练健康数据范围策略"
```

---

### Task 2: 固化视频、动作分析和穿戴健康的跨医生访问契约

**Files:**
- Modify: `backend/apps/training/tests/test_training_video_api.py:1-130`
- Modify: `backend/apps/training/tests/test_training_video_wearable_api.py:1-125,409-423`
- Modify: `backend/apps/wearables/tests/test_queries_api.py:1-75`

**Interfaces:**
- Consumes: Task 1 的 `accessible_project_patients(user)` 和 `TRAINING_HEALTH_ENFORCE_ROW_SCOPE`。
- Produces: 默认跨医生访问与开关开启后旧权限恢复的端到端 API 回归测试；不新增生产函数。

- [x] **Step 1: 运行受影响的旧测试，观察权限断言失败**

Run:

```bash
cd backend
pytest \
  apps/training/tests/test_training_video_api.py::test_inaccessible_doctor_receives_404_for_all_video_endpoints \
  apps/training/tests/test_training_video_wearable_api.py::test_wearable_window_is_hidden_from_inaccessible_doctor \
  apps/wearables/tests/test_queries_api.py::test_measurements_require_accessible_patient_and_matching_project_patient \
  -q
```

Expected: 旧测试失败，因为默认配置下其他医生已能越过原行级过滤；失败必须发生在原来的 404 断言。

- [x] **Step 2: 更新视频端点测试，分别覆盖默认开放和权限恢复**

保留 `test_inaccessible_doctor_receives_404_for_all_video_endpoints` 的参数化结构，在它上方增加：

```python
@override_settings(TRAINING_HEALTH_ENFORCE_ROW_SCOPE=True)
```

并增加默认开放测试：

```python
@pytest.mark.django_db
@override_settings(
    TRAINING_HEALTH_ENFORCE_ROW_SCOPE=False,
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_DOWNLOAD_DOMAIN="https://cdn.example.com",
)
def test_doctor_can_access_other_doctors_video_endpoints_by_default(
    project_patient,
    active_prescription,
    django_capture_on_commit_callbacks,
):
    action = _shoulder_press_action(active_prescription)
    video = _video(project_patient, active_prescription, action)
    other_doctor = _other_doctor()

    download = _client(other_doctor).get(
        f"/api/training/videos/{video.id}/download-url/"
    )
    latest = _client(other_doctor).get(
        f"/api/training/videos/{video.id}/analysis-jobs/latest/"
    )
    with patch("apps.training.tasks.run_motion_analysis_job.delay") as delay:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            created = _client(other_doctor).post(
                f"/api/training/videos/{video.id}/analysis-jobs/"
            )

    assert download.status_code == 200
    assert download.data["url"].startswith(
        f"https://cdn.example.com/{video.object_key}?e="
    )
    assert latest.status_code == 200
    assert latest.data is None
    assert created.status_code == 201
    job = MotionAnalysisJob.objects.get(pk=created.data["id"])
    assert job.requested_by == other_doctor
    assert len(callbacks) == 1
    delay.assert_not_called()
```

- [x] **Step 3: 更新训练视频健康时间窗测试**

在 `test_training_video_wearable_api.py` 导入 `override_settings`。给现有
`test_wearable_window_is_hidden_from_inaccessible_doctor` 增加：

```python
@override_settings(TRAINING_HEALTH_ENFORCE_ROW_SCOPE=True)
```

再增加默认开放用例：

```python
@pytest.mark.django_db
def test_wearable_window_is_visible_to_other_doctor_by_default(
    project_patient,
    active_prescription,
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )

    response = _client(_other_doctor()).get(
        f"/api/training/videos/{video.id}/wearable-window/"
    )

    assert response.status_code == 200
    assert response.data == {"available": False}
```

- [x] **Step 4: 更新穿戴健康查询测试**

在 `test_queries_api.py` 导入 `override_settings`。给现有
`test_measurements_require_accessible_patient_and_matching_project_patient` 增加：

```python
@override_settings(TRAINING_HEALTH_ENFORCE_ROW_SCOPE=True)
```

增加一个覆盖患者级四个读接口和项目汇总的默认开放测试：

```python
@pytest.mark.django_db
def test_doctor_can_read_other_doctors_enrolled_patient_health_by_default(doctor):
    owner = User.objects.create_user(
        phone="13800009991",
        password="pass123456",
        name="健康主管医生",
        role=User.Role.DOCTOR,
    )
    patient = Patient.objects.create(
        name="跨医生健康患者",
        gender=Patient.Gender.UNKNOWN,
        age=70,
        phone="13900009991",
        primary_doctor=owner,
    )
    project = StudyProject.objects.create(name="跨医生健康研究", created_by=owner)
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    project_patient = ProjectPatient.objects.create(
        project=project,
        patient=patient,
        group=group,
        created_by=owner,
    )
    common = {
        "project_patient": project_patient.id,
        "start": "2026-07-01",
        "end": "2026-07-02",
    }

    measurements_response = _client(doctor).get(
        f"/api/wearables/patients/{patient.id}/measurements/",
        {**common, "metric_type": "heart_rate"},
    )
    daily_response = _client(doctor).get(
        f"/api/wearables/patients/{patient.id}/daily-summaries/",
        common,
    )
    sync_response = _client(doctor).get(
        f"/api/wearables/patients/{patient.id}/sync-status/"
    )
    project_response = _client(doctor).get(
        f"/api/wearables/projects/{project.id}/summary/",
        {
            "metric_type": "heart_rate",
            "start": "2026-07-01",
            "end": "2026-07-02",
        },
    )

    assert measurements_response.status_code == 200
    assert measurements_response.data["items"] == []
    assert daily_response.status_code == 200
    assert daily_response.data["items"] == []
    assert sync_response.status_code == 200
    assert sync_response.data["binding_id"] is None
    assert project_response.status_code == 200
    assert project_response.data["groups"][0]["patient_count"] == 1
```

现有测试中的“项目患者属于另一个患者”仍必须返回 404，因为这是资源归属校验，不是医生权限；
不要把该断言改为 200。

- [x] **Step 5: 运行所有直接受影响的后端测试**

Run:

```bash
cd backend
pytest \
  apps/training/tests/test_tracking_api.py \
  apps/training/tests/test_training_video_api.py \
  apps/training/tests/test_training_video_wearable_api.py \
  apps/wearables/tests/test_queries_api.py \
  -q
```

Expected: 四个文件全部通过；默认开放测试返回 200，配置开启的旧权限测试返回空列表或 404。

- [x] **Step 6: 提交下游权限契约测试**

```bash
git add \
  backend/apps/training/tests/test_training_video_api.py \
  backend/apps/training/tests/test_training_video_wearable_api.py \
  backend/apps/wearables/tests/test_queries_api.py
git commit -m "test(training): 覆盖跨医生训练与健康访问"
```

---

### Task 3: 全量验证并记录实施结果

**Files:**
- Modify: `docs/superpowers/plans/2026-08-10-training-health-global-doctor-access.md`

**Interfaces:**
- Consumes: Tasks 1–2 的配置、统一查询策略和权限回归测试。
- Produces: 可发布的验证证据和带执行记录的已完成计划；不新增运行时代码。

- [x] **Step 1: 运行后端全量测试和静态检查**

Run:

```bash
cd backend
pytest -q
ruff check .
python manage.py makemigrations --check --dry-run
```

Expected: 后端全量测试通过；Ruff 返回 `All checks passed!`；Django 返回 `No changes detected`。

- [x] **Step 2: 运行管理端验证**

Run:

```bash
cd frontend
npm run test
npm run lint
npm run build
```

Expected: Vitest 全部通过；lint 没有新增 error；生产构建成功。既有警告必须记录但不得把它们描述为本任务新增问题。

- [x] **Step 3: 运行小程序验证和生产配置构建**

Run:

```bash
cd miniapp
npm test
npm run build:weapp
TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api npm run build:weapp
```

Expected: 小程序测试全部通过；开发与生产 API 配置的微信构建均成功。

- [x] **Step 4: 执行最终差异检查**

Run:

```bash
cd ..
git diff --check
git status --short
git log --oneline -5
```

Expected: `git diff --check` 返回 0；工作树只包含本计划执行记录的待提交改动；最近提交包含 Tasks 1–2 的中文提交。

- [x] **Step 5: 更新计划执行记录并提交**

先读取 Tasks 1–2 的实际短 SHA：

```bash
git log --format='%h %s' --grep='feat(training): 增加训练健康数据范围策略' -1
git log --format='%h %s' --grep='test(training): 覆盖跨医生训练与健康访问' -1
```

确认两条命令均返回唯一提交后，把本文件顶部状态改为 `implemented`，将 Tasks 1–3 的全部复选框
改为 `[x]`，并在顶部追加一行执行记录。执行记录必须写入刚读取的两个真实短 SHA，并明确后端、
管理端和小程序验证结果；本计划不预留可被误提交的 SHA 占位文本。

```bash
git add docs/superpowers/plans/2026-08-10-training-health-global-doctor-access.md
git commit -m "docs(training): 标记全医生可见策略完成"
```

- [x] **Step 6: 交付实施结果但不自动发布**

报告以下内容：

- 默认跨医生读取范围和可恢复开关；
- Tasks 1–3 的提交 SHA；
- 四个目标测试文件、后端全量、管理端和小程序验证结果；
- `makemigrations --check --dry-run` 无迁移；
- 未执行合并、推送或生产发布，等待用户单独授权。
