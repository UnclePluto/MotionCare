import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Collapse, Form, Space, message } from "antd";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";
import { isAxiosError } from "axios";
import { useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { baselineToFormValues, renderBaselineRegistryField } from "../../crf/renderRegistryFields";
import type { CrfRegistry, RegistryField } from "../../crf/types";
import registryJson from "../../crf/registry.v1.json";

const registry = registryJson as CrfRegistry;

type BaselinePayload = Record<string, unknown>;

function backendDetail(err: unknown): string | null {
  if (!isAxiosError(err)) return null;
  const data = err.response?.data;
  if (!data || typeof data !== "object") return null;
  const first = Object.values(data).find((v) => typeof v === "string" || Array.isArray(v));
  if (typeof first === "string") return first;
  if (Array.isArray(first) && first.length && typeof first[0] === "string") return first[0];
  if ("detail" in data && typeof (data as { detail: unknown }).detail === "string") {
    return (data as { detail: string }).detail;
  }
  return null;
}

function stringifyDemographicsDates(d: Record<string, unknown>): Record<string, unknown> {
  const o = { ...d };
  for (const k of Object.keys(o)) {
    const v = o[k];
    if (dayjs.isDayjs(v)) o[k] = (v as Dayjs).format("YYYY-MM-DD");
  }
  return o;
}

export function PatientCrfBaselinePage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { patientId } = useParams();
  const id = Number(patientId);
  const [form] = Form.useForm();

  const baselineFields = useMemo(
    () =>
      (registry.fields as RegistryField[]).filter((f) => f.storage.startsWith("patient_baseline.")),
    [],
  );

  const fieldsByTable = useMemo(() => {
    const m = new Map<string, RegistryField[]>();
    for (const f of baselineFields) {
      const key = f.table_ref || "其他";
      if (!m.has(key)) m.set(key, []);
      m.get(key)!.push(f);
    }
    for (const arr of m.values()) {
      arr.sort((a, b) => (a.doc_table_index ?? 0) - (b.doc_table_index ?? 0));
    }
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [baselineFields]);

  const { data: baseline, isLoading, isError, error } = useQuery({
    queryKey: ["patient-baseline", patientId ?? ""],
    queryFn: async () => {
      const r = await apiClient.get<BaselinePayload>(`/patients/${id}/baseline/`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  useEffect(() => {
    if (!baseline) return;
    form.setFieldsValue(baselineToFormValues(baseline));
  }, [baseline, form]);

  const saveMutation = useMutation({
    mutationFn: async (values: Record<string, unknown>) => {
      const demo = stringifyDemographicsDates(
        (values.demographics as Record<string, unknown>) ?? {},
      );
      await apiClient.patch(`/patients/${id}/baseline/`, {
        subject_id: values.subject_id,
        name_initials: values.name_initials,
        demographics: demo,
        surgery_allergy: values.surgery_allergy,
        comorbidities: values.comorbidities,
        lifestyle: values.lifestyle,
        baseline_medications: values.baseline_medications,
      });
    },
    onSuccess: async () => {
      message.success("已保存");
      await qc.invalidateQueries({ queryKey: ["patient-baseline", String(id)] });
    },
    onError: (err) => message.error(backendDetail(err) ?? "保存失败"),
  });

  if (!Number.isFinite(id)) {
    return <Alert type="error" message="无效的患者 ID" />;
  }

  if (isError) {
    return <Alert type="error" message={backendDetail(error) ?? "加载失败"} />;
  }

  return (
    <Card
      loading={isLoading}
      title="患者 CRF 基线信息"
      extra={
        <Space>
          <Button onClick={() => navigate(`/patients/${id}`)}>返回详情</Button>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={(v) => saveMutation.mutate(v as Record<string, unknown>)}
        style={{ maxWidth: 880 }}
      >
        <Collapse
          defaultActiveKey={fieldsByTable.map(([k]) => k).slice(0, 3)}
          items={fieldsByTable.map(([tableRef, fields]) => ({
            key: tableRef,
            label: tableRef,
            children: <>{fields.map((f) => renderBaselineRegistryField(f))}</>,
          }))}
        />
        <Form.Item style={{ marginTop: 16 }}>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
            保存
          </Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
