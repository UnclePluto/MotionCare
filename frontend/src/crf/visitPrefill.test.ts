import {expect,it} from 'vitest';
import {buildVisitPrefill} from './visitPrefill';
const input={visitType:'T0' as const,serverValues:{},enrolledAt:'2026-10-09T17:30:00Z',doctorName:'验收医生',confirmedProjectCount:1,readOnly:false};
it('prefills real Shanghai enrollment and doctor facts, without inventing later visit dates',()=>{
 expect(buildVisitPrefill(input)).toMatchObject({crf:{cover:{enrolled_on:'2026-10-10',investigator_name:'验收医生'},meta:{assessor_name:'验收医生'}}});
 expect(buildVisitPrefill({...input,visitType:'T1'})).not.toHaveProperty('visit_date');
 expect(buildVisitPrefill({...input,visitType:'T1'})).not.toHaveProperty('crf.cover');
});
it('preserves explicit clears, unknown and zero instead of filling over stored answers',()=>{
 const serverValues={crf:{cover:{enrolled_on:null,investigator_name:{__crf_answer__:1,state:'unknown',value:null,reason:null}},meta:{assessor_name:null,actual_week:0}}};
 expect(buildVisitPrefill({...input,serverValues})).toEqual(serverValues);
});
it('isolates old cover to a single confirmed project and leaves locked answers unchanged',()=>{
 expect(buildVisitPrefill({...input,legacyCover:{protocol_number:'旧'}})).toHaveProperty('crf.cover.protocol_number','旧');
 expect(buildVisitPrefill({...input,confirmedProjectCount:2,legacyCover:{protocol_number:'旧'}})).not.toHaveProperty('crf.cover.protocol_number');
 expect(buildVisitPrefill({...input,readOnly:true})).toEqual({});
 expect(buildVisitPrefill({...input,doctorName:''})).not.toHaveProperty('crf.meta.assessor_name');
});


it.each(['unknown','not_applicable'])('keeps legacy cover %s and reason in the new answer',state=>{
 const legacyCover={protocol_number:'旧方案',enrolled_on:null,investigator_name:'旧医生'};
 const legacyCoverMetadata=Object.fromEntries(Object.keys(legacyCover).map(key=>[`patient_baseline.demographics.document.${key}`,{state,reason:'原理由',extra:'原补充'}]));
 const original=JSON.stringify({legacyCover,legacyCoverMetadata});
 const result=buildVisitPrefill({...input,legacyCover,legacyCoverMetadata});
 for(const [key,value] of Object.entries(legacyCover))expect(result).toHaveProperty(`crf.cover.${key}`,{__crf_answer__:1,state,value,reason:'原理由'});
 expect(JSON.stringify({legacyCover,legacyCoverMetadata})).toBe(original);
});
