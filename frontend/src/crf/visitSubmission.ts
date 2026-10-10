import { useEffect } from 'react';
import type { FormInstance } from 'antd';
import { buildCrfPatch, isCrfRecord, normalizeCrfFormValues } from './formValues';
import { crfMetadataFormName, crfStorageToFormName } from './fieldState';
import type { CrfName } from './fieldState';
import { evaluateCrfDraft } from './draftCompleteness';
import type { RegistryField,CrfVisitDateAnswer } from './types';
/** Empty registered object shells are not an edit; null and arrays are explicit edits. */
export function crfDraftPatch(before: Record<string, unknown>, after: Record<string, unknown>): Record<string, unknown> {
    const compact = (value: Record<string, unknown>): Record<string, unknown> => Object.fromEntries(Object.entries(value).flatMap(([key, v]) => { const next = isCrfRecord(v) ? compact(v) : v; return isCrfRecord(next) && !Object.keys(next).length ? [] : [[key, next]]; }));
    const patch = compact(buildCrfPatch(normalizeCrfFormValues(before), normalizeCrfFormValues(after)));
    delete patch.patient_baseline;
    delete patch.computed_assessments;
    return patch;
}
export function buildVisitSubmission(values: Record<string, unknown>, before: Record<string, unknown>, options: {
    complete: boolean;
}): {
    visit_date?: CrfVisitDateAnswer;
    form_data?: Record<string, unknown>;
    status?: 'completed';
} {
    const patch = crfDraftPatch(before, values);
    const result: {
        visit_date?: CrfVisitDateAnswer;
        form_data?: Record<string, unknown>;
        status?: 'completed';
    } = {};
    if ('visit_date' in patch)
        result.visit_date = patch.visit_date as CrfVisitDateAnswer;
    // The native DTO date is the single submitted answer; JSON is its server projection.
    if('visit_date' in patch&&isCrfRecord(patch.crf)&&isCrfRecord(patch.crf.meta)) {
        delete patch.crf.meta.visit_date_answer;
        if(!Object.keys(patch.crf.meta).length)delete patch.crf.meta;
        if(!Object.keys(patch.crf).length)delete patch.crf;
    }
    const form_data = Object.fromEntries(['assessments', 'crf'].filter(key => key in patch).map(key => [key, patch[key]]));
    if (Object.keys(form_data).length)
        result.form_data = form_data;
    if (options.complete)
        result.status = 'completed';
    return result;
}
export function crfErrorName(path: string, scope: 'visit' | 'baseline'): CrfName {
    let relative = path.replace(/^visit\.form_data\.|^visit\.|^form_data\./, '');
    if (scope === 'baseline')
        relative = relative.replace(/^patient_baseline\./, '');
    const markerMatch = /\.(_(?:crf_)?field_meta)\./.exec(relative);
    const marker = markerMatch?.index ?? -1;
    if (markerMatch) {
        const prefix = relative.slice(0, marker).split('.').map(p => /^\d+$/.test(p) ? Number(p) : p);
        const tail = relative.slice(marker + markerMatch[0].length);
        const suffix = tail.match(/\.(state|reason)$/);
        const business=suffix?tail.slice(0,-suffix[0].length):tail;
        if(business.startsWith('patient_baseline.')||business.startsWith('visit.'))return crfStorageToFormName(business);
        return [...prefix, ...business.split('.')];
    }
    return relative.split('.').map(p => /^\d+$/.test(p) ? Number(p) : p);
}
type CrfServerError = { name: CrfName | null; messages: string[] };
function readCrfServerErrors(error: unknown, scope: 'visit' | 'baseline'): CrfServerError[] {
    const data = (error as { response?: { data?: unknown } })?.response?.data;
    const errors: CrfServerError[] = [];
    const walk = (value: unknown, path: string) => {
        const messages = typeof value === 'string' ? [value] : Array.isArray(value) && value.every(v => typeof v === 'string') ? value : null;
        if (messages) {
            const nonField = !path || path.split('.').some(part => part === 'detail' || part === 'non_field_errors');
            errors.push({ name: nonField ? null : crfErrorName(path, scope), messages: messages.filter(text => text.trim()) });
        } else if (isCrfRecord(value)) {
            Object.entries(value).forEach(([key, child]) => walk(child, path ? `${path}.${key}` : key));
        } else if (Array.isArray(value)) {
            value.forEach((child, index) => walk(child, `${path}.${index}`));
        }
    };
    // Unstructured responses may be gateway HTML; show the Chinese fallback instead.
    if (isCrfRecord(data)) walk(data, '');
    return errors;
}
export function crfServerErrorMessages(error: unknown, scope: 'visit' | 'baseline'): string[] {
    const messages = [...new Set(readCrfServerErrors(error, scope).flatMap(item => item.messages))];
    return messages.length ? messages : ['暂时无法保存，请稍后重试。'];
}
export function applyCrfServerErrors(form: FormInstance, error: unknown, scope: 'visit' | 'baseline'): CrfName | null {
    const errors = readCrfServerErrors(error, scope).flatMap(item => item.name && item.messages.length ? [{ name: item.name, errors: item.messages }] : []);
    // detail/non_field_errors have no input identity and must remain page feedback.
    form.setFields(errors);
    return errors[0]?.name ?? null;
}
/** Completion, chapter progress and navigation consume the same draft model. */
export function unhandledCrfLabels(fields: RegistryField[], values: Record<string, unknown>): string[] {
    return evaluateCrfDraft(fields,values).unresolved.map(item=>item.label);
}
export function crfErrorSection(fields: RegistryField[], name: CrfName): string | undefined {
    if (!name.length) return undefined;
    const prefix = (a: CrfName, b: CrfName) => a.every((part, index) => b[index] === part);
    const related = (path: CrfName) => prefix(path, name) || prefix(name, path);
    // Prefer the clinical data container before metadata, which may live in another section.
    const direct = fields.find(field => related(crfStorageToFormName(field.storage)));
    const partial = fields.find(field => field.partial_date_storage && related(crfStorageToFormName(field.partial_date_storage)));
    const metadata = fields.find(field => {
        const path = crfMetadataFormName(field, crfStorageToFormName(field.storage));
        return path && related(path);
    });
    return (direct ?? partial ?? metadata)?.table_ref;
}
/** Run inside the active tab pane, after its Form.Items have registered. */
export function useCrfServerErrors(form: FormInstance, error: unknown, scope: 'visit' | 'baseline') {
    useEffect(() => { if (error) {
        const name = applyCrfServerErrors(form, error, scope);
        if (name)
            form.scrollToField(name, { focus: true });
    } }, [form, error, scope]);
}


/** AntD Radio.Group and Form.List have containers rather than focusable refs. */
export function focusCrfField(form: FormInstance, name: CrfName) {
    form.scrollToField(name, {focus:true});
    const container=document.getElementById(name.join('_'));
    const target=container?.matches('input:not(:disabled),textarea:not(:disabled),select:not(:disabled),button:not(:disabled)')?container:(container?.querySelector<HTMLElement>('input:not(:disabled),textarea:not(:disabled),select:not(:disabled)')??container?.querySelector<HTMLElement>('button:not(:disabled)'));
    (target??container)?.focus({preventScroll:true});
}
