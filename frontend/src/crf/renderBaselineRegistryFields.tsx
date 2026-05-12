import { DatePicker, Form, Input, InputNumber, Radio } from "antd";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";
import { Fragment, type ReactNode } from "react";

import { baselineStorageToFormName } from "./baselineFormPaths";
import type { RegistryField } from "./types";

function baselineNonChoiceField(field: RegistryField, name: (string | number)[]): ReactNode {
  const label = field.hint ? `${field.label_zh}（${field.hint}）` : field.label_zh;
  const fid = { id: `registry-field-${field.field_id}` as const };

  if (field.widget === "number") {
    return (
      <Form.Item key={field.field_id} name={name} label={label} {...fid}>
        <InputNumber style={{ width: "100%" }} />
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
        <DatePicker style={{ width: "100%" }} />
      </Form.Item>
    );
  }

  if (field.widget === "textarea") {
    return (
      <Form.Item key={field.field_id} name={name} label={label} {...fid}>
        <Input.TextArea rows={3} />
      </Form.Item>
    );
  }

  if (field.widget === "text") {
    return (
      <Form.Item key={field.field_id} name={name} label={label} {...fid}>
        <Input />
      </Form.Item>
    );
  }

  return (
    <Form.Item key={field.field_id} name={name} label={label} {...fid}>
      <Input />
    </Form.Item>
  );
}

function BaselineSingleChoiceField({
  field,
  name,
}: {
  field: RegistryField;
  name: (string | number)[];
}): ReactNode {
  const label = field.hint ? `${field.label_zh}（${field.hint}）` : field.label_zh;
  const fid = { id: `registry-field-${field.field_id}` as const };
  const hasOtherRemark =
    field.options!.includes("其他") &&
    typeof field.other_remark_storage === "string" &&
    field.other_remark_storage.length > 0;
  const remarkName = hasOtherRemark ? baselineStorageToFormName(field.other_remark_storage!) : null;
  const mainValue = Form.useWatch(name) as string | undefined;
  const showRemark = hasOtherRemark && remarkName && mainValue === "其他";
  const RemarkInput = field.other_remark_widget === "textarea" ? Input.TextArea : Input;

  const remarkFid = { id: `registry-field-${field.field_id}-other-remark` as const };

  return (
    <Fragment>
      <Form.Item name={name} label={label} {...fid}>
        <Radio.Group style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px" }}>
          {field.options!.map((o) => (
            <Radio key={o} value={o} style={{ lineHeight: 2 }}>
              {o}
            </Radio>
          ))}
        </Radio.Group>
      </Form.Item>
      {showRemark && remarkName ? (
        <Form.Item key={`${field.field_id}-other-remark`} name={remarkName} label="其他说明" {...remarkFid}>
          <RemarkInput {...(field.other_remark_widget === "textarea" ? { rows: 3 } : {})} />
        </Form.Item>
      ) : null}
    </Fragment>
  );
}

export function renderBaselineRegistryField(field: RegistryField): ReactNode {
  if (field.widget === "single_choice" && field.options?.length) {
    const name = baselineStorageToFormName(field.storage);
    if (!name) return null;
    return <BaselineSingleChoiceField key={field.field_id} field={field} name={name} />;
  }
  const name = baselineStorageToFormName(field.storage);
  if (!name) return null;
  return baselineNonChoiceField(field, name);
}
