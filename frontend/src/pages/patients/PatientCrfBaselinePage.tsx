import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Collapse, Form, Space, message } from "antd";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";
import { isAxiosError } from "axios";
import { useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { ageFromBirthDate } from "./ageFromBirthDate";
import { BaselineLayoutTable } from "../../crf/BaselineLayoutTable";
import { orderBaselineTableEntries } from "../../crf/baselineSectionOrder";
import { mergePatientIntoBaselineApiPayload } from "../../crf/baselinePrefill";
import { baselineToFormValues } from "../../crf/renderRegistryFields";
import type { CrfRegistry, RegistryField } from "../../crf/types";
import registryJson from "../../crf/registry.v1.json";

const registry = registryJson as CrfRegistry;

type BaselinePayload = Record<string, unknown>;

type PatientPrefill = {
  name: string;
  gender?: string | null;
  birth_date?: string | null;
  age?: number | null;
};

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
    return Array.from(m.entries());
  }, [baselineFields]);

  const fieldById = useMemo(() => {
    const map = new Map<string, RegistryField>();
    for (const f of registry.fields as RegistryField[]) {
      map.set(f.field_id, f);
    }
    return map;
  }, []);

  const orderedSections = useMemo(
    () => orderBaselineTableEntries(fieldsByTable, registry.baseline_section_order),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- registry 为构建期 JSON；显式列出 baseline_section_order 与计划一致
    [fieldsByTable, registry.baseline_section_order],
  );

  const queries = useQueries({
    queries: [
      {
        queryKey: ["patient", String(id)],
        queryFn: async () => {
          const r = await apiClient.get<PatientPrefill>(`/patients/${id}/`);
          return r.data;
        },
        enabled: Number.isFinite(id),
      },
      {
        queryKey: ["patient-baseline", String(id)],
        queryFn: async () => {
          const r = await apiClient.get<BaselinePayload>(`/patients/${id}/baseline/`);
          return r.data;
        },
        enabled: Number.isFinite(id),
      },
    ],
  });

  const patient = queries[0].data;
  const baseline = queries[1].data;
  const isLoading = queries.some((q) => q.isLoading);
  const failed = queries.find((q) => q.isError);
  const isError = Boolean(failed);
  const error = failed?.error;

  useEffect(() => {
    if (!patient || !baseline) return;
    const merged = mergePatientIntoBaselineApiPayload(
      {
        name: patient.name ?? "",
        gender: patient.gender ?? "",
        birth_date: patient.birth_date ?? null,
        age: patient.age ?? null,
      },
      baseline as Record<string, unknown>,
    );
    form.setFieldsValue(baselineToFormValues(merged));
    const demo = merged.demographics as Record<string, unknown> | undefined;
    const bd = demo?.birth_date;
    if (typeof bd === "string" && /^\d{4}-\d{2}-\d{2}$/.test(bd)) {
      const dj = dayjs(bd);
      if (dj.isValid()) {
        form.setFieldValue(["demographics", "age_years"], ageFromBirthDate(dj));
      }
    }
  }, [patient, baseline, form]);

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
        onValuesChange={(changed) => {
          const ch = changed as Record<string, unknown>;
          const demo = ch.demographics;
          if (demo == null || typeof demo !== "object") return;
          const d = demo as Record<string, unknown>;
          if (!("birth_date" in d)) return;
          const v = d.birth_date;
          if (v == null || v === "") {
            form.setFieldValue(["demographics", "age_years"], undefined);
            return;
          }
          const dj = dayjs.isDayjs(v) ? v : typeof v === "string" && v ? dayjs(v) : null;
          if (dj?.isValid()) {
            form.setFieldValue(["demographics", "age_years"], ageFromBirthDate(dj));
          }
        }}
        onFinish={(v) => saveMutation.mutate(v as Record<string, unknown>)}
        style={{ maxWidth: 1120 }}
      >
        <Collapse
          defaultActiveKey={orderedSections.map(([k]) => k).slice(0, 3)}
          items={orderedSections.map(([tableRef]) => {
            const title = registry.table_titles?.[tableRef] ?? tableRef;
            const layout = registry.baseline_table_layout?.[tableRef];
            return {
              key: tableRef,
              label: title,
              children: layout ? (
                <BaselineLayoutTable block={layout} fieldById={fieldById} />
              ) : (
                <Alert
                  type="error"
                  message={`未配置表 ${tableRef} 的 baseline_table_layout，无法按表格渲染`}
                />
              ),
            };
          })}
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
