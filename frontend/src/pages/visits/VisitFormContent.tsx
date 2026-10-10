import {useCurrentDoctorName} from '../../auth/AuthContext';
import {buildVisitPrefill} from '../../crf/visitPrefill';
import type {CrfVisitDateAnswer} from '../../crf/types';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Form, Popconfirm, Space, Tabs, Tag, Typography, message } from 'antd';
import type { FormInstance } from 'antd';
import type { CrfSection } from '../../crf/components/CrfSectionForm';
import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import { CrfSectionForm, CrfDraftProgress, CrfSaveBar } from '../../crf/components/CrfSectionForm';
import { registryVisitExtensionFields, groupVisitExtensionFields, deepMergeRecords } from '../../crf/registryVisitExtensions';
import { useCrfDraft } from '../../crf/useCrfDraft';
import { focusCrfField, applyCrfServerErrors, crfServerErrorMessages, buildVisitSubmission, crfErrorSection, useCrfServerErrors } from '../../crf/visitSubmission';
import { crfStorageToFormName, readCrfPath, readCrfStorage } from '../../crf/fieldState';
import { isCrfRecord, normalizeCrfFormValues } from '../../crf/formValues';
import { evaluateCrfDraft } from '../../crf/draftCompleteness';
import type { CrfDraftItem } from '../../crf/draftCompleteness';
type VisitDetail = {
    id: number;
    project_patient: number;
    project_status?: string;
    visit_type: 'T0' | 'T1' | 'T2';
    status: 'draft' | 'completed';
    visit_date: CrfVisitDateAnswer;
    form_data: Record<string, unknown>;
};
type Props = {
    visitId: number;
    patientId?: number;
    title?: string;
    timeDescription?: string;
    onVisitChanged?: () => void | Promise<void>;
};
const EMPTY = {};
/** Preserve the pre-existing display fallback, without creating new manual assessment keys. */
function assessmentPrefill(manual: unknown, computed: unknown): unknown {
    if (manual != null && !isCrfRecord(manual)) return manual;
    const out = normalizeCrfFormValues(isCrfRecord(manual) ? manual : {});
    const paths = [
        ['sppb', 'balance'], ['sppb', 'gait'], ['sppb', 'chair_stand'], ['sppb', 'total'],
        ['moca', 'total'], ['tug_seconds'], ['grip_strength_kg'], ['frailty'],
    ];
    for (const path of paths) {
        if (readCrfPath(out, path) != null) continue;
        const value = readCrfPath(computed, path);
        if (value == null) continue;
        if (path.length === 1) out[path[0]] = value;
        else {
            const parent = out[path[0]];
            if (parent != null && !isCrfRecord(parent)) continue;
            out[path[0]] = {...(isCrfRecord(parent) ? parent : {}), [path[1]]: value};
        }
    }
    return out;
}
function VisitSection({ form, section, disabled, error, progress }: {
    form: FormInstance;
    section: CrfSection;
    disabled: boolean;
    error: unknown;
    progress:CrfDraftItem[];
}) { useCrfServerErrors(form, error, 'visit'); return <CrfSectionForm form={form} disabled={disabled} sections={[section]} progress={progress}/>; }
export function VisitFormContent(props: Props) { return <VisitEditor key={props.visitId} {...props}/>; }
function VisitEditor({ visitId: id, patientId, title = '访视表单', onVisitChanged }: Props) {
    const qc = useQueryClient();
    const doctorName=useCurrentDoctorName();
    const [form] = Form.useForm();
    const [activeSection, setActiveSection] = useState<string>();
    const [savedAt, setSavedAt] = useState<string>();
    const [fieldError, setFieldError] = useState<unknown>();
    const [completing, setCompleting] = useState(false);
    const [confirmationOpen,setConfirmationOpen]=useState(false);
    const [location,setLocation]=useState<CrfDraftItem>();
    useEffect(()=>{if(location){const frame=requestAnimationFrame(()=>focusCrfField(form,location.name));return ()=>cancelAnimationFrame(frame);}},[location,form,activeSection]);
    const { data: visit, isLoading, isError } = useQuery({ queryKey: ['visit', id], queryFn: async () => (await apiClient.get<VisitDetail>(`/visits/${id}/`)).data, enabled: !!id });
    const { data: binding } = useQuery({ queryKey: ['project-patient', visit?.project_patient], queryFn: async () => (await apiClient.get<{
            patient: number; enrolled_at?: string;
        }>(`/studies/project-patients/${visit!.project_patient}/`)).data, enabled: !!visit });
    const currentPatientId = patientId ?? binding?.patient;
    const { data: baseline } = useQuery({ queryKey: ['patient-baseline', String(currentPatientId)], queryFn: async () => (await apiClient.get<Record<string, unknown>>(`/patients/${currentPatientId}/baseline/`)).data, enabled: !!currentPatientId });
    const {data:confirmedBindings}=useQuery({queryKey:['project-patients','patient',currentPatientId],queryFn:async()=>(await apiClient.get<unknown[]>('/studies/project-patients/',{params:{patient:currentPatientId}})).data,enabled:!!currentPatientId});
    // Only the established computed fallback uses a display baseline: an untouched suggestion is not a manual answer.
    const serverValues = useMemo(() => visit ? { assessments: assessmentPrefill(visit.form_data.assessments, visit.form_data.computed_assessments), crf: visit.form_data.crf ?? {}, visit_date: visit.visit_date } : undefined, [visit]);
    const adoptableNames=useMemo(()=>visit?registryVisitExtensionFields(visit.visit_type).filter(field=>field.storage.startsWith('visit.form_data.assessments.')).map(field=>crfStorageToFormName(field.storage)).filter(name=>readCrfPath(visit.form_data,name)==null && readCrfPath(serverValues,name)!=null):[],[visit,serverValues]);
    const recordKey = `visit:${id}`;
    const prefillValues=useMemo(()=>serverValues&&visit?buildVisitPrefill({visitType:visit.visit_type,serverValues,enrolledAt:binding?.enrolled_at,doctorName,confirmedProjectCount:Array.isArray(confirmedBindings)?confirmedBindings.length:0,legacyCover:isCrfRecord(baseline?.demographics)?baseline.demographics.document:undefined,legacyCoverMetadata:isCrfRecord(baseline?.demographics)?baseline.demographics._crf_field_meta:undefined,readOnly:visit.status==='completed'||visit.project_status==='archived'}):serverValues,[serverValues,visit,binding,doctorName,confirmedBindings,baseline]);
    const prefillNames=useMemo(()=>[['crf','cover','protocol_number'],['crf','cover','enrolled_on'],['crf','cover','investigator_name'],['crf','meta','assessor_name'],['crf','meta','assessed_on']],[]);
    const draft = useCrfDraft({ form, serverValues, prefillValues, prefillNames, recordKey, adoptableNames });
    // Canonical context is independently refreshed even while the visit draft is dirty.
    useEffect(() => { if (JSON.stringify(form.getFieldValue(['patient_baseline'])) !== JSON.stringify(baseline ?? EMPTY))
        form.setFieldValue(['patient_baseline'], baseline ?? EMPTY); }, [baseline, form, id, serverValues]);
    const fields = useMemo(() => visit ? registryVisitExtensionFields(visit.visit_type) : [], [visit]);
    const groups = useMemo(() => groupVisitExtensionFields(fields), [fields]);
    const readonly = visit?.status === 'completed' || visit?.project_status === 'archived' || completing;
    const mutation = useMutation({ mutationFn: async ({ values, before, complete }: {
            values: Record<string, unknown>;
            before: Record<string, unknown>;
            complete: boolean;
        }) => {
            const payload = buildVisitSubmission(values, before, { complete });
            if (!Object.keys(payload).length)
                return null;
            await qc.cancelQueries({ queryKey: ['visit', id] });
            return (await apiClient.patch(`/visits/${id}/`, payload)).data;
        } });
    const submit = async (complete: boolean) => {
        if (readonly || !draft.beginSubmit())
            return;
        setCompleting(complete);
        setFieldError(undefined);
        form.setFields(form.getFieldsError().filter(field => field.errors.length).map(field => ({ ...field, errors: [] })));
        const values = draft.getValues();
        const before = draft.before;
        try {
            const result = await mutation.mutateAsync({ values, before, complete });
            if (draft.resetAfterSubmit(values, recordKey)) {
                setSavedAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }));
                message.success(complete ? '已完成' : '已暂存');
                if (result && isCrfRecord(result) && result.id === id && result.form_data)
                    qc.setQueryData(['visit', id], result);
                await qc.invalidateQueries({ queryKey: ['visit', id] });
                await onVisitChanged?.();
            }
        }
        catch (error) {
            if (!draft.isCurrentRecord(recordKey))
                return;
            setFieldError(error || new Error("保存失败"));
            const name = applyCrfServerErrors(form, error, 'visit');
            if (name) {
                const key = crfErrorSection(fields, name);
                if (key)
                    setActiveSection(key);
            }
            message.error('保存失败，请核对字段提示；草稿已保留');
        }
        finally {
            draft.endSubmit();
            if (draft.isCurrentRecord(recordKey))
                setCompleting(false);
        }
    };
    const legacy = fields.filter(f => f.legacy && readCrfStorage(draft.getValues(), f.storage) != null && readCrfStorage(draft.getValues(), f.storage) !== '');
    // Progress follows the exact save candidate; untouched computed suggestions remain suggestions.
    const pending=buildVisitSubmission(draft.getValues(),draft.before,{complete:false});
    const candidate:Record<string,unknown>={...(deepMergeRecords(visit?.form_data,pending.form_data)??{}),visit_date:'visit_date' in pending?pending.visit_date:visit?.visit_date,patient_baseline:baseline??{}};
    if('visit_date' in pending&&isCrfRecord(candidate.crf)) {
        const meta=isCrfRecord(candidate.crf.meta)?candidate.crf.meta:{};
        candidate.crf={...candidate.crf,meta:{...meta,visit_date_answer:pending.visit_date}};
    }
    const progress=evaluateCrfDraft(fields,candidate);
    const reminders=progress.unresolved;
    const locate=(item:CrfDraftItem)=>{setConfirmationOpen(false);setActiveSection(item.table);setLocation(item);};
    return <Card title={title} loading={isLoading} extra={visit ? <Space><Tag>{visit.visit_type}</Tag><Tag>{visit.status === 'completed' ? '已完成' : '草稿'}</Tag></Space> : null}>
  {isError ? <Alert type="error" message="访视记录不存在或无权限访问"/> : null}
  <Form form={form} layout="vertical" disabled={readonly}>
   {draft.navigationGuard}
   {fieldError ? <Alert type="error" showIcon message="保存失败，草稿已保留" description={<ul style={{ marginBottom: 0 }}>{crfServerErrorMessages(fieldError, 'visit').map(text => <li key={text}>{text}</li>)}</ul>} /> : null}
   {visit ? <>
    {visit.status === 'completed' ? <Alert type="info" showIcon message="访视已完成，当前为只读查看。"/> : null}
    {visit.project_status === 'archived' ? <Alert type="warning" message="当前表单只读"/> : null}
    {JSON.stringify(serverValues?.assessments) !== JSON.stringify(visit.form_data.assessments ?? {}) ? <Tag color="blue">系统预填值</Tag> : null}
    <CrfDraftProgress items={progress.items} onLocate={locate}/>
    <Tabs activeKey={groups.some(g => g.key === activeSection) ? activeSection : groups[0]?.key} onChange={setActiveSection} destroyOnHidden items={groups.map(g => ({ key: g.key, label: g.label, children: <VisitSection form={form} disabled={readonly} error={fieldError} progress={progress.items} section={{ key: g.key, title: g.label, fields: g.fields, scope: 'visit', visitType: visit.visit_type }}/> }))}/>
    {legacy.length ? <Card size="small" title="旧记录，待核对">{legacy.map(f => <div key={f.field_id}><Typography.Text>{f.ui_label ?? f.label_zh}</Typography.Text><pre style={{ whiteSpace: 'pre-wrap' }}>{typeof readCrfStorage(draft.getValues(), f.storage) === 'string' ? String(readCrfStorage(draft.getValues(), f.storage)) : JSON.stringify(readCrfStorage(draft.getValues(), f.storage))}</pre></div>)}</Card> : null}
    <CrfSaveBar>
     <Button aria-label="暂存" loading={mutation.isPending} disabled={readonly || mutation.isPending} onClick={() => void submit(false)}>暂存</Button>
     <Popconfirm open={confirmationOpen} onOpenChange={setConfirmationOpen} title="确认完成？" description={<><p>完成后对应记录无法修改。</p><p>{reminders.length ? `仍有 ${reminders.length} 项未处理。可保留缺失并完成。` : '当前未发现未处理的必填项。'}</p><CrfDraftProgress items={progress.items} onLocate={locate} expanded/></>} okText="确认完成" cancelText="取消" onConfirm={() => submit(true)} disabled={readonly || mutation.isPending}>
      <Button type="primary" aria-label="完成" loading={mutation.isPending} disabled={readonly || mutation.isPending}>完成</Button>
     </Popconfirm>
     {savedAt ? <Typography.Text role="status">已保存于 {savedAt}</Typography.Text> : null}{draft.dirty ? <Typography.Text>有未保存的改动</Typography.Text> : null}
    </CrfSaveBar>
   </> : null}
  </Form>
 </Card>;
}
