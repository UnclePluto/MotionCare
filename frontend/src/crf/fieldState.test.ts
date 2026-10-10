import {crfRegistryFields,crfRegistrationName} from './fieldState';
import {expect,it} from "vitest";
import {evaluateCrfCondition,getObservedCrfValue} from "./fieldState";
import type {RegistryField} from "./types";
const field:RegistryField={field_id:"rate",table_ref:"T",label_zh:"完成率",widget:"number",storage:"visit.form_data.crf.rate",min:0,max:100,metadata:{storage:"visit.form_data.crf._field_meta",key:"visit.form_data.crf.rate",states:["value","unknown","not_applicable"]}};
it("uses legal known observations, including zero",()=>{
 expect(getObservedCrfValue(field,{crf:{rate:0}})).toBe(0);
 for(const rate of ["0",175,null]) expect(getObservedCrfValue(field,{crf:{rate}})).toBeNull();
 expect(getObservedCrfValue(field,{crf:{rate:100,_field_meta:{[field.storage]:{state:"unknown"}}}})).toBeNull();
});
it("does not hide reasons for unknown, invalid or missing rate",()=>{
 const condition={storage:field.storage,op:"ne" as const,value:100};
 expect(evaluateCrfCondition(condition,{crf:{rate:100}},[field])).toBe(false);
 for(const rate of [0,75,"old",175,null]) expect(evaluateCrfCondition(condition,{crf:{rate}},[field])).toBe(true);
 expect(evaluateCrfCondition(condition,{crf:{rate:100,_field_meta:{[field.storage]:{state:"not_applicable"}}}},[field])).toBe(true);
});
it("contains only matches whole array members and supports relative repeat fields",()=>{
 const choice={...field,storage:"answers",widget:"multi_choice",options:["其他","其他情况"],metadata:undefined};
 expect(evaluateCrfCondition({storage:"answers",op:"contains",value:"其他"},{answers:["其他情况"]},[choice])).toBe(false);
 expect(evaluateCrfCondition({all:[{storage:"answers",op:"present"},{storage:"answers",op:"contains",value:"其他"}]},{answers:["其他"]},[choice])).toBe(true);
});
it("does not treat malformed metadata or incomplete dates as known",()=>{
 expect(getObservedCrfValue(field,{crf:{rate:10,_field_meta:{[field.storage]:{state:"value",reason:123}}}})).toBeNull();
 const date={...field,widget:"date",date_precision:"day" as const,allow_partial_date:true};
 expect(getObservedCrfValue(date,{crf:{rate:{year:{state:"value",value:2026},month:{state:"unknown"},day:null}}})).toBeNull();
});

it('strips only an exact registration prefix while preserving the complete store path',()=>{
 const full=['crf','events',1,'_field_meta','date','reason'];
 expect(crfRegistrationName(full,['crf','events'])).toEqual([1,'_field_meta','date','reason']);
 expect(crfRegistrationName(full)).toEqual(full);
 expect(crfRegistrationName(full,['crf','different'])).toEqual(full);
 expect(full).toEqual(['crf','events',1,'_field_meta','date','reason']);
});


it('keeps a valid observation with historical metadata keys without accepting an invalid core', () => {
 const field=crfRegistryFields.find(f=>f.field_id==='sa_has_surgery')!;
 const values={surgery_allergy:{has_surgery:'是'},demographics:{_crf_field_meta:{[field.storage]:{state:'value',legacy_feedback:'旧反馈'}}}};
 expect(getObservedCrfValue(field,values)).toBe('是');
 expect(values.demographics._crf_field_meta[field.storage].legacy_feedback).toBe('旧反馈');
 expect(getObservedCrfValue(field,{...values,demographics:{_crf_field_meta:{[field.storage]:{state:'bogus',legacy_feedback:'旧反馈'}}}})).toBeNull();
});

it('matches backend blank observations without accepting a legacy empty native visit date',()=>{
 const text={...field,widget:'text'};
 expect(getObservedCrfValue(text,{crf:{rate:'   '}})).toBeNull();
});
