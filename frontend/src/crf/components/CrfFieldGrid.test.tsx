import {afterEach,expect,it} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {Form} from 'antd';
import {CrfChoiceMatrix} from './CrfChoiceMatrix';
import {CrfSectionForm} from './CrfSectionForm';
import type {RegistryField} from '../types';
afterEach(cleanup);
const fields:RegistryField[]=[{field_id:'hidden',table_ref:'test',label_zh:'隐藏字段',widget:'text',storage:'visit.form_data.hidden',visible_when:{storage:'visit.form_data.trigger',op:'eq',value:'是'}},{field_id:'assessor',table_ref:'test',label_zh:'评估者',widget:'text',storage:'visit.form_data.assessor'},{field_id:'date',table_ref:'test',label_zh:'评估日期',widget:'date',storage:'visit.form_data.date'},{field_id:'remark',table_ref:'test',label_zh:'反馈',widget:'textarea',storage:'visit.form_data.remark'}];
it('filters hidden controls before placing cells, packs short fields and spans feedback',()=>{
 const {container}=render(<Form><CrfChoiceMatrix fields={fields}/></Form>);
 expect(screen.queryByText('隐藏字段')).toBeNull();expect(container.querySelectorAll('table')).toHaveLength(0);
 const cells=container.querySelectorAll('.crf-field-cell');expect(cells).toHaveLength(3);expect(cells[0]).toHaveTextContent('评估者');expect(cells[2]).toHaveClass('crf-field-wide');
});
it('ordinary sections do not reproduce nested paper tables or placeholder blank cells',()=>{
 function Editor(){const [form]=Form.useForm();return <Form form={form}><CrfSectionForm form={form} sections={[{key:'test',title:'普通信息',scope:'visit',visitType:'T0',fields,layout:{rows:[{cells:[{blank:true},{field_id:'assessor'}]}]}}]}/></Form>;}
 const {container}=render(<Editor/>);expect(container.querySelectorAll('table,td')).toHaveLength(0);expect(screen.getByRole('textbox',{name:'评估者'})).toBeInTheDocument();expect(screen.getByRole('textbox',{name:'反馈'})).toBeInTheDocument();
});
