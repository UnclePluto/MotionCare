import registryJson from "./registry.v1.json";
import type { RegistryField } from "./types";
import { visitRegistryStorageToFormName } from "./visitFormPaths";
const registry = registryJson as {
    fields: RegistryField[];
    table_titles?: Record<string, string>;
};
// Entry scope is narrower than the paper form; registry/export bindings and stored history remain intact.
const consentEntryFields = new Set(['scr_t0_icf_signed', 'scr_t0_icf_signed_on', 'scr_t0_icf_signer_type']);
function isPlainObject(v: unknown): v is Record<string, unknown> {
    return typeof v === "object" && v !== null && !Array.isArray(v);
}
/** 当前访视类型下，需由 registry 动态渲染的访视表单扩展字段（去重 storage）。 */
export function registryVisitExtensionFields(visitType: string): RegistryField[] {
    const seen = new Set<string>();
    return registry.fields.filter(f => {
        if (f.table_ref === "#T4" && !consentEntryFields.has(f.field_id))
            return false;
        if (f.visit_types?.length && !f.visit_types.includes(visitType))
            return false;
        if (!f.storage.startsWith("visit.") && !f.canonical_storage)
            return false;
        if (seen.has(f.storage))
            return false;
        seen.add(f.storage);
        return true;
    });
}
export function groupVisitExtensionFields(fields: RegistryField[]): {
    key: string;
    label: string;
    fields: RegistryField[];
}[] {
    const groups = new Map<string, RegistryField[]>();
    for (const field of fields) {
        if (field.legacy)
            continue;
        const key = field.table_ref;
        groups.set(key, [...(groups.get(key) ?? []), field]);
    }
    return [...groups].sort((a, b) => (a[0]==="study_cover"?-1:Number(a[0].replace(/\D/g, ""))) - (b[0]==="study_cover"?-1:Number(b[0].replace(/\D/g, "")))).map(([key, fields]) => ({ key, label: registry.table_titles?.[key] ?? "其他资料", fields }));
}
function getAtPath(obj: unknown, path: (string | number)[]): unknown {
    let cur: unknown = obj;
    for (const p of path) {
        if (!cur || typeof cur !== "object")
            return undefined;
        cur = (cur as Record<string, unknown>)[String(p)];
    }
    return cur;
}
function deepSet(target: Record<string, unknown>, path: (string | number)[], value: unknown): void {
    if (path.length === 0)
        return;
    const [head, ...rest] = path;
    const h = String(head);
    if (rest.length === 0) {
        target[h] = value as never;
        return;
    }
    const next = target[h];
    const child = typeof next === "object" && next !== null && !Array.isArray(next)
        ? (next as Record<string, unknown>)
        : {};
    target[h] = child;
    deepSet(child, rest, value);
}
export function buildVisitExtensionInitial(formData: Record<string, unknown>, fields: RegistryField[]): Record<string, unknown> {
    const root: Record<string, unknown> = {};
    for (const f of fields) {
        const path = visitRegistryStorageToFormName(f.storage);
        if (!path)
            continue;
        const v = getAtPath(formData, path);
        if (v !== undefined) {
            deepSet(root, path, v);
        }
    }
    return root;
}
/** 返回 after 相对 before 的变更子树；无变更则 undefined。 */
export function deepDiffPatch(before: unknown, after: unknown): unknown {
    if (before === after)
        return undefined;
    if (typeof before !== "object" || before === null || Array.isArray(before)) {
        return after;
    }
    if (typeof after !== "object" || after === null || Array.isArray(after)) {
        return after;
    }
    const b = before as Record<string, unknown>;
    const a = after as Record<string, unknown>;
    const keys = new Set([...Object.keys(b), ...Object.keys(a)]);
    const out: Record<string, unknown> = {};
    let any = false;
    for (const k of keys) {
        const d = deepDiffPatch(b[k], a[k]);
        if (d !== undefined) {
            out[k] = d;
            any = true;
        }
    }
    return any ? out : undefined;
}
export function deepMergeRecords(a: Record<string, unknown> | undefined, b: Record<string, unknown> | undefined): Record<string, unknown> | undefined {
    if (!a && !b)
        return undefined;
    if (!a)
        return b;
    if (!b)
        return a;
    const out: Record<string, unknown> = { ...a };
    for (const [k, yv] of Object.entries(b)) {
        const xv = out[k];
        if (isPlainObject(xv) && isPlainObject(yv)) {
            const merged = deepMergeRecords(xv, yv);
            if (merged !== undefined)
                out[k] = merged;
        }
        else {
            out[k] = yv;
        }
    }
    return out;
}
