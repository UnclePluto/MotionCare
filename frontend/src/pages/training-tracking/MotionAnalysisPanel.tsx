import { useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Form, Input, InputNumber, Space, Tag, Typography } from "antd";
import { useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { MotionAnalysisStatus, TrackingRecentRecord } from "./types";

type MotionResultValues = {
  total_count: string;
  standard_count: string;
  nonstandard_count: string;
  quality_note: string;
};

type SaveError = "validation" | "conflict" | "missing" | "network" | null;

const MAX_COUNT = 2_147_483_647;

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

function responseStatus(error: unknown) {
  if (!error || typeof error !== "object" || !("response" in error)) return undefined;
  return (error as { response?: { status?: unknown } }).response?.status;
}

function countRules(requiredMessage: string) {
  return [{
    validator: (_: unknown, value: string | number | null | undefined) => {
      if (value == null || value === "") return Promise.reject(new Error(requiredMessage));
      const raw = String(value);
      if (!/^(0|[1-9]\d*)$/.test(raw) || BigInt(raw) > BigInt(MAX_COUNT)) {
        return Promise.reject(new Error("请输入 0 至 2147483647 之间的整数"));
      }
      return Promise.resolve();
    },
  }];
}

export function MotionAnalysisPanel({ record, onSaved }: MotionAnalysisPanelProps) {
  const [form] = Form.useForm<MotionResultValues>();
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(record.motion_result_source === "doctor");
  const [savingRecordId, setSavingRecordId] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<SaveError>(null);
  const [submissionBlocked, setSubmissionBlocked] = useState(false);
  const activeRecordIdRef = useRef(record.id);
  const requestGenerationRef = useRef(0);
  const mountedRef = useRef(false);
  if (activeRecordIdRef.current !== record.id) {
    activeRecordIdRef.current = record.id;
    requestGenerationRef.current += 1;
  }
  const currentQualityNote = qualityNote(record);
  const saving = savingRecordId === record.id;
  const effectiveStatus = saveError === "conflict" ? "running" : record.analysis_status;
  const editable = !submissionBlocked && (
    effectiveStatus === "succeeded" || effectiveStatus === "failed" || effectiveStatus === "unsupported"
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestGenerationRef.current += 1;
    };
  }, []);

  useEffect(() => {
    form.setFieldsValue({
      total_count: record.motion_total_count == null ? undefined : String(record.motion_total_count),
      standard_count: record.motion_standard_count == null ? undefined : String(record.motion_standard_count),
      nonstandard_count: record.motion_nonstandard_count == null ? undefined : String(record.motion_nonstandard_count),
      quality_note: currentQualityNote,
    });
    setSaved(record.motion_result_source === "doctor");
    setSavingRecordId(null);
    setSaveError(null);
    setSubmissionBlocked(false);
  }, [currentQualityNote, form, record.analysis_status, record.id, record.motion_nonstandard_count,
    record.motion_result_source, record.motion_standard_count, record.motion_total_count]);

  const persist = async (values: MotionResultValues) => {
    const recordId = record.id;
    const videoId = record.video_id;
    requestGenerationRef.current += 1;
    const requestGeneration = requestGenerationRef.current;
    const isCurrentRequest = () => mountedRef.current && activeRecordIdRef.current === recordId &&
      requestGenerationRef.current === requestGeneration;
    setSavingRecordId(recordId);
    setSaveError(null);
    try {
      await apiClient.patch(`/training/${recordId}/motion-result/`, {
        total_count: Number(values.total_count),
        standard_count: Number(values.standard_count),
        nonstandard_count: Number(values.nonstandard_count),
        quality_note: values.quality_note ?? "",
      });
      if (!isCurrentRequest()) return;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["training-tracking"] }),
        queryClient.invalidateQueries({ queryKey: ["latest-analysis", videoId] }),
      ]);
      if (!isCurrentRequest()) return;
      setSaved(true);
      onSaved?.();
    } catch (error) {
      if (!isCurrentRequest()) return;
      const status = responseStatus(error);
      if (status === 400) {
        setSaveError("validation");
      } else if (status === 409 || status === 404) {
        setSaveError(status === 409 ? "conflict" : "missing");
        setSubmissionBlocked(true);
        void Promise.all([
          queryClient.invalidateQueries({ queryKey: ["training-tracking"] }),
          queryClient.invalidateQueries({ queryKey: ["latest-analysis", videoId] }),
        ]);
      } else {
        setSaveError("network");
      }
    } finally {
      if (isCurrentRequest()) setSavingRecordId(null);
    }
  };

  const submit = (values: MotionResultValues) => {
    if (BigInt(values.total_count) !== BigInt(values.standard_count) + BigInt(values.nonstandard_count)) {
      form.setFields([
        {
          name: "total_count",
          errors: ["总次数必须等于标准次数与不标准次数之和"],
        },
      ]);
      return;
    }
    void persist(values);
  };

  const message = statusMessage(effectiveStatus);
  const saveErrorMessage = saveError === "validation"
    ? "输入内容未通过校验，请检查后重试"
    : saveError === "conflict"
      ? "分析状态已变化，系统正在分析视频，请等待完成"
      : saveError === "missing"
        ? "训练记录已不可用，请刷新页面后重新选择"
        : saveError === "network"
          ? "网络连接异常，输入已保留，请重试保存"
          : null;

  return (
    <section className="motion-analysis-panel" aria-labelledby="motion-analysis-heading">
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap align="center">
          <Typography.Title id="motion-analysis-heading" level={5} style={{ margin: 0 }}>
            动作分析
          </Typography.Title>
          <Tag>{effectiveStatus ? STATUS_LABEL[effectiveStatus] : "等待任务"}</Tag>
          {saved ? <Tag color="green">医生已修正</Tag> : null}
        </Space>

        {message ? (
          <Alert
            type={effectiveStatus === "failed" ? "warning" : "info"}
            showIcon
            message={effectiveStatus === "failed" ? (record.analysis_failure_message || message) : message}
          />
        ) : null}

        <Form<MotionResultValues>
          form={form}
          layout="vertical"
          className="motion-analysis-form"
          disabled={!editable}
          onFinish={submit}
        >
          <Form.Item name="total_count" label="总次数" rules={countRules("请输入总次数")}>
            <InputNumber<string> aria-label="总次数" stringMode style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="standard_count" label="标准次数" rules={countRules("请输入标准次数")}>
            <InputNumber<string> aria-label="标准次数" stringMode style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="nonstandard_count" label="不标准次数" rules={countRules("请输入不标准次数")}>
            <InputNumber<string> aria-label="不标准次数" stringMode style={{ width: "100%" }} />
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

        {saveErrorMessage ? (
          <Alert
            type="error"
            showIcon
            message={saveErrorMessage}
          />
        ) : null}
      </Space>
    </section>
  );
}
