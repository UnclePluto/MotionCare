"""Read-only project cover projection; explicit saved keys always win."""
from copy import deepcopy
from zoneinfo import ZoneInfo
from apps.crf.field_values import lookup_path, MISSING, BAD_PARENT
from apps.crf.answer_values import decode_crf_answer

def project_cover(project_patient, form_data, baseline):
    out = deepcopy(form_data)
    old = lookup_path(out, 'crf.cover')
    if old is BAD_PARENT or (old is not MISSING and old is not None and not isinstance(old, dict)):
        return out
    if old is None: return out
    cover = deepcopy(old) if isinstance(old, dict) else {}
    if project_patient.patient.project_links.count() == 1:
        legacy = lookup_path(baseline, 'demographics.document')
        if isinstance(legacy, dict):
            for key in ('protocol_number', 'enrolled_on', 'investigator_name'):
                if key not in cover and key in legacy:
                    metadata = lookup_path(baseline, 'demographics._crf_field_meta')
                    old_meta = metadata.get(f'patient_baseline.demographics.document.{key}') if isinstance(metadata, dict) else metadata if metadata not in (MISSING, BAD_PARENT) else None
                    answer = decode_crf_answer(legacy[key], old_meta)
                    cover[key] = deepcopy(legacy[key])
                    if not answer['error'] and answer['state'] in ('unknown', 'not_applicable'):
                        cover[key] = dict(__crf_answer__=1, state=answer['state'], value=deepcopy(answer['value']), reason=answer['reason'])
                    elif answer['error']:
                        crf = out.setdefault('crf', {})
                        if isinstance(crf, dict):
                            target = crf.setdefault('_field_meta', {})
                            if isinstance(target, dict): target.setdefault(f'visit.form_data.crf.cover.{key}', deepcopy(old_meta))
    if 'enrolled_on' not in cover and project_patient.enrolled_at:
        cover['enrolled_on'] = project_patient.enrolled_at.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    if 'crf' not in out: out['crf'] = {}
    if not isinstance(out['crf'], dict): return out
    out['crf']['cover'] = cover
    return out
