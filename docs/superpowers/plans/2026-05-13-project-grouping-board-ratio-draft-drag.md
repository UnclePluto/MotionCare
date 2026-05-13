# 项目详情分组看板占比草案与拖拽调整 Implementation Plan

执行记录（2026-05-13, Codex）：Task 1-7 已在 worktree `codex/grouping-board-ratio-draft-drag` 落地；验证通过：`npm test -- ProjectGroupingBoard.test.tsx groupingBoardUtils.test.ts App.test.tsx`（41 passed）、`pytest apps/studies/tests/test_confirm_grouping.py apps/studies/tests/test_study_project_delete_guard.py -q`（27 passed）、`npm run test`（62 passed）、`npm run lint`（0 error，4 个既有 warning）、`npm run build`、`pytest`（100 passed）、`rg -n "应用占比到权重|权重" frontend/src docs/superpowers/specs/2026-05-13-project-grouping-board-ratio-draft-drag-design.md`（frontend/src 无匹配，spec 中仅历史/验收描述匹配）。未提交 commit，遵循 AGENTS.md §7“不要主动 commit”。

执行记录（2026-05-13, Codex）：验收反馈已补齐：开始随机使用草案占比、单患者 50/50 随机不固定落第一个组、组列宽增至 460px、占比输入改为窄输入框 + 外置 `%`。最新验证通过：`npm test -- groupingBoardUtils.test.ts ProjectGroupingBoard.test.tsx`（36 passed）、`npm run test`（63 passed）、`npm run lint`（0 error，4 个既有 warning）、`npm run build`、`pytest`（100 passed）。用户选择本地合并回 `main`，开始执行 finishing-a-development-branch Option 1。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目详情分组看板从“权重换算”改为“占比草案确认保存”，并支持本轮随机患者拖拽调整与更紧凑的组列 UI。

**Architecture:** 后端扩展 `confirm-grouping`，在同一事务内保存启用组占比并可选创建确认入组关系；前端把占比、本轮随机、拖拽结果统一作为页面草案，只有点击“确认分组”才提交。拖拽使用 HTML5 native drag events，作用范围只限本轮随机患者，不影响已确认患者。

**Tech Stack:** Django 5 + DRF + pytest-django；React 18 + TypeScript + Ant Design 5 + TanStack Query v5 + Vitest/Testing Library。

**执行约束:** AGENTS.md 规定“不要主动 commit”。本计划中的 commit checkpoint 仅在用户于执行阶段明确要求提交时运行，且提交信息必须为中文。

---

## File Structure

- Modify: `backend/apps/studies/serializers.py`
  - 新增 `ConfirmGroupingRatioSerializer`，让 `ConfirmGroupingSerializer` 支持 `group_ratios` 与可空 `assignments`。
- Modify: `backend/apps/studies/views.py`
  - 扩展 `StudyProjectViewSet.confirm_grouping` 的事务逻辑：先校验并保存占比，再可选创建 `ProjectPatient`。
- Modify: `backend/apps/studies/tests/test_confirm_grouping.py`
  - 添加比例保存、事务回滚、无 assignments 保存比例、非法比例拒绝等后端测试；同步调整旧的“空 assignments 非法”断言。
- Modify: `frontend/src/pages/projects/groupingBoardUtils.ts`
  - 新增纯函数：均衡占比、校验占比、将组映射为随机输入；移除面向用户权重换算依赖。
- Modify: `frontend/src/pages/projects/groupingBoardUtils.test.ts`
  - 覆盖均衡占比、占比校验、按草案占比随机。
- Modify: `frontend/src/pages/projects/ProjectGroupsTab.tsx`
  - 新建分组表单只保留名称；创建后通知父级触发占比草案重平衡。
- Modify: `frontend/src/pages/projects/ProjectDetailPage.tsx`
  - 给 `ProjectGroupsTab` 传入新建成功回调；通过 `groupRevision` 状态让看板读取新组并重平衡。
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
  - 删除“应用占比到权重”按钮；确认提交 `group_ratios`；支持只保存占比；实现紧凑患者卡片、内部 hover 删除 X、本轮患者拖拽。
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`
  - 覆盖权重文案移除、无患者只保存占比、非法占比阻止提交、拖拽后按最终组提交、删除 X 与紧凑操作文案。
- Modify: `frontend/src/styles/global.css`
  - 添加组卡片 hover 删除 X 的样式。
- Modify: `frontend/src/app/App.test.tsx`
  - 若项目详情集成测试因按钮/文案变更失败，更新为新文案。

---

## Task 1: Backend Contract Tests for Ratio Confirmation

**Files:**
- Modify: `backend/apps/studies/tests/test_confirm_grouping.py`

- [x] **Step 1: Add helper and positive ratio tests**

Append these tests after `test_confirm_grouping_creates_project_patients_from_assignments`:

```python
@pytest.mark.django_db
def test_confirm_grouping_updates_group_ratios_without_assignments(doctor, project):
    g1 = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    g2 = StudyGroup.objects.create(project=project, name="对照组", target_ratio=1)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "group_ratios": [
                {"group_id": g1.id, "target_ratio": 60},
                {"group_id": g2.id, "target_ratio": 40},
            ],
            "assignments": [],
        },
        format="json",
    )

    assert r.status_code == 200, r.data
    assert r.data["confirmed"] == 0
    assert r.data["ratios_updated"] == 2
    g1.refresh_from_db()
    g2.refresh_from_db()
    assert g1.target_ratio == 60
    assert g2.target_ratio == 40
    assert not ProjectPatient.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_confirm_grouping_updates_ratios_and_creates_project_patients_atomically(doctor, project):
    g1 = StudyGroup.objects.create(project=project, name="干预组", target_ratio=50)
    g2 = StudyGroup.objects.create(project=project, name="对照组", target_ratio=50)
    p1 = _patient(doctor, "甲", "13900000001")
    p2 = _patient(doctor, "乙", "13900000002")

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "group_ratios": [
                {"group_id": g1.id, "target_ratio": 34},
                {"group_id": g2.id, "target_ratio": 66},
            ],
            "assignments": [
                {"patient_id": p1.id, "group_id": g1.id},
                {"patient_id": p2.id, "group_id": g2.id},
            ],
        },
        format="json",
    )

    assert r.status_code == 200, r.data
    assert r.data["confirmed"] == 2
    assert r.data["ratios_updated"] == 2
    g1.refresh_from_db()
    g2.refresh_from_db()
    assert (g1.target_ratio, g2.target_ratio) == (34, 66)
    assert ProjectPatient.objects.get(project=project, patient=p1).group_id == g1.id
    assert ProjectPatient.objects.get(project=project, patient=p2).group_id == g2.id
```

- [x] **Step 2: Update legacy assignment-only test to include ratios**

In `test_confirm_grouping_creates_project_patients_from_assignments`, change group defaults and payload to:

```python
    g1 = StudyGroup.objects.create(project=project, name="干预组", target_ratio=50)
    g2 = StudyGroup.objects.create(project=project, name="对照组", target_ratio=50)
```

and:

```python
        {
            "group_ratios": [
                {"group_id": g1.id, "target_ratio": 50},
                {"group_id": g2.id, "target_ratio": 50},
            ],
            "assignments": [
                {"patient_id": p1.id, "group_id": g1.id},
                {"patient_id": p2.id, "group_id": g2.id},
            ],
        },
```

- [x] **Step 3: Replace invalid empty assignments expectation**

In `test_confirm_grouping_rejects_invalid_assignment_payload_structure`, remove the `empty_assignments` param:

```python
pytest.param(lambda patient, group: {"assignments": []}, id="empty_assignments"),
```

Then change `missing_assignments` to still be invalid by omitting both fields:

```python
pytest.param(lambda patient, group: {}, id="missing_ratios_and_assignments"),
```

Expected result stays `400`.

- [x] **Step 4: Add negative ratio tests**

Append these tests before `test_confirm_grouping_rejects_patient_already_in_project`:

```python
@pytest.mark.django_db
@pytest.mark.parametrize(
    "ratios, expected",
    [
        pytest.param([70, 20], "合计须为 100", id="sum_not_100"),
        pytest.param([100, 0], "必须大于 0", id="zero_ratio"),
    ],
)
def test_confirm_grouping_rejects_invalid_group_ratios(doctor, project, ratios, expected):
    g1 = StudyGroup.objects.create(project=project, name="干预组", target_ratio=50)
    g2 = StudyGroup.objects.create(project=project, name="对照组", target_ratio=50)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "group_ratios": [
                {"group_id": g1.id, "target_ratio": ratios[0]},
                {"group_id": g2.id, "target_ratio": ratios[1]},
            ],
            "assignments": [],
        },
        format="json",
    )

    assert r.status_code == 400
    assert expected in str(r.data)
    g1.refresh_from_db()
    g2.refresh_from_db()
    assert (g1.target_ratio, g2.target_ratio) == (50, 50)


@pytest.mark.django_db
def test_confirm_grouping_rejects_missing_active_group_ratio(doctor, project):
    g1 = StudyGroup.objects.create(project=project, name="干预组", target_ratio=50)
    g2 = StudyGroup.objects.create(project=project, name="对照组", target_ratio=50)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "group_ratios": [
                {"group_id": g1.id, "target_ratio": 100},
            ],
            "assignments": [],
        },
        format="json",
    )

    assert r.status_code == 400
    assert "启用组占比提交不完整" in str(r.data)
    g1.refresh_from_db()
    g2.refresh_from_db()
    assert (g1.target_ratio, g2.target_ratio) == (50, 50)


@pytest.mark.django_db
def test_confirm_grouping_rejects_inactive_group_ratio(doctor, project):
    active = StudyGroup.objects.create(project=project, name="干预组", target_ratio=100)
    inactive = StudyGroup.objects.create(
        project=project,
        name="停用组",
        target_ratio=1,
        is_active=False,
    )

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "group_ratios": [
                {"group_id": active.id, "target_ratio": 50},
                {"group_id": inactive.id, "target_ratio": 50},
            ],
            "assignments": [],
        },
        format="json",
    )

    assert r.status_code == 400
    assert "分组已停用" in str(r.data)
    active.refresh_from_db()
    inactive.refresh_from_db()
    assert (active.target_ratio, inactive.target_ratio) == (100, 1)


@pytest.mark.django_db
def test_confirm_grouping_rolls_back_ratio_updates_when_assignment_invalid(doctor, project):
    g1 = StudyGroup.objects.create(project=project, name="干预组", target_ratio=50)
    g2 = StudyGroup.objects.create(project=project, name="对照组", target_ratio=50)
    p1 = _patient(doctor, "甲", "13900000001")
    missing_group_id = _missing_id(StudyGroup)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "group_ratios": [
                {"group_id": g1.id, "target_ratio": 34},
                {"group_id": g2.id, "target_ratio": 66},
            ],
            "assignments": [
                {"patient_id": p1.id, "group_id": missing_group_id},
            ],
        },
        format="json",
    )

    assert r.status_code == 400
    assert "以下分组不存在" in str(r.data)
    g1.refresh_from_db()
    g2.refresh_from_db()
    assert (g1.target_ratio, g2.target_ratio) == (50, 50)
    assert not ProjectPatient.objects.filter(project=project).exists()
```

- [x] **Step 5: Run backend tests and confirm expected failure**

Run:

```bash
cd backend && pytest apps/studies/tests/test_confirm_grouping.py -q
```

Expected before implementation: failures mention `group_ratios`, `assignments` empty invalid, or missing `ratios_updated`.

- [x] **Step 6: Commit checkpoint if explicitly requested**

Only if the user explicitly asks for commits during execution:

```bash
git add backend/apps/studies/tests/test_confirm_grouping.py
git commit -m "test: 覆盖确认分组占比保存契约"
```

## Task 2: Backend Confirm Grouping Implementation

**Files:**
- Modify: `backend/apps/studies/serializers.py`
- Modify: `backend/apps/studies/views.py`
- Test: `backend/apps/studies/tests/test_confirm_grouping.py`

- [x] **Step 1: Update serializers**

Replace the current confirm serializers in `backend/apps/studies/serializers.py`:

```python
class ConfirmGroupingAssignmentSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(min_value=1)
    group_id = serializers.IntegerField(min_value=1)


class ConfirmGroupingSerializer(serializers.Serializer):
    assignments = ConfirmGroupingAssignmentSerializer(many=True, allow_empty=False)
```

with:

```python
class ConfirmGroupingAssignmentSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(min_value=1)
    group_id = serializers.IntegerField(min_value=1)


class ConfirmGroupingRatioSerializer(serializers.Serializer):
    group_id = serializers.IntegerField(min_value=1)
    target_ratio = serializers.IntegerField(min_value=1, max_value=100)


class ConfirmGroupingSerializer(serializers.Serializer):
    group_ratios = ConfirmGroupingRatioSerializer(many=True, required=False, allow_empty=False)
    assignments = ConfirmGroupingAssignmentSerializer(many=True, required=False, allow_empty=True)

    def validate(self, attrs):
        if not attrs.get("group_ratios") and not attrs.get("assignments"):
            raise serializers.ValidationError(
                {"detail": "请提交分组占比或本轮随机患者。"}
            )
        return attrs
```

- [x] **Step 2: Add ratio validation block in view**

In `backend/apps/studies/views.py`, inside `confirm_grouping` after `serializer.is_valid(raise_exception=True)`, replace:

```python
        assignments = serializer.validated_data["assignments"]
```

with:

```python
        assignments = serializer.validated_data.get("assignments", [])
        group_ratios = serializer.validated_data.get("group_ratios", [])
```

Then add this block before assignment patient validation:

```python
        ratios_updated = 0
        if group_ratios:
            ratio_group_ids = [item["group_id"] for item in group_ratios]
            duplicate_ratio_group_ids = sorted(
                group_id for group_id, count in Counter(ratio_group_ids).items() if count > 1
            )
            if duplicate_ratio_group_ids:
                return Response(
                    {"detail": f"重复分组占比: {duplicate_ratio_group_ids}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            ratio_groups = StudyGroup.objects.select_for_update(of=("self",)).filter(
                pk__in=ratio_group_ids
            )
            ratio_groups_by_id = {group.id: group for group in ratio_groups}
            missing_ratio_group_ids = sorted(set(ratio_group_ids) - set(ratio_groups_by_id))
            if missing_ratio_group_ids:
                return Response(
                    {"detail": f"以下分组不存在: {missing_ratio_group_ids}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            other_project_ratio_group_ids = sorted(
                group_id
                for group_id, group in ratio_groups_by_id.items()
                if group.project_id != project.id
            )
            if other_project_ratio_group_ids:
                return Response(
                    {"detail": f"分组不属于当前项目: {other_project_ratio_group_ids}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            inactive_ratio_group_ids = sorted(
                group_id for group_id, group in ratio_groups_by_id.items() if not group.is_active
            )
            if inactive_ratio_group_ids:
                return Response(
                    {"detail": f"分组已停用: {inactive_ratio_group_ids}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            active_group_ids = set(
                StudyGroup.objects.select_for_update(of=("self",))
                .filter(project=project, is_active=True)
                .values_list("id", flat=True)
            )
            submitted_group_ids = set(ratio_group_ids)
            if submitted_group_ids != active_group_ids:
                return Response(
                    {
                        "detail": (
                            "启用组占比提交不完整，请刷新后重试。"
                            f" expected={sorted(active_group_ids)} submitted={sorted(submitted_group_ids)}"
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            total_ratio = sum(item["target_ratio"] for item in group_ratios)
            if total_ratio != 100:
                return Response(
                    {"detail": f"启用组占比合计须为 100%，当前为 {total_ratio}%"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for item in group_ratios:
                group = ratio_groups_by_id[item["group_id"]]
                group.target_ratio = item["target_ratio"]
                group.save(update_fields=["target_ratio", "updated_at"])
                ratios_updated += 1
```

- [x] **Step 3: Keep assignment validation optional**

Keep the existing assignment validation, but make sure all references use `assignments` from Step 2. This existing block should still run when `assignments` is non-empty:

```python
        patient_ids = [assignment["patient_id"] for assignment in assignments]
        duplicate_patient_ids = sorted(
            patient_id for patient_id, count in Counter(patient_ids).items() if count > 1
        )
```

When `assignments` is empty, the lists are empty and the validation blocks should pass without creating `ProjectPatient`.

- [x] **Step 4: Add ratios_updated to response**

Replace response body:

```python
        return Response(
            {
                "confirmed": len(created),
                "created": [
```

with:

```python
        return Response(
            {
                "confirmed": len(created),
                "ratios_updated": ratios_updated,
                "created": [
```

- [x] **Step 5: Run focused backend tests**

Run:

```bash
cd backend && pytest apps/studies/tests/test_confirm_grouping.py -q
```

Expected: all tests in `test_confirm_grouping.py` pass.

- [x] **Step 6: Run studies backend tests**

Run:

```bash
cd backend && pytest apps/studies/tests -q
```

Expected: all studies tests pass.

- [x] **Step 7: Commit checkpoint if explicitly requested**

Only if the user explicitly asks for commits during execution:

```bash
git add backend/apps/studies/serializers.py backend/apps/studies/views.py backend/apps/studies/tests/test_confirm_grouping.py
git commit -m "feat: 确认分组时保存分组占比"
```

## Task 3: Frontend Ratio Utility Functions

**Files:**
- Modify: `frontend/src/pages/projects/groupingBoardUtils.ts`
- Modify: `frontend/src/pages/projects/groupingBoardUtils.test.ts`

- [x] **Step 1: Replace utility tests with percent-first tests**

In `frontend/src/pages/projects/groupingBoardUtils.test.ts`, update imports to:

```ts
import { describe, expect, it } from "vitest";

import {
  assignPatientsToGroups,
  balancePercents,
  getPercentValidationError,
  groupsWithDraftPercents,
} from "./groupingBoardUtils";
```

Replace the `targetRatiosToDisplayPercents` and `ratiosToTargetRatios` suites with:

```ts
describe("balancePercents", () => {
  it("balances two groups to 50/50", () => {
    expect(balancePercents([10, 11])).toEqual({ 10: 50, 11: 50 });
  });

  it("balances three groups to 34/33/33", () => {
    expect(balancePercents([10, 11, 12])).toEqual({ 10: 34, 11: 33, 12: 33 });
  });

  it("balances five groups to integers summing to 100", () => {
    const result = balancePercents([10, 11, 12, 13, 14]);
    expect(Object.values(result)).toEqual([20, 20, 20, 20, 20]);
    expect(Object.values(result).reduce((sum, value) => sum + value, 0)).toBe(100);
  });
});

describe("getPercentValidationError", () => {
  it("returns null when active group percents sum to 100", () => {
    expect(getPercentValidationError([50, 50])).toBeNull();
  });

  it("rejects non-positive percents", () => {
    expect(getPercentValidationError([100, 0])).toBe("每个启用组占比必须大于 0。");
  });

  it("rejects percents that do not sum to 100", () => {
    expect(getPercentValidationError([40, 40])).toBe("启用组占比合计须为 100%，当前为 80%。");
  });
});

describe("groupsWithDraftPercents", () => {
  it("uses local draft percents as randomization ratios", () => {
    expect(
      groupsWithDraftPercents(
        [
          { id: 10, target_ratio: 1 },
          { id: 11, target_ratio: 1 },
        ],
        { 10: 75, 11: 25 },
      ),
    ).toEqual([
      { id: 10, target_ratio: 75 },
      { id: 11, target_ratio: 25 },
    ]);
  });
});
```

Keep existing `assignPatientsToGroups` tests, but change any group ratios that were testing weights to percentages. For example:

```ts
const groups = [
  { id: 10, target_ratio: 25 },
  { id: 11, target_ratio: 50 },
  { id: 12, target_ratio: 25 },
];
```

- [x] **Step 2: Run utility tests and confirm expected failure**

Run:

```bash
cd frontend && npm test -- groupingBoardUtils.test.ts
```

Expected before implementation: failures mention missing `balancePercents`, `getPercentValidationError`, or `groupsWithDraftPercents`.

- [x] **Step 3: Implement utility functions**

In `frontend/src/pages/projects/groupingBoardUtils.ts`, delete `gcdPair`, `gcdMany`, `targetRatiosToDisplayPercents`, and `ratiosToTargetRatios`. Add:

```ts
export function balancePercents(groupIds: number[]): Record<number, number> {
  if (!groupIds.length) return {};
  const base = Math.floor(100 / groupIds.length);
  const remainder = 100 - base * groupIds.length;
  return Object.fromEntries(groupIds.map((id, index) => [id, base + (index < remainder ? 1 : 0)]));
}

export function getPercentValidationError(percents: number[]): string | null {
  if (!percents.length) return "没有启用分组，不能确认分组。";
  if (percents.some((percent) => percent <= 0)) return "每个启用组占比必须大于 0。";
  const total = percents.reduce((sum, percent) => sum + percent, 0);
  if (total !== 100) return `启用组占比合计须为 100%，当前为 ${total}%。`;
  return null;
}

export function groupsWithDraftPercents(
  groups: RandomGroupInput[],
  percentByGroupId: Record<number, number>,
): RandomGroupInput[] {
  return groups.map((group) => ({
    ...group,
    target_ratio: percentByGroupId[group.id] ?? group.target_ratio,
  }));
}
```

- [x] **Step 4: Keep randomizer guard messages percent-safe**

Keep `assignPatientsToGroups` unchanged except its input now receives percentage ratios. The existing guard remains valid:

```ts
if (groups.some((g) => g.target_ratio <= 0)) throw new Error("分组比例必须大于 0");
```

- [x] **Step 5: Run utility tests**

Run:

```bash
cd frontend && npm test -- groupingBoardUtils.test.ts
```

Expected: all `groupingBoardUtils` tests pass.

- [x] **Step 6: Commit checkpoint if explicitly requested**

Only if the user explicitly asks for commits during execution:

```bash
git add frontend/src/pages/projects/groupingBoardUtils.ts frontend/src/pages/projects/groupingBoardUtils.test.ts
git commit -m "test: 补充分组占比草案工具函数"
```

## Task 4: Confirm Payload and Ratio Draft UI

**Files:**
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`

- [x] **Step 1: Update component test mock groups to percentages**

In `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`, change default group mocks:

```ts
{ id: 10, name: "试验组", target_ratio: 50, sort_order: 0, is_active: true },
{ id: 11, name: "对照组", target_ratio: 50, sort_order: 1, is_active: true },
```

For the inactive group test, use:

```ts
{ id: 10, name: "试验组", target_ratio: 100, sort_order: 0, is_active: true },
{ id: 12, name: "已停用组", target_ratio: 1, sort_order: 2, is_active: false },
```

- [x] **Step 2: Add tests for removed weight UI and ratio-only confirmation**

Append after `不展示全量患者临时随机说明文案`:

```tsx
  it("不展示权重按钮并允许无本轮随机时只保存占比", async () => {
    mockPost.mockResolvedValueOnce({ data: { confirmed: 0, ratios_updated: 2, created: [] } });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoard projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("全量患者")).toBeInTheDocument());
    expect(screen.queryByText(/权重/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /应用占比/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost).toHaveBeenCalledWith("/studies/projects/1/confirm-grouping/", {
      group_ratios: [
        { group_id: 10, target_ratio: 50 },
        { group_id: 11, target_ratio: 50 },
      ],
      assignments: [],
    });
  });

  it("占比合计不是 100 时不提交确认", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoard projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByLabelText("试验组占比")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("试验组占比"), { target: { value: "40" } });
    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    expect(mockPost).not.toHaveBeenCalled();
    expect(await screen.findByText(/启用组占比合计须为 100%/)).toBeInTheDocument();
  });
```

- [x] **Step 3: Update existing confirm test expected payload**

In `确认分组提交本地 assignments 并刷新`, replace final assertions with:

```tsx
    const [url, payload] = mockPost.mock.calls.at(-1) ?? [];
    expect(url).toBe("/studies/projects/1/confirm-grouping/");
    expect(payload.group_ratios).toEqual([
      { group_id: 10, target_ratio: 50 },
      { group_id: 11, target_ratio: 50 },
    ]);
    expect(payload.assignments).toHaveLength(1);
    expect(payload.assignments[0].patient_id).toBe(1);
    expect([10, 11]).toContain(payload.assignments[0].group_id);
```

- [x] **Step 4: Run component tests and confirm expected failure**

Run:

```bash
cd frontend && npm test -- ProjectGroupingBoard.test.tsx
```

Expected before implementation: failures mention “权重” still visible, `group_ratios` missing, or `确认分组` disabled.

- [x] **Step 5: Update imports and remove patch mutation**

In `ProjectGroupingBoard.tsx`, change import:

```ts
import { assignPatientsToGroups, ratiosToTargetRatios, targetRatiosToDisplayPercents } from "./groupingBoardUtils";
```

to:

```ts
import {
  assignPatientsToGroups,
  getPercentValidationError,
  groupsWithDraftPercents,
} from "./groupingBoardUtils";
```

Delete `patchGroupRatioMutation` and `applyPercents`.

- [x] **Step 6: Initialize draft percents from saved percentages**

Replace the `useEffect` that calls `targetRatiosToDisplayPercents` with:

```ts
  useEffect(() => {
    if (!activeGroups.length) return;
    setPercentByGroupId((prev) => {
      const activeIds = new Set(activeGroups.map((g) => g.id));
      const next: Record<number, number> = {};
      for (const g of activeGroups) {
        next[g.id] = prev[g.id] ?? g.target_ratio;
      }
      for (const key of Object.keys(prev)) {
        const id = Number(key);
        if (activeIds.has(id)) next[id] = prev[id];
      }
      return next;
    });
  }, [activeGroups]);
```

- [x] **Step 7: Submit ratios with confirmation**

Replace `confirmGroupingMutation.mutationFn` with:

```ts
    mutationFn: async () => {
      const groupRatios = activeGroups.map((g) => ({
        group_id: g.id,
        target_ratio: percentByGroupId[g.id] ?? g.target_ratio,
      }));
      await apiClient.post(`/studies/projects/${projectId}/confirm-grouping/`, {
        group_ratios: groupRatios,
        assignments: localAssignments.map((a) => ({ patient_id: a.patientId, group_id: a.groupId })),
      });
    },
```

Before calling `mutate`, add a validation handler:

```ts
  const activePercents = activeGroups.map((g) => percentByGroupId[g.id] ?? g.target_ratio);
  const percentValidationError = getPercentValidationError(activePercents);

  const confirmCurrentDraft = () => {
    if (percentValidationError) {
      message.warning(percentValidationError);
      return;
    }
    confirmGroupingMutation.mutate();
  };
```

- [x] **Step 8: Use draft percentages for randomization**

In `runLocalRandomize`, replace:

```ts
setLocalAssignments(assignPatientsToGroups(eligibleIds, activeGroups, Date.now()));
```

with:

```ts
const validationError = getPercentValidationError(activePercents);
if (validationError) {
  message.warning(validationError);
  return;
}
setLocalAssignments(assignPatientsToGroups(eligibleIds, groupsWithDraftPercents(activeGroups, percentByGroupId), Date.now()));
```

- [x] **Step 9: Replace toolbar**

Replace the first `<Card size="small">...</Card>` block with:

```tsx
      <Card size="small">
        <Space wrap align="center">
          <Button
            type="primary"
            disabled={!hasEligibleSelection || !activeGroups.length}
            onClick={runLocalRandomize}
          >
            随机分组
          </Button>
          <Button
            type="primary"
            style={{ backgroundColor: "#16a34a", borderColor: "#16a34a" }}
            disabled={!activeGroups.length}
            loading={confirmGroupingMutation.isPending}
            onClick={confirmCurrentDraft}
          >
            确认分组
          </Button>
          <Typography.Text type={percentValidationError ? "danger" : "secondary"}>
            {percentValidationError ?? "占比与本轮随机结果仅在确认后保存。"}
          </Typography.Text>
        </Space>
      </Card>
```

Then remove the bottom “随机分组” button from the patient selection card.

- [x] **Step 10: Add accessible ratio inputs**

In each active group header, set `aria-label` on `InputNumber`:

```tsx
                    aria-label={`${g.name}占比`}
```

and update `onChange` to store rounded integers:

```tsx
                      setPercentByGroupId((prev) => ({
                        ...prev,
                        [g.id]: typeof v === "number" ? Math.round(v) : 0,
                      }))
```

- [x] **Step 11: Run component tests**

Run:

```bash
cd frontend && npm test -- ProjectGroupingBoard.test.tsx
```

Expected: `ProjectGroupingBoard` tests pass.

- [x] **Step 12: Commit checkpoint if explicitly requested**

Only if the user explicitly asks for commits during execution:

```bash
git add frontend/src/pages/projects/ProjectGroupingBoard.tsx frontend/src/pages/projects/ProjectGroupingBoard.test.tsx
git commit -m "feat: 分组看板确认时保存占比草案"
```

## Task 5: New Group Form and Auto-Balanced Draft

**Files:**
- Modify: `frontend/src/pages/projects/ProjectGroupsTab.tsx`
- Modify: `frontend/src/pages/projects/ProjectDetailPage.tsx`
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`

- [x] **Step 1: Add callback prop to ProjectGroupsTab**

In `ProjectGroupsTab.tsx`, change props:

```ts
type Props = {
  projectId: number;
  onGroupCreated?: () => void;
};

export function ProjectGroupsTab({ projectId, onGroupCreated }: Props) {
```

Change form type:

```ts
const [form] = Form.useForm<{ name: string }>();
```

Change mutation input and payload:

```ts
mutationFn: async (values: { name: string }) => {
  await apiClient.post("/studies/groups/", {
    project: projectId,
    name: values.name.trim(),
    description: "",
    sort_order: data?.length ?? 0,
    is_active: true,
  });
},
```

In `onSuccess`, add:

```ts
onGroupCreated?.();
```

- [x] **Step 2: Remove target ratio form item and table wording**

In `ProjectGroupsTab.tsx`, change table column:

```ts
{ title: "已保存占比", dataIndex: "target_ratio", width: 120, render: (v: number) => `${v}%` },
```

Delete the entire `Form.Item` with `label="目标比例"`.

Change form initial values:

```tsx
initialValues={{}}
```

- [x] **Step 3: Pass callback from ProjectDetailPage**

In `ProjectDetailPage.tsx`, add state:

```ts
const [groupRevision, setGroupRevision] = useState(0);
```

Pass it to board:

```tsx
<ProjectGroupingBoard projectId={id} groupRevision={groupRevision} />
```

Update board props type in `ProjectGroupingBoard.tsx`:

```ts
type Props = {
  projectId: number;
  groupRevision?: number;
};

export function ProjectGroupingBoard({ projectId, groupRevision = 0 }: Props) {
```

Pass callback to drawer tab:

```tsx
<ProjectGroupsTab projectId={id} onGroupCreated={() => setGroupRevision((value) => value + 1)} />
```

- [x] **Step 4: Balance percents after group creation**

In `ProjectGroupingBoard.tsx`, import `balancePercents`:

```ts
import {
  assignPatientsToGroups,
  balancePercents,
  getPercentValidationError,
  groupsWithDraftPercents,
} from "./groupingBoardUtils";
```

Add this effect after `activeGroups`:

```ts
  useEffect(() => {
    if (!groupRevision || !activeGroups.length) return;
    setPercentByGroupId(balancePercents(activeGroups.map((g) => g.id)));
  }, [activeGroups, groupRevision]);
```

- [x] **Step 5: Add or adjust tests**

Add a focused test in `ProjectGroupingBoard.test.tsx` for three groups initialized from saved values:

```tsx
  it("三组占比展示为后端保存的百分比", async () => {
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config
          ? (config as { params?: Record<string, unknown> }).params
          : undefined;
      if (url === "/patients/") return Promise.resolve({ data: [] });
      if (url === "/studies/groups/" && params?.project === 1) {
        return Promise.resolve({
          data: [
            { id: 10, name: "A组", target_ratio: 34, sort_order: 0, is_active: true },
            { id: 11, name: "B组", target_ratio: 33, sort_order: 1, is_active: true },
            { id: 12, name: "C组", target_ratio: 33, sort_order: 2, is_active: true },
          ],
        });
      }
      if (url === "/studies/project-patients/" && params?.project === 1) return Promise.resolve({ data: [] });
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoard projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByLabelText("A组占比")).toHaveValue("34"));
    expect(screen.getByLabelText("B组占比")).toHaveValue("33");
    expect(screen.getByLabelText("C组占比")).toHaveValue("33");
  });
```

- [x] **Step 6: Run focused frontend tests**

Run:

```bash
cd frontend && npm test -- ProjectGroupingBoard.test.tsx App.test.tsx
```

Expected: focused frontend tests pass, or failures are limited to predictable ProjectGroupsTab text changes. Fix any stale “目标比例” assertions if present.

- [x] **Step 7: Commit checkpoint if explicitly requested**

Only if the user explicitly asks for commits during execution:

```bash
git add frontend/src/pages/projects/ProjectGroupsTab.tsx frontend/src/pages/projects/ProjectDetailPage.tsx frontend/src/pages/projects/ProjectGroupingBoard.tsx frontend/src/pages/projects/ProjectGroupingBoard.test.tsx frontend/src/app/App.test.tsx
git commit -m "feat: 新建分组后生成均衡占比草案"
```

## Task 6: Compact Cards, Hover Delete X, and Drag Adjustment

**Files:**
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`

- [x] **Step 1: Add a drag adjustment test**

At the top of `ProjectGroupingBoard.test.tsx`, keep existing imports. Add this helper near mocks:

```ts
function makeDataTransfer() {
  const store: Record<string, string> = {};
  return {
    setData: (key: string, value: string) => {
      store[key] = value;
    },
    getData: (key: string) => store[key],
    dropEffect: "move",
    effectAllowed: "move",
  };
}
```

Append test:

```tsx
  it("本轮随机患者拖拽到另一组后按最终组提交", async () => {
    mockPost.mockResolvedValueOnce({
      data: { confirmed: 1, ratios_updated: 2, created: [{ project_patient_id: 9010, patient_id: 1, group_id: 11 }] },
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoard projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
    fireEvent.click(screen.getByRole("button", { name: "随机分组" }));
    await waitFor(() => expect(screen.getByText("本轮")).toBeInTheDocument());

    const dragCard = screen.getByTestId("local-assignment-1");
    const targetColumn = screen.getByTestId("group-drop-11");
    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(dragCard, { dataTransfer });
    fireEvent.dragOver(targetColumn, { dataTransfer });
    fireEvent.drop(targetColumn, { dataTransfer });

    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [, payload] = mockPost.mock.calls.at(-1) ?? [];
    expect(payload.assignments).toEqual([{ patient_id: 1, group_id: 11 }]);
  });
```

- [x] **Step 2: Add markup assertions for compact actions and delete X**

Append:

```tsx
  it("组卡片使用内部悬浮删除 X 和精简患者操作", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoard projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("试验组")).toBeInTheDocument());
    const groupCard = screen.getByTestId("group-card-10");
    expect(within(groupCard).getByRole("button", { name: "删除试验组" })).toHaveClass("group-delete-bubble");
    expect(within(groupCard).getByRole("link", { name: "详情" })).toBeInTheDocument();
    expect(within(groupCard).getByRole("button", { name: "解绑" })).toBeInTheDocument();
  });
```

- [x] **Step 3: Run tests and confirm expected failure**

Run:

```bash
cd frontend && npm test -- ProjectGroupingBoard.test.tsx
```

Expected before implementation: failures mention missing `data-testid`, missing `本轮`, old action text, or no drag handlers.

- [x] **Step 4: Add drag state and handlers**

In `ProjectGroupingBoard.tsx`, add handlers before `return`:

```ts
  const handleLocalAssignmentDragStart = (event: React.DragEvent<HTMLElement>, patientId: number) => {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-motioncare-patient-id", String(patientId));
  };

  const handleGroupDragOver = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  };

  const handleGroupDrop = (event: React.DragEvent<HTMLElement>, groupId: number) => {
    event.preventDefault();
    const rawPatientId = event.dataTransfer.getData("application/x-motioncare-patient-id");
    const patientId = Number(rawPatientId);
    if (!Number.isFinite(patientId)) return;
    setLocalAssignments((prev) =>
      prev.map((assignment) =>
        assignment.patientId === patientId ? { ...assignment, groupId } : assignment,
      ),
    );
  };
```

This uses native drag events for a small board-level interaction and keeps the implementation testable with the current Testing Library setup.

- [x] **Step 5: Compact local assignment card**

Update `LocalAssignmentCard` props:

```ts
  onDragStart: (event: React.DragEvent<HTMLElement>, patientId: number) => void;
```

Update root card wrapper:

```tsx
    <div
      data-testid={`local-assignment-${assignment.patientId}`}
      draggable
      onDragStart={(event) => onDragStart(event, assignment.patientId)}
      style={{ marginBottom: 8 }}
    >
      <Card size="small" styles={{ body: { padding: 10 } }}>
        <Space direction="vertical" size={4} style={{ width: "100%" }}>
          <Space align="center" wrap style={{ width: "100%", justifyContent: "space-between" }}>
            <Typography.Text strong>{p?.name ?? `患者 ${assignment.patientId}`}</Typography.Text>
            <Tag color="blue">本轮</Tag>
          </Space>
          <Space size={8} wrap>
            <Typography.Text type="secondary">
              {(p && genderLabel[p.gender]) ?? "—"} · 尾号 {phoneTail(p?.phone ?? "")}
            </Typography.Text>
            <Link to={`/patients/${assignment.patientId}`}>详情</Link>
            <Button type="link" danger size="small" style={{ padding: 0 }} onClick={() => onRemove(assignment.patientId)}>
              移除
            </Button>
          </Space>
        </Space>
      </Card>
    </div>
```

- [x] **Step 6: Compact confirmed patient card**

In `ConfirmedPatientCard`, change link/button labels:

```tsx
<Link to={`/patients/${row.patient}`}>详情</Link>
...
解绑
```

Use AntD v5 `styles` and keep opacity:

```tsx
<Card size="small" style={{ opacity: 0.6 }} styles={{ body: { padding: 10 } }}>
```

- [x] **Step 7: Add group card test ids, drop handlers, wider columns, and delete bubble**

In the group `<Card>`, add:

```tsx
data-testid={`group-card-${g.id}`}
className="group-card"
style={{ minWidth: 340, flex: "0 0 340px", position: "relative" }}
```

Inside the card body wrapper, add:

```tsx
data-testid={`group-drop-${g.id}`}
onDragOver={handleGroupDragOver}
onDrop={(event) => handleGroupDrop(event, g.id)}
```

Replace delete button in title with:

```tsx
                  <Button
                    aria-label={`删除${g.name}`}
                    className="group-delete-bubble"
                    type="text"
                    danger
                    size="small"
                    onClick={() => openDeleteGroupModal(g)}
                    loading={deleteGroupMutation.isPending}
                    disabled={!g.is_active}
                  >
                    ×
                  </Button>
```

Set the button positioning inline:

```tsx
                    style={{
                      position: "absolute",
                      right: 8,
                      top: 8,
                      width: 24,
                      height: 24,
                      borderRadius: 999,
                      zIndex: 2,
                    }}
```

Then add hover visibility styles to `frontend/src/styles/global.css`:

```css
.group-card .group-delete-bubble {
  opacity: 0;
  transition: opacity 0.12s ease, transform 0.12s ease;
}

.group-card:hover .group-delete-bubble {
  opacity: 1;
}
```

- [x] **Step 8: Pass drag handler into local cards**

When rendering `LocalAssignmentCard`, add:

```tsx
onDragStart={handleLocalAssignmentDragStart}
```

- [x] **Step 9: Run component tests**

Run:

```bash
cd frontend && npm test -- ProjectGroupingBoard.test.tsx
```

Expected: all `ProjectGroupingBoard` tests pass.

- [x] **Step 10: Commit checkpoint if explicitly requested**

Only if the user explicitly asks for commits during execution:

```bash
git add frontend/src/pages/projects/ProjectGroupingBoard.tsx frontend/src/pages/projects/ProjectGroupingBoard.test.tsx frontend/src/styles/global.css
git commit -m "feat: 支持本轮随机患者拖拽调整"
```

## Task 7: Full Verification and Documentation Status

**Files:**
- Modify: `docs/superpowers/plans/2026-05-13-project-grouping-board-ratio-draft-drag.md`

- [x] **Step 1: Run focused frontend tests**

Run:

```bash
cd frontend && npm test -- ProjectGroupingBoard.test.tsx groupingBoardUtils.test.ts App.test.tsx
```

Expected: all focused frontend tests pass.

- [x] **Step 2: Run focused backend tests**

Run:

```bash
cd backend && pytest apps/studies/tests/test_confirm_grouping.py apps/studies/tests/test_study_project_delete_guard.py -q
```

Expected: all focused backend tests pass.

- [x] **Step 3: Run full frontend test suite**

Run:

```bash
cd frontend && npm run test
```

Expected: all frontend tests pass.

- [x] **Step 4: Run frontend lint and build**

Run:

```bash
cd frontend && npm run lint
cd frontend && npm run build
```

Expected: lint exits 0; build exits 0.

- [x] **Step 5: Run backend full test suite**

Run:

```bash
cd backend && pytest
```

Expected: all backend tests pass.

- [x] **Step 6: Search for removed user-facing weight copy**

Run:

```bash
rg -n "应用占比到权重|权重" frontend/src docs/superpowers/specs/2026-05-13-project-grouping-board-ratio-draft-drag-design.md
```

Expected: no matches in `frontend/src`; matches in the design spec are allowed only where describing removed legacy behavior.

- [x] **Step 7: Update this plan execution record**

At the top of this file, add one execution record sentence that names each command from Steps 1-6 and records its actual pass/fail result. Do not claim commands passed unless they did.

- [x] **Step 8: Final git status**

Run:

```bash
git status --short
```

Expected: only intentional files are modified or untracked.

- [x] **Step 9: Commit checkpoint if explicitly requested**

Only if the user explicitly asks for commits during execution:

```bash
git add backend/apps/studies/serializers.py backend/apps/studies/views.py backend/apps/studies/tests/test_confirm_grouping.py frontend/src/pages/projects/groupingBoardUtils.ts frontend/src/pages/projects/groupingBoardUtils.test.ts frontend/src/pages/projects/ProjectGroupingBoard.tsx frontend/src/pages/projects/ProjectGroupingBoard.test.tsx frontend/src/pages/projects/ProjectGroupsTab.tsx frontend/src/pages/projects/ProjectDetailPage.tsx frontend/src/app/App.test.tsx frontend/src/styles/global.css docs/superpowers/specs/2026-05-13-project-grouping-board-ratio-draft-drag-design.md docs/superpowers/plans/2026-05-13-project-grouping-board-ratio-draft-drag.md
git commit -m "feat: 优化项目分组看板占比与拖拽"
```

## Self-Review Notes

- Spec coverage: plan covers percentage semantics, no weight UI, confirmation-only persistence, ratio-only confirmation, new group balancing, compact cards, hover delete X, drag adjustment, backend transaction validation, and verification.
- Placeholder scan: no unfinished placeholder markers are present.
- Type consistency: frontend payload uses `group_ratios: { group_id, target_ratio }[]` and `assignments: { patient_id, group_id }[]`; backend serializers use the same names.
