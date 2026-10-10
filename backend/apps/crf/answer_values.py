"""Single-path CRF answers; no storage writes or clinical value coercion."""
from collections.abc import Mapping
from copy import deepcopy

def has_crf_answer_marker(value:object)->bool:
    return isinstance(value,Mapping) and '__crf_answer__' in value

def decode_crf_answer(value:object,legacy_meta:object=None)->dict:
    if has_crf_answer_marker(value):
        error = (type(value['__crf_answer__']) is not int or value['__crf_answer__'] != 1
                 or value.get('state') not in ('unknown','not_applicable')
                 or 'value' not in value or has_crf_answer_marker(value.get('value'))
                 or (value.get('reason') is not None and not isinstance(value['reason'],str)))
        return dict(state=value.get('state') if not error else 'value',value=value.get('value'),reason=value.get('reason'),marked=True,error='答案状态或原因无效' if error else None)
    meta=legacy_meta if isinstance(legacy_meta,Mapping) else {}
    error=legacy_meta is not None and (not isinstance(legacy_meta,Mapping) or meta.get('state') not in (None,'value','unknown','not_applicable') or (meta.get('reason') is not None and not isinstance(meta['reason'],str)))
    return dict(state=meta.get('state') or 'value',value=value,reason=meta.get('reason'),marked=False,error='字段状态或原因无效' if error else None)

def is_crf_marked_answer(value:object)->bool:
    return has_crf_answer_marker(value) and decode_crf_answer(value)['error'] is None

def reconcile_answer_patch(current:dict,patch:dict,fields:list[dict])->dict:
    from apps.crf.field_values import lookup_path,MISSING,BAD_PARENT,match_crf_rows
    result=deepcopy(patch)
    def check(old,new,definitions):
        for field in definitions:
            submitted=lookup_path(new,field['storage'])
            if submitted is MISSING or submitted is BAD_PARENT:
                continue
            stored=lookup_path(old,field['storage'])
            if field.get('widget')=='table_repeat' and isinstance(submitted,list):
                rows=stored if isinstance(stored,list) else []
                matched=match_crf_rows(rows,submitted)
                for i,row in enumerate(submitted):
                    if isinstance(row,dict):check(rows[matched[i]] if i in matched and isinstance(rows[matched[i]],dict) else {},row,field.get('children',[]))
            meta=field.get('metadata')
            if not meta:continue
            previous=lookup_path(old,meta['storage'])
            if not isinstance(previous,Mapping) or meta['key'] not in previous:continue
            # An explicit legacy state submission belongs to the legacy client.
            posted=lookup_path(new,meta['storage'])
            if not has_crf_answer_marker(submitted) and isinstance(posted,Mapping) and meta['key'] in posted:continue
            entry=previous[meta['key']]
            if not isinstance(entry,Mapping):continue
            parent=new
            for segment in meta['storage'].split('.'):
                if segment in parent and not isinstance(parent[segment],dict):break
                parent=parent.setdefault(segment,{})
            else:
                existing=parent.get(meta['key'])
                parent[meta['key']]={**deepcopy(entry),**(existing if isinstance(existing,dict) else {}),'state':None,'reason':None}
    check(current,result,fields)
    return result
