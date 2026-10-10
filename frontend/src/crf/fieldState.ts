import {decodeCrfAnswer,hasCrfAnswerMarker} from "./answerValues";
import registry from "./registry.v1.json";
import { baselineStorageToFormName } from "./baselineFormPaths";
import { visitRegistryStorageToFormName } from "./visitFormPaths";
import { isCrfRecord } from "./formValues";
import type { CrfCondition, RegistryField } from "./types";
export type CrfName = (string | number)[];
export const crfRegistryFields = registry.fields as RegistryField[];

export function readCrfPath(data: unknown, name: CrfName): unknown {
  let value = data;
  for (const key of name) {
    if (value == null || typeof value !== "object") return undefined;
    value = (value as Record<string | number, unknown>)[key];
  }
  return value;
}
export function crfStorageToFormName(storage: string): CrfName {
  return baselineStorageToFormName(storage) ?? visitRegistryStorageToFormName(storage) ?? storage.split(".");
}
/** Relative repeat children retain the Form.List prefix (including row index). */
export function crfRelatedFormName(field: RegistryField, name: CrfName, storage: string): CrfName {
  if (field.storage.startsWith("patient_baseline.")) return baselineStorageToFormName(storage) ?? storage.split(".");
  if (field.storage.startsWith("visit.")) return visitRegistryStorageToFormName(storage) ?? storage.split(".");
  return [...name.slice(0, -field.storage.split(".").length), ...storage.split(".")];
}
export function crfMetadataFormName(field: RegistryField, name: CrfName): CrfName | null {
  if (!field.metadata) return null;
  return [...crfRelatedFormName(field,name,field.metadata.storage), field.metadata.key];
}
export function readCrfStorage(data: Record<string, unknown>, storage: string): unknown {
  const direct = readCrfPath(data,storage.split("."));
  if (direct !== undefined) return direct;
  if (storage.startsWith("patient_baseline.") && "patient_baseline" in data) return undefined;
  if (storage.startsWith("visit.") && "visit" in data) return undefined;
  return readCrfPath(data,crfStorageToFormName(storage));
}
export function getCrfFieldRawValue(field: RegistryField, data: Record<string,unknown>): unknown {
  if(field.date_answer_storage) {
    const canonical=readCrfStorage(data,field.date_answer_storage);
    if(canonical!==undefined)return canonical;
  }
  const partial = field.partial_date_storage ? readCrfStorage(data,field.partial_date_storage) : null;
  return partial != null ? partial : readCrfStorage(data,field.storage);
}
export function hasUnknownDatePart(value: unknown): boolean {
  return isCrfRecord(value) && ["year","month","day"].some(key => isCrfRecord(value[key]) && value[key].state === "unknown");
}

/** A lossless readable summary only for date parts represented by the date controls. */
export function formatCrfDateForReview(field: Pick<RegistryField, "widget" | "allow_partial_date" | "date_precision">, value: unknown): string | null {
  if (field.widget !== "date" || !field.allow_partial_date || !isCrfRecord(value)) return null;
  const names=field.date_precision === "month" ? ["year","month"] : ["year","month","day"];
  if (Object.keys(value).some(key=>!["year","month","day"].includes(key)) || (field.date_precision === "month" && value.day != null)) return null;
  const labels:Record<string,string>={year:"年",month:"月",day:"日"};
  const parts:string[]=[];
  for (const name of names) {
    const part=value[name], label=labels[name];
    if (part == null) { parts.push(`${label}未填写`); continue; }
    if (!isCrfRecord(part) || Object.keys(part).some(key=>!["state","value"].includes(key))) return null;
    if (part.state === "value" && typeof part.value === "number" && Number.isFinite(part.value)) parts.push(`${part.value}${label}`);
    else if (part.state === "unknown" && part.value == null) parts.push(`不详${label}`);
    else if ([undefined,null,"value"].includes(part.state as string) && part.value == null) parts.push(`${label}未填写`);
    else return null; // Keep unrecognized historical values verbatim.
  }
  return parts.join("");
}

export function validateCrfFieldValue(field: RegistryField, value: unknown): string | null {
  if(hasCrfAnswerMarker(value)) {
    const answer=decodeCrfAnswer(value);
    if(answer.error)return answer.error;
    if(!field.metadata?.states.includes(answer.state))return '此字段不支持该答案状态';
    return validateCrfFieldValue(field,answer.value);
  }
  if (field.storage === "visit.visit_date" && typeof value === "string" && !value.trim()) return "请输入有效日期";
  if (value == null || (typeof value === "string" && !value.trim())) return null;
  const min = field.min ?? field.validation?.min, max = field.max ?? field.validation?.max;
  if (field.widget === "number") {
    if (typeof value !== "number" || !Number.isFinite(value)) return "请输入有效数字";
    if ((field.integer ?? field.validation?.integer) && !Number.isInteger(value)) return "请输入整数";
    if (min !== undefined && value < min) return `不能小于${min}`;
    if (max !== undefined && value > max) return `不能大于${max}`;
  } else if (field.widget === "single_choice") {
    if (typeof value !== "string" || !field.options?.includes(value)) return "请选择有效选项";
  } else if (field.widget === "multi_choice") {
    if (!Array.isArray(value) || value.some(v => typeof v !== "string" || !field.options?.includes(v)) || new Set(value).size !== value.length) return "请选择有效选项";
  } else if (field.widget === "date") {
    if (typeof value === "string") {
      if (!(field.allow_partial_date ? /^\d{4}(-\d{2})?(-\d{2})?$/ : /^\d{4}-\d{2}(-\d{2})?$/).test(value) || (!field.allow_partial_date && field.date_precision !== "month" && value.length !== 10)) return "请输入有效日期";
      const [year,month,day] = value.split("-").map(Number);
      if (!validCalendar(year,month,day)) return "请输入有效日期";
    } else if (isCrfRecord(value) && field.allow_partial_date) {
      if (Object.keys(value).some(k => !["year","month","day"].includes(k))) return "日期格式无效";
      const known: Record<string,number> = {};
      for (const [key,part] of Object.entries(value)) {
        if (part == null) continue;
        if (!isCrfRecord(part) || Object.keys(part).some(k => !["state","value"].includes(k))) return "日期分量无效";
        if (![undefined,null,"value","unknown"].includes(part.state as string)) return "日期状态无效";
        if (field.date_precision === "month" && key === "day") return "此日期仅填写年月";
        if (part.state === "value") {
          const n=part.value, limit=key === "year" ? 9999 : key === "month" ? 12 : 31;
          if (typeof n !== "number" || !Number.isInteger(n) || n < 1 || n > limit) return "日期分量超出范围";
          known[key]=n;
        } else if (part.value != null) return "未知日期不能保留数值";
      }
      if (!validCalendar(known.year,known.month,known.day)) return "请输入有效日期";
    } else return "日期格式无效";
  } else if (field.widget === "table_repeat" && !Array.isArray(value)) return "明细必须是列表";
  else if (["text","textarea"].includes(field.widget)) {
    if (typeof value !== "string") return "请输入文本";
    const limit=field.max_length ?? field.validation?.max_length;
    if (limit !== undefined && value.length > limit) return `最多${limit}字`;
  }
  return null;
}
function validCalendar(year?: number,month?: number,day?: number): boolean {
  if (year !== undefined && (year < 1 || year > 9999)) return false;
  if (month !== undefined && (month < 1 || month > 12)) return false;
  if (day !== undefined && (day < 1 || day > 31)) return false;
  if (month !== undefined && day !== undefined) {
    const leap = year === undefined || (year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0));
    const days=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31];
    if (day > days[month-1]) return false;
  }
  return true;
}
export function getObservedCrfValue(field: RegistryField, data: Record<string,unknown>): unknown | null {
  const raw=getCrfFieldRawValue(field,data);
  const container = field.metadata ? readCrfStorage(data,field.metadata.storage) : undefined;
  const meta=field.metadata && isCrfRecord(container) ? container[field.metadata.key] : container;
  const answer=decodeCrfAnswer(raw,meta);
  if(answer.error||answer.state!=='value')return null;
  if (raw == null || (typeof raw === "string" && !raw.trim()) || validateCrfFieldValue(field,raw) || field.legacy_options?.includes(raw as string)) return null;
  if (field.widget === "date" && isCrfRecord(raw)) {
    if ((field.date_precision === "month" ? ["year","month"] : ["year","month","day"]).some(k => !isCrfRecord(raw[k]) || raw[k].state !== "value")) return null;
  }
  if (field.partial_date_storage && readCrfStorage(data,field.storage) != null && readCrfStorage(data,field.partial_date_storage) != null) {
    const canonical=field.date_answer_storage?readCrfStorage(data,field.date_answer_storage):undefined;
    if(canonical===undefined||JSON.stringify(canonical)!==JSON.stringify(readCrfStorage(data,field.partial_date_storage)))return null;
  }
  return raw;
}
export function evaluateCrfCondition(condition: CrfCondition | null | undefined, data: Record<string,unknown>, fields: RegistryField[] = crfRegistryFields): boolean {
  if (!condition) return true;
  if ("all" in condition) return condition.all.every(c => evaluateCrfCondition(c,data,fields));
  if ("any" in condition) return condition.any.some(c => evaluateCrfCondition(c,data,fields));
  const matches=fields.filter(f => f.storage === condition.storage);
  const field=matches.find(f => !f.legacy) ?? matches[0];
  const observed=field ? getObservedCrfValue(field,data) : null;
  switch (condition.op) {
    case "present": return observed != null && (!Array.isArray(observed) || observed.length > 0);
    case "eq": return observed != null && observed === condition.value;
    case "ne": return observed == null || observed !== condition.value;
    case "in": return observed != null && Array.isArray(condition.value) && condition.value.includes(observed);
    case "contains": return Array.isArray(observed) && observed.includes(condition.value);
    default: return false;
  }
}

/** Only Form.Item registration is relative to Form.List; reads and writes stay complete. */
export function crfRegistrationName(name: CrfName, registrationPrefix?: CrfName): CrfName {
  return registrationPrefix?.length && registrationPrefix.every((key,index)=>name[index]===key)
    ? name.slice(registrationPrefix.length) : name;
}
