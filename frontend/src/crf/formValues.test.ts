import {expect,it} from "vitest";
import dayjs from "dayjs";
import {buildCrfPatch,normalizeCrfFormValues} from "./formValues";
import {baselineToFormValues} from "./renderRegistryFields";
import {visitRegistryStorageToFormName} from "./visitFormPaths";
it("preserves clears, zero, arrays and omitted values",()=>{
 expect(buildCrfPatch({score:0,hidden:"keep",list:[1]},{score:null,list:[]})).toEqual({score:null,list:[]});
 expect(buildCrfPatch({nested:{a:1,b:2}},{nested:{a:0}})).toEqual({nested:{a:0}});
});
it("preserves historical scalars and complete dates",()=>{
 expect(normalizeCrfFormValues({score:"0",date:"2020-01-24",none:null,list:[],zero:0})).toEqual({score:"0",date:"2020-01-24",none:null,list:[],zero:0});
 expect(normalizeCrfFormValues({date:dayjs("2020-02-20")})).toEqual({date:"2020-02-20"});
 expect(baselineToFormValues({demographics:{birth_date:"2020-01-24"},lifestyle:"old text"})).toEqual({demographics:{birth_date:"2020-01-24"},lifestyle:"old text"});
});
it("maps native date and preserves literal metadata keys",()=>{
 expect(visitRegistryStorageToFormName("visit.visit_date")).toEqual(["visit_date"]);
 expect(visitRegistryStorageToFormName("visit.form_data.crf.meta.visit_date_parts")).toEqual(["crf","meta","visit_date_parts"]);
 expect(buildCrfPatch({}, {crf:{_field_meta:{"visit.visit_date":{state:"unknown"}}}})).toEqual({crf:{_field_meta:{"visit.visit_date":{state:"unknown"}}}});
});
it('does not treat database key ordering as an edit to the same marked answer or repeated row',()=>{
 const before={answer:{state:'unknown',value:66,reason:null,__crf_answer__:1},rows:[{name:'原记录',_row_id:'a'}]};
 const after={answer:{__crf_answer__:1,state:'unknown',value:66,reason:null},rows:[{_row_id:'a',name:'原记录'}]};
 expect(buildCrfPatch(before,after)).toEqual({});
});
