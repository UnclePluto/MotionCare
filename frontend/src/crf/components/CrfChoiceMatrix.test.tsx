import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {Form} from 'antd';
import type {FormInstance} from 'antd';
import {afterEach,expect,it} from 'vitest';
import {CrfChoiceMatrix} from './CrfChoiceMatrix';
import {crfRegistryFields} from '../fieldState';
import {registryVisitExtensionFields} from '../registryVisitExtensions';
import {evaluateCrfDraft} from '../draftCompleteness';
import {buildVisitSubmission} from '../visitSubmission';
afterEach(cleanup);
it('stores each numeric satisfaction score and remark separately with an independent overall score',()=>{
 let form:FormInstance;const fields=crfRegistryFields.filter(f=>f.field_id.startsWith('sat_T1_')&&!f.legacy);
 function Harness(){const [f]=Form.useForm();form=f;return <Form form={f}><CrfChoiceMatrix fields={fields}/></Form>;}
 render(<Harness/>);const scores=fields.filter(f=>f.storage.endsWith('.score')||f.storage.endsWith('overall_score'));
 scores.forEach((f,i)=>{const group=screen.getByRole('radiogroup',{name:f.ui_label!});fireEvent.click(within(group).getByRole('radio',{name:String(i===5?1:5)}));});
 fields.filter(f=>f.storage.endsWith('.remark')).forEach((f,i)=>fireEvent.change(screen.getByRole('textbox',{name:f.ui_label!}),{target:{value:`备注${i}`}}));
 expect(form!.getFieldValue(['crf','satisfaction','overall_score'])).toBe(1);expect(screen.getByText('计算值：25')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'使用计算结果'}));expect(form!.getFieldValue(['crf','satisfaction','total'])).toBe(25);
 expect(form!.getFieldValue(['crf','satisfaction','items'])).toEqual(Object.fromEntries(['operation','clarity','reminders','burden','recommendation'].map((key,i)=>[key,{score:5,remark:`备注${i}`}])));
});
it('keeps clinical decision conditions but does not append source hints',()=>{
 const f=crfRegistryFields.find(f=>f.field_id==='sa_has_surgery')!;render(<Form><CrfChoiceMatrix fields={[{...f,ui_label:'手术史（已接受手术治疗）',hint:'registry #T9 原文说明'}]}/></Form>);
 expect(screen.getByText('手术史（已接受手术治疗）')).toBeInTheDocument();expect(screen.queryByText(/registry/)).not.toBeInTheDocument();
});

it('limits wide matrix rows to three controls and labels physical test groups',()=>{
 const fields=crfRegistryFields.filter(f=>f.field_id.startsWith('as_T1_physical_gait_'));
 const {container}=render(<Form><CrfChoiceMatrix fields={fields}/></Form>);
 expect(screen.getByText('4米步行测试')).toBeInTheDocument();
 container.querySelectorAll('tr').forEach(row=>expect(row.querySelectorAll(':scope > td').length).toBeLessThanOrEqual(3));
});

it('keeps education and income questions in separate semantic rows, including conditional details',()=>{
 const fields=crfRegistryFields.filter(f=>['dm_education_level','dm_education_years','dm_income_band','dm_income_afford','dm_self_health','dm_address_city_county','dm_address_district_town','dm_address_village_community','dm_address_detail'].includes(f.field_id));
 render(<Form><CrfChoiceMatrix fields={fields}/></Form>);
 const grid=(label:string)=>screen.getByLabelText(label).closest('.crf-field-grid');
 const education=grid('文化水平');const income=grid('个人收入水平');const address=grid('市/县');
 expect(education).not.toBeNull();expect(income).not.toBe(education);
 expect(grid('教育年限（年）')).toBe(education);
 expect(grid('当前收入是否能维持日常开支')).toBe(income);
 expect(grid('自我健康评价')).not.toBe(income);
 expect(grid('区/镇/乡')).toBe(address);expect(grid('村/社区')).toBe(address);
 expect(grid('详细地址')).toBe(address);
});

it('drops entirely hidden semantic rows and keeps visible conditional details next to their parent',()=>{
 const fields=crfRegistryFields.filter(f=>['dm_marital','dm_ethnicity','dm_insurance','dm_marital_other','dm_ethnicity_other','dm_insurance_other','dm_income_afford'].includes(f.field_id)).map(f=>f.field_id==='dm_income_afford'?{...f,visible_when:{storage:'patient_baseline.demographics.show_income',op:'eq' as const,value:'是'}}:f);
 const {container}=render(<Form initialValues={{demographics:{marital_status:'其他'}}}><CrfChoiceMatrix fields={fields}/></Form>);
 expect(screen.getByRole('textbox',{name:'其他婚姻状况'}).closest('.crf-field-grid')).toBe(screen.getByLabelText('婚姻状况').closest('.crf-field-grid'));
 expect(screen.queryByLabelText('当前收入是否能维持日常开支')).toBeNull();
 expect(container.querySelectorAll('.crf-field-grid')).toHaveLength(1);
 expect(container.querySelectorAll('.crf-field-grid:empty, .crf-field-cell:empty')).toHaveLength(0);
});

it.each([
 ['纳入标准','scr_t0_inclusion_1_judgment','scr_t0_inclusion_1_remark'],
 ['满意度','sat_T1_operation_score','sat_T1_operation_remark'],
 ['质控','crf_qc_1_judgment','crf_qc_1_remark'],
 ['MoCA','as_T1_moca_naming','as_T1_moca_naming_remark'],
])('%s keeps its choice or score and remark in one complete question',(_title,choiceId,noteId)=>{
 const fields=crfRegistryFields.filter(f=>[choiceId,noteId].includes(f.field_id));
 render(<Form><CrfChoiceMatrix fields={fields}/></Form>);
 const choice=screen.getAllByLabelText(fields.find(f=>f.field_id===choiceId)!.ui_label!)[0];const note=screen.getAllByLabelText(fields.find(f=>f.field_id===noteId)!.ui_label!)[0];
 expect(choice).not.toBeNull();expect(note).not.toBeNull();
 expect(choice!.closest('.crf-linked-fields')).not.toBeNull();
 expect(note!.closest('.crf-linked-fields')).toBe(choice!.closest('.crf-linked-fields'));
});
it('keeps each satisfaction remark with its own question rather than the next score',()=>{
 const fields=crfRegistryFields.filter(f=>f.field_id.startsWith('sat_T1_')&&!f.legacy);
 const {container}=render(<Form><CrfChoiceMatrix fields={fields}/></Form>);
 const groups=container.querySelectorAll('.crf-linked-fields');expect(groups).toHaveLength(5);
 expect(groups[0]).toHaveTextContent('操作简单、易学习备注');expect(groups[0]).not.toHaveTextContent('内容清楚、容易理解');
});

it('links conditional explanations to the triggering choice and removes hidden notes without empty units',()=>{
 const fields=crfRegistryFields.filter(f=>f.field_id.startsWith('adh_T1_')&&!f.legacy);
 const {container,rerender}=render(<Form initialValues={{crf:{adherence:{completion_rate:50,incomplete_reason:'其他'}}}}><CrfChoiceMatrix fields={fields}/></Form>);
 const choice=screen.getAllByLabelText('主要未完成原因')[0];
 expect(screen.getByRole('textbox',{name:'其他未完成原因'}).closest('.crf-linked-fields')).toBe(choice.closest('.crf-linked-fields'));
 expect(choice.closest('.crf-linked-fields')).not.toContainElement(screen.getByLabelText('完成率'));
 expect(screen.queryByLabelText('其他处理说明')).toBeNull();
 rerender(<Form key="complete" initialValues={{crf:{adherence:{completion_rate:100}}}}><CrfChoiceMatrix fields={fields}/></Form>);
 expect(screen.queryByLabelText('主要未完成原因')).toBeNull();expect(screen.queryByLabelText('其他未完成原因')).toBeNull();
 expect(container.querySelectorAll('.crf-linked-fields:empty, .crf-field-cell:empty, section:empty')).toHaveLength(0);
});
it('groups planned and actual adherence separately while retaining each count and duration pair',()=>{
 const fields=crfRegistryFields.filter(f=>f.field_id.startsWith('adh_T1_')&&!f.legacy);
 render(<Form><CrfChoiceMatrix fields={fields}/></Form>);
 const grid=(label:string)=>screen.getByLabelText(label).closest('.crf-field-grid');
 expect(grid('计划次数')).toBe(grid('计划时长'));expect(grid('实际次数')).toBe(grid('实际时长'));
 expect(grid('实际次数')).not.toBe(grid('计划次数'));
});

it('limits consent entry and reminders to three fields while preserving hidden history on save',()=>{
 const fields=registryVisitExtensionFields('T0').filter(f=>f.table_ref==='#T4');
 const before={crf:{screening:{icf:'旧知情同意原文',icf_record:{signed:'是',signed_on:'2026-10-09',signer_type:'法定代理人/照护者协助签署',protocol_version:'旧方案2.0',icf_version:'旧ICF1.0',icf_version_date:'2026-09-01',proxy_relationship:'女儿'}}}};
 let form:FormInstance;
 function Harness(){const [f]=Form.useForm();form=f;return <Form form={f} initialValues={before}><CrfChoiceMatrix fields={fields}/></Form>;}
 render(<Harness/>);
 expect(screen.getAllByLabelText('已签署知情同意书')[0]).toBeInTheDocument();
 expect(screen.getByRole('textbox',{name:'签署日期',exact:true})).toHaveValue('2026-10-09');
 expect(screen.getAllByLabelText('签署主体')[0]).toBeInTheDocument();
 for(const label of ['方案版本','ICF版本','ICF版本日期','代理人/照护者关系','知情同意旧记录'])expect(screen.queryByText(label,{exact:true})).toBeNull();
 expect(evaluateCrfDraft(fields,{crf:{screening:{icf_record:{signed:'是',signed_on:'2026-10-09',signer_type:'法定代理人/照护者协助签署'}}}}).unresolved).toEqual([]);
 expect(screen.queryByText('女儿')).toBeNull();
 fireEvent.click(within(screen.getAllByLabelText('已签署知情同意书')[0]).getByRole('radio',{name:'否',exact:true}));
 expect(buildVisitSubmission(form!.getFieldsValue(true),before,{complete:false})).toEqual({form_data:{crf:{screening:{icf_record:{signed:'否'}}}}});
 expect(form!.getFieldValue(['crf','screening','icf_record','proxy_relationship'])).toBe('女儿');
 expect(form!.getFieldValue(['crf','screening','icf'])).toBe('旧知情同意原文');
});

it.each(['T0','T1','T2'])('keeps each QC signer name and date in its own semantic row on %s',visitType=>{
 const fields=registryVisitExtensionFields(visitType).filter(f=>f.table_ref==='#T30');
 const {container}=render(<Form><CrfChoiceMatrix fields={fields}/></Form>);
 const grid=(label:string)=>screen.getByRole('textbox',{name:label,exact:true}).closest('.crf-field-grid');
 const investigator=grid('研究者姓名');const reviewer=grid('质控人员姓名');
 expect(investigator).not.toBeNull();expect(grid('研究者日期')).toBe(investigator);
 expect(reviewer).not.toBe(investigator);expect(grid('质控人员日期')).toBe(reviewer);
 expect(investigator).not.toHaveTextContent('质控人员姓名');
 expect(container.querySelectorAll('.crf-field-grid:empty,.crf-field-cell:empty')).toHaveLength(0);
});
it('starts a separate screening signature row with the investigator name and date together',()=>{
 const fields=registryVisitExtensionFields('T0').filter(f=>f.table_ref==='#T7');
 render(<Form><CrfChoiceMatrix fields={fields}/></Form>);
 const name=screen.getByRole('textbox',{name:'研究者姓名',exact:true}).closest('.crf-field-grid');
 expect(name).not.toBeNull();expect(screen.getByRole('textbox',{name:'研究者签署日期',exact:true}).closest('.crf-field-grid')).toBe(name);
 expect(name).not.toHaveTextContent('受试者入选');expect(name).not.toHaveTextContent('进入干预/随访');
});


it.each(['T0','T1','T2'])('gives every MoCA domain its own row, keeps remarks paired and groups the final result on %s',visitType=>{
 const fields=crfRegistryFields.filter(f=>f.field_id.startsWith(`as_${visitType}_moca_`));
 const {container}=render(<Form><CrfChoiceMatrix fields={fields}/></Form>);
 const domains=['视空间与执行功能','命名','注意','语言','抽象','延迟回忆','定向','教育修正加分'];
 const grids=domains.map(label=>screen.getAllByLabelText(label)[0].closest('.crf-field-grid'));
 expect(new Set(grids).size).toBe(8);expect(grids.every(Boolean)).toBe(true);
 expect(screen.getByRole('textbox',{name:'命名备注'}).closest('.crf-field-grid')).toBe(grids[1]);
 expect(screen.getByRole('textbox',{name:'抽象备注'}).closest('.crf-field-grid')).toBe(grids[4]);
 const total=screen.getByRole('spinbutton',{name:'MoCA总分'}).closest('.crf-field-grid');
 expect(screen.getAllByLabelText('MoCA是否≤22分')[0].closest('.crf-field-grid')).toBe(total);
 expect(grids).not.toContain(total);expect(screen.getAllByText('MoCA分项评分',{exact:true})).toHaveLength(1);
 expect(screen.getByRole('spinbutton',{name:'注意'})).toHaveAttribute('placeholder','0–6分');
 expect(screen.getByRole('spinbutton',{name:'定向'})).toHaveAttribute('placeholder','0–6分');
 expect(screen.getByRole('spinbutton',{name:'MoCA总分'})).toHaveAttribute('placeholder','0–30分');
 expect(container.querySelectorAll('.crf-field-cell:empty,.crf-field-grid:empty')).toHaveLength(0);
});
