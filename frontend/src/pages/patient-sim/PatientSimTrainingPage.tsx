import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Empty, Form, Input, InputNumber, List, Space, Tag, message } from "antd";
import dayjs from "dayjs";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { weeklyFrequencyLabel } from "../prescriptions/prescriptionUtils";
import type { Prescription, PrescriptionAction } from "../prescriptions/types";

function formatDateTime(value: string | null) {
  return value ? value.replace("T", " ").slice(0, 16) : "—";
}

function isValidProjectPatientId(value: number) {
  return Number.isSafeInteger(value) && value > 0;
}

function getErrorMessage(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  return typeof detail === "string" && detail ? detail : "训练记录提交失败";
}

export function PatientSimTrainingPage() {
  const { projectPatientId } = useParams<{ projectPatientId: string }>();
  const id = Number(projectPatientId);
  const isValidId = isValidProjectPatientId(id);
  const [selected, setSelected] = useState<PrescriptionAction | null>(null);
  const [actualDuration, setActualDuration] = useState<number>(1);
  const [note, setNote] = useState("");

  const { data, isError, isLoading } = useQuery({
    queryKey: ["patient-sim-current-prescription", id],
    queryFn: async () => {
      const response = await apiClient.get<Prescription | null>(
        `/patient-sim/project-patients/${id}/current-prescription/`,
      );
      return response.data;
    },
    enabled: isValidId,
  });

  const selectAction = (action: PrescriptionAction) => {
    setSelected(action);
    setActualDuration(action.duration_minutes ?? 1);
    setNote("");
  };

  const submitMutation = useMutation({
    mutationFn: async (action: PrescriptionAction) => {
      const response = await apiClient.post(`/patient-sim/project-patients/${id}/training-records/`, {
        prescription_action: action.id,
        training_date: dayjs().format("YYYY-MM-DD"),
        status: "completed",
        actual_duration_minutes: actualDuration,
        form_data: {
          perceived_difficulty: action.difficulty,
          discomfort: "无",
        },
        note,
      });
      return response.data;
    },
    onSuccess: () => message.success("训练记录已提交"),
    onError: (error) => message.error(getErrorMessage(error)),
  });

  if (!isValidId) return <Alert type="error" message="无效的项目患者 ID" />;
  if (isError) return <Alert type="error" message="无法读取当前处方" />;
  if (!isLoading && !data) return <Empty description="暂无可执行处方" />;

  return (
    <Card loading={isLoading} title={data ? `当前处方 v${data.version}` : "患者跟练模拟"}>
      {data ? (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Descriptions size="small" bordered column={2}>
            <Descriptions.Item label="生效时间">{formatDateTime(data.effective_at)}</Descriptions.Item>
            <Descriptions.Item label="动作数量">{data.actions.length}</Descriptions.Item>
          </Descriptions>
          <List
            dataSource={data.actions}
            locale={{ emptyText: <Empty description="当前处方暂无动作" /> }}
            renderItem={(action) => (
              <List.Item
                onClick={() => selectAction(action)}
                style={{ cursor: "pointer" }}
                aria-current={selected?.id === action.id ? "true" : undefined}
              >
                <List.Item.Meta
                  title={action.action_name_snapshot}
                  description={
                    <Space wrap>
                      <Tag>{action.action_type_snapshot}</Tag>
                      <Tag>{weeklyFrequencyLabel(action.weekly_frequency)}</Tag>
                      <Tag>{action.duration_minutes ? `${action.duration_minutes} 分钟` : "未配置时长"}</Tag>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
          {selected ? (
            <Card type="inner" title={selected.action_name_snapshot}>
              <Space direction="vertical" style={{ width: "100%" }}>
                {selected.video_url_snapshot ? (
                  <video src={selected.video_url_snapshot} controls style={{ width: "100%", maxHeight: 320 }} />
                ) : (
                  <Alert type="info" showIcon message="视频待配置" />
                )}
                <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                  {selected.action_instruction_snapshot || "暂无动作说明"}
                </p>
                <Descriptions size="small" bordered column={2}>
                  <Descriptions.Item label="频次">{weeklyFrequencyLabel(selected.weekly_frequency)}</Descriptions.Item>
                  <Descriptions.Item label="时长">
                    {selected.duration_minutes ? `${selected.duration_minutes} 分钟` : "—"}
                  </Descriptions.Item>
                </Descriptions>
                <Form layout="vertical">
                  <Form.Item label="实际时长">
                    <Space.Compact>
                      <InputNumber value={actualDuration} min={1} onChange={(value) => setActualDuration(value ?? 1)} />
                      <Button disabled>分钟</Button>
                    </Space.Compact>
                  </Form.Item>
                  <Form.Item label="备注">
                    <Input.TextArea
                      value={note}
                      placeholder="可记录本次跟练情况"
                      autoSize={{ minRows: 2, maxRows: 4 }}
                      onChange={(event) => setNote(event.target.value)}
                    />
                  </Form.Item>
                </Form>
                <Button type="primary" loading={submitMutation.isPending} onClick={() => submitMutation.mutate(selected)}>
                  提交训练记录
                </Button>
              </Space>
            </Card>
          ) : null}
        </Space>
      ) : null}
    </Card>
  );
}
