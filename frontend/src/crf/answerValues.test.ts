import {expect,it} from 'vitest';
import {crfRegistryFields,getObservedCrfValue,validateCrfFieldValue} from './fieldState';
import {evaluateCrfDraft} from './draftCompleteness';
import {buildCrfPatch} from './formValues';
import {calculateCrfDerivedValue} from './fieldCalculations';
const field=crfRegistryFields.find(f=>f.storage==='visit.form_data.assessments.sppb.balance'&&!f.legacy)!;
const marked={__crf_answer__:1,state:'unknown',value:0,reason:null};
it('handles a single-field unknown without requiring a generic reason and excludes it from scores',()=>{
 const values={assessments:{sppb:{balance:marked,gait:4,chair_stand:4}}};
 expect(validateCrfFieldValue(field,marked)).toBeNull();
 expect(getObservedCrfValue(field,values)).toBeNull();
 expect(evaluateCrfDraft([field],values).items[0]).toMatchObject({state:'unknown',issues:[]});
 expect(calculateCrfDerivedValue('sppb_total',values)).toBeNull();
});
it('replaces the whole marked answer in a patch, preserving null and zero',()=>{
 expect(buildCrfPatch({balance:marked},{balance:{...marked,state:'not_applicable',reason:'原记录'}})).toEqual({balance:{...marked,state:'not_applicable',reason:'原记录'}});
 expect(buildCrfPatch({balance:marked},{balance:0})).toEqual({balance:0});
 expect(buildCrfPatch({balance:0},{balance:null})).toEqual({balance:null});
});
it.each([{...marked,__crf_answer__:true},{...marked,__crf_answer__:2},{...marked,state:'value'},{...marked,reason:9},{...marked,value:true}])('rejects malformed marked core rather than hiding it under unknown: %j',answer=>{
 expect(validateCrfFieldValue(field,answer)).not.toBeNull();
 expect(evaluateCrfDraft([field],{assessments:{sppb:{balance:answer}}}).items[0].state).toBe('unresolved');
});
it('keeps an invalid ancestor unresolved even when legacy metadata says unknown',()=>{
 const values={assessments:{sppb:[]},crf:{_field_meta:{[field.storage]:{state:'unknown',reason:null}}}};
 expect(evaluateCrfDraft([field],values).items[0]).toMatchObject({state:'unresolved',issues:['上级字段必须是对象']});
});
it('treats an old explicit unknown without generic reason as handled',()=>{
 const values={assessments:{sppb:{balance:0}},crf:{_field_meta:{[field.storage]:{state:'unknown'}}}};
 expect(evaluateCrfDraft([field],values).items[0].state).toBe('unknown');
});
