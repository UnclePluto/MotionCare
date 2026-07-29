# Shoulder Press Video Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shoulder-press-only video follow-along flow: miniapp camera recording, Qiniu Kodo direct upload, training record attachment, doctor video review, and manual PP-TinyPose analysis results.

**Architecture:** Keep the existing `ActionLibraryItem -> PrescriptionAction -> TrainingRecord` chain. Add `TrainingVideo` and `MotionAnalysisJob` under `apps.training`, expose patient upload intent/complete APIs under `/api/patient-app/`, expose doctor video/analysis APIs under `/api/training/`, and surface the result in the existing miniapp prescription flow and doctor training tracking page.

**Tech Stack:** Django 5, DRF, PostgreSQL, Celery, Python standard-library HMAC/base64 signing for Qiniu tokens, React 18, Ant Design 5, TanStack Query v5, Taro 4 + React + TypeScript.

## Global Constraints

- Always keep `ProjectPatient` as the patient-project-group relationship carrier; do not create a `PatientPool` model.
- Do not reintroduce `GroupingBatch`, `grouping_batch`, or batch grouping concepts outside historical migrations.
- Training records must still be based on the current active prescription action.
- Only `source_key = motion-resistance-shoulder-press` uses the new video flow in this plan.
- Other `motion` actions keep the existing miniapp `/pages/training/index` form flow.
- Qiniu AK/SK stay server-side in Django settings and environment variables.
- Patient app APIs must derive `ProjectPatient` from the bearer token, not from frontend-supplied patient or project IDs.
- Doctor APIs must enforce backend permission checks and row-level filtering.
- Keep the default local CSRF trusted origins in `backend/config/settings.py`.
- Do not delete existing specs or plans.

---

## File Structure

Backend:

- Create `backend/apps/training/video_models.py`: model definitions for `TrainingVideo` and `MotionAnalysisJob` if the main model file becomes too large.
- Modify `backend/apps/training/models.py`: import video models so Django migrations discover them.
- Create `backend/apps/training/migrations/0002_training_video_analysis.py`: database migration.
- Create `backend/apps/training/qiniu.py`: Qiniu upload-token and private-download URL helpers.
- Create `backend/apps/training/video_services.py`: upload intent, complete upload, download URL, and analysis-job orchestration services.
- Create `backend/apps/training/analysis.py`: deterministic shoulder press rule helpers and PP-TinyPose adapter boundary.
- Create `backend/apps/training/tasks.py`: Celery task entrypoint for analysis.
- Modify `backend/apps/patient_app/serializers.py`: serializers for upload intent and complete.
- Modify `backend/apps/patient_app/views.py`: patient upload intent and complete views.
- Modify `backend/apps/patient_app/urls.py`: patient video API routes.
- Create `backend/apps/training/video_serializers.py`: doctor-facing video and analysis serializers.
- Create `backend/apps/training/video_views.py`: doctor download URL and analysis job views.
- Modify `backend/apps/training/urls.py`: doctor video API routes.
- Modify `backend/apps/training/tracking.py`: include video and analysis summary in recent records.
- Modify `backend/config/__init__.py`: expose Celery app for task autodiscovery.
- Modify `backend/config/settings.py`: Qiniu settings with environment defaults.
- Test `backend/apps/training/tests/test_training_video_api.py`.
- Test `backend/apps/training/tests/test_motion_analysis.py`.
- Test `backend/apps/patient_app/tests/test_patient_app_video_api.py`.
- Test `backend/apps/training/tests/test_tracking_api.py`.

Miniapp:

- Modify `miniapp/src/app.config.ts`: add shoulder press page and upload page.
- Create `miniapp/src/pages/prescription/actionRouting.ts`: decide miniapp action entry URL and button label.
- Create `miniapp/src/pages/shoulder-press/session.ts`: local state and URL builders for pending shoulder press uploads.
- Create `miniapp/src/pages/shoulder-press/api.ts`: upload intent, Qiniu upload, complete calls.
- Create `miniapp/src/pages/shoulder-press/index.tsx`: camera and example-video follow-along page.
- Create `miniapp/src/pages/shoulder-press/upload.tsx`: forced upload waiting page.
- Modify `miniapp/src/pages/prescription/index.tsx`: route shoulder press to the dedicated page.
- Modify `miniapp/src/app.scss`: styles for camera preview, recording controls, and upload progress.
- Test `miniapp/src/pages/shoulder-press/session.test.ts`.
- Test `miniapp/src/pages/shoulder-press/api.test.ts`.
- Test `miniapp/src/pages/prescription/actionRouting.test.ts`.

Doctor frontend:

- Modify `frontend/src/pages/training-tracking/types.ts`: video and analysis fields on recent records.
- Modify `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`: video drawer, analysis action, result columns.
- Modify `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`: UI and API behavior tests.

---

### Task 1: Backend Video Models and Qiniu Helpers

**Files:**
- Create: `backend/apps/training/video_models.py`
- Modify: `backend/apps/training/models.py`
- Create: `backend/apps/training/migrations/0002_training_video_analysis.py`
- Create: `backend/apps/training/qiniu.py`
- Modify: `backend/config/settings.py`
- Test: `backend/apps/training/tests/test_qiniu.py`

**Interfaces:**
- Produces: `TrainingVideo`, `MotionAnalysisJob`, `generate_upload_token(bucket: str, key: str, expires_at: int) -> str`, `private_download_url(base_url: str, expires_at: int) -> str`.
- Consumes: Django settings values `QINIU_ACCESS_KEY`, `QINIU_SECRET_KEY`, `QINIU_BUCKET`, `QINIU_UPLOAD_HOST`, `QINIU_DOWNLOAD_DOMAIN`.

- [ ] **Step 1: Write failing Qiniu signing tests**

Create `backend/apps/training/tests/test_qiniu.py`:

```python
import base64
import json

import pytest
from django.test import override_settings

from apps.training.qiniu import generate_upload_token, private_download_url


@pytest.mark.django_db
@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_generate_upload_token_contains_fixed_bucket_key_scope():
    token = generate_upload_token(
        bucket="motioncare",
        key="training-videos/1/2026/07/10/video.mp4",
        expires_at=1783692000,
    )

    access_key, encoded_sign, encoded_policy = token.split(":")
    assert access_key == "ak-test"
    assert encoded_sign
    policy = json.loads(base64.urlsafe_b64decode(encoded_policy + "==").decode("utf-8"))
    assert policy["scope"] == "motioncare:training-videos/1/2026/07/10/video.mp4"
    assert policy["deadline"] == 1783692000


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_private_download_url_adds_deadline_and_token():
    url = private_download_url(
        "https://cdn.example.com/training-videos/a.mp4",
        expires_at=1783692000,
    )

    assert url.startswith("https://cdn.example.com/training-videos/a.mp4?e=1783692000&token=ak-test:")
```

- [ ] **Step 2: Run Qiniu signing tests and verify failure**

Run: `cd backend && pytest apps/training/tests/test_qiniu.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.training.qiniu'`.

- [ ] **Step 3: Implement Qiniu helper**

Create `backend/apps/training/qiniu.py`:

```python
import base64
import hashlib
import hmac
import json
from urllib.parse import quote, urlencode

from django.conf import settings


def _urlsafe_base64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _sign(data: str) -> str:
    digest = hmac.new(
        settings.QINIU_SECRET_KEY.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return _urlsafe_base64(digest)


def generate_upload_token(*, bucket: str, key: str, expires_at: int) -> str:
    policy = {
        "scope": f"{bucket}:{key}",
        "deadline": expires_at,
        "returnBody": '{"key":"$(key)","hash":"$(etag)","size":$(fsize)}',
    }
    encoded_policy = _urlsafe_base64(
        json.dumps(policy, separators=(",", ":")).encode("utf-8")
    )
    return f"{settings.QINIU_ACCESS_KEY}:{_sign(encoded_policy)}:{encoded_policy}"


def private_download_url(base_url: str, *, expires_at: int) -> str:
    separator = "&" if "?" in base_url else "?"
    unsigned = f"{base_url}{separator}{urlencode({'e': expires_at})}"
    token = f"{settings.QINIU_ACCESS_KEY}:{_sign(unsigned)}"
    return f"{unsigned}&token={quote(token)}"
```

- [ ] **Step 4: Add Qiniu settings defaults**

Modify `backend/config/settings.py` near the existing media settings:

```python
QINIU_ACCESS_KEY = os.getenv("QINIU_ACCESS_KEY", "")
QINIU_SECRET_KEY = os.getenv("QINIU_SECRET_KEY", "")
QINIU_BUCKET = os.getenv("QINIU_BUCKET", "motioncare-training")
QINIU_UPLOAD_HOST = os.getenv("QINIU_UPLOAD_HOST", "https://upload.qiniup.com")
QINIU_DOWNLOAD_DOMAIN = os.getenv("QINIU_DOWNLOAD_DOMAIN", "")
QINIU_UPLOAD_TOKEN_TTL_SECONDS = int(os.getenv("QINIU_UPLOAD_TOKEN_TTL_SECONDS", "1800"))
QINIU_DOWNLOAD_TOKEN_TTL_SECONDS = int(os.getenv("QINIU_DOWNLOAD_TOKEN_TTL_SECONDS", "600"))
TRAINING_VIDEO_MAX_SIZE_BYTES = int(os.getenv("TRAINING_VIDEO_MAX_SIZE_BYTES", str(200 * 1024 * 1024)))
TRAINING_VIDEO_MAX_DURATION_SECONDS = int(os.getenv("TRAINING_VIDEO_MAX_DURATION_SECONDS", "600"))
```

- [ ] **Step 5: Write failing model migration test**

Append to `backend/apps/training/tests/test_qiniu.py`:

```python
from apps.training.models import MotionAnalysisJob, TrainingVideo


@pytest.mark.django_db
def test_training_video_and_analysis_job_models_are_available(
    project_patient,
    active_prescription,
    prescription_action,
):
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        bucket="motioncare",
        object_key="training-videos/1/a.mp4",
        content_type="video/mp4",
        size_bytes=100,
        duration_seconds=30,
        upload_token_expires_at="2026-07-10T10:00:00+08:00",
    )
    job = MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=None,
        project_patient=project_patient,
        prescription_action=prescription_action,
        algorithm_name="pp-tiny-pose",
        rule_version="shoulder-press-v1",
    )

    assert video.status == TrainingVideo.Status.UPLOADING
    assert job.status == MotionAnalysisJob.Status.PENDING
```

- [ ] **Step 6: Run model test and verify failure**

Run: `cd backend && pytest apps/training/tests/test_qiniu.py::test_training_video_and_analysis_job_models_are_available -q`

Expected: FAIL with import error for `TrainingVideo`.

- [ ] **Step 7: Implement models**

Create `backend/apps/training/video_models.py`:

```python
from django.conf import settings
from django.db import models

from apps.common.models import UserStampedModel


class TrainingVideo(UserStampedModel):
    class Status(models.TextChoices):
        UPLOADING = "uploading", "上传中"
        UPLOADED = "uploaded", "已上传"
        ATTACHED = "attached", "已绑定"
        FAILED = "failed", "失败"
        EXPIRED = "expired", "已过期"

    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="training_video_uploads",
    )
    prescription = models.ForeignKey("prescriptions.Prescription", on_delete=models.PROTECT)
    prescription_action = models.ForeignKey(
        "prescriptions.PrescriptionAction",
        on_delete=models.PROTECT,
    )
    training_record = models.OneToOneField(
        "training.TrainingRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="video",
    )
    storage_backend = models.CharField("存储后端", max_length=40, default="qiniu_kodo")
    bucket = models.CharField("空间", max_length=120)
    object_key = models.CharField("对象 Key", max_length=500, unique=True)
    object_hash = models.CharField("对象 Hash", max_length=120, blank=True)
    original_filename = models.CharField("原始文件名", max_length=255, blank=True)
    content_type = models.CharField("文件类型", max_length=120)
    size_bytes = models.PositiveBigIntegerField("文件大小")
    duration_seconds = models.PositiveIntegerField("视频时长")
    status = models.CharField("状态", max_length=20, choices=Status.choices, default=Status.UPLOADING)
    upload_token_expires_at = models.DateTimeField("上传凭证过期时间")
    uploaded_at = models.DateTimeField("上传完成时间", null=True, blank=True)
    failure_reason = models.TextField("失败原因", blank=True)


class MotionAnalysisJob(UserStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "待分析"
        RUNNING = "running", "分析中"
        SUCCEEDED = "succeeded", "分析成功"
        FAILED = "failed", "分析失败"

    training_video = models.ForeignKey(
        TrainingVideo,
        on_delete=models.CASCADE,
        related_name="analysis_jobs",
    )
    training_record = models.ForeignKey(
        "training.TrainingRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="motion_analysis_jobs",
    )
    project_patient = models.ForeignKey("studies.ProjectPatient", on_delete=models.CASCADE)
    prescription_action = models.ForeignKey("prescriptions.PrescriptionAction", on_delete=models.PROTECT)
    status = models.CharField("状态", max_length=20, choices=Status.choices, default=Status.PENDING)
    algorithm_name = models.CharField("算法名称", max_length=80, default="pp-tiny-pose")
    algorithm_version = models.CharField("算法版本", max_length=80, blank=True)
    rule_version = models.CharField("规则版本", max_length=80, default="shoulder-press-v1")
    total_count = models.PositiveIntegerField("总次数", null=True, blank=True)
    standard_count = models.PositiveIntegerField("标准次数", null=True, blank=True)
    nonstandard_count = models.PositiveIntegerField("不标准次数", null=True, blank=True)
    result_payload = models.JSONField("分析结果", default=dict)
    failure_reason = models.TextField("失败原因", blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_motion_analysis_jobs",
    )
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("完成时间", null=True, blank=True)
```

Modify `backend/apps/training/models.py` after `TrainingRecord`:

```python
from .video_models import MotionAnalysisJob, TrainingVideo  # noqa: E402,F401
```

- [ ] **Step 8: Generate migration**

Run: `cd backend && python manage.py makemigrations training`

Expected: creates `backend/apps/training/migrations/0002_training_video_analysis.py`.

- [ ] **Step 9: Run backend tests for this task**

Run: `cd backend && pytest apps/training/tests/test_qiniu.py -q`

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/config/settings.py backend/apps/training/models.py backend/apps/training/video_models.py backend/apps/training/qiniu.py backend/apps/training/migrations/0002_training_video_analysis.py backend/apps/training/tests/test_qiniu.py
git commit -m "feat(training): 新增训练视频模型与七牛签名"
```

### Task 2: Patient Upload Intent and Complete APIs

**Files:**
- Create: `backend/apps/training/video_services.py`
- Modify: `backend/apps/patient_app/serializers.py`
- Modify: `backend/apps/patient_app/views.py`
- Modify: `backend/apps/patient_app/urls.py`
- Test: `backend/apps/patient_app/tests/test_patient_app_video_api.py`

**Interfaces:**
- Consumes: `TrainingVideo`, `generate_upload_token`, `create_training_record`.
- Produces: `create_upload_intent(project_patient, prescription_action_id, content_type, size_bytes, duration_seconds) -> dict` and `complete_training_video(project_patient, video_id, key, object_hash, training_date, actual_duration_minutes, note) -> tuple[TrainingVideo, bool]`; the boolean is true only when this call created the training record.

- [ ] **Step 1: Write failing patient video API tests**

Create `backend/apps/patient_app/tests/test_patient_app_video_api.py`:

```python
import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.patient_app.services import bind_project_patient_with_code, create_binding_code
from apps.prescriptions.models import ActionLibraryItem
from apps.training.models import TrainingRecord, TrainingVideo


def _auth_client(project_patient, doctor):
    code, _ = create_binding_code(project_patient=project_patient, created_by=doctor)
    token, _ = bind_project_patient_with_code(code, wx_openid="openid-video")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _shoulder_press_action(active_prescription):
    item = ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press")
    return active_prescription.add_action_snapshot(
        item,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=10,
    )


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
)
def test_patient_app_creates_shoulder_press_upload_intent(project_patient, doctor, active_prescription):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        {
            "prescription_action": action.id,
            "content_type": "video/mp4",
            "size_bytes": 1024,
            "duration_seconds": 60,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["upload_token"].startswith("ak-test:")
    assert response.data["upload_host"] == "https://upload.qiniup.com"
    video = TrainingVideo.objects.get(pk=response.data["video_id"])
    assert video.prescription_action == action
    assert video.status == TrainingVideo.Status.UPLOADING
    assert video.object_key == response.data["key"]


@pytest.mark.django_db
def test_patient_app_rejects_upload_intent_for_non_shoulder_action(
    project_patient,
    doctor,
    active_prescription,
    prescription_action,
):
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        {
            "prescription_action": prescription_action.id,
            "content_type": "video/mp4",
            "size_bytes": 1024,
            "duration_seconds": 60,
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "肩部推举" in str(response.data)


@pytest.mark.django_db
@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_patient_app_complete_upload_creates_training_record_once(
    project_patient,
    doctor,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    intent = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        {
            "prescription_action": action.id,
            "content_type": "video/mp4",
            "size_bytes": 2048,
            "duration_seconds": 120,
        },
        format="json",
    )

    payload = {
        "key": intent.data["key"],
        "hash": "qiniu-hash",
        "training_date": str(timezone.localdate()),
        "actual_duration_minutes": 2,
        "note": "完成肩部推举",
    }
    first = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        payload,
        format="json",
    )
    second = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        payload,
        format="json",
    )

    assert first.status_code == 201, first.data
    assert second.status_code == 200, second.data
    assert TrainingRecord.objects.filter(project_patient=project_patient).count() == 1
    video = TrainingVideo.objects.get(pk=intent.data["video_id"])
    assert video.status == TrainingVideo.Status.ATTACHED
    assert video.object_hash == "qiniu-hash"
    assert video.training_record_id == first.data["training_record"]["id"]
```

- [ ] **Step 2: Run patient video tests and verify failure**

Run: `cd backend && pytest apps/patient_app/tests/test_patient_app_video_api.py -q`

Expected: FAIL with 404 for `/api/patient-app/training-videos/upload-intent/`.

- [ ] **Step 3: Implement serializers**

Modify `backend/apps/patient_app/serializers.py`:

```python
class PatientAppTrainingVideoUploadIntentSerializer(serializers.Serializer):
    prescription_action = serializers.IntegerField(min_value=1)
    content_type = serializers.ChoiceField(choices=["video/mp4", "video/quicktime"])
    size_bytes = serializers.IntegerField(min_value=1)
    duration_seconds = serializers.IntegerField(min_value=1)


class PatientAppTrainingVideoCompleteSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=500)
    hash = serializers.CharField(max_length=120)
    training_date = serializers.DateField()
    actual_duration_minutes = serializers.IntegerField(min_value=0, max_value=2147483647)
    note = serializers.CharField(required=False, allow_blank=True)
```

- [ ] **Step 4: Implement video services**

Create `backend/apps/training/video_services.py`:

```python
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.prescriptions.models import Prescription, PrescriptionAction

from .models import TrainingRecord, TrainingVideo
from .qiniu import generate_upload_token
from .services import create_training_record

SHOULDER_PRESS_SOURCE_KEY = "motion-resistance-shoulder-press"


def _active_prescription(project_patient):
    return (
        Prescription.objects.filter(project_patient=project_patient, status=Prescription.Status.ACTIVE)
        .order_by("-effective_at", "-id")
        .first()
    )


def _get_current_shoulder_action(project_patient, prescription_action_id):
    active = _active_prescription(project_patient)
    if active is None:
        raise ValidationError("当前无生效处方")
    action = PrescriptionAction.objects.select_related("action_library_item").filter(
        pk=prescription_action_id,
        prescription=active,
    ).first()
    if action is None:
        raise ValidationError("处方已更新，请返回当前处方重新进入")
    if action.action_library_item.source_key != SHOULDER_PRESS_SOURCE_KEY:
        raise ValidationError("当前仅肩部推举支持录像上传")
    return active, action


def _object_key(project_patient_id):
    today = timezone.localdate()
    return (
        f"training-videos/{project_patient_id}/"
        f"{today:%Y/%m/%d}/{uuid.uuid4().hex}.mp4"
    )


@transaction.atomic
def create_upload_intent(*, project_patient, prescription_action_id, content_type, size_bytes, duration_seconds):
    if size_bytes > settings.TRAINING_VIDEO_MAX_SIZE_BYTES:
        raise ValidationError("训练视频文件过大")
    if duration_seconds > settings.TRAINING_VIDEO_MAX_DURATION_SECONDS:
        raise ValidationError("训练视频时长超过限制")
    active, action = _get_current_shoulder_action(project_patient, prescription_action_id)
    expires_at = timezone.now() + timezone.timedelta(seconds=settings.QINIU_UPLOAD_TOKEN_TTL_SECONDS)
    key = _object_key(project_patient.id)
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active,
        prescription_action=action,
        bucket=settings.QINIU_BUCKET,
        object_key=key,
        content_type=content_type,
        size_bytes=size_bytes,
        duration_seconds=duration_seconds,
        upload_token_expires_at=expires_at,
    )
    token = generate_upload_token(
        bucket=settings.QINIU_BUCKET,
        key=key,
        expires_at=int(expires_at.timestamp()),
    )
    return {
        "video_id": video.id,
        "bucket": video.bucket,
        "key": video.object_key,
        "upload_token": token,
        "upload_host": settings.QINIU_UPLOAD_HOST,
        "expires_at": expires_at.isoformat(),
    }


@transaction.atomic
def complete_training_video(
    *,
    project_patient,
    video_id,
    key,
    object_hash,
    training_date,
    actual_duration_minutes,
    note="",
):
    video = (
        TrainingVideo.objects.select_for_update()
        .select_related("prescription_action", "training_record")
        .filter(pk=video_id, project_patient=project_patient)
        .first()
    )
    if video is None:
        raise ValidationError("训练视频不存在")
    if video.object_key != key:
        raise ValidationError("训练视频对象不匹配")
    if video.training_record_id:
        return video, False
    active, action = _get_current_shoulder_action(project_patient, video.prescription_action_id)
    record = create_training_record(
        project_patient=project_patient,
        prescription_action=action,
        training_date=training_date,
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=actual_duration_minutes,
        form_data={"video_id": video.id, "video_object_key": video.object_key},
        note=note,
    )
    video.prescription = active
    video.object_hash = object_hash
    video.status = TrainingVideo.Status.ATTACHED
    video.uploaded_at = timezone.now()
    video.training_record = record
    video.save(
        update_fields=[
            "prescription",
            "object_hash",
            "status",
            "uploaded_at",
            "training_record",
            "updated_at",
        ]
    )
    return video, True
```

- [ ] **Step 5: Implement patient views and routes**

Modify imports in `backend/apps/patient_app/views.py`:

```python
from apps.training.video_services import complete_training_video, create_upload_intent
from .serializers import (
    PatientAppTrainingVideoCompleteSerializer,
    PatientAppTrainingVideoUploadIntentSerializer,
)
```

Add views:

```python
class PatientAppTrainingVideoUploadIntentView(PatientAppBaseView):
    def post(self, request):
        serializer = PatientAppTrainingVideoUploadIntentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            data = create_upload_intent(
                project_patient=self.project_patient(),
                prescription_action_id=serializer.validated_data["prescription_action"],
                content_type=serializer.validated_data["content_type"],
                size_bytes=serializer.validated_data["size_bytes"],
                duration_seconds=serializer.validated_data["duration_seconds"],
            )
        except DjangoValidationError as exc:
            return Response({"detail": validation_detail(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data, status=status.HTTP_201_CREATED)


class PatientAppTrainingVideoCompleteView(PatientAppBaseView):
    def post(self, request, video_id):
        serializer = PatientAppTrainingVideoCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            video, created = complete_training_video(
                project_patient=self.project_patient(),
                video_id=video_id,
                key=serializer.validated_data["key"],
                object_hash=serializer.validated_data["hash"],
                training_date=serializer.validated_data["training_date"],
                actual_duration_minutes=serializer.validated_data["actual_duration_minutes"],
                note=serializer.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return Response({"detail": validation_detail(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            {
                "video_id": video.id,
                "status": video.status,
                "training_record": serialize_training_record(video.training_record),
            },
            status=response_status,
        )
```

Modify `backend/apps/patient_app/urls.py`:

```python
path(
    "training-videos/upload-intent/",
    PatientAppTrainingVideoUploadIntentView.as_view(),
    name="patient-app-training-video-upload-intent",
),
path(
    "training-videos/<int:video_id>/complete/",
    PatientAppTrainingVideoCompleteView.as_view(),
    name="patient-app-training-video-complete",
),
```

- [ ] **Step 6: Run patient video API tests**

Run: `cd backend && pytest apps/patient_app/tests/test_patient_app_video_api.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/training/video_services.py backend/apps/patient_app/serializers.py backend/apps/patient_app/views.py backend/apps/patient_app/urls.py backend/apps/patient_app/tests/test_patient_app_video_api.py
git commit -m "feat(patient-app): 支持肩部推举视频直传绑定"
```

### Task 3: Doctor Video Review and Analysis Job APIs

**Files:**
- Create: `backend/apps/training/analysis.py`
- Create: `backend/apps/training/tasks.py`
- Create: `backend/apps/training/video_serializers.py`
- Create: `backend/apps/training/video_views.py`
- Modify: `backend/apps/training/urls.py`
- Modify: `backend/config/__init__.py`
- Test: `backend/apps/training/tests/test_motion_analysis.py`
- Test: `backend/apps/training/tests/test_training_video_api.py`

**Interfaces:**
- Consumes: `TrainingVideo`, `MotionAnalysisJob`, `private_download_url`.
- Produces: `analyze_shoulder_press_keypoints(frames: list[dict]) -> dict`, `run_motion_analysis_job(job_id: int) -> MotionAnalysisJob`.

- [ ] **Step 1: Write failing deterministic analysis rule tests**

Create `backend/apps/training/tests/test_motion_analysis.py`:

```python
from apps.training.analysis import analyze_shoulder_press_keypoints


def _frame(ms, wrist_y, confidence=0.95):
    return {
        "timestamp_ms": ms,
        "keypoints": {
            "left_shoulder": {"x": 0.4, "y": 0.5, "score": confidence},
            "left_elbow": {"x": 0.4, "y": 0.45, "score": confidence},
            "left_wrist": {"x": 0.4, "y": wrist_y, "score": confidence},
        },
    }


def test_analyze_shoulder_press_counts_down_up_down_repetitions():
    frames = [
        _frame(0, 0.52),
        _frame(400, 0.50),
        _frame(1000, 0.28),
        _frame(1500, 0.26),
        _frame(2400, 0.52),
        _frame(3000, 0.51),
        _frame(3700, 0.27),
        _frame(4300, 0.26),
        _frame(5200, 0.53),
    ]

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 2
    assert result["standard_count"] == 2
    assert result["nonstandard_count"] == 0
    assert len(result["rep_details"]) == 2


def test_analyze_shoulder_press_marks_low_confidence_rep_nonstandard():
    frames = [
        _frame(0, 0.52),
        _frame(1000, 0.28, confidence=0.2),
        _frame(2200, 0.52),
    ]

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert result["standard_count"] == 0
    assert result["nonstandard_count"] == 1
    assert "low_confidence" in result["rep_details"][0]["flags"]
```

- [ ] **Step 2: Run analysis tests and verify failure**

Run: `cd backend && pytest apps/training/tests/test_motion_analysis.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.training.analysis'`.

- [ ] **Step 3: Implement deterministic analysis rule helper**

Create `backend/apps/training/analysis.py`:

```python
def _point(frame, name):
    return frame.get("keypoints", {}).get(name, {})


def _frame_state(frame):
    shoulder = _point(frame, "left_shoulder")
    wrist = _point(frame, "left_wrist")
    score = min(float(shoulder.get("score", 0)), float(wrist.get("score", 0)))
    shoulder_y = float(shoulder.get("y", 0.5))
    wrist_y = float(wrist.get("y", 0.5))
    if wrist_y <= shoulder_y - 0.16:
        state = "up"
    elif wrist_y >= shoulder_y - 0.02:
        state = "down"
    else:
        state = "transition"
    return state, score


def analyze_shoulder_press_keypoints(frames):
    compressed = []
    for frame in frames:
        state, score = _frame_state(frame)
        if state == "transition":
            continue
        if not compressed or compressed[-1]["state"] != state:
            compressed.append(
                {
                    "state": state,
                    "timestamp_ms": int(frame.get("timestamp_ms", 0)),
                    "min_score": score,
                }
            )
        else:
            compressed[-1]["min_score"] = min(compressed[-1]["min_score"], score)

    rep_details = []
    index = 0
    while index + 2 < len(compressed):
        first, second, third = compressed[index : index + 3]
        if first["state"] == "down" and second["state"] == "up" and third["state"] == "down":
            duration = third["timestamp_ms"] - first["timestamp_ms"]
            flags = []
            if min(first["min_score"], second["min_score"], third["min_score"]) < 0.4:
                flags.append("low_confidence")
            if duration < 800 or duration > 8000:
                flags.append("tempo_abnormal")
            rep_details.append(
                {
                    "index": len(rep_details) + 1,
                    "start_ms": first["timestamp_ms"],
                    "end_ms": third["timestamp_ms"],
                    "is_standard": not flags,
                    "flags": flags,
                }
            )
            index += 2
        else:
            index += 1

    standard_count = sum(1 for item in rep_details if item["is_standard"])
    total_count = len(rep_details)
    return {
        "total_count": total_count,
        "standard_count": standard_count,
        "nonstandard_count": total_count - standard_count,
        "rep_details": rep_details,
        "quality_flags": ["camera_angle_unverified"],
    }
```

- [ ] **Step 4: Write failing doctor video API tests**

Create `backend/apps/training/tests/test_training_video_api.py`:

```python
import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.training.models import MotionAnalysisJob, TrainingRecord, TrainingVideo


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _attached_video(project_patient, active_prescription, prescription_action):
    record = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=2,
    )
    return TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_record=record,
        bucket="motioncare-training",
        object_key="training-videos/1/a.mp4",
        object_hash="hash-a",
        content_type="video/mp4",
        size_bytes=1024,
        duration_seconds=120,
        status=TrainingVideo.Status.ATTACHED,
        upload_token_expires_at=timezone.now(),
        uploaded_at=timezone.now(),
    )


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_DOWNLOAD_DOMAIN="https://cdn.example.com",
)
def test_doctor_gets_private_video_download_url(doctor, project_patient, active_prescription, prescription_action):
    video = _attached_video(project_patient, active_prescription, prescription_action)

    response = _client(doctor).get(f"/api/training/videos/{video.id}/download-url/")

    assert response.status_code == 200, response.data
    assert response.data["url"].startswith("https://cdn.example.com/training-videos/1/a.mp4?e=")
    assert "token=ak-test%3A" in response.data["url"]


@pytest.mark.django_db
def test_doctor_creates_analysis_job_for_attached_video(
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    video = _attached_video(project_patient, active_prescription, prescription_action)

    response = _client(doctor).post(f"/api/training/videos/{video.id}/analysis-jobs/")

    assert response.status_code == 201, response.data
    job = MotionAnalysisJob.objects.get(pk=response.data["id"])
    assert job.status == MotionAnalysisJob.Status.PENDING
    assert job.requested_by == doctor


@pytest.mark.django_db
def test_doctor_cannot_create_duplicate_running_analysis_job(
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    video = _attached_video(project_patient, active_prescription, prescription_action)
    MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=video.training_record,
        project_patient=project_patient,
        prescription_action=prescription_action,
        status=MotionAnalysisJob.Status.RUNNING,
    )

    response = _client(doctor).post(f"/api/training/videos/{video.id}/analysis-jobs/")

    assert response.status_code == 400, response.data
    assert "分析任务" in str(response.data)
```

- [ ] **Step 5: Run doctor video tests and verify failure**

Run: `cd backend && pytest apps/training/tests/test_training_video_api.py -q`

Expected: FAIL with 404 for `/api/training/videos/1/download-url/`.

- [ ] **Step 6: Implement serializers**

Create `backend/apps/training/video_serializers.py`:

```python
from rest_framework import serializers

from .models import MotionAnalysisJob


class MotionAnalysisJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = MotionAnalysisJob
        fields = [
            "id",
            "training_video",
            "training_record",
            "status",
            "algorithm_name",
            "algorithm_version",
            "rule_version",
            "total_count",
            "standard_count",
            "nonstandard_count",
            "result_payload",
            "failure_reason",
            "started_at",
            "finished_at",
            "created_at",
        ]
        read_only_fields = fields
```

- [ ] **Step 7: Implement doctor video services and views**

Append to `backend/apps/training/video_services.py`:

```python
from django.http import Http404

from apps.training.qiniu import private_download_url

from .models import MotionAnalysisJob


def get_training_video_for_user(user, video_id):
    from apps.training.tracking import accessible_project_patients

    video = (
        TrainingVideo.objects.select_related("project_patient", "training_record", "prescription_action")
        .filter(pk=video_id, project_patient__in=accessible_project_patients(user))
        .first()
    )
    if video is None:
        raise Http404
    return video


def create_private_download_url(video):
    if not settings.QINIU_DOWNLOAD_DOMAIN:
        raise ValidationError("七牛下载域名未配置")
    expires_at = timezone.now() + timezone.timedelta(seconds=settings.QINIU_DOWNLOAD_TOKEN_TTL_SECONDS)
    base = f"{settings.QINIU_DOWNLOAD_DOMAIN.rstrip('/')}/{video.object_key}"
    return private_download_url(base, expires_at=int(expires_at.timestamp()))


def create_analysis_job(*, video, requested_by):
    if video.status != TrainingVideo.Status.ATTACHED or not video.training_record_id:
        raise ValidationError("训练视频尚未绑定训练记录")
    exists = MotionAnalysisJob.objects.filter(
        training_video=video,
        status__in=[MotionAnalysisJob.Status.PENDING, MotionAnalysisJob.Status.RUNNING],
    ).exists()
    if exists:
        raise ValidationError("已有进行中的分析任务")
    return MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=video.training_record,
        project_patient=video.project_patient,
        prescription_action=video.prescription_action,
        requested_by=requested_by,
    )
```

Create `backend/apps/training/video_views.py`:

```python
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOrDoctor

from .models import MotionAnalysisJob
from .serializers import TrainingRecordSerializer
from .video_serializers import MotionAnalysisJobSerializer
from .video_services import create_analysis_job, create_private_download_url, get_training_video_for_user
from .views import validation_detail


class TrainingVideoDownloadUrlView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, video_id):
        video = get_training_video_for_user(request.user, video_id)
        try:
            url = create_private_download_url(video)
        except DjangoValidationError as exc:
            return Response({"detail": validation_detail(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"url": url})


class TrainingVideoAnalysisJobView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def post(self, request, video_id):
        video = get_training_video_for_user(request.user, video_id)
        try:
            job = create_analysis_job(video=video, requested_by=request.user)
        except DjangoValidationError as exc:
            return Response({"detail": validation_detail(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(MotionAnalysisJobSerializer(job).data, status=status.HTTP_201_CREATED)


class TrainingVideoLatestAnalysisJobView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, video_id):
        video = get_training_video_for_user(request.user, video_id)
        job = MotionAnalysisJob.objects.filter(training_video=video).order_by("-created_at", "-id").first()
        return Response(MotionAnalysisJobSerializer(job).data if job else None)
```

Modify `backend/apps/training/urls.py`:

```python
from .video_views import (
    TrainingVideoAnalysisJobView,
    TrainingVideoDownloadUrlView,
    TrainingVideoLatestAnalysisJobView,
)

path("videos/<int:video_id>/download-url/", TrainingVideoDownloadUrlView.as_view()),
path("videos/<int:video_id>/analysis-jobs/", TrainingVideoAnalysisJobView.as_view()),
path("videos/<int:video_id>/analysis-jobs/latest/", TrainingVideoLatestAnalysisJobView.as_view()),
```

- [ ] **Step 8: Implement Celery task boundary**

Modify `backend/config/__init__.py`:

```python
from .celery import app as celery_app

__all__ = ("celery_app",)
```

Create `backend/apps/training/tasks.py`:

```python
from celery import shared_task
from django.utils import timezone

from .analysis import analyze_shoulder_press_keypoints
from .models import MotionAnalysisJob


def load_keypoint_frames_for_video(_video):
    return []


@shared_task
def run_motion_analysis_job(job_id):
    job = MotionAnalysisJob.objects.select_related("training_video").get(pk=job_id)
    job.status = MotionAnalysisJob.Status.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])
    try:
        frames = load_keypoint_frames_for_video(job.training_video)
        result = analyze_shoulder_press_keypoints(frames)
        job.status = MotionAnalysisJob.Status.SUCCEEDED
        job.total_count = result["total_count"]
        job.standard_count = result["standard_count"]
        job.nonstandard_count = result["nonstandard_count"]
        job.result_payload = result
        job.failure_reason = ""
    except Exception as exc:
        job.status = MotionAnalysisJob.Status.FAILED
        job.failure_reason = str(exc)
    job.finished_at = timezone.now()
    job.save(
        update_fields=[
            "status",
            "total_count",
            "standard_count",
            "nonstandard_count",
            "result_payload",
            "failure_reason",
            "finished_at",
            "updated_at",
        ]
    )
    return job.id
```

- [ ] **Step 9: Run doctor video and analysis tests**

Run:

```bash
cd backend
pytest apps/training/tests/test_motion_analysis.py apps/training/tests/test_training_video_api.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/config/__init__.py backend/apps/training/analysis.py backend/apps/training/tasks.py backend/apps/training/video_serializers.py backend/apps/training/video_views.py backend/apps/training/video_services.py backend/apps/training/urls.py backend/apps/training/tests/test_motion_analysis.py backend/apps/training/tests/test_training_video_api.py
git commit -m "feat(training): 支持医生端视频查看与分析任务"
```

### Task 4: Training Tracking Video and Analysis Summary

**Files:**
- Modify: `backend/apps/training/tracking.py`
- Test: `backend/apps/training/tests/test_tracking_api.py`

**Interfaces:**
- Consumes: `TrainingVideo` and `MotionAnalysisJob`.
- Produces: additional `recent_records` fields: `video_id`, `video_status`, `latest_analysis_status`, `analysis_total_count`, `analysis_standard_count`, `analysis_nonstandard_count`.

- [ ] **Step 1: Add failing tracking API test**

Append to `backend/apps/training/tests/test_tracking_api.py`:

```python
@pytest.mark.django_db
def test_tracking_recent_records_include_video_and_analysis_summary(
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    from apps.training.models import MotionAnalysisJob, TrainingVideo

    record = _record(
        project_patient,
        active_prescription,
        prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
    )
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_record=record,
        bucket="motioncare-training",
        object_key="training-videos/1/a.mp4",
        content_type="video/mp4",
        size_bytes=1024,
        duration_seconds=120,
        status=TrainingVideo.Status.ATTACHED,
        upload_token_expires_at=timezone.now(),
        uploaded_at=timezone.now(),
    )
    MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=record,
        project_patient=project_patient,
        prescription_action=prescription_action,
        status=MotionAnalysisJob.Status.SUCCEEDED,
        total_count=8,
        standard_count=6,
        nonstandard_count=2,
    )

    response = _client(doctor).get(f"/api/training/tracking/patients/{project_patient.patient_id}/")

    assert response.status_code == 200, response.data
    recent = response.data["recent_records"][0]
    assert recent["video_id"] == video.id
    assert recent["video_status"] == TrainingVideo.Status.ATTACHED
    assert recent["latest_analysis_status"] == MotionAnalysisJob.Status.SUCCEEDED
    assert recent["analysis_total_count"] == 8
    assert recent["analysis_standard_count"] == 6
    assert recent["analysis_nonstandard_count"] == 2
```

- [ ] **Step 2: Run the tracking test and verify failure**

Run: `cd backend && pytest apps/training/tests/test_tracking_api.py::test_tracking_recent_records_include_video_and_analysis_summary -q`

Expected: FAIL with missing `video_id`.

- [ ] **Step 3: Add tracking serialization fields**

Modify `recent_records` in `backend/apps/training/tracking.py`:

```python
records = (
    TrainingRecord.objects.filter(project_patient=project_patient)
    .select_related("prescription", "prescription_action", "video")
    .prefetch_related("motion_analysis_jobs")
    .order_by("-training_date", "-id")[:30]
)
```

Inside the loop before `rows.append(...)`:

```python
video = getattr(record, "video", None)
latest_job = (
    sorted(
        record.motion_analysis_jobs.all(),
        key=lambda item: (item.created_at, item.id),
        reverse=True,
    )[0]
    if record.motion_analysis_jobs.all()
    else None
)
```

Add fields to each row:

```python
"video_id": video.id if video else None,
"video_status": video.status if video else None,
"latest_analysis_status": latest_job.status if latest_job else None,
"analysis_total_count": latest_job.total_count if latest_job else None,
"analysis_standard_count": latest_job.standard_count if latest_job else None,
"analysis_nonstandard_count": latest_job.nonstandard_count if latest_job else None,
```

- [ ] **Step 4: Run tracking tests**

Run: `cd backend && pytest apps/training/tests/test_tracking_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/training/tracking.py backend/apps/training/tests/test_tracking_api.py
git commit -m "feat(training): 训练追踪返回视频分析摘要"
```

### Task 5: Miniapp Shoulder Press Recording and Forced Upload Flow

**Files:**
- Modify: `miniapp/src/app.config.ts`
- Create: `miniapp/src/pages/prescription/actionRouting.ts`
- Create: `miniapp/src/pages/shoulder-press/session.ts`
- Create: `miniapp/src/pages/shoulder-press/api.ts`
- Create: `miniapp/src/pages/shoulder-press/index.tsx`
- Create: `miniapp/src/pages/shoulder-press/upload.tsx`
- Modify: `miniapp/src/pages/prescription/index.tsx`
- Modify: `miniapp/src/app.scss`
- Test: `miniapp/src/pages/shoulder-press/session.test.ts`
- Test: `miniapp/src/pages/shoulder-press/api.test.ts`
- Test: `miniapp/src/pages/prescription/actionRouting.test.ts`

**Interfaces:**
- Consumes: patient APIs from Task 2.
- Produces: miniapp route pattern such as `/pages/shoulder-press/index?actionId=42` and upload route `/pages/shoulder-press/upload`.

- [ ] **Step 1: Write failing miniapp session tests**

Create `miniapp/src/pages/shoulder-press/session.test.ts`:

```typescript
import { describe, expect, it, vi } from 'vitest'

import {
  PENDING_SHOULDER_PRESS_UPLOAD_KEY,
  buildShoulderPressSessionUrl,
  buildShoulderPressUploadUrl,
  loadPendingShoulderPressUpload,
  savePendingShoulderPressUpload,
} from './session'

function memoryStorage() {
  const store = new Map<string, unknown>()
  return {
    getStorageSync: vi.fn((key: string) => store.get(key)),
    setStorageSync: vi.fn((key: string, value: unknown) => store.set(key, value)),
  }
}

describe('shoulder press session helpers', () => {
  it('builds session and upload urls', () => {
    expect(buildShoulderPressSessionUrl(42)).toBe('/pages/shoulder-press/index?actionId=42')
    expect(buildShoulderPressUploadUrl()).toBe('/pages/shoulder-press/upload')
  })

  it('stores pending upload state', () => {
    const storage = memoryStorage()

    savePendingShoulderPressUpload(storage, {
      actionId: 42,
      tempFilePath: 'wxfile://video.mp4',
      durationSeconds: 120,
      sizeBytes: 2048,
      createdAt: 1783692000000,
    })

    expect(storage.setStorageSync).toHaveBeenCalledWith(
      PENDING_SHOULDER_PRESS_UPLOAD_KEY,
      expect.objectContaining({ actionId: 42 }),
    )
    expect(loadPendingShoulderPressUpload(storage)?.tempFilePath).toBe('wxfile://video.mp4')
  })
})
```

- [ ] **Step 2: Write failing miniapp API tests**

Create `miniapp/src/pages/shoulder-press/api.test.ts`:

```typescript
import { describe, expect, it, vi } from 'vitest'

const { mockRequest, mockUploadFile } = vi.hoisted(() => ({
  mockRequest: vi.fn(),
  mockUploadFile: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  request: (...args: unknown[]) => mockRequest(...args),
}))

vi.mock('@tarojs/taro', () => ({
  default: {
    uploadFile: (...args: unknown[]) => mockUploadFile(...args),
  },
}))

import { completeShoulderPressUpload, createShoulderPressUploadIntent, uploadVideoToQiniu } from './api'

describe('shoulder press upload api', () => {
  it('creates upload intent through patient app api', async () => {
    mockRequest.mockResolvedValue({ video_id: 1, key: 'k', upload_token: 'token', upload_host: 'https://upload' })

    await createShoulderPressUploadIntent({ actionId: 42, sizeBytes: 100, durationSeconds: 30 })

    expect(mockRequest).toHaveBeenCalledWith('/patient-app/training-videos/upload-intent/', {
      method: 'POST',
      data: {
        prescription_action: 42,
        content_type: 'video/mp4',
        size_bytes: 100,
        duration_seconds: 30,
      },
    })
  })

  it('uploads video to qiniu with key token and file', async () => {
    mockUploadFile.mockImplementation((options) => {
      options.success({ statusCode: 200, data: '{"key":"k","hash":"h"}' })
    })

    await expect(
      uploadVideoToQiniu({
        uploadHost: 'https://upload',
        key: 'k',
        uploadToken: 'token',
        filePath: 'wxfile://video.mp4',
      }),
    ).resolves.toEqual({ key: 'k', hash: 'h' })
  })

  it('completes upload with training fields', async () => {
    mockRequest.mockResolvedValue({ video_id: 1, status: 'attached' })

    await completeShoulderPressUpload({
      videoId: 1,
      key: 'k',
      hash: 'h',
      trainingDate: '2026-07-10',
      actualDurationMinutes: 2,
      note: '',
    })

    expect(mockRequest).toHaveBeenCalledWith('/patient-app/training-videos/1/complete/', {
      method: 'POST',
      data: {
        key: 'k',
        hash: 'h',
        training_date: '2026-07-10',
        actual_duration_minutes: 2,
        note: '',
      },
    })
  })
})
```

- [ ] **Step 3: Write failing prescription route helper test**

Create `miniapp/src/pages/prescription/actionRouting.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'

import { actionButtonLabel, actionEntryUrl } from './actionRouting'

describe('prescription action routing', () => {
  it('routes shoulder press to dedicated follow-along page', () => {
    const action = { id: 42, source_key: 'motion-resistance-shoulder-press', internal_type: 'motion' as const }

    expect(actionEntryUrl(action)).toBe('/pages/shoulder-press/index?actionId=42')
    expect(actionButtonLabel(action)).toBe('开始跟练')
  })

  it('keeps other motion actions on the normal training page', () => {
    const action = { id: 43, source_key: 'motion-resistance-row', internal_type: 'motion' as const }

    expect(actionEntryUrl(action)).toBe('/pages/training/index?actionId=43')
    expect(actionButtonLabel(action)).toBe('开始训练')
  })

  it('keeps game actions on the game session flow', () => {
    const action = { id: 44, source_key: 'game-memory-color-sequence', internal_type: 'game' as const }

    expect(actionEntryUrl(action)).toBe('/pages/game-session/index?actionId=44')
    expect(actionButtonLabel(action)).toBe('开始游戏')
  })
})
```

- [ ] **Step 4: Run miniapp tests and verify failure**

Run: `cd miniapp && npm run test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/api.test.ts src/pages/prescription/actionRouting.test.ts`

Expected: FAIL with module import errors.

- [ ] **Step 5: Implement session helpers**

Create `miniapp/src/pages/shoulder-press/session.ts`:

```typescript
export const SHOULDER_PRESS_SOURCE_KEY = 'motion-resistance-shoulder-press'
export const PENDING_SHOULDER_PRESS_UPLOAD_KEY = 'motioncare.pendingShoulderPressUpload'

export type PendingShoulderPressUpload = {
  actionId: number
  tempFilePath: string
  durationSeconds: number
  sizeBytes: number
  createdAt: number
  videoId?: number
  key?: string
  uploadToken?: string
  uploadHost?: string
  hash?: string
  lastError?: string
}

type StorageLike = {
  getStorageSync: (key: string) => unknown
  setStorageSync: (key: string, value: unknown) => void
}

export function buildShoulderPressSessionUrl(actionId: number): string {
  return `/pages/shoulder-press/index?actionId=${actionId}`
}

export function buildShoulderPressUploadUrl(): string {
  return '/pages/shoulder-press/upload'
}

export function savePendingShoulderPressUpload(storage: StorageLike, payload: PendingShoulderPressUpload): void {
  storage.setStorageSync(PENDING_SHOULDER_PRESS_UPLOAD_KEY, payload)
}

export function loadPendingShoulderPressUpload(storage: StorageLike): PendingShoulderPressUpload | null {
  const value = storage.getStorageSync(PENDING_SHOULDER_PRESS_UPLOAD_KEY)
  if (!value || typeof value !== 'object') return null
  const pending = value as Partial<PendingShoulderPressUpload>
  if (typeof pending.actionId !== 'number' || typeof pending.tempFilePath !== 'string') return null
  return pending as PendingShoulderPressUpload
}
```

- [ ] **Step 6: Implement API helpers**

Create `miniapp/src/pages/shoulder-press/api.ts`:

```typescript
import Taro from '@tarojs/taro'

import { request } from '../../api/client'

type UploadIntent = {
  video_id: number
  bucket: string
  key: string
  upload_token: string
  upload_host: string
  expires_at: string
}

export async function createShoulderPressUploadIntent(input: {
  actionId: number
  sizeBytes: number
  durationSeconds: number
}): Promise<UploadIntent> {
  return request('/patient-app/training-videos/upload-intent/', {
    method: 'POST',
    data: {
      prescription_action: input.actionId,
      content_type: 'video/mp4',
      size_bytes: input.sizeBytes,
      duration_seconds: input.durationSeconds,
    },
  })
}

export async function uploadVideoToQiniu(input: {
  uploadHost: string
  key: string
  uploadToken: string
  filePath: string
}): Promise<{ key: string; hash: string }> {
  return new Promise((resolve, reject) => {
    Taro.uploadFile({
      url: input.uploadHost,
      filePath: input.filePath,
      name: 'file',
      formData: {
        key: input.key,
        token: input.uploadToken,
      },
      success(response) {
        if (response.statusCode < 200 || response.statusCode >= 300) {
          reject(new Error(`七牛上传失败：${response.statusCode}`))
          return
        }
        const data = JSON.parse(response.data || '{}') as { key?: string; hash?: string }
        if (!data.key || !data.hash) {
          reject(new Error('七牛上传响应缺少 key 或 hash'))
          return
        }
        resolve({ key: data.key, hash: data.hash })
      },
      fail(error) {
        reject(new Error(error.errMsg || '七牛上传失败'))
      },
    })
  })
}

export async function completeShoulderPressUpload(input: {
  videoId: number
  key: string
  hash: string
  trainingDate: string
  actualDurationMinutes: number
  note: string
}): Promise<unknown> {
  return request(`/patient-app/training-videos/${input.videoId}/complete/`, {
    method: 'POST',
    data: {
      key: input.key,
      hash: input.hash,
      training_date: input.trainingDate,
      actual_duration_minutes: input.actualDurationMinutes,
      note: input.note,
    },
  })
}
```

- [ ] **Step 7: Implement prescription route helper**

Create `miniapp/src/pages/prescription/actionRouting.ts`:

```typescript
import { gameSessionUrl } from './gameSubpackage'
import { buildShoulderPressSessionUrl, SHOULDER_PRESS_SOURCE_KEY } from '../shoulder-press/session'

type RoutableAction = {
  id: number
  source_key: string | null
  internal_type: 'motion' | 'game' | 'video'
}

export function actionEntryUrl(action: RoutableAction): string {
  if (action.source_key === SHOULDER_PRESS_SOURCE_KEY) {
    return buildShoulderPressSessionUrl(action.id)
  }
  if (action.internal_type === 'game') {
    return gameSessionUrl(action.id)
  }
  return `/pages/training/index?actionId=${action.id}`
}

export function actionButtonLabel(action: RoutableAction): string {
  if (action.source_key === SHOULDER_PRESS_SOURCE_KEY) return '开始跟练'
  if (action.internal_type === 'game') return '开始游戏'
  return '开始训练'
}
```

- [ ] **Step 8: Add routes and prescription branching**

Modify `miniapp/src/app.config.ts` pages:

```typescript
pages: [
  'pages/bind/index',
  'pages/home/index',
  'pages/prescription/index',
  'pages/training/index',
  'pages/shoulder-press/index',
  'pages/shoulder-press/upload',
  'pages/action-history/index',
  'pages/daily-health/index'
],
```

Modify `miniapp/src/pages/prescription/index.tsx` imports:

```typescript
import { actionButtonLabel, actionEntryUrl } from './actionRouting'
```

Modify `startAction`:

```typescript
if (action.internal_type !== 'game' || action.source_key === 'motion-resistance-shoulder-press') {
  Taro.navigateTo({ url: actionEntryUrl(action) })
  return
}
if (gameLoadingActionId !== null) return

setGameLoadingActionId(action.id)
setGameLoadProgress(0)
try {
  await loadGameSessionSubpackage((event) => setGameLoadProgress(event.progress))
  Taro.navigateTo({ url: actionEntryUrl(action) })
} catch (err) {
  setGameLoadError(err instanceof Error ? err.message : '游戏资源加载失败，请稍后重试')
} finally {
  setGameLoadingActionId(null)
}
```

Modify button text:

```tsx
{actionButtonLabel(action)}
```

- [ ] **Step 9: Implement shoulder press pages**

Create `miniapp/src/pages/shoulder-press/index.tsx`:

```tsx
import { Button, Camera, Text, View } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { useState } from 'react'

import { buildShoulderPressUploadUrl, savePendingShoulderPressUpload } from './session'

export default function ShoulderPressPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [recording, setRecording] = useState(false)
  const [error, setError] = useState('')

  async function startRecording() {
    setError('')
    try {
      const context = Taro.createCameraContext()
      await context.startRecord()
      setRecording(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : '摄像头启动失败')
    }
  }

  async function stopRecording() {
    try {
      const context = Taro.createCameraContext()
      const result = await context.stopRecord()
      savePendingShoulderPressUpload(Taro, {
        actionId,
        tempFilePath: result.tempVideoPath,
        durationSeconds: Math.max(1, Math.round(result.duration || 1)),
        sizeBytes: result.size || 1,
        createdAt: Date.now(),
      })
      Taro.redirectTo({ url: buildShoulderPressUploadUrl() })
    } catch (err) {
      setError(err instanceof Error ? err.message : '录像保存失败')
      setRecording(false)
    }
  }

  return (
    <View className='page shoulder-press-page'>
      <View className='page-hero'>
        <Text className='eyebrow'>抗阻训练</Text>
        <Text className='title'>肩部推举</Text>
        <Text className='muted'>请保持正面或近正面，跟随示例完成动作。</Text>
      </View>
      <Camera
        className='camera-preview'
        devicePosition='front'
        mode='normal'
        onError={() => setError('请开启摄像头权限后再开始训练')}
      />
      <View className='field-card'>
        <Text className='label'>示例动作</Text>
        <Text className='value'>弹力带肩部推举：下放到肩部附近，向上推举后回到起始位。</Text>
      </View>
      {error ? <Text className='error'>{error}</Text> : null}
      {recording ? (
        <Button className='primary-button full-button' onClick={() => void stopRecording()}>
          完成并上传
        </Button>
      ) : (
        <Button className='primary-button full-button' onClick={() => void startRecording()}>
          开始录像
        </Button>
      )}
    </View>
  )
}
```

Create `miniapp/src/pages/shoulder-press/upload.tsx`:

```tsx
import { Button, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'

import { todayLocalDate } from '../../utils/date'
import { completeShoulderPressUpload, createShoulderPressUploadIntent, uploadVideoToQiniu } from './api'
import { loadPendingShoulderPressUpload, savePendingShoulderPressUpload } from './session'

function durationMinutes(seconds: number): number {
  return Math.max(1, Math.ceil(seconds / 60))
}

export default function ShoulderPressUploadPage() {
  const [statusText, setStatusText] = useState('正在准备上传')
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)

  async function upload() {
    const pending = loadPendingShoulderPressUpload(Taro)
    if (!pending || uploading) return
    setUploading(true)
    setError('')
    try {
      setStatusText('正在申请上传凭证')
      const intent = pending.videoId && pending.key && pending.uploadToken && pending.uploadHost
        ? {
            video_id: pending.videoId,
            key: pending.key,
            upload_token: pending.uploadToken,
            upload_host: pending.uploadHost,
          }
        : await createShoulderPressUploadIntent({
            actionId: pending.actionId,
            sizeBytes: pending.sizeBytes,
            durationSeconds: pending.durationSeconds,
          })
      savePendingShoulderPressUpload(Taro, {
        ...pending,
        videoId: intent.video_id,
        key: intent.key,
        uploadToken: intent.upload_token,
        uploadHost: intent.upload_host,
      })
      setStatusText('正在上传训练视频')
      const uploaded = await uploadVideoToQiniu({
        uploadHost: intent.upload_host,
        key: intent.key,
        uploadToken: intent.upload_token,
        filePath: pending.tempFilePath,
      })
      setStatusText('正在保存训练记录')
      await completeShoulderPressUpload({
        videoId: intent.video_id,
        key: uploaded.key,
        hash: uploaded.hash,
        trainingDate: todayLocalDate(),
        actualDurationMinutes: durationMinutes(pending.durationSeconds),
        note: '',
      })
      Taro.removeStorageSync('motioncare.pendingShoulderPressUpload')
      Taro.redirectTo({ url: '/pages/prescription/index' })
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传失败')
    } finally {
      setUploading(false)
    }
  }

  useDidShow(() => {
    void upload()
  })

  return (
    <View className='page shoulder-press-upload-page'>
      <View className='page-hero'>
        <Text className='eyebrow'>训练上传</Text>
        <Text className='title'>请保持小程序打开</Text>
        <Text className='muted'>{statusText}</Text>
      </View>
      {error ? <Text className='error'>{error}</Text> : null}
      <Button className='primary-button full-button' loading={uploading} onClick={() => void upload()}>
        重试上传
      </Button>
    </View>
  )
}
```

- [ ] **Step 10: Add minimal styles**

Append to `miniapp/src/app.scss`:

```scss
.shoulder-press-page,
.shoulder-press-upload-page {
  min-height: 100vh;
}

.camera-preview {
  width: 100%;
  height: 620px;
  border-radius: 8px;
  overflow: hidden;
  background: #101418;
}
```

- [ ] **Step 11: Run miniapp tests**

Run: `cd miniapp && npm run test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/api.test.ts src/pages/prescription/actionRouting.test.ts`

Expected: PASS.

- [ ] **Step 12: Build miniapp**

Run: `cd miniapp && npm run build:weapp`

Expected: PASS.

- [ ] **Step 13: Commit**

```bash
git add miniapp/src/app.config.ts miniapp/src/pages/prescription/index.tsx miniapp/src/pages/prescription/actionRouting.ts miniapp/src/pages/prescription/actionRouting.test.ts miniapp/src/pages/shoulder-press miniapp/src/app.scss
git commit -m "feat(miniapp): 新增肩部推举录像上传流程"
```

### Task 6: Doctor Training Tracking Video UI

**Files:**
- Modify: `frontend/src/pages/training-tracking/types.ts`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Test: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`

**Interfaces:**
- Consumes: tracking fields from Task 4 and doctor APIs from Task 3.
- Produces: video drawer and manual analysis action on recent records.

- [ ] **Step 1: Add failing frontend test**

Extend the mocked `trackingDetail.recent_records[2]` in `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`:

```typescript
video_id: 8801,
video_status: 'attached',
latest_analysis_status: 'succeeded',
analysis_total_count: 8,
analysis_standard_count: 6,
analysis_nonstandard_count: 2,
```

Add a test:

```typescript
it("shows shoulder press video and analysis actions", async () => {
  mockGet.mockImplementation((url: string) => {
    if (url === "/training/tracking/patients/201/") {
      return Promise.resolve({ data: trackingDetail });
    }
    if (url === "/training/videos/8801/download-url/") {
      return Promise.resolve({ data: { url: "https://cdn.example.com/video.mp4?e=1&token=x" } });
    }
    return Promise.reject(new Error(`unexpected url ${url}`));
  });

  renderAt("/training-tracking/patients/201");

  expect(await screen.findByText("坐站训练")).toBeInTheDocument();
  expect(await screen.findByText("8 / 6 / 2")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "查看视频" }));
  expect(await screen.findByText("训练视频")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run frontend test and verify failure**

Run: `cd frontend && npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`

Expected: FAIL with missing “查看视频”.

- [ ] **Step 3: Extend types**

Modify `TrackingRecentRecord` in `frontend/src/pages/training-tracking/types.ts`:

```typescript
video_id: number | null;
video_status: string | null;
latest_analysis_status: string | null;
analysis_total_count: number | null;
analysis_standard_count: number | null;
analysis_nonstandard_count: number | null;
```

- [ ] **Step 4: Implement video drawer and analysis actions**

Modify imports in `TrainingTrackingDetailPage.tsx`:

```typescript
import { Alert, Button, Card, Descriptions, Drawer, Empty, Segmented, Select, Space, Spin, Statistic, Table, Tag } from "antd";
```

Add state inside `TrainingTrackingDetailPage`:

```typescript
const [videoRecord, setVideoRecord] = useState<TrackingRecentRecord | null>(null);
const [videoUrl, setVideoUrl] = useState("");
const [videoError, setVideoError] = useState("");
```

Add helper:

```typescript
async function openVideo(record: TrackingRecentRecord) {
  if (!record.video_id) return;
  setVideoRecord(record);
  setVideoUrl("");
  setVideoError("");
  try {
    const response = await apiClient.get<{ url: string }>(`/training/videos/${record.video_id}/download-url/`);
    setVideoUrl(response.data.url);
  } catch (err) {
    setVideoError(errorMessage(err));
  }
}
```

Add columns in the recent records table:

```tsx
{
  title: "视频",
  dataIndex: "video_id",
  render: (_value: number | null, record) =>
    record.video_id ? (
      <Button size="small" onClick={() => void openVideo(record)}>
        查看视频
      </Button>
    ) : (
      "—"
    ),
},
{
  title: "动作分析",
  dataIndex: "latest_analysis_status",
  render: (_value: string | null, record) =>
    record.analysis_total_count != null
      ? `${record.analysis_total_count} / ${record.analysis_standard_count ?? 0} / ${record.analysis_nonstandard_count ?? 0}`
      : record.latest_analysis_status ?? "—",
},
```

Add drawer after the recent records card:

```tsx
<Drawer
  title="训练视频"
  open={Boolean(videoRecord)}
  width={720}
  onClose={() => {
    setVideoRecord(null);
    setVideoUrl("");
    setVideoError("");
  }}
>
  {videoError ? <Alert type="error" showIcon message={videoError} /> : null}
  {videoUrl ? <video src={videoUrl} controls style={{ width: "100%", maxHeight: 420 }} /> : <Spin />}
  {videoRecord ? (
    <Descriptions
      size="small"
      column={1}
      items={[
        { key: "action", label: "动作", children: videoRecord.action_name },
        {
          key: "analysis",
          label: "分析结果",
          children:
            videoRecord.analysis_total_count != null
              ? `${videoRecord.analysis_total_count} / ${videoRecord.analysis_standard_count ?? 0} / ${videoRecord.analysis_nonstandard_count ?? 0}`
              : "暂无分析结果",
        },
      ]}
    />
  ) : null}
</Drawer>
```

- [ ] **Step 5: Add manual analysis trigger**

Extend `mockGet` test setup with a `mockPost` mock, and mock `apiClient.post`. In implementation, add:

```typescript
async function requestAnalysis(record: TrackingRecentRecord) {
  if (!record.video_id) return;
  await apiClient.post(`/training/videos/${record.video_id}/analysis-jobs/`);
}
```

Add an action button:

```tsx
{record.video_id ? (
  <Button size="small" onClick={() => void requestAnalysis(record)}>
    动作分析
  </Button>
) : "—"}
```

- [ ] **Step 6: Run frontend tests**

Run: `cd frontend && npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`

Expected: PASS.

- [ ] **Step 7: Run frontend lint and build**

Run:

```bash
cd frontend
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/training-tracking/types.ts frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
git commit -m "feat(frontend): 医生端展示肩部推举视频分析"
```

### Task 7: Full Verification and Plan Status Update

**Files:**
- Modify: `docs/superpowers/plans/2026-07-10-shoulder-press-video-analysis.md`

**Interfaces:**
- Consumes: all previous task deliverables.
- Produces: verified implementation state and completed checklist entries.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_patient_app_video_api.py apps/training/tests/test_qiniu.py apps/training/tests/test_motion_analysis.py apps/training/tests/test_training_video_api.py apps/training/tests/test_tracking_api.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full backend tests**

Run: `cd backend && pytest`

Expected: PASS.

- [ ] **Step 3: Run miniapp tests and build**

Run:

```bash
cd miniapp
npm run test
npm run build:weapp
```

Expected: PASS.

- [ ] **Step 4: Run frontend tests, lint, and build**

Run:

```bash
cd frontend
npm run test
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 5: Update this plan execution record**

At the top of this file, add:

```text
执行记录（2026-07-10, codex）：肩部推举录像跟练与动作分析已按 Task 1-7 落地于 commit 实际最终提交短 SHA
```

执行这一步时，将句尾的“实际最终提交短 SHA”改成当时 `git log --oneline -1` 显示的短 SHA。

- [ ] **Step 6: Commit verification status**

```bash
git add docs/superpowers/plans/2026-07-10-shoulder-press-video-analysis.md
git commit -m "docs(plan): 标记肩部推举录像分析实施完成"
```

---

## Self-Review

Spec coverage:

- 小程序录像跟练：Task 5.
- 七牛 Kodo 直传：Task 1 and Task 2.
- 上传完成后创建训练记录：Task 2.
- 医生端查看视频：Task 3 and Task 6.
- 医生端手动分析：Task 3 and Task 6.
- PP-TinyPose 规则层边界：Task 3.
- 训练追踪展示分析结果：Task 4 and Task 6.
- 权限与行级过滤：Task 2 and Task 3.
- 测试与验收：Task 1 through Task 7.

Placeholder scan:

- No placeholder markers or unspecified implementation steps are intentionally left in this plan.

Type consistency:

- `TrainingVideo`, `MotionAnalysisJob`, `create_upload_intent`, `complete_training_video`, `generate_upload_token`, `private_download_url`, and frontend `TrackingRecentRecord` fields are defined before later tasks consume them.
