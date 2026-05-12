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
};

export type CrfRegistry = {
  template_id: string;
  template_revision: string;
  source_docx: string;
  fields: RegistryField[];
};
