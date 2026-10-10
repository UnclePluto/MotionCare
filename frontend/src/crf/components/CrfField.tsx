import {CrfAnswerControl} from "./CrfAnswerControl";
import {decodeCrfAnswer,hasCrfAnswerMarker} from "../answerValues";
import {Button,Checkbox,Form,Input,InputNumber,Radio,Select,Space,Typography} from "antd";
import {calculateCrfDerivedValue,crfCalculationForStorage} from "../fieldCalculations";
import {crfRegistrationName,crfMetadataFormName,crfRegistryFields,crfRelatedFormName,evaluateCrfCondition,getObservedCrfValue,formatCrfDateForReview,readCrfPath,validateCrfFieldValue} from "../fieldState";
import type {CrfName} from "../fieldState";
import {isCrfRecord} from "../formValues";
import type {RegistryField} from "../types";
import {CrfDateField} from "./CrfDateField";

type Props={field:RegistryField;name:CrfName;registrationPrefix?:CrfName;disabled?:boolean};
// Only explicit editing clears text; historical empty strings stay intact on mount.
function textInputValue(value: string | null | {target:{value:string}}): string | null {
 const text=typeof value === "object" && value !== null ? value.target.value : value;
 return text === "" ? null : text;
}
function LegacyControl({value,onChange,disabled}:{value?:unknown;onChange?:(v:unknown)=>void;disabled?:boolean}) {
 return <Input disabled={disabled} value={typeof value === "string" ? value : JSON.stringify(value)} onChange={e=>onChange?.(e.target.value || null)}/>;
}
function NumberControl({field,value,onChange,disabled}:{field:RegistryField;value?:unknown;onChange?:(v:unknown)=>void;disabled?:boolean}) {
 if (value != null && typeof value !== "number") return <Input aria-label={field.ui_label ?? field.label_zh} disabled={disabled} value={typeof value === "string" ? value : JSON.stringify(value)} onChange={e=>{
  const text=e.target.value;onChange?.(text === "" ? null : /^-?\d+(\.\d+)?$/.test(text) ? Number(text) : text);
 }}/>;
 const min=field.min ?? field.validation?.min;const max=field.max ?? field.validation?.max;
 const unit=field.unit??(field.storage.includes('.moca.')?'分':'');
 const placeholder=min!=null&&max!=null?`${min}–${max}${unit}`:min!=null?`≥${min}${unit}`:max!=null?`≤${max}${unit}`:undefined;
 return <InputNumber placeholder={placeholder} aria-label={field.ui_label ?? field.label_zh} style={{width:"100%"}} disabled={disabled} value={value as number | null | undefined} onChange={onChange}
  min={field.min ?? field.validation?.min} max={field.max ?? field.validation?.max} precision={(field.integer ?? field.validation?.integer) ? 0 : undefined}/>;
}
export function CrfField({field,name,registrationPrefix,disabled}:Props) {
 const form=Form.useFormInstance();
 return <Form.Item noStyle shouldUpdate>{()=>{
  const all=form.getFieldsValue(true) as Record<string,unknown>;
  const relative=!field.storage.startsWith("patient_baseline.") && !field.storage.startsWith("visit.");
  const row=relative ? readCrfPath(all,name.slice(0,-field.storage.split(".").length)) : all;
  const data=isCrfRecord(row) ? row : all;
  const siblings=relative ? crfRegistryFields.find(f=>f.children?.some(c=>c.field_id === field.field_id))?.children ?? [field] : crfRegistryFields;
  if (!evaluateCrfCondition(field.visible_when,data,siblings)) return null;
  const label=field.ui_label ?? field.label_zh;
  const raw=readCrfPath(all,name);
  const metadataName=crfMetadataFormName(field,name);
  const meta=metadataName ? readCrfPath(all,metadataName) : undefined;
  const answer=decodeCrfAnswer(raw,meta);
  const state=answer.state;
  const handled=state === "unknown" || state === "not_applicable";
  const canonical=Boolean(field.canonical_storage && field.visit_types?.length);
  const inactive=disabled || handled || canonical;
  const partial=field.partial_date_storage ? readCrfPath(all,crfRelatedFormName(field,name,field.partial_date_storage)) : raw;

  const options=field.options?.map(value=>({value,label:field.option_labels?.[value] ?? value})) ?? [];
  const short=options.length <= 6 && options.every(o=>o.label.length <= 16);
  const kind=crfCalculationForStorage(field.storage);
  const result=kind ? calculateCrfDerivedValue(kind,all) : null;
  const displayedRaw=partial ?? raw;
  const currentError=validateCrfFieldValue(field,displayedRaw);
  const readableDate=formatCrfDateForReview(field,displayedRaw);
  const touchedName=field.partial_date_storage && partial != null ? crfRelatedFormName(field,name,field.partial_date_storage) : name;
  const observed=getObservedCrfValue(field,data);
  const remarkName=field.other_remark_storage ? crfRelatedFormName(field,name,field.other_remark_storage) : null;
  const showRemark=remarkName && (observed === "其他" || (Array.isArray(observed) && observed.includes("其他")));
  const shortScore=field.widget==='number'&&(field.integer??field.validation?.integer)&&field.min!==undefined&&field.max!==undefined&&field.max-field.min<=5&&name[name.length-1]!=='total';
  const control=(props:{value:unknown;onChange:(v:unknown)=>void;disabled:boolean})=>{
   if(field.widget==='number')return shortScore&&!validateCrfFieldValue(field,props.value)?<div role="radiogroup" aria-label={label}><Radio.Group aria-label={label} disabled={props.disabled} value={props.value} onChange={e=>props.onChange(e.target.value)} options={Array.from({length:field.max!-field.min!+1},(_,i)=>({label:String(field.min!+i),value:field.min!+i}))}/></div>:<NumberControl field={field} {...props}/>;
   if(props.value!=null&&validateCrfFieldValue(field,props.value))return <LegacyControl {...props}/>;
   if(field.widget==='single_choice')return short?<Radio.Group aria-label={label} {...props} onChange={e=>props.onChange(e.target.value)} options={options} style={{display:'flex',flexWrap:'wrap',gap:'8px 16px'}}/>:<Select aria-label={label} {...props} allowClear showSearch optionFilterProp="label" options={options} onChange={v=>props.onChange(v??null)} placeholder="请选择"/>;
   if(field.widget==='multi_choice')return short?<Checkbox.Group aria-label={label} {...props} value={props.value as string[]|undefined} options={options} style={{display:'flex',flexWrap:'wrap',gap:'8px 16px'}}/>:<Select aria-label={label} {...props} mode="multiple" value={props.value as string[]|undefined} allowClear showSearch optionFilterProp="label" options={options} placeholder="请选择"/>;
   return field.widget==='textarea'?<Input.TextArea aria-label={label} disabled={props.disabled} value={(props.value??undefined) as string|undefined} rows={3} maxLength={field.max_length} onChange={e=>props.onChange(textInputValue(e))}/>:<Input aria-label={label} disabled={props.disabled} value={(props.value??undefined) as string|undefined} maxLength={field.max_length} onChange={e=>props.onChange(textInputValue(e))}/>;
  };
  return <>
   {field.widget==='date'?<CrfDateField field={field} name={name} registrationPrefix={registrationPrefix} disabled={disabled||canonical}/>:<Form.Item name={crfRegistrationName(name,registrationPrefix)} id={`registry-field-${field.field_id}`} getValueFromEvent={value=>{
    if(handled&&!hasCrfAnswerMarker(value)&&metadataName&&isCrfRecord(meta))form.setFields([{name:metadataName,value:{...meta,state:null,reason:null},touched:true}]);
    return value;
   }}><CrfAnswerControl field={field} disabled={disabled||canonical} legacyMeta={meta}>{control}</CrfAnswerControl></Form.Item>}
   {((field.widget==='single_choice'&&short)||shortScore)&&answer.value!=null?<Button size="small" disabled={inactive} style={{marginBottom:12}} onClick={()=>form.setFields([{name,value:null,touched:true}])}>{shortScore?'清除评分':'清除选择'}</Button>:null}
   {field.storage === "visit.form_data.crf.adherence.completion_rate" ? <Space wrap style={{marginBottom:16}}>
    <Typography.Text>次数比值：{calculateCrfDerivedValue("count_ratio",all) == null ? "待填写" : `${calculateCrfDerivedValue("count_ratio",all)}%`}</Typography.Text>
    <Typography.Text>时长比值：{calculateCrfDerivedValue("time_ratio",all) == null ? "待填写" : `${calculateCrfDerivedValue("time_ratio",all)}%`}</Typography.Text>
   </Space> : null}
   {currentError && readableDate ? <Typography.Text type="warning">日期需核对：{readableDate}（{currentError}）</Typography.Text> : currentError && !form.isFieldTouched(touchedName) ? <Typography.Text type="warning">原值需核对：{typeof displayedRaw === "object" ? JSON.stringify(displayedRaw) : String(displayedRaw)}</Typography.Text> : null}
   {kind ? <Space style={{marginBottom:16}}><Button disabled={inactive || result == null} onClick={()=>form.setFields([{name,value:result,touched:true}])}>使用计算结果</Button>{result != null ? <Typography.Text>计算值：{result}</Typography.Text> : null}</Space> : null}
   {showRemark && remarkName ? <Form.Item name={crfRegistrationName(remarkName,registrationPrefix)} label="其他说明" getValueFromEvent={textInputValue}>{field.other_remark_widget === "textarea" ? <Input.TextArea disabled={disabled} rows={3}/> : <Input disabled={disabled}/>}</Form.Item> : null}
  </>;
 }}</Form.Item>;
}
