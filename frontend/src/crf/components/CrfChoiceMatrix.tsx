import {Form,Typography} from 'antd';
import {crfStorageToFormName,crfRegistryFields,evaluateCrfCondition,readCrfPath} from '../fieldState';
import type {RegistryField} from '../types';
import {CrfFieldGrid,type CrfNamedField} from './CrfFieldGrid';
export type {CrfNamedField} from './CrfFieldGrid';
const testTitles:Record<string,string>={circumference:'围度测量',side_by_side:'并脚站立测试',semi_tandem:'半串联站立测试',tandem:'串联站立测试',gait:'4米步行测试',chair:'5次坐立测试',tug:'TUG测试',grip:'握力测试',sppb:'SPPB评分',subscores:'MoCA分项评分'};
// Presentation groups only: field identities, stored answers and paper bindings stay unchanged.
const demographicRows = [
 ['dm_age_years','dm_birth_date','dm_gender'],
 ['dm_marital','dm_marital_other','dm_ethnicity','dm_ethnicity_other','dm_insurance','dm_insurance_other'],
 ['dm_education_level','dm_education_years'],
 ['dm_income_band','dm_income_afford'],
 ['dm_self_health'],
 ['dm_address_city_county','dm_address_district_town','dm_address_village_community','dm_address_detail','dm_address'],
 ['dm_has_children','dm_children_count','dm_children'],
 ['dm_caregiver_type','dm_caregiver_other','dm_caregiver_contact','dm_caregiver'],
 ['dm_contact_self','dm_contact_backup','dm_phone'],
];
const demographicRowByField = new Map(demographicRows.flatMap((ids,row)=>ids.map((id,order)=>[id,{key:`demographics:${row}`,order}] as const)));
const signatureRows = [
 ['scr_t0_enrollment_investigator_name','scr_t0_enrollment_signed_on'],
 ['crf_qc_investigator_name','crf_qc_investigator_signed_on'],
 ['crf_qc_reviewer_name','crf_qc_reviewer_signed_on'],
];
const signatureRowByField = new Map(signatureRows.flatMap((ids,row)=>ids.map(id=>[id,{key:`signature:${row}`}] as const)));
function semanticGroup(binding:CrfNamedField):{key:string;title?:string}|undefined {
 const {field,name}=binding;
 const demographic=demographicRowByField.get(field.field_id);
 if(demographic)return demographic;
 const signature=signatureRowByField.get(field.field_id);
 if(signature)return signature;
 if(/^vd_T[012]_/.test(field.field_id)) {
  const suffix=field.field_id.replace(/^vd_T[012]_/, '');
  const row=suffix==='subject_id'?'identity':['assessor_name','assessed_on'].includes(suffix)?'assessor':'schedule';
  return {key:`visit-meta:${row}`};
 }
 if(/^adh_T[12]_/.test(field.field_id)) {
  const suffix=field.field_id.replace(/^adh_T[12]_/, '');
  const row=suffix.startsWith('planned_')?'planned':suffix.startsWith('actual_')?'actual':suffix.startsWith('investigator_')?'handling':suffix==='completion_rate'||suffix.startsWith('incomplete_')?'completion':'participation';
  return {key:`adherence:${row}`};
 }
 let parent=name.slice(0,-1).join('.');
 if(parent==='assessments.moca.subscores'||parent==='assessments.moca.remarks') {
  const domain=String(name[name.length-1]);
  return {key:`moca:${domain}`,title:domain==='visuospatial'?testTitles.subscores:undefined};
 }
 if(parent==='assessments.moca')return {key:'moca:result'};
 if(parent==='assessments'&&name[name.length-1]==='tug_seconds')parent='assessments.physical.tug';
 if(parent==='assessments'&&name[name.length-1]==='grip_strength_kg')parent='assessments.physical.grip';
 const part=parent.split('.').slice(-1)[0];const title=parent.startsWith('assessments.')?testTitles[part]:undefined;
 if(title)return {key:parent,title};
 if(/\.(inclusion_items|exclusion_items|items)\.[^.]+$/.test(parent)&&parent.startsWith('crf.'))return {key:parent};
 if(parent==='crf.satisfaction')return {key:parent};
 return undefined;
}
export function CrfChoiceMatrix({fields,disabled}:{fields:(RegistryField|CrfNamedField)[];disabled?:boolean}) {
 const form=Form.useFormInstance();
 return <Form.Item noStyle shouldUpdate>{()=>{
  const all=form.getFieldsValue(true) as Record<string,unknown>;
  const visible=fields.map(f=>'field' in f?f:{field:f,name:crfStorageToFormName(f.storage)}).filter(({field,name})=>evaluateCrfCondition(field.visible_when,all,crfRegistryFields)&&(!field.legacy||(readCrfPath(all,name)!=null&&readCrfPath(all,name)!=='')));
  if(!visible.length)return null;
  const groups:{key:string;title?:string;fields:CrfNamedField[]}[]=[];
  for(const binding of visible) {
   const semantic=semanticGroup(binding);const title=semantic?.title;
   const key=semantic?.key??'plain';
   const group=semantic?groups.find(g=>g.key===key):groups[groups.length-1];
   if(group?.key===key)group.fields.push(binding);else groups.push({key,title,fields:[binding]});
  }
  for(const group of groups)if(group.key.startsWith('demographics:'))group.fields.sort((a,b)=>demographicRowByField.get(a.field.field_id)!.order-demographicRowByField.get(b.field.field_id)!.order);
  return <div className="crf-grid-container"><div className="crf-choice-groups">{groups.map((group,index)=><section key={`${group.key}:${index}`} className={group.key.startsWith('moca:')?'crf-moca-row':undefined} aria-label={group.title}>{group.title?<Typography.Title level={5}>{group.title}</Typography.Title>:null}<CrfFieldGrid fields={group.fields} disabled={disabled}/></section>)}</div></div>;
 }}</Form.Item>;
}
