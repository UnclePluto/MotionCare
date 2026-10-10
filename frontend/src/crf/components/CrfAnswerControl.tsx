import {useState,type ReactNode} from 'react';
import {decodeCrfAnswer} from '../answerValues';
import {isCrfRecord} from '../formValues';
import type {RegistryField} from '../types';
import {CrfMoreOptions,type CrfDatePrecision} from './CrfMoreOptions';
function precision(value:unknown,field:RegistryField):CrfDatePrecision {return typeof value==='string'&&/^\d{4}$/.test(value)?'year':typeof value==='string'&&/^\d{4}-\d{2}$/.test(value)?'month':field.date_precision??'day';}
export function CrfAnswerControl({field,value,onChange,disabled=false,legacyMeta,children,id}:{id?:string;field:RegistryField;value?:unknown;onChange?:(value:unknown)=>void;disabled?:boolean;legacyMeta?:unknown;children:(props:{value:unknown;onChange:(value:unknown)=>void;disabled:boolean;datePrecision:CrfDatePrecision})=>ReactNode}) {
 const answer=decodeCrfAnswer(value,legacyMeta);const [emptyPrecision,setPrecision]=useState<CrfDatePrecision>(field.date_precision??'day');
 const datePrecision=answer.value==null||isCrfRecord(answer.value)?emptyPrecision:precision(answer.value,field);
 const change=(next:unknown)=>onChange?.(next);
 const setDatePrecision=(next:CrfDatePrecision)=>{
  setPrecision(next);
  if(typeof answer.value==='string'&&/^\d{4}(-\d{2}){0,2}$/.test(answer.value)) {
   const count=next==='year'?1:next==='month'?2:3;const parts=answer.value.split('-');
   // Increasing precision must not manufacture month or day.
   change(parts.length>=count?parts.slice(0,count).join('-'):null);
  } else if(isCrfRecord(answer.value)) {
   const names=next==='year'?['year']:next==='month'?['year','month']:['year','month','day'];
   if(names.every(key=>isCrfRecord(answer.value)&&isCrfRecord(answer.value[key])&&answer.value[key].state==='value'))change(names.map((key,index)=>String((answer.value as Record<string,{value:number}>)[key].value).padStart(index?2:4,'0')).join('-'));
  }
 };
 return <div className="crf-answer-control" id={id}><div className="crf-answer-label"><label htmlFor={id?`${id}-input`:undefined}>{field.ui_label??field.label_zh}{field.unit&&!(field.ui_label??field.label_zh).includes(field.unit)?<span className="crf-unit">（{field.unit}）</span>:null}</label><CrfMoreOptions field={field} answer={value} legacyMeta={legacyMeta} onChange={change} disabled={disabled} datePrecision={datePrecision} onDatePrecisionChange={field.widget==='date'&&field.allow_partial_date?setDatePrecision:undefined}/></div>
 {children({value:answer.value,onChange:change,disabled:disabled||answer.state!=='value',datePrecision})}</div>;
}
