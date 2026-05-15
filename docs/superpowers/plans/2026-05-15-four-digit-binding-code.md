# Four Digit Binding Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

执行记录（2026-05-15, codex）：四位数字绑定码、15 分钟有效期、医生端展示和小程序四格数字输入已实现但未提交；验证通过：后端绑定相关 pytest 43 passed、Django migration check no changes、医生端组件测试 4 passed、frontend lint 0 errors/4 existing warnings、miniapp TypeScript 与 weapp build 通过。

**Goal:** 将患者端绑定码改为 4 位纯数字、生成后 15 分钟有效，并把小程序绑定页改成四格数字输入体验。

**Architecture:** 后端继续只保存绑定码哈希，但生成逻辑改为 `0000`-`9999` 的数字字符串，并只避免“当前有效、未使用、未撤销”的码重复，历史码允许复用。医生端 API 仍在 `ProjectPatient` 维度返回明文码一次，Web 管理端用大号等宽数字展示；小程序端只接受 4 位数字并唤起数字键盘。

**Tech Stack:** Django 5 + DRF + pytest；React 18 + TypeScript + Ant Design 5 + Vitest；Taro 4 + React + TypeScript + WeChat miniapp。

**Execution Note:** 本仓库 `AGENTS.md` 明确要求“不要主动 commit”，所以本计划不包含自动提交步骤。执行完成后只保留工作区改动、运行验证并汇报。

---

## File Structure

- `backend/apps/patient_app/services.py`
  - 负责绑定码规范化、哈希、生成、有效期、绑定和撤销。
  - 本次改为 4 位数字、15 分钟 TTL、仅检查当前有效码冲突。
- `backend/apps/patient_app/serializers.py`
  - 负责患者端绑定请求校验。
  - 本次将 `code` 收紧为 4 位数字字符串。
- `backend/apps/patient_app/tests/test_binding_services.py`
  - 覆盖服务层绑定码规则、过期、复用、冲突重试。
- `backend/apps/patient_app/tests/test_patient_app_api.py`
  - 覆盖患者端绑定 API 对 4 位数字码的接受与非法输入拒绝。
- `backend/apps/studies/tests/test_project_patient_binding_api.py`
  - 覆盖医生端生成接口返回 4 位数字码与 15 分钟有效期。
- `frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx`
  - 负责医生端生成/撤销/状态展示。
  - 本次增强生成后的四位码视觉样式与“15 分钟内有效”提示。
- `frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx`
  - 覆盖医生端生成后显示四位码和有效期提示。
- `miniapp/src/pages/bind/index.tsx`
  - 负责小程序绑定页。
  - 本次改为四格数字输入、数字键盘、4 位提交限制。
- `miniapp/src/app.scss`
  - 放置小程序绑定页四格输入样式。

---

## Task 1: Backend Binding Code Rules

**Files:**
- Modify: `backend/apps/patient_app/services.py`
- Modify: `backend/apps/patient_app/serializers.py`
- Modify: `backend/apps/patient_app/tests/test_binding_services.py`
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py`
- Modify: `backend/apps/studies/tests/test_project_patient_binding_api.py`

- [x] **Step 1: Update service tests for 4 digit code and 15 minute TTL**

Edit `backend/apps/patient_app/tests/test_binding_services.py`.

Change `test_create_binding_code_returns_plain_code_and_stores_hash_only` assertions to:

```python
assert len(plain_code) == 4
assert plain_code.isdigit()
assert abs(
    binding.expires_at - (binding.created_at + timezone.timedelta(minutes=15))
) <= timezone.timedelta(seconds=2)
```

Replace `test_invalid_binding_code_is_rejected` input with:

```python
bind_project_patient_with_code("12AB", wx_openid="openid-001")
```

Add this test after `test_create_binding_code_revokes_old_unused_code`:

```python
@pytest.mark.django_db
def test_expired_numeric_binding_code_can_be_reused(project_patient, doctor, monkeypatch):
    from apps.patients.models import Patient
    from apps.studies.models import ProjectPatient, StudyGroup, StudyProject

    second_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900002222",
        primary_doctor=doctor,
    )
    second_project = StudyProject.objects.create(name="认知衰弱研究二", created_by=doctor)
    second_group = StudyGroup.objects.create(project=second_project, name="干预组", target_ratio=1)
    second_project_patient = ProjectPatient.objects.create(
        project=second_project,
        patient=second_patient,
        group=second_group,
    )

    monkeypatch.setattr(services, "_generate_binding_code", lambda: "0387")
    first_code, first_binding = create_binding_code(project_patient, created_by=doctor)
    PatientAppBindingCode.objects.filter(pk=first_binding.pk).update(
        expires_at=timezone.now() - timezone.timedelta(seconds=1)
    )

    second_code, second_binding = create_binding_code(second_project_patient, created_by=doctor)

    assert first_code == "0387"
    assert second_code == "0387"
    assert second_binding.project_patient == second_project_patient
```

Add this test after the reuse test:

```python
@pytest.mark.django_db
def test_active_numeric_binding_code_collision_retries(project_patient, doctor, monkeypatch):
    from apps.patients.models import Patient
    from apps.studies.models import ProjectPatient, StudyGroup, StudyProject

    second_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900002222",
        primary_doctor=doctor,
    )
    second_project = StudyProject.objects.create(name="认知衰弱研究二", created_by=doctor)
    second_group = StudyGroup.objects.create(project=second_project, name="干预组", target_ratio=1)
    second_project_patient = ProjectPatient.objects.create(
        project=second_project,
        patient=second_patient,
        group=second_group,
    )

    codes = iter(["0387", "4912"])
    monkeypatch.setattr(services, "_generate_binding_code", lambda: next(codes))
    first_code, _ = create_binding_code(project_patient, created_by=doctor)

    second_code, second_binding = create_binding_code(second_project_patient, created_by=doctor)

    assert first_code == "0387"
    assert second_code == "4912"
    assert second_binding.project_patient == second_project_patient
```

Keep the existing race-condition test for `IntegrityError`; it still verifies database-level uniqueness retry.

- [x] **Step 2: Update patient app API tests**

Edit `backend/apps/patient_app/tests/test_patient_app_api.py`.

Add an API validation test near the bind API tests:

```python
@pytest.mark.django_db
def test_bind_api_rejects_non_numeric_or_wrong_length_code():
    client = APIClient()
    response = client.post(
        "/api/patient-app/bind/",
        {"code": "12AB", "wx_openid": "openid-a"},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "4 位数字" in str(response.data)
```

- [x] **Step 3: Update doctor-side API tests**

Edit `backend/apps/studies/tests/test_project_patient_binding_api.py`.

In `test_generate_project_patient_binding_code_returns_plain_code_once`, replace:

```python
assert len(response.data["code"]) == 8
```

with:

```python
assert len(response.data["code"]) == 4
assert response.data["code"].isdigit()
assert abs(
    binding.expires_at - (binding.created_at + timezone.timedelta(minutes=15))
) <= timezone.timedelta(seconds=2)
```

Add imports at the top if missing:

```python
from django.utils import timezone
```

- [x] **Step 4: Run backend tests and verify they fail before implementation**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_binding_services.py apps/patient_app/tests/test_patient_app_api.py apps/studies/tests/test_project_patient_binding_api.py -q
```

Expected before implementation:

- Fails because generated code is still 8 character alphanumeric.
- Fails because TTL is still 30 minutes.
- Fails because serializer still accepts non-4-digit code.

- [x] **Step 5: Implement service constants and normalization**

Edit `backend/apps/patient_app/services.py`.

Replace the binding code constants with:

```python
BINDING_CODE_ALPHABET = "0123456789"
BINDING_CODE_LENGTH = 4
BINDING_CODE_MAX_ATTEMPTS = 20
BINDING_CODE_TTL = timezone.timedelta(minutes=15)
SESSION_TTL = timezone.timedelta(days=30)
```

Replace `_normalize_binding_code` with:

```python
def _normalize_binding_code(code: str) -> str:
    return code if isinstance(code, str) else ""
```

Important: do not trim or filter input here. Whitespace-wrapped codes and non-string values must fail the strict `[0-9]{4}` check instead of being normalized into a valid code.

Keep `_generate_binding_code` as:

```python
def _generate_binding_code() -> str:
    return "".join(secrets.choice(BINDING_CODE_ALPHABET) for _ in range(BINDING_CODE_LENGTH))
```

- [x] **Step 6: Implement active-window collision check**

Edit `backend/apps/patient_app/services.py`.

Inside `create_binding_code`, keep the existing transaction and old-code revocation, but replace the generation loop body with this logic:

```python
for _ in range(BINDING_CODE_MAX_ATTEMPTS):
    plain_code = _generate_binding_code()
    code_hash = _hash_binding_code(plain_code)
    active_collision_exists = PatientAppBindingCode.objects.select_for_update().filter(
        code_hash=code_hash,
        used_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=now,
    ).exists()
    if active_collision_exists:
        continue
    try:
        with transaction.atomic():
            binding = PatientAppBindingCode.objects.create(
                project_patient=locked_project_patient,
                code_hash=code_hash,
                expires_at=expires_at,
                created_by=created_by,
            )
    except IntegrityError:
        continue
    return plain_code, binding
else:
    raise ValidationError("绑定码生成失败，请重试")
```

Important: if the existing model still has `code_hash` globally unique, this implementation will still retry on `IntegrityError`; do not remove the retry. A historical expired hash must not block reuse, so the next step removes global uniqueness and replaces it with a normal index.

- [x] **Step 7: Remove historical global uniqueness if required**

Check `backend/apps/patient_app/models.py`. If `code_hash = models.CharField(max_length=128, unique=True)`, change it to:

```python
code_hash = models.CharField(max_length=128, db_index=True)
```

Then generate a migration:

```bash
cd backend
python manage.py makemigrations patient_app
```

Expected: creates the next `backend/apps/patient_app/migrations/0002_*.py` altering `code_hash` uniqueness/index.

- [x] **Step 8: Prefer latest binding row during bind lookup**

Edit `backend/apps/patient_app/services.py`.

Inside `bind_project_patient_with_code`, replace:

```python
binding_ref = (
    PatientAppBindingCode.objects.filter(code_hash=code_hash)
    .only("id", "project_patient_id")
    .first()
)
```

with:

```python
binding_ref = (
    PatientAppBindingCode.objects.filter(code_hash=code_hash)
    .order_by("-created_at", "-id")
    .only("id", "project_patient_id")
    .first()
)
```

Reason: once expired/used/revoked historical numeric codes can be reused, a code hash may have multiple rows. Binding must evaluate the newest generated row for that four-digit code.

- [x] **Step 9: Implement serializer validation**

Edit `backend/apps/patient_app/serializers.py`.

Replace:

```python
code = serializers.CharField(max_length=32)
```

with:

```python
class BindingCodeField(serializers.CharField):
    def __init__(self, **kwargs):
        super().__init__(
            max_length=4,
            min_length=4,
            trim_whitespace=False,
            error_messages={
                "required": "绑定码必须是 4 位数字",
                "null": "绑定码必须是 4 位数字",
                "blank": "绑定码必须是 4 位数字",
                "invalid": "绑定码必须是 4 位数字",
                "max_length": "绑定码必须是 4 位数字",
                "min_length": "绑定码必须是 4 位数字",
            },
            **kwargs,
        )

    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("绑定码必须是 4 位数字")
        value = super().to_internal_value(data)
        if not BINDING_CODE_PATTERN.fullmatch(value):
            raise serializers.ValidationError("绑定码必须是 4 位数字")
        return value


code = BindingCodeField()
```

Use the shared strict ASCII pattern `[0-9]{4}` through `BINDING_CODE_PATTERN`; do not use `\d{4}`, because it also matches non-ASCII digits.

- [x] **Step 10: Run backend verification**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_binding_services.py apps/patient_app/tests/test_patient_app_api.py apps/studies/tests/test_project_patient_binding_api.py -q
python manage.py makemigrations --check --dry-run
```

Expected:

- Targeted pytest passes.
- `makemigrations --check --dry-run` reports no model changes left after any required migration is generated.

---

## Task 2: Doctor Web Binding Code Display

**Files:**
- Modify: `frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx`
- Modify: `frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx`

- [x] **Step 1: Update frontend test expectation**

Edit `frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx`.

In `shows binding status and generated code`, change mocked code:

```ts
code: "0387",
expires_at: "2026-05-14T12:15:00+08:00",
```

Replace the assertion:

```ts
expect(await screen.findByText("ABCD2345")).toBeInTheDocument();
```

with:

```ts
expect(await screen.findByText("0387")).toBeInTheDocument();
expect(screen.getByText("15 分钟内有效，请提供给患者。")).toBeInTheDocument();
```

- [x] **Step 2: Run frontend card test and verify it fails**

Run:

```bash
cd frontend
npm run test -- src/pages/research-entry/ProjectPatientBindingCard.test.tsx
```

Expected before implementation: fails because the new 15-minute hint is not rendered.

- [x] **Step 3: Update generated-code display**

Edit `frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx`.

Replace the `Alert` message:

```tsx
message="绑定码只显示一次，请提供给患者。"
```

with:

```tsx
message="绑定码只显示一次"
```

Replace the `Typography.Text` block with:

```tsx
<Typography.Text
  copyable
  strong
  style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 28, letterSpacing: 8 }}
>
  {createCode.data.code}
</Typography.Text>
<span>15 分钟内有效，请提供给患者。</span>
<span>过期时间：{formatTime(createCode.data.expires_at)}</span>
```

- [x] **Step 4: Run frontend verification**

Run:

```bash
cd frontend
npm run test -- src/pages/research-entry/ProjectPatientBindingCard.test.tsx
npm run lint
```

Expected:

- Targeted test passes.
- Lint has no new errors. Existing Fast Refresh warnings in unrelated files may remain.

---

## Task 3: Miniapp Four Slot Numeric Binding Input

**Files:**
- Modify: `miniapp/src/pages/bind/index.tsx`
- Modify: `miniapp/src/app.scss`

- [x] **Step 1: Update bind page state handling**

Edit `miniapp/src/pages/bind/index.tsx`.

Add this helper above `export default function BindPage()`:

```ts
function normalizeBindingCode(value: string) {
  return value.replace(/\D/g, '').slice(0, 4)
}
```

Inside `BindPage`, add:

```ts
const codeDigits = Array.from({ length: 4 }, (_, index) => code[index] ?? '')
const canSubmit = code.length === 4 && !loading
```

Replace `submit` normalization:

```ts
const normalizedCode = code.trim().toUpperCase()
if (!normalizedCode) return
```

with:

```ts
const normalizedCode = normalizeBindingCode(code)
if (normalizedCode.length !== 4) return
```

Replace the API payload code with `normalizedCode`.

- [x] **Step 2: Replace text input UI with hidden numeric input plus four slots**

In `miniapp/src/pages/bind/index.tsx`, replace the current `<Input ... />` block with:

```tsx
<View className='code-input-wrap'>
  <Input
    className='code-input'
    value={code}
    type='number'
    focus
    onInput={(event) => setCode(normalizeBindingCode(event.detail.value))}
  />
  <View className='code-slots'>
    {codeDigits.map((digit, index) => (
      <View className={`code-slot${digit ? ' filled' : ''}`} key={index}>
        <Text className='code-slot-text'>{digit}</Text>
      </View>
    ))}
  </View>
</View>
```

Replace the button `disabled` prop:

```tsx
disabled={!code.trim()}
```

with:

```tsx
disabled={!canSubmit}
```

Change placeholder/help text by adding this under the `label`:

```tsx
<Text className='muted'>请输入医生提供的 4 位数字绑定码</Text>
```

- [x] **Step 3: Add miniapp styles**

Edit `miniapp/src/app.scss`.

Append:

```scss
.code-input-wrap {
  position: relative;
  margin-top: 8px;
}

.code-input {
  position: absolute;
  inset: 0;
  z-index: 2;
  width: 100%;
  min-height: 96px;
  opacity: 0;
}

.code-slots {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.code-slot {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 96px;
  border: 2px solid #d0d5dd;
  border-radius: 8px;
  background: #ffffff;
}

.code-slot.filled {
  border-color: #2563eb;
  background: #eff6ff;
}

.code-slot-text {
  color: #101828;
  font-size: 40px;
  font-weight: 700;
  line-height: 1;
}
```

- [x] **Step 4: Build miniapp**

Run:

```bash
cd miniapp
npx tsc --noEmit --skipLibCheck
npm run build:weapp
```

Expected:

- TypeScript check passes with `--skipLibCheck`.
- WeChat miniapp build succeeds.

---

## Task 4: Full Verification And Plan Tracking

**Files:**
- Modify: `docs/superpowers/plans/2026-05-15-four-digit-binding-code.md`

- [x] **Step 1: Run focused full-stack verification**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_binding_services.py apps/patient_app/tests/test_patient_app_api.py apps/studies/tests/test_project_patient_binding_api.py -q
python manage.py makemigrations --check --dry-run

cd ../frontend
npm run test -- src/pages/research-entry/ProjectPatientBindingCard.test.tsx
npm run lint

cd ../miniapp
npx tsc --noEmit --skipLibCheck
npm run build:weapp
```

Expected:

- Backend targeted tests pass.
- No pending Django model changes.
- Frontend targeted test passes.
- Frontend lint has no new errors.
- Miniapp TypeScript and WeChat build pass.

- [x] **Step 2: Update plan execution notes**

At the top of this plan, add an execution record line under the header:

```markdown
执行记录（2026-05-15, codex）：四位数字绑定码、15 分钟有效期、医生端展示和小程序四格数字输入已实现但未提交；验证命令见本任务记录。
```

- [x] **Step 3: Review git diff**

Run:

```bash
git status --short
git diff -- backend/apps/patient_app backend/apps/studies/tests/test_project_patient_binding_api.py frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx miniapp/src/pages/bind/index.tsx miniapp/src/app.scss docs/superpowers/plans/2026-05-15-four-digit-binding-code.md
```

Expected:

- Diff contains only the planned binding-code changes plus any required `patient_app` migration.
- No unrelated files are reverted or reformatted.
