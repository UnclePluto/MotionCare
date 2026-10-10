import {Button,Checkbox,Input,Popover,Select,Space} from 'antd';
import {decodeCrfAnswer,setCrfAnswerState} from '../answerValues';
import type {RegistryField} from '../types';
export type CrfDatePrecision='day'|'month'|'year';
export function CrfMoreOptions({field,answer,onChange,disabled,datePrecision,onDatePrecisionChange,legacyMeta}:{field:RegistryField;answer:unknown;onChange:(value:unknown)=>void;disabled?:boolean;datePrecision?:CrfDatePrecision;onDatePrecisionChange?:(value:CrfDatePrecision)=>void;legacyMeta?:unknown}) {
 const decoded=decodeCrfAnswer(answer,legacyMeta);const label=field.ui_label??field.label_zh;
 const supported=field.metadata?.states.filter(state=>state!=='value')??[];
 if(!supported.length&&!onDatePrecisionChange)return null;
 return <Popover trigger="click" placement="bottomRight" content={<Space direction="vertical" style={{maxWidth:280}}>
  {supported.map(state=><Checkbox key={state} disabled={disabled} checked={decoded.state===state} onChange={e=>onChange(setCrfAnswerState(answer,e.target.checked?state:'value',legacyMeta))}>{state==='unknown'?'不详':'不适用'}</Checkbox>)}
  {decoded.state!=='value'?<Input aria-label={`${label}原因`} disabled={disabled} placeholder="原因（可选）" value={decoded.reason??''} onChange={e=>onChange({...setCrfAnswerState(answer,decoded.state,legacyMeta) as Record<string,unknown>,reason:e.target.value||null})}/>:null}
  {onDatePrecisionChange?<Select aria-label={`${label}日期精度`} disabled={disabled||decoded.state!=='value'} value={datePrecision} style={{width:160}} options={[{value:'day',label:'完整日期'},{value:'month',label:'年月'},{value:'year',label:'仅年'}].filter(o=>field.date_precision!=='month'||o.value!=='day')} onChange={onDatePrecisionChange}/>:null}
 </Space>}><Button type="text" size="small" aria-label={`${label}更多`} disabled={disabled}>更多</Button></Popover>;
}
