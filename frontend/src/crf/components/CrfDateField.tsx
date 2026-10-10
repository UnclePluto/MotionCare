import {decodeCrfAnswer,hasCrfAnswerMarker} from '../answerValues';
import {isCrfRecord} from '../formValues';
import {DatePicker,Form,Input,Space,Typography} from 'antd';
import dayjs from 'dayjs';
import {crfMetadataFormName,crfRegistrationName,crfRelatedFormName,formatCrfDateForReview,readCrfPath,validateCrfFieldValue} from '../fieldState';
import {CrfAnswerControl} from './CrfAnswerControl';
import type {CrfDatePrecision} from './CrfMoreOptions';
import type {CrfName} from '../fieldState';
import type {RegistryField} from '../types';
export function CrfDateInput({field,value,onChange,disabled,datePrecision}:{field:RegistryField;value:unknown;onChange:(v:unknown)=>void;disabled:boolean;datePrecision:CrfDatePrecision}) {
 const label=field.ui_label??field.label_zh;const valid=typeof value==='string'&&!validateCrfFieldValue(field,value);
 if(typeof value==='string'&&value&&!valid)return <Input aria-label={label} disabled={disabled} value={value} onChange={e=>onChange(e.target.value||null)}/>;
 const format=datePrecision==='year'?'YYYY':datePrecision==='month'?'YYYY-MM':'YYYY-MM-DD';
 return <Space direction="vertical" style={{width:'100%'}}>
  <DatePicker aria-label={label} style={{width:'100%'}} disabled={disabled} picker={datePrecision==='day'?'date':datePrecision} format={format} value={valid?dayjs(value as string):null} onChange={date=>onChange(date?date.format(format):null)}/>
  {value!=null&&typeof value!=='string'?<Typography.Text type="warning">原日期：{formatCrfDateForReview(field,value)??JSON.stringify(value)}</Typography.Text>:null}
 </Space>;
}
export function CrfDateField({field,name,registrationPrefix,disabled}:{field:RegistryField;name:CrfName;registrationPrefix?:CrfName;disabled?:boolean}) {
 const form=Form.useFormInstance();
 return <Form.Item noStyle shouldUpdate>{()=>{
  const all=form.getFieldsValue(true);const partialName=field.partial_date_storage?crfRelatedFormName(field,name,field.partial_date_storage):null;
  const partial=partialName?readCrfPath(all,partialName):null;const native=readCrfPath(all,name);
  const metadataName=crfMetadataFormName(field,name);const meta=metadataName?readCrfPath(all,metadataName):undefined;
  const canonical=field.date_answer_storage?readCrfPath(all,crfRelatedFormName(field,name,field.date_answer_storage)):undefined;
  const activeName=canonical===undefined&&partial!=null&&partialName?partialName:name;
  return <>
   {canonical===undefined&&partial!=null&&native!=null?<Typography.Paragraph type="warning"><span>日期存储冲突，请核对</span><br/><span>原日期：{typeof native==='string'?native:JSON.stringify(native)}</span><br/><span>部分日期：{JSON.stringify(partial)}</span></Typography.Paragraph>:null}
   <Form.Item name={crfRegistrationName(activeName,registrationPrefix)} id={`registry-field-${field.field_id}`} getValueFromEvent={value=>{
    if(decodeCrfAnswer(native,meta).state!=='value'&&!hasCrfAnswerMarker(value)&&metadataName&&isCrfRecord(meta))form.setFields([{name:metadataName,value:{...meta,state:null,reason:null},touched:true}]);
    if(partialName&&partial!=null)form.setFields([{name:partialName,value:null,touched:true}]);
    if(activeName!==name){form.setFields([{name,value,touched:true}]);return null;}
    if(field.date_answer_storage)form.setFields([{name:crfRelatedFormName(field,name,field.date_answer_storage),value,touched:true}]);
    return value;
   }}>
    <CrfAnswerControl field={field} disabled={disabled} legacyMeta={meta}>{props=><CrfDateInput field={field} {...props}/>}</CrfAnswerControl>
   </Form.Item>
  </>;
 }}</Form.Item>;
}
