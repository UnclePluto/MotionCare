import { useMutation, useQueries, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Form, Tabs, Typography, message } from 'antd';
import dayjs from 'dayjs';
import type { FormInstance } from 'antd';
import type { CrfSection } from '../../crf/components/CrfSectionForm';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { ageFromBirthDate } from './ageFromBirthDate';
import { orderBaselineTableEntries } from '../../crf/baselineSectionOrder';
import { mergePatientIntoBaselineApiPayload } from '../../crf/baselinePrefill';
import { CrfSectionForm, CrfDraftProgress, CrfSaveBar } from '../../crf/components/CrfSectionForm';
import { useCrfDraft } from '../../crf/useCrfDraft';
import { focusCrfField, applyCrfServerErrors, crfServerErrorMessages, crfErrorSection, useCrfServerErrors } from '../../crf/visitSubmission';
import { readCrfStorage, validateCrfFieldValue } from '../../crf/fieldState';
import { isCrfRecord } from '../../crf/formValues';
import type { CrfRegistry, RegistryField } from '../../crf/types';
import registryJson from '../../crf/registry.v1.json';
import { evaluateCrfDraft } from '../../crf/draftCompleteness';
import type { CrfDraftItem } from '../../crf/draftCompleteness';
const registry = registryJson as CrfRegistry;
type PatientPrefill = {
    name: string;
    gender?: string | null;
    birth_date?: string | null;
    age?: number | null;
};
const writable = ['subject_id', 'name_initials', 'demographics', 'surgery_allergy', 'comorbidities', 'lifestyle', 'baseline_medications'];
function baselineValues(value: Record<string, unknown>) { return Object.fromEntries(writable.filter(k => k in value).map(k => [k, value[k]])); }
function BaselineSection({ form, section, error, progress }: {
    form: FormInstance;
    section: CrfSection;
    error: unknown;
    progress: CrfDraftItem[];
}) { useCrfServerErrors(form, error, 'baseline'); return <CrfSectionForm form={form} sections={[section]} progress={progress}/>; }
export function PatientCrfBaselinePage() { const { patientId } = useParams(); return <BaselineEditor key={patientId}/>; }
function BaselineEditor() {
    const qc = useQueryClient();
    const navigate = useNavigate();
    const { patientId } = useParams();
    const id = Number(patientId);
    const [form] = Form.useForm();
    const [activeSection, setActiveSection] = useState<string>();
    const [savedAt, setSavedAt] = useState<string>();
    const [fieldError, setFieldError] = useState<unknown>();
    const [location,setLocation] = useState<CrfDraftItem>();
    useEffect(()=>{if(location){const frame=requestAnimationFrame(()=>focusCrfField(form,location.name));return ()=>cancelAnimationFrame(frame);}},[location,form,activeSection]);
    const sections = useMemo(() => {
        const tables = new Map<string, RegistryField[]>();
        for (const field of registry.fields.filter(f => f.storage.startsWith('patient_baseline.') && !f.visit_types?.length && !f.legacy))
            tables.set(field.table_ref, [...(tables.get(field.table_ref) ?? []), field]);
        return orderBaselineTableEntries([...tables], registry.baseline_section_order).map(([key, fields]) => ({ key, title: registry.table_titles?.[key] ?? '其他资料', fields, scope: 'baseline' as const, layout: registry.baseline_table_layout?.[key] }));
    }, []);
    const queries = useQueries({ queries: [{ queryKey: ['patient', String(id)], queryFn: async () => (await apiClient.get<PatientPrefill>(`/patients/${id}/`)).data, enabled: Number.isFinite(id) }, { queryKey: ['patient-baseline', String(id)], queryFn: async () => (await apiClient.get<Record<string, unknown>>(`/patients/${id}/baseline/`)).data, enabled: Number.isFinite(id) }] });
    const patient = queries[0].data;
    const baseline = queries[1].data;
    const serverValues = useMemo(() => baseline ? baselineValues(baseline) : undefined, [baseline]);
    const prefillValues = useMemo(() => {
        if (!patient || !serverValues)
            return serverValues;
        const merged = mergePatientIntoBaselineApiPayload({ name: patient.name ?? '', gender: patient.gender ?? '', birth_date: patient.birth_date ?? null, age: patient.age ?? null }, serverValues);
        if (serverValues.demographics != null && !isCrfRecord(serverValues.demographics))
            merged.demographics = serverValues.demographics;
        const demo = merged.demographics;
        if (isCrfRecord(demo) && (demo.age_years == null || demo.age_years === '') && typeof demo.birth_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(demo.birth_date) && dayjs(demo.birth_date).isValid())
            demo.age_years = ageFromBirthDate(dayjs(demo.birth_date));
        return merged;
    }, [patient, serverValues]);
    const legacyFields = registry.fields.filter(f => f.legacy && f.storage.startsWith('patient_baseline.') && !f.visit_types?.length);
    const recordKey = `baseline:${id}`;
    const draft = useCrfDraft({ form, serverValues: patient ? serverValues : undefined, prefillValues, prefillNames:[['name_initials'],['demographics','birth_date'],['demographics','age_years'],['demographics','gender']], recordKey });
    const mutation = useMutation({ mutationFn: async (patch: Record<string, unknown>) => { await qc.cancelQueries({ queryKey: ['patient-baseline', String(id)] }); return (await apiClient.patch(`/patients/${id}/baseline/`, patch)).data; } });
    const save = async () => {
        if (!draft.beginSubmit())
            return;
        setFieldError(undefined);
        form.setFields(form.getFieldsError().filter(field => field.errors.length).map(field => ({ ...field, errors: [] })));
        const values = draft.getValues();
        const patch = baselineValues(draft.getPatch());
        try {
            if (Object.keys(patch).length)
                await mutation.mutateAsync(patch);
            if (draft.resetAfterSubmit(values, recordKey)) {
                setSavedAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }));
                message.success('已保存');
                await qc.invalidateQueries({ queryKey: ['patient-baseline', String(id)] });
            }
        }
        catch (error) {
            if (!draft.isCurrentRecord(recordKey))
                return;
            setFieldError(error || new Error("保存失败"));
            const name = applyCrfServerErrors(form, error, 'baseline');
            if (name) {
                const key = crfErrorSection(registry.fields, name);
                if (key)
                    setActiveSection(key);
            }
            message.error('保存失败，请核对字段提示；草稿已保留');
        }
        finally {
            draft.endSubmit();
        }
    };
    const progress=evaluateCrfDraft(sections.flatMap(s=>s.fields),draft.getValues());
    const locate=(item:CrfDraftItem)=>{setActiveSection(item.table);setLocation(item);};
    if (!Number.isFinite(id))
        return <Alert type="error" message="无效的患者 ID"/>;
    if (queries.some(q => q.isError))
        return <Alert type="error" message="加载失败"/>;
    return <Card title="患者基础基线资料" loading={queries.some(q => q.isLoading)} extra={<Button aria-label="返回" onClick={() => navigate(-1)}>返回</Button>}>
  <Form form={form} layout="vertical" onFinish={() => void save()} onValuesChange={changed => {
            const demo = changed.demographics;
            if (!isCrfRecord(demo) || !('birth_date' in demo))
                return;
            // A representation switch or incomplete date does not clear an independent age.
            const dateField = registry.fields.find(f => f.field_id === 'dm_birth_date')!;
            if (typeof demo.birth_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(demo.birth_date) && !validateCrfFieldValue(dateField, demo.birth_date))
                form.setFields([{ name: ['demographics', 'age_years'], value: ageFromBirthDate(dayjs(demo.birth_date)), touched: true }]);
        }}>
   {draft.navigationGuard}
   {fieldError ? <Alert type="error" showIcon message="保存失败，草稿已保留" description={<ul style={{ marginBottom: 0 }}>{crfServerErrorMessages(fieldError, 'baseline').map(text => <li key={text}>{text}</li>)}</ul>} /> : null}
   <CrfDraftProgress items={progress.items} onLocate={locate}/>
   <Tabs activeKey={sections.some(s => s.key === activeSection) ? activeSection : sections[0]?.key} onChange={setActiveSection} destroyOnHidden items={sections.map(s => ({ key: s.key, label: s.title, children: <BaselineSection form={form} section={s} error={fieldError} progress={progress.items}/> }))}/>
   {legacyFields.some(f => readCrfStorage(draft.getValues(), f.storage) != null && readCrfStorage(draft.getValues(), f.storage) !== '') ? <Card size="small" title="旧记录，待核对">{legacyFields.map(f => { const value = readCrfStorage(draft.getValues(), f.storage); return value != null && value !== '' ? <div key={f.field_id}><Typography.Text>{f.ui_label ?? f.label_zh}</Typography.Text><pre style={{ whiteSpace: 'pre-wrap' }}>{typeof value === 'string' ? value : JSON.stringify(value)}</pre></div> : null; })}</Card> : null}
   <CrfSaveBar><Button type="primary" htmlType="submit" loading={mutation.isPending} disabled={mutation.isPending}>保存</Button>{savedAt ? <Typography.Text role="status">已保存于 {savedAt}</Typography.Text> : null}{draft.dirty ? <Typography.Text>有未保存的改动</Typography.Text> : null}</CrfSaveBar>
  </Form>
 </Card>;
}
