import { Card, Descriptions, Space, Tag, Typography } from "antd";

export type CrfProjectionIssue = {
  code: string;
  scope: string;
  storage: string;
  message: string;
};

export type CrfReadOnlyField = {
  field_id: string;
  storage: string;
  label: string;
  widget: string;
  unit?: string | null;
  applicable: boolean;
  required: boolean;
  counted: boolean;
  state: "normal" | "unknown" | "not_applicable" | "unresolved";
  value: unknown;
  raw_value: unknown;
  partial_date_value?: unknown;
  metadata?: { state?: string; reason?: string } | null;
  reason: string;
  issues: CrfProjectionIssue[];
  rows: { key: string; index: number; raw_value?: unknown; fields: CrfReadOnlyField[] }[];
};

export type CrfReadOnlySection = {
  key: string;
  title: string;
  scope: string;
  table_ref: string | null;
  supplemental: boolean;
  fields: CrfReadOnlyField[];
  static_table?: { headers: string[]; rows: string[][] };
};

function displayValue(value: unknown, partialDate = false): string {
  if (value === null || value === undefined || value === "") return "未填写";
  if (Array.isArray(value)) return value.map((item) => displayValue(item)).join("、") || "未填写";
  if (typeof value === "object") {
    const object = value as Record<string, unknown>;
    if (partialDate && ["year", "month", "day"].some((part) => part in object)) {
      return (["year", "month", "day"] as const)
        .filter((part) => part in object)
        .map((part) => {
          const component = object[part] as { state?: string; value?: number } | null;
          const suffix = { year: "年", month: "月", day: "日" }[part];
          return `${component?.state === "value" ? component.value : component?.state === "unknown" ? "不详" : "未填写"}${suffix}`;
        }).join(" / ");
    }
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function FieldValue({ field, supplemental }: { field: CrfReadOnlyField; supplemental: boolean }) {
  if (!field.applicable && !supplemental) {
    return <Typography.Text type="secondary">条件未触发</Typography.Text>;
  }
  const stateText = { normal: "", unknown: "不详", not_applicable: "不适用", unresolved: field.counted ? "待处理" : "" }[field.state];
  const isRawReview = supplemental || field.issues.length > 0;
  return (
    <Space direction="vertical" size={4} style={{ width: "100%", overflowWrap: "anywhere" }}>
      {stateText && !supplemental && <Tag>{stateText}</Tag>}
      {field.widget === "table_repeat" && field.rows.length > 0 ? (
        field.rows.map((row) => (
          <div key={row.key} style={{ width: "100%" }}>
            <Typography.Text strong>第 {row.index + 1} 条</Typography.Text>
            {row.fields.length > 0 ? <FieldList fields={row.fields} supplemental={supplemental} /> : (
              <Typography.Paragraph style={{ whiteSpace: "pre-wrap" }}>{displayValue(row.raw_value)}</Typography.Paragraph>
            )}
          </div>
        ))
      ) : (
        (field.value !== null || field.state === "normal" || field.state === "unresolved") && (
          <Typography.Text style={{ whiteSpace: "pre-wrap" }}>
            {displayValue(field.value, field.widget === "date")}{field.value !== null && field.unit ? ` ${field.unit}` : ""}
          </Typography.Text>
        )
      )}
      {field.reason && <Typography.Text>{field.reason}</Typography.Text>}
      {isRawReview && !supplemental && field.raw_value !== null && (
        <Typography.Text style={{ whiteSpace: "pre-wrap" }}>原值：{displayValue(field.raw_value)}</Typography.Text>
      )}
      {isRawReview && field.partial_date_value != null && (
        <Typography.Text>部分日期：{displayValue(field.partial_date_value, true)}</Typography.Text>
      )}
      {field.issues.map((issue, index) => <Typography.Text type="warning" key={index}>{issue.message}</Typography.Text>)}
    </Space>
  );
}

function FieldList({ fields, supplemental }: { fields: CrfReadOnlyField[]; supplemental: boolean }) {
  return (
    <Descriptions bordered size="small" column={1} items={fields.map((field) => ({
      key: field.field_id,
      label: field.label,
      children: <FieldValue field={field} supplemental={supplemental} />,
    }))} />
  );
}

export function CrfReadOnlySections({ sections }: { sections: CrfReadOnlySection[] }) {
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      {sections.map((section) => (
        <Card key={section.key} title={section.scope === "study" ? section.title : `${section.scope === "patient_baseline" ? "基线资料" : section.scope} · ${section.title}`}>
          {section.static_table ? (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr>{section.static_table.headers.map((header, index) => (
                  <th key={index} scope="col" style={{ textAlign: "left", padding: 8, whiteSpace: "pre-wrap" }}>{header}</th>
                ))}</tr></thead>
                <tbody>{section.static_table.rows.map((row, index) => (
                  <tr key={index}>{row.map((cell, column) => (
                    <td key={column} style={{ padding: 8, whiteSpace: "pre-wrap" }}>{cell}</td>
                  ))}</tr>
                ))}</tbody>
              </table>
            </div>
          ) : <FieldList fields={section.fields} supplemental={section.supplemental} />}
        </Card>
      ))}
    </Space>
  );
}
