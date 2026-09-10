import { Alert, DatePicker, Form, Modal, Radio, Select, Space, Typography } from "antd";
import type { Dayjs } from "dayjs";
import { useEffect, useRef, useState } from "react";

import type { TrackingPatient, TrackingProjectPatient } from "./types";
import { downloadTrainingDetail, type TrainingExportRequest } from "./trainingDetailExport";
import "./TrainingDetailExportModal.css";

type ExportRange = TrainingExportRequest["range"];

type ExportFormValues = {
  project_patient: number;
  range: ExportRange;
  custom_dates?: [Dayjs, Dayjs];
};

export type TrainingDetailExportModalProps = {
  open: boolean;
  onClose: () => void;
  patient: TrackingPatient;
  projects: TrackingProjectPatient[];
  defaultProjectPatientId?: number;
};

function shanghaiToday(): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = (type: "year" | "month" | "day") => parts.find((part) => part.type === type)?.value ?? "";
  return `${value("year")}-${value("month")}-${value("day")}`;
}

function customDateError(dates: [Dayjs, Dayjs] | undefined): string | null {
  if (!dates?.[0] || !dates?.[1]) return "请选择完整日期范围";
  const start = dates[0].format("YYYY-MM-DD");
  const end = dates[1].format("YYYY-MM-DD");
  if (start > end) return "结束日期不能早于开始日期";
  if (start > shanghaiToday() || end > shanghaiToday()) return "日期不能晚于今天";
  return null;
}

function initialProjectId(projects: TrackingProjectPatient[], defaultProjectPatientId: number | undefined) {
  if (projects.some((project) => project.id === defaultProjectPatientId)) return defaultProjectPatientId;
  return projects[0]?.id;
}

export function TrainingDetailExportModal({
  open,
  onClose,
  patient,
  projects,
  defaultProjectPatientId,
}: TrainingDetailExportModalProps) {
  const [form] = Form.useForm<ExportFormValues>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lockRef = useRef(false);
  const sessionRef = useRef(0);
  const identityRef = useRef({ open, patientId: patient.id });
  const projectsRef = useRef(projects);
  const defaultProjectPatientIdRef = useRef(defaultProjectPatientId);
  projectsRef.current = projects;
  defaultProjectPatientIdRef.current = defaultProjectPatientId;

  if (identityRef.current.open !== open || identityRef.current.patientId !== patient.id) {
    identityRef.current = { open, patientId: patient.id };
    sessionRef.current += 1;
    lockRef.current = false;
  }

  useEffect(() => () => {
    sessionRef.current += 1;
    lockRef.current = false;
  }, []);

  useEffect(() => {
    if (!open) return;
    setLoading(false);
    setError(null);
    form.setFieldsValue({
      project_patient: initialProjectId(projectsRef.current, defaultProjectPatientIdRef.current),
      range: "30d",
      custom_dates: undefined,
    });
  }, [form, open, patient.id]);

  const selectedRange = Form.useWatch("range", form) ?? "30d";
  const selectedDates = Form.useWatch("custom_dates", form);
  const dateError = selectedRange === "custom" ? customDateError(selectedDates) : null;
  const exportDisabled = loading || projects.length === 0 || dateError !== null;

  const closeIfIdle = () => {
    if (!lockRef.current && !loading) onClose();
  };

  const handleExport = async (values: ExportFormValues) => {
    if (lockRef.current) return;
    const selectedDateError = values.range === "custom" ? customDateError(values.custom_dates) : null;
    if (selectedDateError || !values.project_patient) return;

    const request: TrainingExportRequest = {
      project_patient: values.project_patient,
      range: values.range,
    };
    if (values.range === "custom" && values.custom_dates) {
      request.start_date = values.custom_dates[0].format("YYYY-MM-DD");
      request.end_date = values.custom_dates[1].format("YYYY-MM-DD");
    }

    lockRef.current = true;
    const session = sessionRef.current;
    setLoading(true);
    setError(null);
    try {
      await downloadTrainingDetail(patient.id, request);
      if (session === sessionRef.current) onClose();
    } catch (caught) {
      if (session === sessionRef.current) {
        setError(caught instanceof Error && caught.message ? caught.message : "导出失败，请稍后重试");
      }
    } finally {
      if (session === sessionRef.current) {
        lockRef.current = false;
        setLoading(false);
      }
    }
  };

  return (
    <Modal
      title="导出训练明细"
      open={open}
      width={600}
      rootClassName="training-detail-export-modal"
      onCancel={closeIfIdle}
      onOk={() => {
        if (!lockRef.current) void form.submit();
      }}
      okText="导出 Excel"
      confirmLoading={loading}
      okButtonProps={{ disabled: exportDisabled }}
      cancelButtonProps={{ disabled: loading }}
      closable={!loading}
      maskClosable={!loading}
      keyboard={!loading}
      destroyOnHidden
    >
      <Typography.Paragraph className="training-detail-export-patient">
        {patient.name}（{patient.phone_masked}）
      </Typography.Paragraph>

      <Form<ExportFormValues>
        form={form}
        layout="vertical"
        initialValues={{
          project_patient: initialProjectId(projects, defaultProjectPatientId),
          range: "30d",
        }}
        onFinish={(values) => void handleExport(values)}
      >
        <Form.Item name="project_patient" label="项目" rules={[{ required: true, message: "请选择项目" }]}>
          <Select
            disabled={loading}
            options={projects.map((project) => ({ value: project.id, label: project.project_name }))}
          />
        </Form.Item>

        <Form.Item name="range" label="日期范围">
          <Radio.Group disabled={loading}>
            <Radio.Button value="7d">近7天</Radio.Button>
            <Radio.Button value="30d">近30天</Radio.Button>
            <Radio.Button value="custom">自定义</Radio.Button>
            <Radio.Button value="all">全部历史</Radio.Button>
          </Radio.Group>
        </Form.Item>

        {selectedRange === "custom" ? (
          <Form.Item
            name="custom_dates"
            label="自定义日期"
            validateStatus={dateError ? "error" : undefined}
            help={dateError}
          >
            <DatePicker.RangePicker
              allowClear
              disabled={loading}
              format="YYYY-MM-DD"
              placeholder={["开始日期", "结束日期"]}
              classNames={{ popup: { root: "training-detail-export-date-popup" } }}
              style={{ width: "100%" }}
            />
          </Form.Item>
        ) : null}

        {error ? <Alert type="error" showIcon message={error} className="training-detail-export-error" /> : null}
      </Form>

      <Space direction="vertical" size={4} className="training-detail-export-help">
        <Typography.Text type="secondary">导出内容包含游戏逐题、顺序选择明细、运动结果和生理读数。</Typography.Text>
        <Typography.Text type="secondary">
          历史数据可能缺失。游戏暂无可用生理观察窗口，运动生理窗口包含处方时长后5分钟。
        </Typography.Text>
        <Typography.Text type="secondary">
          单次最多10000场，每个数据表200000行，总计500000行；超限请缩小日期范围。
        </Typography.Text>
      </Space>
    </Modal>
  );
}
