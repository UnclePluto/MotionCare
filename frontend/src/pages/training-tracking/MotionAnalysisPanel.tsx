import { useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Form, Input, InputNumber, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { MotionAnalysisStatus, TrackingRecentRecord } from "./types";

type MotionResultValues = {
  total_count: number;
  standard_count: number;
  nonstandard_count: number;
  quality_note: string;
};

type MotionAnalysisPanelProps = {
  record: TrackingRecentRecord;
  onSaved?: () => void;
};

const STATUS_LABEL: Record<Exclude<MotionAnalysisStatus, null>, string> = {
  pending: "待分析",
  running: "分析中",
  succeeded: "分析成功",
  failed: "分析失败",
  unsupported: "暂不支持",
};

function qualityNote(record: TrackingRecentRecord) {
  const note = record.motion_quality_data.doctor_note;
  return typeof note === "string" ? note : "";
}

function statusMessage(status: MotionAnalysisStatus) {
  if (status === "pending") return "视频已进入自动分析队列，请等待分析完成";
  if (status === "running") return "系统正在分析视频，请等待分析完成";
  if (status === "failed") return "自动分析未完成，请填写训练结果";
  if (status === "unsupported") return "该动作暂不支持自动分析，请填写训练结果";
  if (status === null) return "正在等待自动分析任务，请稍后查看";
  return null;
}

export function MotionAnalysisPanel({ record, onSaved }: MotionAnalysisPanelProps) {
  const [form] = Form.useForm<MotionResultValues>();
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(record.motion_result_source === "doctor");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const currentQualityNote = qualityNote(record);
  const editable = record.analysis_status === "succeeded" ||
    record.analysis_status === "failed" ||
    record.analysis_status === "unsupported";

  useEffect(() => {
    form.setFieldsValue({
      total_count: record.motion_total_count ?? undefined,
      standard_count: record.motion_standard_count ?? undefined,
      nonstandard_count: record.motion_nonstandard_count ?? undefined,
      quality_note: currentQualityNote,
    });
    setSaved(record.motion_result_source === "doctor");
    setSaveError(false);
  }, [currentQualityNote, form, record.id, record.motion_nonstandard_count, record.motion_result_source,
    record.motion_standard_count, record.motion_total_count]);

  const persist = async (values: MotionResultValues) => {
    setSaving(true);
    setSaveError(false);
    try {
      await apiClient.patch(`/training/${record.id}/motion-result/`, values);
      setSaved(true);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["training-tracking"] }),
        queryClient.invalidateQueries({ queryKey: ["latest-analysis", record.video_id] }),
      ]);
      onSaved?.();
    } catch {
      setSaveError(true);
    } finally {
      setSaving(false);
    }
  };

  const submit = (values: MotionResultValues) => {
    if (values.total_count !== values.standard_count + values.nonstandard_count) {
      form.setFields([
        {
          name: "total_count",
          errors: ["总次数必须等于标准次数与不标准次数之和"],
        },
      ]);
      return;
    }
    setSaved(false);
    void persist({
      total_count: values.total_count,
      standard_count: values.standard_count,
      nonstandard_count: values.nonstandard_count,
      quality_note: values.quality_note ?? "",
    });
  };

  const message = statusMessage(record.analysis_status);

  return (
    <section className="motion-analysis-panel" aria-labelledby="motion-analysis-heading">
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap align="center">
          <Typography.Title id="motion-analysis-heading" level={5} style={{ margin: 0 }}>
            动作分析
          </Typography.Title>
          <Tag>{record.analysis_status ? STATUS_LABEL[record.analysis_status] : "等待任务"}</Tag>
          {saved ? <Tag color="green">医生已修正</Tag> : null}
        </Space>

        {message ? (
          <Alert
            type={record.analysis_status === "failed" ? "warning" : "info"}
            showIcon
            message={record.analysis_status === "failed" ? (record.analysis_failure_message || message) : message}
          />
        ) : null}

        <Form<MotionResultValues>
          form={form}
          layout="vertical"
          className="motion-analysis-form"
          disabled={!editable}
          onFinish={submit}
        >
          <Form.Item name="total_count" label="总次数" rules={[{ required: true, message: "请输入总次数" }]}>
            <InputNumber aria-label="总次数" min={0} max={2_147_483_647} precision={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="standard_count" label="标准次数" rules={[{ required: true, message: "请输入标准次数" }]}>
            <InputNumber aria-label="标准次数" min={0} max={2_147_483_647} precision={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="nonstandard_count" label="不标准次数" rules={[{ required: true, message: "请输入不标准次数" }]}>
            <InputNumber aria-label="不标准次数" min={0} max={2_147_483_647} precision={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="quality_note" label="质量备注" className="motion-analysis-note">
            <Input.TextArea aria-label="质量备注" maxLength={2000} rows={3} placeholder="可填写动作质量说明" />
          </Form.Item>
          <Form.Item className="motion-analysis-actions">
            <Button type="primary" htmlType="submit" loading={saving} disabled={!editable}>
              保存训练结果
            </Button>
          </Form.Item>
        </Form>

        {saveError ? (
          <Alert
            type="error"
            showIcon
            message="保存训练结果失败，请稍后再试"
          />
        ) : null}
      </Space>
    </section>
  );
}
