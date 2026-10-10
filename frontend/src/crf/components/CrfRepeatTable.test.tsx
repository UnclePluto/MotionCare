import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {Button,Form} from 'antd';
import type {FormInstance} from 'antd';
import {afterEach,expect,it,vi} from 'vitest';
import {CrfRepeatTable} from './CrfRepeatTable';
import {crfRegistryFields,crfStorageToFormName} from '../fieldState';
import {buildCrfPatch} from '../formValues';
import type {RegistryField} from '../types';
afterEach(cleanup);
function setup(field:RegistryField,initial:Record<string,unknown>={}) {
 let form:FormInstance; const name=crfStorageToFormName(field.storage);
 function Harness(){const [f]=Form.useForm();form=f;return <Form form={f} initialValues={initial}><CrfRepeatTable field={field} name={name}/></Form>;}
 render(<Harness/>);return {get form(){return form!;},name};
}
const find=(id:string)=>crfRegistryFields.find(f=>f.field_id===id)!;
it.each([['sa_surgery_records',4],['sa_allergy_records',3],['crf_T1_medication_change_entries',3],['crf_T1_adverse_events_entries',4]] as const)('adds %s beyond paper rows with complete column values and stable IDs', (id,count)=>{
 const field=find(id); const h=setup({...field,visible_when:null});expect(h.form.getFieldValue(h.name)).toBeUndefined();
 for(let i=0;i<count;i++) fireEvent.click(screen.getByRole('button',{name:`新增${field.ui_label}`}));
 const rows=h.form.getFieldValue(h.name);expect(rows).toHaveLength(count);expect(new Set(rows.map((r:Record<string,unknown>)=>r._row_id)).size).toBe(count);
 field.children!.filter(c=>!c.visible_when).forEach(child=>expect(screen.getAllByText(child.ui_label!,{selector:'label'})).toHaveLength(count));
 const complete=rows.map((r:Record<string,unknown>,i:number)=>({...r,...Object.fromEntries(field.children!.map(c=>[c.storage,c.widget==='date'?'2026-10-08':c.widget==='single_choice'?c.options![0]:`第${i+1}条${c.ui_label}`])),_field_meta:{[field.children![0].storage]:{state:'value',reason:`行${i+1}`}}}));
 act(()=>h.form.setFields([{name:h.name,value:complete,touched:true}]));
 expect(h.form.getFieldsValue(true)).toEqual(expect.objectContaining(id.startsWith('sa_')?{surgery_allergy:expect.any(Object)}:{crf:expect.any(Object)}));
 expect(h.form.getFieldValue(h.name)).toEqual(complete);
 if(id==='crf_T1_adverse_events_entries')expect(h.form.getFieldValue(['crf','adverse_events','entries'])).toHaveLength(4);
 fireEvent.click(screen.getByRole('button',{name:'上移第2条'}));
 expect(h.form.getFieldValue(h.name)).toEqual([complete[1],complete[0],...complete.slice(2)]);
 fireEvent.click(screen.getByRole('button',{name:'删除第2条'}));
 fireEvent.click(screen.getByRole('button',{name:'确认删除'}));
 expect(h.form.getFieldValue(h.name)).toEqual([complete[1],...complete.slice(2)]);
 expect(buildCrfPatch({},h.form.getFieldsValue(true))).toEqual(h.form.getFieldsValue(true));
});
it('keeps row-local unknown reason and clears only that row while preserving identity',async()=>{
 const field={...find('sa_surgery_records'),visible_when:null};
 const rows=[{_row_id:'a',name:'甲',date:'2026-05-01',hospital_note:'备注甲',_field_meta:{date:{state:'unknown',reason:'年份不详甲'}}},{_row_id:'b',name:'乙',date:'2026-06-01',hospital_note:'备注乙',_field_meta:{date:{state:'unknown',reason:'年份不详乙'}}}];
 const h=setup(field,{surgery_allergy:{surgery_records:rows}});
 fireEvent.click(within(screen.getByRole('group',{name:'手术记录第2条'})).getByRole('button',{name:'手术日期更多'}));
 fireEvent.change(await screen.findByRole('textbox',{name:'手术日期原因'}),{target:{value:'更正乙'}});
 fireEvent.click(screen.getByRole('button',{name:'上移第2条'}));
 expect(h.form.getFieldValue(h.name)[0]).toEqual({...rows[1],date:{__crf_answer__:1,state:'unknown',value:'2026-06-01',reason:'更正乙'}});
 fireEvent.click(screen.getByRole('button',{name:'清空第1条'}));
 const current=h.form.getFieldValue(h.name);expect(current[0]._row_id).toBe('b');expect(current[0].hospital_note).toBeNull();expect(current[0]._field_meta.date).toEqual({state:null,reason:null});expect(current[1]).toEqual(rows[0]);
});
it('keeps missing and duplicate historical IDs without collapsing or rewriting rows',()=>{
 const field={...find('sa_surgery_records'),visible_when:null};const rows=[{name:'旧无ID'},{_row_id:'same',name:'旧甲'},{_row_id:'same',name:'旧乙'}];
 const h=setup(field,{surgery_allergy:{surgery_records:rows}});expect(h.form.getFieldValue(h.name)).toEqual(rows);
 expect(screen.getByDisplayValue('旧无ID')).toBeInTheDocument();expect(screen.getByDisplayValue('旧甲')).toBeInTheDocument();expect(screen.getByDisplayValue('旧乙')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'上移第3条'}));expect(h.form.getFieldValue(h.name)).toEqual([rows[0],rows[2],rows[1]]);
});
it('preserves a historical scalar without guessing rows',()=>{const h=setup({...find('sa_surgery_records'),visible_when:null},{surgery_allergy:{surgery_records:'原手术散文'}});expect(screen.getByText('原手术散文')).toBeInTheDocument();expect(screen.queryByRole('button',{name:'新增手术记录'})).not.toBeInTheDocument();expect(h.form.getFieldValue(h.name)).toBe('原手术散文');});

it('preserves a historical scalar parent container',()=>{const h=setup({...find('sa_surgery_records'),visible_when:null},{surgery_allergy:'原完整手术过敏文字'});expect(screen.getByText('原完整手术过敏文字')).toBeInTheDocument();expect(h.form.getFieldsValue(true)).toEqual({surgery_allergy:'原完整手术过敏文字'});});
it('retains the outer Form submission and change callbacks',async()=>{const finish=vi.fn(),change=vi.fn();function Harness(){const [form]=Form.useForm();return <Form form={form} onFinish={finish} onValuesChange={change}><CrfRepeatTable field={{...find('sa_surgery_records'),visible_when:null}} name={['surgery_allergy','surgery_records']}/><Button htmlType="submit">保存</Button></Form>;}render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'新增手术记录'}));fireEvent.change(screen.getByRole('textbox',{name:'手术名称'}),{target:{value:'新手术'}});fireEvent.click(screen.getByRole('button',{name:/保.*存/}));await waitFor(()=>expect(finish).toHaveBeenCalled());expect(change).toHaveBeenCalled();expect(finish.mock.calls[0][0].surgery_allergy.surgery_records[0].name).toBe('新手术');});

it('edits each row date and metadata through the list prefix without crossing rows',async()=>{
 const rows=[{_row_id:'date-a',name:'甲',date:'2026-05-01',hospital_note:'甲医院'},{_row_id:'date-b',name:'乙',date:'2026-06-02',hospital_note:'乙医院'}];const h=setup({...find('sa_surgery_records'),visible_when:null},{surgery_allergy:{surgery_records:rows}});
 const group=screen.getByRole('group',{name:'手术记录第2条'});fireEvent.click(within(group).getByRole('button',{name:'手术日期更多'}));
 fireEvent.mouseDown(await screen.findByRole('combobox',{name:'手术日期日期精度'}));fireEvent.click(await screen.findByText('年月'));
 fireEvent.click(screen.getByRole('checkbox',{name:'不详'}));fireEvent.change(screen.getByRole('textbox',{name:'手术日期原因'}),{target:{value:'乙日期不详'}});
 expect(h.form.getFieldValue(h.name)).toEqual([rows[0],{...rows[1],date:{__crf_answer__:1,state:'unknown',value:'2026-06',reason:'乙日期不详'}}]);
 fireEvent.click(screen.getByRole('button',{name:'上移第2条'}));expect(h.form.getFieldValue(h.name)[0]._row_id).toBe('date-b');expect(h.form.getFieldValue(h.name)[0].date.reason).toBe('乙日期不详');expect(h.form.getFieldValue(h.name)[1]).toEqual(rows[0]);
});

it('fills four adverse events through every column control and retains unmounted data in the complete store',()=>{
 const field={...find('crf_T1_adverse_events_entries'),visible_when:null};const h=setup(field,{unmounted:{zero:0,old:'其他章节',nullValue:null}});
 for(let i=0;i<4;i++)fireEvent.click(screen.getByRole('button',{name:'新增不良事件明细'}));
 for(let i=0;i<4;i++){
  const group=screen.getByRole('group',{name:`不良事件明细第${i+1}条`});
  for(const child of field.children!){
   if(child.widget==='single_choice')fireEvent.click(within(group).getByRole('radio',{name:child.options![i%child.options!.length]}));
   else {const input=within(group).getByRole('textbox',{name:child.ui_label!});fireEvent.change(input,{target:{value:child.widget==='date'?`2026-10-0${i+1}`:`${child.ui_label}${i+1}`}});if(child.widget==='date'){fireEvent.keyDown(input,{key:'Enter',code:'Enter'});fireEvent.blur(input);}}
  }
 }
 const rows=h.form.getFieldValue(['crf','adverse_events','entries']);expect(rows).toHaveLength(4);
 rows.forEach((row:Record<string,unknown>,i:number)=>field.children!.forEach(child=>expect(row[child.storage]).toEqual(child.widget==='date'?`2026-10-0${i+1}`:child.widget==='single_choice'?child.options![i%child.options!.length]:`${child.ui_label}${i+1}`)));
 expect(h.form.getFieldsValue(true).unmounted).toEqual({zero:0,old:'其他章节',nullValue:null});
});

it('protects an old array where the repeat parent should be an object',()=>{const h=setup({...find('sa_surgery_records'),visible_when:null},{surgery_allergy:['旧父容器']});expect(screen.getByText('["旧父容器"]')).toBeInTheDocument();expect(screen.queryByRole('button',{name:'新增手术记录'})).not.toBeInTheDocument();expect(h.form.getFieldsValue(true)).toEqual({surgery_allergy:['旧父容器']});});


it('requires deletion confirmation, cancellation preserves untouched store, confirmed deletion preserves the adjacent record',async()=>{
 const rows=[{_row_id:'first',name:'甲',_field_meta:{date:{state:'unknown',reason:'甲原因'}}},{_row_id:'second',name:'乙',_field_meta:{date:{state:'unknown',reason:'乙原因'}}}];
 const h=setup({...find('sa_surgery_records'),visible_when:null},{surgery_allergy:{surgery_records:rows}});
 fireEvent.click(screen.getByRole('button',{name:'删除第1条'}));
 expect(h.form.getFieldValue(h.name)).toEqual(rows);
 expect(h.form.isFieldsTouched()).toBe(false);
 expect(await screen.findByText(/该条明细及反馈.*原因.*保存后移除/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/取.*消/}));
 expect(h.form.getFieldValue(h.name)).toEqual(rows);expect(h.form.isFieldsTouched()).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'删除第1条'}));
 fireEvent.click(await screen.findByRole('button',{name:'确认删除'}));
 await waitFor(()=>expect(h.form.getFieldValue(h.name)).toEqual([rows[1]]));
});

it('renders conditional surgery rows when the valid controlling metadata retains historical feedback',()=>{
 const h=setup(find('sa_surgery_records'),{surgery_allergy:{has_surgery:'是',surgery_records:[{_row_id:'a',name:'旧手术'}]},demographics:{_crf_field_meta:{'patient_baseline.surgery_allergy.has_surgery':{state:'value',legacy_feedback:'旧反馈'}}}});
 fireEvent.change(screen.getByRole('textbox',{name:'手术名称'}),{target:{value:'修订手术'}});
 expect(h.form.getFieldValue(h.name)[0].name).toBe('修订手术');
 expect(h.form.getFieldValue(['demographics','_crf_field_meta','patient_baseline.surgery_allergy.has_surgery']).legacy_feedback).toBe('旧反馈');
});
