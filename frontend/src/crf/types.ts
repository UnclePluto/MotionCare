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
