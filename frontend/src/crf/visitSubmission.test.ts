import { describe, it, expect } from 'vitest';
import { buildVisitSubmission, crfErrorName } from './visitSubmission';
describe('buildVisitSubmission', () => {
    it('test_clear_and_unchanged_legacy_values_are_not_confused', () => {
        const before = { visit_date: '2026-10-07', assessments: { sppb: { total: '0' } }, crf: { legacy: '', adherence: { planned: '旧原文', platform_id: 'ABC' } } };
        expect(buildVisitSubmission({ ...before, patient_baseline: { subject_id: 'READONLY' }, crf: { ...before.crf, adherence: { ...before.crf.adherence, platform_id: null } } }, before, { complete: false })).toEqual({ form_data: { crf: { adherence: { platform_id: null } } } });
    });
    it('preserves hidden native clear, mixed date reason, arrays and metadata on complete', () => {
        const before = { visit_date: '2026-10-07', crf: { medication_change: { entries: [{ id: 'a', name: 'A', dose: 3 }] } } };
        const after = { visit_date: null, crf: { meta: { visit_date_parts: { year: { state: 'value', value: 2026 }, month: { state: 'unknown', value: null } } }, _field_meta: { 'visit.visit_date': { state: 'value', reason: '月份不详' } }, medication_change: { entries: [{ id: 'a', name: 'A', dose: 0, _field_meta: { dose: { state: 'value' } } }] } }, patient_baseline: { subject_id: 'S1' }, computed_assessments: { sppb: { total: 12 } } };
        expect(buildVisitSubmission(after, before, { complete: true })).toEqual({ visit_date: null, status: 'completed', form_data: { crf: after.crf } });
    });
    it('maps relative errors and literal metadata keys including final row index', () => {
        expect(crfErrorName('crf._field_meta.visit.form_data.assessments.sppb.total.reason', 'visit')).toEqual(['assessments', 'sppb', 'total']);
        expect(crfErrorName('crf.medication_change.entries.2._field_meta.started_on.reason', 'visit')).toEqual(['crf', 'medication_change', 'entries', 2, 'started_on']);
        expect(crfErrorName('demographics._crf_field_meta.patient_baseline.demographics.age_years.reason', 'baseline')).toEqual(['demographics', 'age_years']);
        expect(crfErrorName('patient_baseline.demographics.age_years', 'baseline')).toEqual(['demographics', 'age_years']);
    });
});


it('lists all applicable ordinary T1 fields instead of claiming five old totals are complete',async()=>{
 const {unhandledCrfLabels}=await import('./visitSubmission');
 const {registryVisitExtensionFields}=await import('./registryVisitExtensions');
 const result=unhandledCrfLabels(registryVisitExtensionFields('T1'),{visit_date:'2026-10-09',assessments:{sppb:{total:9},moca:{total:22},tug_seconds:8,physical:{chair:{seconds:8}}}});
 expect(result.length).toBeGreaterThanOrEqual(68);
 expect(result).toContain('实际访视周数');
});


it('uses row-local requirements and optional generic reasons without losing partial dates',async()=>{
 const {unhandledCrfLabels}=await import('./visitSubmission');const {crfRegistryFields}=await import('./fieldState');
 const field=crfRegistryFields.find(f=>f.field_id==='sa_surgery_records')!;
 const parent=crfRegistryFields.find(f=>f.field_id==='sa_has_surgery')!;
 const values={surgery_allergy:{has_surgery:'是',surgery_records:[{_row_id:'a',name:'手术甲',date:{year:{state:'value',value:2020},month:{state:'unknown'},day:{state:'value',value:3}},_field_meta:{date:{reason:'   '}}},{_row_id:'b',name:'手术乙'}]}};
 expect(unhandledCrfLabels([parent,field],values)).not.toContain('手术记录 第1行 · 手术日期');
 expect(unhandledCrfLabels([parent,field],values)).toContain('手术记录 第2行 · 手术日期');
 values.surgery_allergy.surgery_records[0]._field_meta!.date.reason='月份不详';
 expect(unhandledCrfLabels([parent,field],values)).not.toContain('手术记录 第1行 · 手术日期');
});
