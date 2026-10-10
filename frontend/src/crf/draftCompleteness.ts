import {decodeCrfAnswer,hasCrfAnswerMarker} from './answerValues';
import { crfMetadataFormName, crfRegistryFields, crfStorageToFormName, evaluateCrfCondition, getCrfFieldRawValue, getObservedCrfValue, readCrfPath, readCrfStorage, validateCrfFieldValue } from './fieldState';
import type { CrfName } from './fieldState';
import { isCrfRecord } from './formValues';
import type { RegistryField } from './types';

type State = 'normal' | 'unknown' | 'not_applicable' | 'unresolved';
export type CrfDraftItem = { fieldId: string; table: string; label: string; name: CrfName; state: State; counted: boolean; required: boolean; applicable: boolean; issues: string[]; source: 'manual' | 'patient_baseline' | 'legacy' };
type Definition = RegistryField & { alternative_group?: string; export_visit_selection?: string };
const present = (v: unknown): boolean => v != null && (typeof v === 'string' ? !!v.trim() : Array.isArray(v) ? !!v.length : isCrfRecord(v) ? Object.values(v).some(present) : true);
const states = () => ({ normal: 0, unknown: 0, not_applicable: 0, unresolved: 0 });

/** Read-only draft projection of the registry rules used by backend completeness.
 * Callers pass the actual save candidate, never the display-only computed fallback.
 * Repeated children have row-local rules and full names for clinical navigation.
 */
export function evaluateCrfDraft(fields: RegistryField[], values: Record<string, unknown>, visitType = fields.find(f=>f.visit_types?.length===1)?.visit_types?.[0]) {
 const items: CrfDraftItem[] = [];
 const project = (field: Definition, data: Record<string, unknown>, local: RegistryField[], prefix: CrfName = [], labelPrefix = '', parentActive = true, table = field.table_ref): CrfDraftItem => {
  const name = prefix.length ? [...prefix, ...field.storage.split('.')] : crfStorageToFormName(field.storage);
  const raw = readCrfStorage(data, field.storage), value = getCrfFieldRawValue(field, data);
  const container = field.metadata ? readCrfStorage(data, field.metadata.storage) : undefined;
  const meta = isCrfRecord(container) && field.metadata ? container[field.metadata.key] : undefined;
  const answer=decodeCrfAnswer(value,meta);
  const explicit = answer.state;
  const reason = answer.reason?.trim() ?? '';
  const applicable = parentActive && evaluateCrfCondition(field.visible_when, data, local);
  const required = applicable && (field.include_in_completeness ?? field.required_for_complete ?? false) && evaluateCrfCondition(field.required_when, data, local);
  const issues: string[] = [];
  const rawName = prefix.length ? field.storage.split('.') : crfStorageToFormName(field.storage);
  for (let index = 1; index < rawName.length; index++) {
   const parent = readCrfPath(data, rawName.slice(0,index));
   // Arrays are valid ancestors only when the next segment indexes a row.
   const indexesRow = Array.isArray(parent) && /^\d+$/.test(String(rawName[index]));
   if (parent !== undefined && !isCrfRecord(parent) && !indexesRow) { issues.push('上级字段必须是对象'); break; }
  }
  const invalid = validateCrfFieldValue(field, value);
  if (invalid) issues.push(invalid);
  if (field.widget === 'table_repeat' && present(answer.value) && !Array.isArray(answer.value)) issues.push('明细必须是列表');
  if (!hasCrfAnswerMarker(value) && ((container != null && !isCrfRecord(container)) || (meta != null && (!isCrfRecord(meta) || (meta.state != null && !field.metadata?.states.includes(meta.state as never)) || (meta.reason != null && typeof meta.reason !== 'string'))))) issues.push('字段状态或原因无效');
  if (field.partial_date_storage) {
   const partial = readCrfStorage(data, field.partial_date_storage);
   if (raw != null && partial != null && (!field.date_answer_storage||readCrfStorage(data,field.date_answer_storage)===undefined)) issues.push('完整日期与部分日期不能同时填写');
   if (raw != null && field.storage!=='visit.visit_date' && validateCrfFieldValue({...field,allow_partial_date:false},raw)) issues.push('日期无效');
  }
  const observed = getObservedCrfValue(field,data);
  const rule = field.validation?.consistency as (NonNullable<RegistryField['validation']>['consistency'] & {comparison?:string; matched_value?:unknown; otherwise_value?:unknown; true_value?:unknown; false_value?:unknown}) | undefined;
  if (rule) {
   const operands = rule.operands.map(path => {const f=local.find(f=>f.storage===path&&!f.legacy) ?? crfRegistryFields.find(f=>f.storage===path&&!f.legacy);return f?getObservedCrfValue(f,data):null;});
   if (operands.length && operands.every(v=>typeof v==='number') && observed != null) {
    const ns=operands as number[];
    const expected = rule.operation==='sum' ? Math.min(ns.reduce((a,b)=>a+b,0),rule.cap??Infinity) : rule.operation==='min' ? Math.min(...ns) : rule.operation==='max' ? Math.max(...ns) : rule.operation==='education_bonus' && rule.comparison==='leq' ? (ns[0]<=rule.threshold! ? rule.matched_value : rule.otherwise_value) : rule.operation==='leq' ? (ns[0]<=rule.threshold! ? rule.true_value : rule.false_value) : undefined;
    if (expected!==undefined && observed!==expected) issues.push(`与已录原始值不一致，应为 ${expected}`);
   }
  }
  let state:State='unresolved';
  if (!issues.length) {
   if (explicit==='unknown'||explicit==='not_applicable') { state=explicit; }
   else if (observed!=null&&present(observed)) state='normal';
   else if(field.widget==='date'&&isCrfRecord(value)) {
    const parts=(field.date_precision==='month'?['year','month']:['year','month','day']).map(key=>isCrfRecord(value[key])?value[key].state:null);
    if(parts.every(s=>s==='value'||s==='unknown')&&parts.includes('unknown'))state='unknown';
   }
   if(present(value)&&field.legacy_options?.includes(value as string)){issues.push('旧选项，待核对');state='unresolved';}
  }
  const label=labelPrefix+(field.ui_label??field.label_zh);
  if(field.widget==='table_repeat'&&Array.isArray(answer.value)) {
   const rows=answer.value;
   const rowPrefix=answer.marked?[...name,'value']:name;
   const idKey=field.row_id_key??'_row_id';const ids=rows.flatMap(row=>isCrfRecord(row)&&typeof row[idKey]==='string'?[row[idKey]]:[]);
   rows.forEach((row,index)=>{
    if(!isCrfRecord(row)){issues.push(`第${index+1}行需核对`);state='unresolved';return;}
    const id=row[idKey];if(id!=null&&(typeof id!=='string'||!id.trim()||ids.filter(v=>v===id).length>1)){issues.push(`第${index+1}行标识需核对`);state='unresolved';}
    field.children?.forEach(child=>project(child,row,field.children!,[...rowPrefix,index],`${label} 第${index+1}行 · `,applicable&&explicit!=='unknown'&&explicit!=='not_applicable',table));
   });
  }
  const metadataName=crfMetadataFormName(field,name);
  const targetName=!hasCrfAnswerMarker(value) && state==='unresolved' && metadataName && !reason && (explicit==='unknown'||explicit==='not_applicable'||(field.widget==='date'&&isCrfRecord(value)&&Object.values(value).some(part=>isCrfRecord(part)&&part.state==='unknown'))) ? [...metadataName,'reason'] : name;
  const item:CrfDraftItem={fieldId:field.field_id,table,label,name:targetName,state,counted:applicable&&(required||present(value)||explicit==='unknown'||explicit==='not_applicable'||!!issues.length),required,applicable,issues,source:field.storage.startsWith('patient_baseline.')?'patient_baseline':'manual'};
  if(field.legacy){item.source='legacy';item.counted=false;item.required=false;if(present(raw))item.issues=['旧记录，待核对'];}
  items.push(item);
  if(isCrfRecord(meta)) for(const [key,extra] of Object.entries(meta)) {
   if(!['state','reason'].includes(key)&&present(extra)) items.push({...item,fieldId:field.field_id+':'+key,label:label+'历史补充记录',state:'unresolved',counted:false,required:false,source:'legacy',issues:[`旧记录，待核对：${typeof extra==='string'?extra:JSON.stringify(extra)}`]});
  }
  return item;
 };
 const definitions=fields as Definition[];
 // A terminal record with no entry belongs to T2. Once entered here it is
 // assessed as this visit's whole record (cross-visit conflicts remain preview issues).
 const recordedTerminal=new Set(definitions.filter(f=>f.export_visit_selection && (present(readCrfStorage(values,f.storage)) || (f.metadata&&present(readCrfStorage(values,f.metadata.storage) && (readCrfStorage(values,f.metadata.storage) as Record<string,unknown>)[f.metadata.key])))).map(f=>f.table_ref));
 const projected=definitions.filter(f=>!f.export_visit_selection || visitType==='T2' || recordedTerminal.has(f.table_ref)).map(field=>({field,item:project(field,values,[...fields,...crfRegistryFields.filter(f=>!f.visit_types?.length)])}));
 const groups=new Set(definitions.flatMap(f=>f.alternative_group?[f.alternative_group]:[]));
 for(const group of groups){const entries=projected.filter(({field})=>field.alternative_group===group);if(entries.some(({item})=>item.applicable&&item.state!=='unresolved'))for(const {field,item} of entries){const container=field.metadata?readCrfStorage(values,field.metadata.storage):null;const meta=isCrfRecord(container)&&field.metadata?container[field.metadata.key]:null;if(item.state==='unresolved'&&!present(readCrfStorage(values,field.storage))&&!item.issues.length&&(!isCrfRecord(meta)||meta.state==null||meta.state==='value'))item.counted=item.required=false;}}
 const counts=states();items.filter(i=>i.counted).forEach(i=>counts[i.state]++);
 return {items,counts,unresolved:items.filter(i=>i.counted&&i.state==='unresolved'),reviews:items.filter(i=>i.issues.length)};
}
