"""Logical visit-date answer and complete-date database projection."""
from collections.abc import Mapping
from copy import deepcopy
from datetime import date
from rest_framework import serializers
from apps.crf.answer_values import decode_crf_answer,has_crf_answer_marker
from apps.crf.field_values import lookup_path,MISSING,BAD_PARENT
from apps.crf.field_rules import validate_field_value
from apps.crf.registry_loader import load_crf_registry

def read_visit_date_answer(visit_date:object,form_data:dict)->object:
    answer=lookup_path(form_data,'crf.meta.visit_date_answer')
    if answer is not MISSING and answer is not BAD_PARENT:return deepcopy(answer)
    if visit_date is not None:return visit_date.isoformat() if type(visit_date) is date else visit_date
    parts=lookup_path(form_data,'crf.meta.visit_date_parts')
    return deepcopy(parts) if parts is not MISSING and parts is not BAD_PARENT else None

def project_visit_date_answer(answer:object)->date|None:
    decoded=decode_crf_answer(answer)
    if decoded['error'] or decoded['state']!='value':return None
    value=decoded['value']
    if type(value) is date:return value
    if isinstance(value,str) and len(value)==10:
        try:return date.fromisoformat(value)
        except ValueError:return None
    return None

class CrfVisitDateAnswerField(serializers.Field):
    def to_internal_value(self,value):
        if isinstance(value,Mapping) and not has_crf_answer_marker(value):
            raise serializers.ValidationError("请使用日期组件填写日期")
        field=next(f for f in load_crf_registry()['fields'] if f['storage']=='visit.visit_date' and not f.get('legacy'))
        error=validate_field_value(field,value)
        if error:raise serializers.ValidationError(error)
        return deepcopy(value)
    def to_representation(self,value):
        return value.isoformat() if type(value) is date else value
