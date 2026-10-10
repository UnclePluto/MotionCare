import {cleanup,render,screen} from '@testing-library/react';
import {Form} from 'antd';
import {afterEach,expect,it} from 'vitest';
import {BaselineLayoutTable} from './BaselineLayoutTable';
import {crfRegistryFields} from './fieldState';
afterEach(cleanup);
it('renders repeat definitions and unlisted registry fields belonging to the baseline section',()=>{
 const fields=crfRegistryFields.filter(f=>f.table_ref==='#T9');const first=fields.find(f=>f.field_id==='sa_has_surgery')!;
 render(<Form initialValues={{surgery_allergy:{has_surgery:'是',surgery_records:[{_row_id:'one',name:'已录手术'}]}}}><BaselineLayoutTable block={{rows:[{cells:[{field_id:first.field_id}]}]}} fieldById={new Map(fields.map(f=>[f.field_id,f]))}/></Form>);
 expect(screen.getByDisplayValue('已录手术')).toBeInTheDocument();expect(screen.getByText('是否有过敏史')).toBeInTheDocument();expect(screen.queryByText(/#T9|registry/)).not.toBeInTheDocument();
});
it('accepts section-scoped fields outside a layout table and excludes canonical visit aliases',()=>{
 const subject=crfRegistryFields.find(f=>f.field_id==='pb_subject_id')!;const extra=crfRegistryFields.find(f=>f.field_id==='sa_has_allergy')!;const alias=crfRegistryFields.find(f=>f.canonical_storage)!;
 render(<Form><BaselineLayoutTable block={{rows:[{cells:[{field_id:subject.field_id}]}]}} fieldById={new Map([subject,extra,alias].map(f=>[f.field_id,f]))} fields={[subject,extra,alias]}/></Form>);
 expect(screen.getAllByRole('textbox',{name:'受试者编号'})).toHaveLength(1);expect(screen.getByText('是否有过敏史')).toBeInTheDocument();
});
