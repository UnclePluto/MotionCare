import {afterEach,expect,it} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {Button,Form} from 'antd';
import {useState} from 'react';
import {CrfField} from './CrfField';
import type {RegistryField} from '../types';
afterEach(cleanup);
const field:RegistryField={field_id:'test',table_ref:'test',label_zh:'测量',storage:'visit.form_data.score',widget:'number',min:0,max:10,metadata:{storage:'visit.form_data._field_meta',key:'visit.form_data.score',states:['value','unknown','not_applicable']}};
function Editor({value=0,disabled=false,f=field}:{value?:unknown;disabled?:boolean;f?:RegistryField}){const [form]=Form.useForm();const [saved,setSaved]=useState<unknown>();return <Form form={form} initialValues={{score:value}}><CrfField field={f} name={['score']} disabled={disabled}/><Button onClick={()=>setSaved(form.getFieldsValue(true))}>保存数据</Button><output data-testid="saved">{JSON.stringify(saved)}</output></Form>;}
it('uses one business answer, preserves zero and disables the input while unknown',async()=>{
 render(<Editor/>);expect(screen.queryByRole('combobox',{name:'测量状态'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'测量更多'}));fireEvent.click(await screen.findByRole('checkbox',{name:'不详'}));
 expect(screen.getByRole('spinbutton')).toBeDisabled();fireEvent.click(screen.getByText('保存数据'));
 expect(screen.getByTestId('saved')).toHaveTextContent('{"score":{"__crf_answer__":1,"state":"unknown","value":0,"reason":null}}');
 fireEvent.click(screen.getByRole('checkbox',{name:'不详'}));expect(screen.getByRole('spinbutton')).not.toBeDisabled();expect(screen.getByRole('spinbutton')).toHaveValue('0');
 fireEvent.click(screen.getByText('保存数据'));expect(screen.getByTestId('saved')).toHaveTextContent('{"score":0}');
});
it('keeps only one mutual-exclusive state, optional reason and readonly menu',async()=>{
 render(<Editor/>);fireEvent.click(screen.getByRole('button',{name:'测量更多'}));fireEvent.click(await screen.findByRole('checkbox',{name:'不详'}));fireEvent.click(screen.getByRole('checkbox',{name:'不适用'}));fireEvent.change(screen.getByRole('textbox',{name:'测量原因'}),{target:{value:'无法测量'}});fireEvent.click(screen.getByText('保存数据'));
 expect(screen.getByTestId('saved')).toHaveTextContent('"state":"not_applicable"');expect(screen.getByTestId('saved')).toHaveTextContent('"reason":"无法测量"');
 cleanup();render(<Editor disabled/>);expect(screen.getByRole('button',{name:'测量更多'})).toBeDisabled();
});
it('offers a single date input and precision through More without separate date-part states',async()=>{
 render(<Editor value="2026-10-10" f={{...field,widget:'date',allow_partial_date:true}}/>);
 expect(screen.getAllByRole('textbox')).toHaveLength(1);expect(screen.queryByText('分别填写年月日')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'测量更多'}));fireEvent.mouseDown(await screen.findByRole('combobox',{name:'测量日期精度'}));fireEvent.click(await screen.findByText('仅年'));fireEvent.click(screen.getByText('保存数据'));
 await waitFor(()=>expect(screen.getByTestId('saved')).toHaveTextContent('{"score":"2026"}'));
});
