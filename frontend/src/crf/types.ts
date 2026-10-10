export type CrfMarkedAnswer = {__crf_answer__:1;state:'unknown'|'not_applicable';value:unknown;reason:string|null};
export type CrfFieldState = "value" | "unknown" | "not_applicable";
export type CrfCondition = { all: CrfCondition[] } | { any: CrfCondition[] } | {
  storage: string; op: "eq" | "ne" | "in" | "present" | "contains"; value?: unknown;
};
export type CrfPartialDate = Partial<Record<"year" | "month" | "day", {state?: "value" | "unknown" | null; value?: number | null} | null>>;

export type CrfVisitDateAnswer = string | CrfPartialDate | CrfMarkedAnswer | null;

export type RegistryField = {
  field_id: string;
  table_ref: string;
  label_zh: string;
  widget: string;
  storage: string;
  required_for_complete?: boolean;
  visit_types?: string[] | null;
  options?: string[];
  hint?: string;
  ui_label?: string;
  unit?: string;
  min?: number;
  max?: number;
  integer?: boolean;
  max_length?: number;
  date_precision?: "day" | "month";
  allow_partial_date?: boolean;
  partial_date_storage?: string;
  date_answer_storage?: string;
  canonical_storage?: string;
  edit_scope?: string;
  visible_when?: CrfCondition | null;
  required_when?: CrfCondition | null;
  metadata?: { storage: string; key: string; states: CrfFieldState[]; reason_required_for_handled?: boolean };
  legacy?: boolean;
  legacy_options?: string[];
  option_labels?: Record<string, string>;
  children?: RegistryField[];
  row_id_key?: string;
  row_metadata_key?: string;
  section?: string;
  order?: number;
  include_in_completeness?: boolean;
  validation?: {min?: number; max?: number; integer?: boolean; max_length?: number; consistency?: {operation: string; operands: string[]; cap?: number; threshold?: number}};
  doc_table_index?: number;
  other_remark_storage?: string;
  other_remark_widget?: "text" | "textarea";
};

export type BaselineLayoutCell = {
  field_id?: string;
  blank?: boolean;
  colspan?: number;
  rowspan?: number;
};

export type BaselineLayoutRow = {
  cells: BaselineLayoutCell[];
};

export type BaselineTableLayoutBlock = {
  rows: BaselineLayoutRow[];
};

export type CrfRegistry = {
  template_id: string;
  template_revision: string;
  source_docx: string;
  table_titles?: Record<string, string>;
  fields: RegistryField[];
  baseline_section_order?: string[];
  baseline_table_layout?: Record<string, BaselineTableLayoutBlock>;
};
