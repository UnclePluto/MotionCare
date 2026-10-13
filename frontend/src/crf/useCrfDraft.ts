import { createElement, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Form } from 'antd';
import type { FormInstance } from 'antd';
import { UNSAFE_DataRouterContext, useBlocker } from 'react-router-dom';
import { isCrfRecord, normalizeCrfFormValues } from './formValues';
import { readCrfPath } from './fieldState';
import type {CrfName} from './fieldState';
import { crfDraftPatch } from './visitSubmission';
function DraftNavigationGuard({ isDirty }: {
    isDirty: () => boolean;
}) {
    const blocker = useBlocker(() => isDirty());
    useEffect(() => { if (blocker.state === 'blocked') {
        if (window.confirm('有未保存的资料，确认离开并放弃这些改动？'))
            blocker.proceed();
        else
            blocker.reset();
    } }, [blocker]);
    return null;
}
export function useCrfDraft({ form, serverValues, recordKey, prefillValues, prefillNames = [], adoptableNames = [] }: {
    form: FormInstance;
    serverValues?: Record<string, unknown>;
    recordKey: string;
    prefillValues?: Record<string, unknown>;
    adoptableNames?: CrfName[];
    prefillNames?: CrfName[];
}) {
    const snapshot = useRef<{
        key: string;
        before: Record<string, unknown>;
        initial: Record<string, unknown>;
        adoptableNames: CrfName[];
        adopted: Set<string>;
    } | null>(null);
    const initializedPrefills = useRef(new Set<string>());
    const currentKey = useRef(recordKey);
    currentKey.current = recordKey;
    const alive = useRef(true);
    useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
    const pending = useRef(false);
    const lastServer = useRef<string>();
    const [, refresh] = useState(0);
    const watched = Form.useWatch(values => ({values, adopted:(snapshot.current?.adoptableNames ?? []).map(name=>form.isFieldTouched(name))}), { form, preserve: true });
    const getBefore = useCallback(() => {
        const before=normalizeCrfFormValues(snapshot.current?.before ?? {});
        for(const name of snapshot.current?.adoptableNames ?? []) {
            const identity=JSON.stringify(name);
            if(form.isFieldTouched(name)) snapshot.current?.adopted.add(identity);
            if(!snapshot.current?.adopted.has(identity)) continue;
            const parent=readCrfPath(before,name.slice(0,-1));
            if(isCrfRecord(parent)) delete parent[String(name[name.length-1])];
        }
        return before;
    },[form]);
    const getValues = useCallback(() => normalizeCrfFormValues(form.getFieldsValue(true)), [form]);
    const getPatch = useCallback(() => crfDraftPatch(getBefore(), getValues()), [getValues,getBefore]);
    const isDirty = useCallback(() => pending.current || Boolean(snapshot.current?.key === currentKey.current && Object.keys(getPatch()).length), [getPatch]);
    useLayoutEffect(() => {
        if (!serverValues)
            return;
        const identity = JSON.stringify([recordKey, serverValues, prefillValues]);
        if (lastServer.current === identity)
            return;
        if (snapshot.current?.key === recordKey && isDirty()) {
            // Late facts may fill only untouched, never initialized missing fields.
            const current = form.getFieldsValue(true);
            const initial = normalizeCrfFormValues(prefillValues ?? serverValues);
            const additions = prefillNames.flatMap(name => {
                const key = JSON.stringify(name);
                const value = readCrfPath(initial, name);
                if (initializedPrefills.current.has(key) || form.isFieldTouched(name) || readCrfPath(current, name) !== undefined || value === undefined) return [];
                initializedPrefills.current.add(key);
                return [{name, value, touched: false}];
            });
            lastServer.current = identity;
            if (additions.length) { form.setFields(additions); refresh(n => n + 1); }
            return;
        }
        const before = normalizeCrfFormValues(serverValues);
        const initial = normalizeCrfFormValues(prefillValues ?? serverValues);
        if(snapshot.current?.key !== recordKey)initializedPrefills.current.clear();
        for(const name of prefillNames) {
            const key=JSON.stringify(name);
            const old=readCrfPath(form.getFieldsValue(true),name);
            if(initializedPrefills.current.has(key)&&old!==undefined) {
                let parent=initial;
                for(const part of name.slice(0,-1)) {
                    const child=parent[String(part)];
                    if(!isCrfRecord(child))parent[String(part)]={};
                    parent=parent[String(part)] as Record<string,unknown>;
                }
                parent[String(name[name.length-1])]=old;
            }
            if(readCrfPath(initial,name)!==undefined)initializedPrefills.current.add(key);
        }
        lastServer.current = identity;
        snapshot.current = { key: recordKey, before, initial, adoptableNames, adopted:new Set() };
        form.resetFields();
        form.setFieldsValue(initial);
        // setFieldsValue is initialization, not an explicit adoption of a suggestion.
        form.setFields(adoptableNames.map(name=>({name,touched:false})));
        refresh(n => n + 1);
    }, [serverValues, prefillValues, recordKey, form, isDirty, adoptableNames, prefillNames]);
    useEffect(() => { const leave = (event: BeforeUnloadEvent) => { if (isDirty()) {
        event.preventDefault();
        event.returnValue = '';
    } }; window.addEventListener('beforeunload', leave); return () => window.removeEventListener('beforeunload', leave); }, [isDirty]);
    const isCurrentRecord = (key: string) => alive.current && currentKey.current === key;
    const beginSubmit = () => { if (pending.current)
        return false; pending.current = true; return true; };
    const endSubmit = () => { pending.current = false; if (alive.current)
        refresh(n => n + 1); };
    const resetAfterSubmit = (submitted: Record<string, unknown>, key: string) => {
        if (!alive.current || currentKey.current !== key)
            return false;
        const value = normalizeCrfFormValues(submitted);
        const names=snapshot.current?.adoptableNames ?? [];
        snapshot.current = { key, before: value, initial: value, adoptableNames:names, adopted:new Set() };
        form.setFields(names.map(name=>({name,touched:false})));
        refresh(n => n + 1);
        return true;
    };
    const reloadFromServer = (key: string) => {
        if (!isCurrentRecord(key)) return;
        snapshot.current = null;
        lastServer.current = undefined;
        initializedPrefills.current.clear();
        refresh(n => n + 1);
    };
    // A separate component keeps hooks unconditional and supports legacy MemoryRouter consumers.
    const dataRouter = useContext(UNSAFE_DataRouterContext);
    void watched;
    return { initialValues: snapshot.current?.initial ?? {}, before: getBefore(), dirty: isDirty(), patch: getPatch(), getValues, getPatch, isDirty, isCurrentRecord, beginSubmit, endSubmit, resetAfterSubmit, reloadFromServer, navigationGuard: dataRouter ? createElement(DraftNavigationGuard, { isDirty }) : null };
}
