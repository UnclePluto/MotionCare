import dayjs from "dayjs";
import {hasCrfAnswerMarker} from "./answerValues";

export function isCrfRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) && !dayjs.isDayjs(value);
}

/** Preserve raw strings, explicit null, zero and arrays; dates are converted only if already Dayjs. */
export function normalizeCrfFormValues(values: Record<string, unknown>): Record<string, unknown> {
  function normalize(value: unknown): unknown {
    if (dayjs.isDayjs(value)) return value.format("YYYY-MM-DD");
    if (Array.isArray(value)) return value.map(normalize);
    if (isCrfRecord(value)) return Object.fromEntries(Object.entries(value).filter(([,v]) => v !== undefined).map(([key,v]) => [key,normalize(v)]));
    return value;
  }
  return normalize(values) as Record<string, unknown>;
}

/** Object key ordering from JSON storage is not a clinical edit. Array order is. */
function sameCrfValue(left:unknown,right:unknown):boolean {
 if(left===right)return true;
 if(Array.isArray(left)&&Array.isArray(right))return left.length===right.length&&left.every((value,index)=>sameCrfValue(value,right[index]));
 if(isCrfRecord(left)&&isCrfRecord(right)) {
  const keys=Object.keys(left);
  return keys.length===Object.keys(right).length&&keys.every(key=>Object.prototype.hasOwnProperty.call(right,key)&&sameCrfValue(left[key],right[key]));
 }
 return false;
}

/** Omitted/unmounted fields are not clears. Arrays are atomic replacement values. */
function diffCrfValues(before: Record<string, unknown>, after: Record<string, unknown>): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(after)) {
    if (value === undefined) continue;
    if (isCrfRecord(value) && isCrfRecord(before[key]) && !hasCrfAnswerMarker(value) && !hasCrfAnswerMarker(before[key])) {
      const child = diffCrfValues(before[key], value);
      if (Object.keys(child).length) patch[key] = child;
    } else if (!sameCrfValue(before[key],value)) patch[key] = value;
  }
  return patch;
}

/** Old state cleanup is expressed by explicitly re-submitting the corresponding business leaf. */
export function buildCrfPatch(before:Record<string,unknown>,after:Record<string,unknown>):Record<string,unknown> {
 const patch=diffCrfValues(before,after);
 const get=(root:unknown,path:string[])=>path.reduce<unknown>((v,key)=>isCrfRecord(v)?v[key]:undefined,root);
 const set=(root:Record<string,unknown>,path:string[],value:unknown)=>{let parent=root;for(const key of path.slice(0,-1)){if(!isCrfRecord(parent[key]))parent[key]={};parent=parent[key] as Record<string,unknown>;}parent[path[path.length-1]]=value;};
 const walk=(old:unknown,next:unknown,path:string[])=>{
  if(!isCrfRecord(old)||!isCrfRecord(next))return;
  for(const [key,value] of Object.entries(next)) {
   if((key==='_crf_field_meta'||key==='_field_meta')&&isCrfRecord(old[key])&&isCrfRecord(value))for(const [business,newMeta] of Object.entries(value)) {
    const oldMeta=(old[key] as Record<string,unknown>)[business];
    if(!isCrfRecord(oldMeta)||!isCrfRecord(newMeta)||!['unknown','not_applicable'].includes(oldMeta.state as string)||newMeta.state!=null)continue;
    const name=business.replace(/^patient_baseline\.|^visit\.form_data\.|^visit\./,'').split('.');
    const answer=get(after,name);if(answer===undefined)continue;
    set(patch,name,answer);
    const changed=get(patch,[...path,key,business]);
    if(isCrfRecord(changed)){delete changed.state;delete changed.reason;}
   }
   else if(!Array.isArray(value))walk(old[key],value,[...path,key]);
  }
 };
 walk(before,after,[]);
 const compact=(value:Record<string,unknown>):Record<string,unknown>=>Object.fromEntries(Object.entries(value).flatMap(([key,v])=>{const next=isCrfRecord(v)&&!hasCrfAnswerMarker(v)?compact(v):v;return isCrfRecord(next)&&!Object.keys(next).length?[]:[[key,next]];}));
 return compact(patch);
}
