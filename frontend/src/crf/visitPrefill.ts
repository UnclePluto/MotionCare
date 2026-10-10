import {isCrfRecord,normalizeCrfFormValues} from './formValues';
import {decodeCrfAnswer,setCrfAnswerState} from './answerValues';
export function buildVisitPrefill({visitType,serverValues,enrolledAt,doctorName,confirmedProjectCount,legacyCover,legacyCoverMetadata,readOnly}:{visitType:'T0'|'T1'|'T2';serverValues:Record<string,unknown>;enrolledAt?:string;doctorName?:string;confirmedProjectCount:number;legacyCover?:unknown;legacyCoverMetadata?:unknown;readOnly:boolean}):Record<string,unknown> {
 const out=normalizeCrfFormValues(serverValues);
 if(readOnly)return out;
 if('crf' in out&&!isCrfRecord(out.crf))return out;
 const crf=isCrfRecord(out.crf)?out.crf:{};
 out.crf=crf;
 if(!('meta' in crf)||isCrfRecord(crf.meta)) {
  const meta=isCrfRecord(crf.meta)?crf.meta:{};
  if(!('assessor_name' in meta)&&doctorName?.trim())meta.assessor_name=doctorName.trim();
  if(!('assessed_on' in meta)&&typeof out.visit_date==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(out.visit_date))meta.assessed_on=out.visit_date;
  if(Object.keys(meta).length)crf.meta=meta;
 }
 if(visitType==='T0'&&(!('cover' in crf)||isCrfRecord(crf.cover))) {
  const cover=isCrfRecord(crf.cover)?crf.cover:{};
  if(confirmedProjectCount===1&&isCrfRecord(legacyCover))for(const key of ['protocol_number','enrolled_on','investigator_name'])if(!(key in cover)&&key in legacyCover) {
   const meta=isCrfRecord(legacyCoverMetadata)?legacyCoverMetadata[`patient_baseline.demographics.document.${key}`]:legacyCoverMetadata;
   const answer=decodeCrfAnswer(legacyCover[key],meta);
   cover[key]=!answer.error&&answer.state!=='value'?setCrfAnswerState(legacyCover[key],answer.state,meta):legacyCover[key];
   if(answer.error&&(!('_field_meta' in crf)||isCrfRecord(crf._field_meta))) {
    const metadata=isCrfRecord(crf._field_meta)?crf._field_meta:{};
    const path=`visit.form_data.crf.cover.${key}`;
    if(!(path in metadata))metadata[path]=meta;
    crf._field_meta=metadata;
   }
  }
  if(!('enrolled_on' in cover)&&enrolledAt&&Number.isFinite(Date.parse(enrolledAt))) {
   const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(enrolledAt));
   const get=(type:string)=>parts.find(p=>p.type===type)?.value;
   cover.enrolled_on=`${get('year')}-${get('month')}-${get('day')}`;
  }
  if(!('investigator_name' in cover)&&doctorName?.trim())cover.investigator_name=doctorName.trim();
  if(Object.keys(cover).length)crf.cover=cover;
 }
 if(!Object.keys(crf).length)delete out.crf;
 return out;
}
