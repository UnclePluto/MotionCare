import {Form,Typography} from 'antd';
import {crfRegistryFields,evaluateCrfCondition,readCrfPath} from '../fieldState';
import {CrfField} from './CrfField';
import {CrfRepeatTable} from './CrfRepeatTable';
import type {CrfName} from '../fieldState';
import type {CrfCondition,RegistryField} from '../types';
export type CrfNamedField={field:RegistryField;name:CrfName};
function FieldCell({field,name,disabled}:CrfNamedField&{disabled?:boolean}) {
 const form=Form.useFormInstance();const all=form.getFieldsValue(true);
 for(let n=1;n<name.length;n++) {
  const parent=readCrfPath(all,name.slice(0,n));
  if(parent!=null&&(typeof parent!=='object'||(Array.isArray(parent)&&typeof name[n]!=='number')))return <><Typography.Text type="warning">旧记录，待核对</Typography.Text><p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{typeof parent==='string'?parent:JSON.stringify(parent)}</p></>;
 }
 const raw=readCrfPath(all,name);
 if(field.legacy)return raw!=null&&raw!==''?<><Typography.Text type="warning">旧记录，待核对</Typography.Text><Typography.Text>{field.ui_label??field.label_zh}</Typography.Text><p style={{whiteSpace:'pre-wrap'}}>{typeof raw==='string'?raw:JSON.stringify(raw)}</p></>:null;
 return field.widget==='table_repeat'?<CrfRepeatTable field={field} name={name} disabled={disabled}/>:<CrfField field={field} name={name} disabled={disabled}/>;
}
// Link presentation only; each answer keeps its original form name and validation.
function conditionStorages(condition:CrfCondition):string[] {
 if('all' in condition)return condition.all.flatMap(conditionStorages);
 if('any' in condition)return condition.any.flatMap(conditionStorages);
 return [condition.storage];
}
function linkedUnits(fields:CrfNamedField[]):CrfNamedField[][] {
 const units=fields.map(binding=>[binding]);
 for(const note of fields) {
  const field=note.field;
  if(field.legacy||!['text','textarea'].includes(field.widget))continue;
  let parents:CrfNamedField[]=[];
  if(/\.(remark|note)$/.test(field.storage)) {
   const parent=field.storage.slice(0,field.storage.lastIndexOf('.'));
   parents=fields.filter(b=>b!==note&&!b.field.legacy&&b.field.storage.slice(0,b.field.storage.lastIndexOf('.'))===parent&&['single_choice','multi_choice','number'].includes(b.field.widget));
  } else if(field.storage.includes('.moca.remarks.')) {
   parents=fields.filter(b=>b.field.storage===field.storage.replace('.moca.remarks.','.moca.subscores.'));
  } else if(field.storage.startsWith('visit.')&&field.visible_when) {
   const references=conditionStorages(field.visible_when);
   // The last explicit choice is the closest trigger (e.g. "other"), rather than a completion-rate prerequisite.
   const candidates=references.map(storage=>fields.find(b=>b.field.storage===storage&&!b.field.legacy&&['single_choice','multi_choice'].includes(b.field.widget))).filter((b):b is CrfNamedField=>Boolean(b));
   const primary=candidates[candidates.length-1];
   if(primary)parents=[primary];
  }
  if(!parents.length)continue;
  const members=[...parents,note];const matching=units.filter(unit=>unit.some(b=>members.includes(b)));
  const merged=fields.filter(b=>matching.some(unit=>unit.includes(b)));
  const first=units.indexOf(matching[0]);
  for(const unit of matching)units.splice(units.indexOf(unit),1);
  units.splice(first,0,merged);
 }
 return units;
}
export function CrfFieldGrid({fields,disabled}:{fields:CrfNamedField[];disabled?:boolean}) {
 const form=Form.useFormInstance();
 return <Form.Item noStyle shouldUpdate>{()=>{
  const all=form.getFieldsValue(true) as Record<string,unknown>;
  const visible=fields.filter(({field,name})=>evaluateCrfCondition(field.visible_when,all,crfRegistryFields)&&(!field.legacy||(readCrfPath(all,name)!=null&&readCrfPath(all,name)!=='')));
  if(!visible.length)return null;
  return <div className="crf-grid-container"><div className="crf-field-grid">{linkedUnits(visible).map(unit=>{
   const field=unit[0].field;const linked=unit.length>1;
   const wide=linked||field.widget==='textarea'||field.widget==='table_repeat'||(field.widget==='multi_choice'&&(field.options?.length??0)>4)||(field.options?.some(o=>o.length>32)??false);
   return <div key={field.field_id} className={`crf-field-cell${wide?' crf-field-wide':''}`}>{linked?<div className={`crf-linked-fields${unit.length>2?' crf-linked-fields-multiple':''}`}>{unit.map(binding=><div key={binding.field.field_id} className="crf-linked-part"><FieldCell {...binding} disabled={disabled}/></div>)}</div>:<FieldCell {...unit[0]} disabled={disabled}/>}</div>;
  })}</div></div>;
 }}</Form.Item>;
}
