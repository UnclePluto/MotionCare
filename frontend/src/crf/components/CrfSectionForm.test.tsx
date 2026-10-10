import {act,cleanup,fireEvent,render,screen} from '@testing-library/react';
import {Form} from 'antd';
import type {FormInstance} from 'antd';
import {afterEach,expect,it,vi} from 'vitest';
import {CrfSectionForm} from './CrfSectionForm';
import type {CrfSection} from './CrfSectionForm';
import {crfRegistryFields} from '../fieldState';
afterEach(cleanup);
function setup(sections:CrfSection[],initial:Record<string,unknown>={}) {let form:FormInstance;const dirty=vi.fn();function Harness(){const [f]=Form.useForm();form=f;return <Form form={f} initialValues={initial}><CrfSectionForm sections={sections} form={f} onDirty={dirty}/></Form>;}const view=render(<Harness/>);return {get form(){return form!;},dirty,view};}
const f=(id:string)=>crfRegistryFields.find(f=>f.field_id===id)!;
it('renders registry fields omitted by a baseline layout and excludes visit aliases',()=>{
 setup([{key:'baseline',title:'筛选信息',scope:'baseline',fields:[f('pb_subject_id'),f('sa_has_surgery'),crfRegistryFields.find(f=>f.canonical_storage)!],layout:{rows:[{cells:[{field_id:'pb_subject_id'}]}]}}]);
 expect(screen.getByRole('textbox',{name:'受试者编号'})).toBeInTheDocument();expect(screen.getByText(f('sa_has_surgery').ui_label!)).toBeInTheDocument();expect(screen.getAllByRole('textbox',{name:'受试者编号'})).toHaveLength(1);
});
it('uses observed parent state, retains condition-hidden values and unmounted section data',()=>{
 const sections:CrfSection[]=[{key:'surgery',title:'手术史',scope:'baseline',fields:[f('sa_has_surgery'),f('sa_surgery_records')]}];
 const initial={surgery_allergy:{has_surgery:'是',surgery_records:[{_row_id:'old',name:'保留手术',hospital_note:'保留备注'}]},demographics:{_crf_field_meta:{'patient_baseline.surgery_allergy.has_surgery':{state:'unknown',reason:'待核实'}}},unmounted:{all_columns:['保留',0,null]}};
 const h=setup(sections,initial);expect(screen.queryByDisplayValue('保留手术')).not.toBeInTheDocument();expect(h.form.getFieldsValue(true)).toEqual(initial);
 act(()=>h.form.setFields([{name:['demographics','_crf_field_meta','patient_baseline.surgery_allergy.has_surgery','state'],value:'value',touched:true}]));expect(screen.getByDisplayValue('保留手术')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('radio',{name:'否'}));expect(screen.queryByDisplayValue('保留手术')).not.toBeInTheDocument();expect(h.form.getFieldValue(['surgery_allergy','surgery_records'])).toEqual(initial.surgery_allergy.surgery_records);expect(h.form.getFieldValue(['unmounted'])).toEqual(initial.unmounted);expect(h.dirty).toHaveBeenCalled();
});
it('shows old total text only when present, never fabricates structured details',()=>{const legacy=f('sat_T1_matrix_note');const h=setup([{key:'sat',title:'满意度',scope:'visit',visitType:'T1',fields:[legacy,f('sat_T1_operation_score')]}],{crf:{satisfaction:{matrix_note:'以前的总体意见'}}});expect(screen.getByText('旧记录，待核对')).toBeInTheDocument();expect(screen.getByText('以前的总体意见')).toBeInTheDocument();expect(h.form.getFieldValue(['crf','satisfaction','items'])).toBeUndefined();});
it('does not mount empty legacy text or another visit type and reads canonical baseline number',()=>{setup([{key:'sat',title:'满意度',scope:'visit',visitType:'T1',fields:[f('sat_T1_matrix_note'),f('sat_T2_operation_score'),crfRegistryFields.find(f=>f.canonical_storage&&f.visit_types?.includes('T1'))!]}],{patient_baseline:{subject_id:'NO001'}});expect(screen.queryByText('旧记录，待核对')).not.toBeInTheDocument();expect(screen.queryByRole('radio')).not.toBeInTheDocument();expect(screen.getByDisplayValue('NO001')).toBeDisabled();});


it('shows counted progress and a complete keyboard-reachable unresolved list with clinical labels',()=>{
 const h=setup([{key:'surgery',title:'手术史',scope:'baseline',fields:[f('sa_has_surgery'),f('sa_surgery_records')]}],{surgery_allergy:{has_surgery:'是',surgery_records:[{_row_id:'a',name:'甲'}]}});
 expect(screen.getByText(/正常已填.*不详.*不适用.*未处理/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/查看未处理项/}));
 const jump=screen.getByRole('button',{name:'手术记录 第1行 · 手术日期'});expect(jump).toBeInTheDocument();
 const scroll=vi.spyOn(h.form,'scrollToField');fireEvent.click(jump);
 expect(scroll).toHaveBeenCalledWith(['surgery_allergy','surgery_records',0,'date'],{focus:true});
});


it('focuses the first radio after jumping to a missing clinical choice',()=>{
 setup([{key:'surgery',title:'手术史',scope:'baseline',fields:[f('sa_has_surgery')]}]);
 fireEvent.click(screen.getByRole('button',{name:/查看未处理项/}));
 fireEvent.click(screen.getByRole('button',{name:f('sa_has_surgery').ui_label!}));
 expect(screen.getByRole('radio',{name:'否'})).toHaveFocus();
});
