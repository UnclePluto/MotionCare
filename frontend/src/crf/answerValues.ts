import type {CrfFieldState,CrfMarkedAnswer} from './types';
const record=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);
export const hasCrfAnswerMarker=(v:unknown):boolean=>record(v)&&Object.prototype.hasOwnProperty.call(v,'__crf_answer__');
export function decodeCrfAnswer(value:unknown,legacyMeta?:unknown):{state:CrfFieldState;value:unknown;reason:string|null;marked:boolean;error:string|null} {
 if(hasCrfAnswerMarker(value)) {
  const v=value as Record<string,unknown>;
  const error=v.__crf_answer__!==1||!['unknown','not_applicable'].includes(v.state as string)||!Object.prototype.hasOwnProperty.call(v,'value')||(v.reason!=null&&typeof v.reason!=='string')||hasCrfAnswerMarker(v.value)?'答案状态或原因无效':null;
  return {state:!error?v.state as CrfFieldState:'value',value:v.value,reason:typeof v.reason==='string'?v.reason:null,marked:true,error};
 }
 const meta=record(legacyMeta)?legacyMeta:undefined;
 const error=legacyMeta!=null&&(!meta||![undefined,null,'value','unknown','not_applicable'].includes(meta.state as string)||(meta.reason!=null&&typeof meta.reason!=='string'))?'字段状态或原因无效':null;
 return {state:meta?.state==='unknown'||meta?.state==='not_applicable'?meta.state:'value',value,reason:typeof meta?.reason==='string'?meta.reason:null,marked:false,error};
}
export function isCrfMarkedAnswer(value:unknown):value is CrfMarkedAnswer {return hasCrfAnswerMarker(value)&&!decodeCrfAnswer(value).error;}
export function setCrfAnswerState(value:unknown,state:CrfFieldState,legacyMeta?:unknown):unknown {
 const decoded=decodeCrfAnswer(value,legacyMeta);
 if(state==='value')return decoded.value;
 return {__crf_answer__:1,state,value:decoded.value??null,reason:decoded.reason} satisfies CrfMarkedAnswer;
}
export function setCrfAnswerReason(value:CrfMarkedAnswer,reason:string|null):CrfMarkedAnswer {return {...value,reason};}
