import {
  Button,
  Checkbox,
  Collapse,
  Drawer,
  Empty,
  Form,
  InputNumber,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useEffect, useMemo } from "react";

import {
  formatWeeklyFrequency,
  parseWeeklyFrequencyTimes,
  weeklyFrequencyLabel,
} from "./prescriptionUtils";
import type { ActionLibraryItem, ActivateNowActionPayload, Prescription, PrescriptionAction } from "./types";

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
  actionParams?: Record<string, ActionParamValues>;
};

type ActionParamValues = {
  weekly_times?: number | null;
  duration_minutes?: number | null;
  difficulty?: string;
  notes?: string;
};

function defaultParamsForAction(action: ActionLibraryItem, currentAction?: PrescriptionAction): ActionParamValues {
  return {
    weekly_times: parseWeeklyFrequencyTimes(currentAction?.weekly_frequency ?? action.suggested_frequency) ?? 1,
    duration_minutes: currentAction?.duration_minutes ?? action.suggested_duration_minutes,
    difficulty: currentAction?.difficulty ?? action.default_difficulty,
    notes: currentAction?.notes ?? "",
  };
}

function buildActionPayload(
  action: ActionLibraryItem,
  params: ActionParamValues,
  sortOrder: number,
): ActivateNowActionPayload {
  return {
    action_library_item: action.id,
    weekly_frequency: formatWeeklyFrequency(params.weekly_times),
    duration_minutes: params.duration_minutes ?? action.suggested_duration_minutes ?? 1,
    difficulty: params.difficulty ?? action.default_difficulty,
    notes: params.notes ?? "",
    sort_order: sortOrder,
  };
}

function renderDuration(action: ActionLibraryItem) {
  return action.suggested_duration_minutes ? `${action.suggested_duration_minutes} 分钟` : "—";
}

export function PrescriptionDrawer({
  open,
  actions,
  currentPrescription,
  submitting,
  onClose,
  onSubmit,
}: Props) {
  const [form] = Form.useForm<FormValues>();
  const currentActionByLibraryId = useMemo(() => {
    return Object.fromEntries(
      (currentPrescription?.actions ?? []).map((item) => [item.action_library_item, item]),
    ) as Record<number, PrescriptionAction>;
  }, [currentPrescription]);

  const initialSelected = useMemo(
    () => currentPrescription?.actions.map((item) => item.action_library_item) ?? [],
    [currentPrescription],
  );
  const initialActionParams = useMemo(() => {
    return Object.fromEntries(
      actions.map((action) => [
        String(action.id),
        defaultParamsForAction(action, currentActionByLibraryId[action.id]),
      ]),
    ) as Record<string, ActionParamValues>;
  }, [actions, currentActionByLibraryId]);

  const selectedActionIds = Form.useWatch("selectedActionIds", form) ?? initialSelected;
  const selectedActions = useMemo(
    () => actions.filter((action) => selectedActionIds.includes(action.id)),
    [actions, selectedActionIds],
  );
  const watchedActionParams = Form.useWatch("actionParams", form) ?? initialActionParams;
  const totalDurationMinutes = selectedActions.reduce((sum, action) => {
    const params = watchedActionParams[String(action.id)];
    return sum + (params?.duration_minutes ?? action.suggested_duration_minutes ?? 0);
  }, 0);
  const groupedActions = useMemo(() => {
    const groups = new Map<string, ActionLibraryItem[]>();
    for (const action of actions) {
      const group = groups.get(action.action_type) ?? [];
      group.push(action);
      groups.set(action.action_type, group);
    }
    return [...groups.entries()];
  }, [actions]);

  useEffect(() => {
    if (open) {
      form.setFieldsValue({ selectedActionIds: initialSelected, actionParams: initialActionParams });
    }
  }, [form, initialActionParams, initialSelected, open]);

  useEffect(() => {
    if (!open) return;
    const existingParams = form.getFieldValue("actionParams") ?? {};
    let changed = false;
    const nextParams = { ...existingParams };
    for (const action of selectedActions) {
      const key = String(action.id);
      if (!nextParams[key]) {
        nextParams[key] = initialActionParams[key] ?? defaultParamsForAction(action);
        changed = true;
      }
    }
    if (changed) {
      form.setFieldsValue({ actionParams: nextParams });
    }
  }, [form, initialActionParams, open, selectedActions]);

  const submit = async () => {
    const values = await form.validateFields();
    const selected = values.selectedActionIds ?? [];
    const selectedActionsForPayload = actions.filter((action) => selected.includes(action.id));
    if (selectedActionsForPayload.length !== selected.length) {
      message.error("动作库未加载完成，请刷新后重试");
      return;
    }
    const actionParams = values.actionParams ?? {};
    onSubmit({
      expected_active_version: currentPrescription?.version ?? null,
      actions: selectedActionsForPayload.map((action, index) =>
        buildActionPayload(
          action,
          actionParams[String(action.id)] ?? initialActionParams[String(action.id)] ?? defaultParamsForAction(action),
          index,
        ),
      ),
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
            <Collapse
              size="small"
              defaultActiveKey={groupedActions.map(([actionType]) => actionType)}
              items={groupedActions.map(([actionType, groupActions]) => ({
                key: actionType,
                label: (
                  <Space>
                    <span>{actionType}</span>
                    <Tag>{groupActions.length} 个动作</Tag>
                  </Space>
                ),
                children: (
                  <Space direction="vertical" size={8} style={{ width: "100%" }}>
                    {groupActions.map((action) => (
                      <Checkbox key={action.id} value={action.id} aria-label={action.name} disabled={!action.is_active}>
                        <Space wrap size={8}>
                          <span>{action.name}</span>
                          <Tag>{weeklyFrequencyLabel(action.suggested_frequency)}</Tag>
                          <Tag>{renderDuration(action)}</Tag>
                        </Space>
                      </Checkbox>
                    ))}
                  </Space>
                ),
              }))}
            />
          </Checkbox.Group>
        </Form.Item>

        <Typography.Title level={5}>处方参数</Typography.Title>
        {selectedActions.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请选择动作" />
        ) : (
          <Table<ActionLibraryItem>
            rowKey="id"
            size="small"
            pagination={false}
            dataSource={selectedActions}
            columns={[
              {
                title: "动作",
                dataIndex: "name",
                render: (value: string, action) => (
                  <Space direction="vertical" size={2}>
                    <span>{value}</span>
                    <Typography.Text type="secondary">{action.action_type}</Typography.Text>
                  </Space>
                ),
              },
              {
                title: "频次",
                render: (_: unknown, action) => (
                  <Space.Compact>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        paddingInline: 8,
                        border: "1px solid #d9d9d9",
                        borderRight: 0,
                        borderRadius: "6px 0 0 6px",
                        color: "rgba(0, 0, 0, 0.65)",
                        background: "#fafafa",
                      }}
                    >
                      每周
                    </span>
                    <Form.Item
                      name={["actionParams", String(action.id), "weekly_times"]}
                      rules={[{ required: true, message: "请填写每周次数" }]}
                      noStyle
                    >
                      <InputNumber
                        min={1}
                        max={21}
                        controls={false}
                        aria-label={`${action.name}频次`}
                        style={{ width: 72 }}
                      />
                    </Form.Item>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        paddingInline: 8,
                        border: "1px solid #d9d9d9",
                        borderLeft: 0,
                        borderRadius: "0 6px 6px 0",
                        color: "rgba(0, 0, 0, 0.65)",
                        background: "#fafafa",
                      }}
                    >
                      次
                    </span>
                  </Space.Compact>
                ),
              },
              {
                title: "时长(分钟)",
                render: (_: unknown, action) => (
                  <Form.Item
                    name={["actionParams", String(action.id), "duration_minutes"]}
                    rules={[{ required: true, message: "请填写时长" }]}
                    style={{ marginBottom: 0 }}
                  >
                    <InputNumber min={1} aria-label={`${action.name}时长`} style={{ width: 96 }} />
                  </Form.Item>
                ),
              },
              { title: "难度", dataIndex: "default_difficulty", render: (value: string) => value || "—" },
            ]}
          />
        )}
        <Form.Item label="预计单次总时长" style={{ marginTop: 16 }}>
          <Space>
            <InputNumber disabled value={totalDurationMinutes} />
            <Typography.Text>分钟</Typography.Text>
          </Space>
        </Form.Item>
      </Form>
    </Drawer>
  );
}
