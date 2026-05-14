import { Button, Checkbox, Drawer, Empty, Form, InputNumber, Space, Table, Tag, Typography } from "antd";
import { useEffect, useMemo } from "react";

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

function buildActionPayload(action: ActionLibraryItem, sortOrder: number): ActivateNowActionPayload {
  const mode = getActionParameterMode(action.action_type);

  return {
    action_library_item: action.id,
    weekly_frequency: action.suggested_frequency,
    duration_minutes: mode === "duration" ? action.suggested_duration_minutes : action.suggested_duration_minutes,
    sets: mode === "count" ? action.suggested_sets : null,
    repetitions: mode === "count" ? action.suggested_repetitions : null,
    difficulty: action.default_difficulty,
    notes: "",
    sort_order: sortOrder,
  };
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
  const initialSelected = useMemo(
    () => currentPrescription?.actions.map((item) => item.action_library_item) ?? [],
    [currentPrescription],
  );
  const selectedActionIds = Form.useWatch("selectedActionIds", form) ?? initialSelected;
  const selectedActions = actions.filter((action) => selectedActionIds.includes(action.id));

  useEffect(() => {
    if (open) {
      form.setFieldsValue({ selectedActionIds: initialSelected });
    }
  }, [form, initialSelected, open]);

  const submit = async () => {
    const values = await form.validateFields();
    const selected = values.selectedActionIds ?? [];
    const selectedActionsForPayload = actions.filter((action) => selected.includes(action.id));
    onSubmit({
      expected_active_version: currentPrescription?.version ?? null,
      actions: selectedActionsForPayload.map((action, index) => buildActionPayload(action, index)),
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
            <Space direction="vertical" size={8} style={{ width: "100%" }}>
              {actions.map((action) => (
                <Checkbox key={action.id} value={action.id} aria-label={action.name} disabled={!action.is_active}>
                  <Space wrap size={8}>
                    <span>{action.name}</span>
                    <Tag>{action.action_type}</Tag>
                    <Tag>{getActionParameterMode(action.action_type) === "duration" ? "时长型" : "计数型"}</Tag>
                  </Space>
                </Checkbox>
              ))}
            </Space>
          </Checkbox.Group>
        </Form.Item>

        <Typography.Title level={5}>参数预览</Typography.Title>
        {selectedActions.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请选择动作" />
        ) : (
          <Table
            rowKey="id"
            size="small"
            pagination={false}
            dataSource={selectedActions}
            columns={[
              { title: "动作", dataIndex: "name" },
              { title: "频次", dataIndex: "suggested_frequency", render: (value: string) => value || "未配置" },
              {
                title: "时长",
                dataIndex: "suggested_duration_minutes",
                render: (value: number | null) => (value ? `${value} 分钟` : "—"),
              },
              { title: "组数", dataIndex: "suggested_sets", render: (value: number | null) => value ?? "—" },
              { title: "次数", dataIndex: "suggested_repetitions", render: (value: number | null) => value ?? "—" },
              { title: "难度", dataIndex: "default_difficulty", render: (value: string) => value || "—" },
            ]}
          />
        )}
        <Form.Item label="预计单次总时长" style={{ marginTop: 16 }}>
          <Space>
            <InputNumber
              disabled
              value={selectedActions.reduce((sum, action) => sum + (action.suggested_duration_minutes ?? 0), 0)}
            />
            <Typography.Text>分钟</Typography.Text>
          </Space>
        </Form.Item>
      </Form>
    </Drawer>
  );
}
