import {crfRegistryFields,getObservedCrfValue} from "./fieldState";
export type CrfCalculationKind = "sppb_total" | "moca_total" | "satisfaction_total" | "fastest_walk" | "maximum_grip" | "count_ratio" | "time_ratio";
const targets: Partial<Record<CrfCalculationKind,string>> = {
 sppb_total:"visit.form_data.assessments.sppb.total", moca_total:"visit.form_data.assessments.moca.total",
 satisfaction_total:"visit.form_data.crf.satisfaction.total", fastest_walk:"visit.form_data.assessments.physical.gait.fastest_seconds", maximum_grip:"visit.form_data.assessments.grip_strength_kg",
};
export function crfCalculationForStorage(storage:string): CrfCalculationKind | null {
 return (Object.entries(targets).find(([,target]) => target === storage)?.[0] as CrfCalculationKind | undefined) ?? null;
}
function numberAt(storage:string,values:Record<string,unknown>): number | null {
 const field=crfRegistryFields.find(f => f.storage === storage && !f.legacy);
 const value=field ? getObservedCrfValue(field,values) : null;
 return typeof value === "number" ? value : null;
}
export function calculateCrfDerivedValue(kind:CrfCalculationKind,values:Record<string,unknown>): number | null {
 if (kind === "count_ratio" || kind === "time_ratio") {
  const suffix=kind === "count_ratio" ? "count" : "minutes";
  const actual=numberAt(`visit.form_data.crf.adherence.actual_${suffix}`,values), planned=numberAt(`visit.form_data.crf.adherence.planned_${suffix}`,values);
  return actual == null || planned == null || planned === 0 ? null : actual / planned * 100;
 }
 const field=crfRegistryFields.find(f => f.storage === targets[kind] && !f.legacy);
 const rule=field?.validation?.consistency;
 if (!rule) return null;
 const numbers=rule.operands.map(path => numberAt(path,values));
 if (numbers.some(n => n == null)) return null;
 const known=numbers as number[];
 const total=kind === "fastest_walk" ? Math.min(...known) : kind === "maximum_grip" ? Math.max(...known) : known.reduce((sum,n)=>sum+n,0);
 return rule.cap === undefined ? total : Math.min(rule.cap,total);
}
