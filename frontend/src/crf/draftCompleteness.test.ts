import {expect,it} from 'vitest';
import {evaluateCrfDraft} from './draftCompleteness';
import {crfRegistryFields} from './fieldState';
import {registryVisitExtensionFields} from './registryVisitExtensions';
// Expected counts are from actual backend evaluate_completeness fixtures;
// final-fix parity evidence additionally compares every field/state/count flag.
const cases=[
  {
    "name": "T1 minimal",
    "scope": "T1",
    "values": {
      "visit_date": "2026-10-09",
      "assessments": {
        "sppb": {
          "total": 9
        },
        "moca": {
          "total": 22
        },
        "tug_seconds": 8,
        "physical": {
          "chair_stand": {
            "seconds": 8
          }
        }
      }
    },
    "counts": {
      "normal": 4,
      "unknown": 0,
      "not_applicable": 0,
      "unresolved": 70
    },
    "items": 94
  },
  {
    "name": "T1 unknown whitespace",
    "scope": "T1",
    "values": {
      "crf": {
        "_field_meta": {
          "visit.form_data.crf.meta.actual_week": {
            "state": "unknown",
            "reason": "   "
          }
        }
      }
    },
    "counts": {
      "normal": 0,
      "unknown": 1,
      "not_applicable": 0,
      "unresolved": 73
    },
    "items": 94
  },
  {
    "name": "T1 partial",
    "scope": "T1",
    "values": {
      "visit_date": null,
      "crf": {
        "meta": {
          "visit_date_parts": {
            "year": {
              "state": "value",
              "value": 2026
            },
            "month": {
              "state": "unknown"
            },
            "day": {
              "state": "value",
              "value": 3
            }
          }
        },
        "_field_meta": {
          "visit.visit_date": {
            "reason": "月份不详"
          }
        }
      }
    },
    "counts": {
      "normal": 0,
      "unknown": 1,
      "not_applicable": 0,
      "unresolved": 73
    },
    "items": 94
  },
  {
    "name": "T1 invalid",
    "scope": "T1",
    "values": {
      "assessments": {
        "sppb": {
          "balance": 4,
          "gait": 3,
          "chair_stand": 2,
          "total": 12
        }
      },
      "crf": {
        "adverse_events": {
          "has_events": "是",
          "entries": [
            {
              "_row_id": "a",
              "event_name": "甲"
            },
            {
              "_row_id": "b",
              "event_name": "乙"
            }
          ]
        }
      }
    },
    "counts": {
      "normal": 7,
      "unknown": 0,
      "not_applicable": 0,
      "unresolved": 82
    },
    "items": 108
  },
  {
    "name": "T1 legacy",
    "scope": "T1",
    "values": {
      "assessments": {
        "sppb": "旧总文"
      },
      "crf": {
        "satisfaction": {
          "matrix_note": "旧反馈"
        },
        "_field_meta": {
          "visit.form_data.crf.meta.actual_week": {
            "state": "value",
            "reason": 3
          }
        }
      }
    },
    "counts": {
      "normal": 0,
      "unknown": 0,
      "not_applicable": 0,
      "unresolved": 74
    },
    "items": 94
  },
  {
    "name": "baseline extras",
    "scope": "baseline",
    "values": {
      "surgery_allergy": {
        "has_surgery": "是",
        "surgery_records": [
          {
            "_row_id": "a",
            "name": "甲",
            "date": {
              "year": {
                "state": "value",
                "value": 2000
              },
              "month": {
                "state": "unknown"
              },
              "day": {
                "state": "value",
                "value": 3
              }
            },
            "_field_meta": {
              "date": {
                "reason": "   "
              }
            }
          }
        ]
      },
      "demographics": {
        "_crf_field_meta": {
          "patient_baseline.surgery_allergy.has_surgery": {
            "state": "value",
            "legacy_feedback": "旧反馈"
          }
        }
      }
    },
    "counts": {
      "normal": 3,
      "unknown": 1,
      "not_applicable": 0,
      "unresolved": 73
    },
    "items": 172
  },
  {
    "name": "baseline optional",
    "scope": "baseline",
    "values": {
      "demographics": {
        "_crf_field_meta": {
          "patient_baseline.surgery_allergy.has_surgery": {
            "state": "unknown",
            "reason": "未确认"
          }
        }
      },
      "surgery_allergy": {
        "has_surgery": "是",
        "surgery_records": [
          {
            "name": "隐藏旧手术"
          }
        ]
      }
    },
    "counts": {
      "normal": 0,
      "unknown": 1,
      "not_applicable": 0,
      "unresolved": 73
    },
    "items": 172
  },
  {
    "name": "baseline date invalid",
    "scope": "baseline",
    "values": {
      "demographics": {
        "birth_date": {
          "year": null,
          "month": {
            "state": "value",
            "value": 13
          },
          "day": null
        },
        "_crf_field_meta": {
          "patient_baseline.demographics.birth_date": {
            "state": "unknown",
            "reason": "待核对"
          }
        }
      }
    },
    "counts": {
      "normal": 0,
      "unknown": 0,
      "not_applicable": 0,
      "unresolved": 74
    },
    "items": 169
  },
  {
    "name": "baseline alternate",
    "scope": "baseline",
    "values": {
      "lifestyle": {
        "drinking_status": "目前饮酒",
        "alcohol_current": {
          "ml_per_week": 500
        }
      }
    },
    "counts": {
      "normal": 1,
      "unknown": 0,
      "not_applicable": 0,
      "unresolved": 76
    },
    "items": 169
  },
  {
    "name": "T1 terminal",
    "scope": "T1",
    "values": {
      "crf": {
        "completion_record": {
          "status": "完成"
        }
      }
    },
    "counts": {
      "normal": 0,
      "unknown": 0,
      "not_applicable": 0,
      "unresolved": 77
    },
    "items": 102
  }
];
it.each(cases)('matches the backend draft projection: $name',c=>{
 const fields=c.scope==='baseline'?crfRegistryFields.filter(f=>f.storage.startsWith('patient_baseline.')&&!f.visit_types?.length):registryVisitExtensionFields(c.scope);
 const projection=evaluateCrfDraft(fields,c.values);
 expect(projection.counts).toEqual(c.counts);
 expect(projection.items.filter(i=>i.source!=='legacy')).toHaveLength(c.items);
});

// Independently checked with backend evaluate_completeness; the I2 array
// evidence's backend-four-fields.json reports invalid_value for all four.
it.each([
 {parent:[],state:'unknown'},
 {parent:[{old:'历史原文'}],state:'unknown'},
 {parent:[],state:'not_applicable'},
 {parent:[{old:'历史原文'}],state:'not_applicable'},
 {parent:null,state:'unknown'},
 {parent:'历史原文',state:'unknown'},
])('keeps malformed SPPB parent $parent unresolved despite $state and reason',({parent,state})=>{
 const values={assessments:{sppb:parent},crf:{_field_meta:Object.fromEntries(['balance','gait','chair_stand','total'].map(key=>[`visit.form_data.assessments.sppb.${key}`,{state,reason:'历史父容器待核对'}]))}};
 const before=JSON.stringify(values);
 const result=evaluateCrfDraft(registryVisitExtensionFields('T1'),values);
 const fields=result.items.filter(item=>['as_T1_sppb_balance','as_T1_sppb_gait','as_T1_sppb_chair','as_T1_sppb_total'].includes(item.fieldId));
 expect(fields.map(({fieldId,state,counted,required,applicable})=>({fieldId,state,counted,required,applicable}))).toEqual([
  {fieldId:'as_T1_sppb_balance',state:'unresolved',counted:true,required:true,applicable:true},
  {fieldId:'as_T1_sppb_gait',state:'unresolved',counted:true,required:true,applicable:true},
  {fieldId:'as_T1_sppb_chair',state:'unresolved',counted:true,required:true,applicable:true},
  {fieldId:'as_T1_sppb_total',state:'unresolved',counted:true,required:true,applicable:true},
 ]);
 expect(fields.every(item=>item.issues.includes('上级字段必须是对象'))).toBe(true);
 expect(result.unresolved).toEqual(expect.arrayContaining(fields));
 expect(JSON.stringify(values)).toBe(before);
});

it.each(['unknown','not_applicable'])('preserves valid repeat rows and row-local %s reasons',state=>{
 const field=crfRegistryFields.find(f=>f.field_id==='sa_surgery_records')!;
 const values={surgery_allergy:{has_surgery:'是',surgery_records:[{_row_id:'a',name:'手术甲',_field_meta:{date:{state,reason:'日期待核对'}}},{_row_id:'b',name:'手术乙',date:'2001-01-01'}]}};
 const result=evaluateCrfDraft([field],values);
 const dateItems=result.items.filter(i=>i.name.at(-1)==='date');
 expect(dateItems.map(i=>[i.state,i.issues])).toEqual([[state,[]],['normal',[]]]);
 expect(dateItems.map(i=>i.name)).toEqual([['surgery_allergy','surgery_records',0,'date'],['surgery_allergy','surgery_records',1,'date']]);
});

it('accepts a numeric row index in the actual storage path',()=>{
 const field=crfRegistryFields.find(f=>f.field_id==='sa_surgery_records')!.children!.find(f=>f.storage==='name')!;
 const indexed={...field,storage:'patient_baseline.surgery_allergy.surgery_records.0.name',metadata:undefined};
 const result=evaluateCrfDraft([indexed],{surgery_allergy:{surgery_records:[{name:'手术甲'}]}});
 expect(result.items[0]).toMatchObject({state:'normal',issues:[]});
});


it.each(['unknown','not_applicable'])('handles whole repeated %s while retaining inactive children and correct field paths',state=>{
 const field=crfRegistryFields.find(f=>f.field_id==='sa_surgery_records')!;
 const rows=[{_row_id:'a',name:'原手术',date:'2001-01-01'}];
 const result=evaluateCrfDraft([field],{surgery_allergy:{has_surgery:'是',surgery_records:{__crf_answer__:1,state,value:rows,reason:null}}});
 expect(result.items.find(i=>i.fieldId===field.field_id)).toMatchObject({state,issues:[],counted:true});
 const child=result.items.find(i=>i.name.at(-1)==='name')!;
 expect(child).toMatchObject({counted:false,applicable:false,name:['surgery_allergy','surgery_records','value',0,'name']});
 const malformed=evaluateCrfDraft([field],{surgery_allergy:{has_surgery:'是',surgery_records:{__crf_answer__:1,state,value:[7],reason:null}}});
 expect(malformed.items.find(i=>i.fieldId===field.field_id)?.state).toBe('unresolved');
});
it('treats a projected canonical copy of legacy date parts as the same observation',()=>{
 const field=registryVisitExtensionFields('T1').find(f=>f.storage==='visit.visit_date')!;
 const parts={year:{state:'value',value:2026},month:{state:'value',value:2},day:{state:'value',value:28}};
 const result=evaluateCrfDraft([field],{visit_date:parts,crf:{meta:{visit_date_answer:parts,visit_date_parts:parts}}});
 expect(result.items[0]).toMatchObject({state:'normal',issues:[]});
});
