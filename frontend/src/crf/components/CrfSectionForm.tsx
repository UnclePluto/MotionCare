import {useEffect,useState,type ReactNode} from 'react';
import {Button,Form,Space,Typography} from 'antd';
import type {FormInstance} from 'antd';
import {baselineStorageToFormName} from '../baselineFormPaths';
import {visitRegistryStorageToFormName} from '../visitFormPaths';
import type {BaselineTableLayoutBlock,RegistryField} from '../types';
import {CrfChoiceMatrix} from './CrfChoiceMatrix';
import {focusCrfField} from '../visitSubmission';
import {evaluateCrfDraft} from '../draftCompleteness';
import type {CrfDraftItem} from '../draftCompleteness';

export type CrfSection={key:string;title:string;fields:RegistryField[];scope:'baseline'|'visit';visitType?:'T0'|'T1'|'T2';layout?:BaselineTableLayoutBlock};
/** Render-only: caller owns Form, snapshots, validation and payload/save. */
export function CrfSectionForm({sections,form,disabled,onDirty,progress}:{sections:CrfSection[];form:FormInstance;disabled?:boolean;onDirty?:()=>void;progress?:CrfDraftItem[]}) {
 const values=Form.useWatch([], {form,preserve:true});
 // Watching the complete store also observes setFields, row actions and dates.
 useEffect(()=>{if(form.isFieldsTouched())onDirty?.();},[values,form,onDirty]);
 return <>{sections.map(section=>{
  const fields=section.fields.filter(f=>section.scope==='baseline'?f.storage.startsWith('patient_baseline.')&&!f.visit_types?.length:(!f.visit_types?.length||Boolean(section.visitType&&f.visit_types.includes(section.visitType)))&&(f.storage.startsWith('visit.')||Boolean(f.canonical_storage)));
  const bindings=fields.flatMap(field=>{const name=section.scope==='baseline'?baselineStorageToFormName(field.storage):visitRegistryStorageToFormName(field.storage);return name?[{field,name}]:[];});

  return <section key={section.key} aria-label={section.title} style={{marginBottom:24}}><Typography.Title level={4}>{section.title}</Typography.Title><CrfDraftProgress items={progress?.filter(i=>i.table===section.key)??evaluateCrfDraft(fields,values??form.getFieldsValue(true)).items} onLocate={item=>focusCrfField(form,item.name)}/><CrfChoiceMatrix fields={bindings} disabled={disabled}/></section>;
 })}</>;
}
// Consumers read form.getFieldsValue(true); never use mounted-only onFinish.


/** Shared clinical navigation for a chapter and the full completion reminder. */
export function CrfDraftProgress({items,onLocate,expanded=false}:{items:CrfDraftItem[];onLocate:(item:CrfDraftItem)=>void;expanded?:boolean}) {
 const [open,setOpen]=useState(expanded);
 const counted=items.filter(i=>i.counted);
 const count=(state:CrfDraftItem['state'])=>counted.filter(i=>i.state===state).length;
 const unresolved=items.filter(i=>(i.counted&&i.state==='unresolved')||i.issues.length);
 return <div style={{marginBottom:12}}>
  <Typography.Paragraph>正常已填 {count('normal')} · 不详 {count('unknown')} · 不适用 {count('not_applicable')} · 未处理 {count('unresolved')}</Typography.Paragraph>
  {unresolved.length?<><Button htmlType="button" disabled={false} aria-expanded={open} onClick={()=>setOpen(!open)}>查看未处理项（{unresolved.length}）</Button>{open?<div role="region" aria-label="未处理项列表" tabIndex={0} style={{maxHeight:280,overflowY:'auto',marginTop:8}}><ul style={{paddingLeft:20}}>{unresolved.map((item,index)=><li key={`${item.fieldId}:${item.name.join('.')}:${index}`}><Button type="link" disabled={false} style={{height:'auto',whiteSpace:'normal',textAlign:'left'}} onClick={()=>onLocate(item)}>{item.label}</Button>{item.issues.length?<Typography.Text type="warning">{item.issues.join('；')}</Typography.Text>:null}</li>)}</ul></div>:null}</>:null}
 </div>;
}
const crfSaveBarStyle = {position:'sticky' as const,width:'100%',bottom:0,zIndex:10,background:'var(--ant-color-bg-container, #fff)',padding:'12px 0',marginTop:16,borderTop:'1px solid #f0f0f0'};

export function CrfSaveBar({children}:{children:ReactNode}) {return <Space wrap style={crfSaveBarStyle}>{children}</Space>;}
