import { DatePicker, Form, Input, InputNumber, Select } from "antd";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";
import type { ReactNode } from "react";

import type { RegistryField } from "./types";
import { visitRegistryStorageToFormName } from "./visitFormPaths";

type RenderOpts = { disabled?: boolean };

function widgetFormItem(
  field: RegistryField,
  name: (string | number)[],
  opts: RenderOpts,
): ReactNode {
  const label = field.hint ? `${field.label_zh}（${field.hint}）` : field.label_zh;
  const fid = { id: `registry-field-${field.field_id}` as const };

  if (field.widget === "number") {
    return (
      <Form.Item key={field.field_id} name={name} label={label} {...fid}>
        <InputNumber style={{ width: "100%" }} disabled={opts.disabled} />
      </Form.Item>
    );
  }

  if (field.widget === "single_choice" && field.options?.length) {
    return (
      <Form.Item key={field.field_id} name={name} label={label} {...fid}>
        <Select
          allowClear
          disabled={opts.disabled}
          options={field.options.map((o) => ({ value: o, label: o }))}
          placeholder="请选择"
        />
      </Form.Item>
    );
  }

  if (field.widget === "date") {
    return (
      <Form.Item
        key={field.field_id}
        name={name}
        label={label}
        {...fid}
        getValueProps={(v) => ({
          value:
            v == null || v === ""
              ? undefined
              : typeof v === "string"
                ? dayjs(v)
                : dayjs.isDayjs(v)
                  ? v
                  : undefined,
        })}
        getValueFromEvent={(d: Dayjs | null) => (d ? d.format("YYYY-MM-DD") : undefined)}
      >
        <DatePicker style={{ width: "100%" }} disabled={opts.disabled} />
      </Form.Item>
    );
  }

  if (field.widget === "textarea") {
    return (
      <Form.Item key={field.field_id} name={name} label={label} {...fid}>
        <Input.TextArea rows={3} disabled={opts.disabled} />
      </Form.Item>
    );
  }

  if (field.widget === "text") {
    return (
      <Form.Item key={field.field_id} name={name} label={label} {...fid}>
        <Input disabled={opts.disabled} />
      </Form.Item>
    );
  }

  return (
    <Form.Item key={field.field_id} name={name} label={label} {...fid}>
      <Input disabled={opts.disabled} />
    </Form.Item>
  );
}

export function renderVisitRegistryField(field: RegistryField, opts: RenderOpts = {}): ReactNode {
  const name = visitRegistryStorageToFormName(field.storage);
  if (!name) return null;
  return widgetFormItem(field, name, opts);
}

/** 将 baseline API 对象转为 Form initialValues（日期字段转 dayjs 供 DatePicker） */
export function baselineToFormValues(raw: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {
    subject_id: raw.subject_id ?? "",
    name_initials: raw.name_initials ?? "",
    demographics: { ...(typeof raw.demographics === "object" && raw.demographics ? raw.demographics : {}) },
    surgery_allergy: {
      ...(typeof raw.surgery_allergy === "object" && raw.surgery_allergy ? raw.surgery_allergy : {}),
    },
    comorbidities: {
      ...(typeof raw.comorbidities === "object" && raw.comorbidities ? raw.comorbidities : {}),
    },
    lifestyle: { ...(typeof raw.lifestyle === "object" && raw.lifestyle ? raw.lifestyle : {}) },
    baseline_medications: {
      ...(typeof raw.baseline_medications === "object" && raw.baseline_medications
        ? raw.baseline_medications
        : {}),
    },
  };

  const demo = out.demographics as Record<string, unknown>;
  for (const k of Object.keys(demo)) {
    const v = demo[k];
    if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v)) {
      demo[k] = dayjs(v);
    }
  }
  return out;
}
