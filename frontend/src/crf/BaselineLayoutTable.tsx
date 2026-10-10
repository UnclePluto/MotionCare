import {Form} from 'antd';
import {crfRegistryFields,evaluateCrfCondition} from './fieldState';
import type {ReactNode} from 'react';
import {baselineStorageToFormName} from './baselineFormPaths';
import {CrfChoiceMatrix} from './components/CrfChoiceMatrix';
import type {BaselineTableLayoutBlock,RegistryField} from './types';

export function BaselineLayoutTable({block,fieldById,fields,renderField:_renderField}:{block:BaselineTableLayoutBlock;fieldById:Map<string,RegistryField>;fields?:RegistryField[];renderField?:(field:RegistryField)=>ReactNode}) {
 const form=Form.useFormInstance();
 const listed=new Set(block.rows.flatMap(row=>row.cells.flatMap(cell=>cell.field_id?[cell.field_id]:[])));
 const refs=new Set([...listed].flatMap(id=>fieldById.get(id)?[fieldById.get(id)!.table_ref]:[]));
 const candidates=(fields??[...fieldById.values()].filter(f=>refs.has(f.table_ref))).filter(f=>f.storage.startsWith('patient_baseline.')&&!f.visit_types?.length);
 if(_renderField)return <Form.Item noStyle shouldUpdate>{()=>{const data=form.getFieldsValue(true);const visible=candidates.filter(f=>evaluateCrfCondition(f.visible_when,data,crfRegistryFields));return <div className="crf-grid-container"><div className="crf-field-grid">{visible.map(field=><div className="crf-field-cell" key={field.field_id}>{_renderField(field)}</div>)}</div></div>;}}</Form.Item>;
 return <CrfChoiceMatrix fields={candidates.map(field=>({field,name:baselineStorageToFormName(field.storage)!}))}/>;
}
