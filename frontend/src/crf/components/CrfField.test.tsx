import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {Form,Button,Tabs} from "antd";
import type {FormInstance} from "antd";
import {buildCrfPatch,normalizeCrfFormValues} from "../formValues";
import {afterEach,expect,it,vi} from "vitest";
import type {RegistryField} from "../types";
import {renderBaselineRegistryField} from "../renderBaselineRegistryFields";
import {renderVisitRegistryField} from "../renderRegistryFields";
afterEach(cleanup);
const field=(extra:Partial<RegistryField>):RegistryField=>({field_id:"sample",table_ref:"#T13",label_zh:"原标签",ui_label:"测量值",hint:"原文记录 registry #T13",widget:"number",storage:"patient_baseline.demographics.score",...extra});
function setup(f:RegistryField,initialValues:Record<string,unknown>={},visit=false){
 const finish=vi.fn();render(<Form initialValues={initialValues} onFinish={finish}>{visit?renderVisitRegistryField(f):renderBaselineRegistryField(f)}<Button htmlType="submit">保存</Button></Form>);return finish;
}
it("uses concise labels and clears zero to null",async()=>{
 const finish=setup(field({unit:"kg",min:0,max:100}),{demographics:{score:0}});
 expect(screen.queryByText(/原文记录/)).not.toBeInTheDocument();expect(screen.getByText("测量值")).toBeInTheDocument();
 fireEvent.change(screen.getByRole("spinbutton"),{target:{value:""}});fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].demographics.score).toBeNull();
});
it("uses short radios without defaulting to no",()=>{setup(field({widget:"single_choice",options:["是","否"]}));expect(screen.getByRole("radio",{name:"否"})).not.toBeChecked();});
it("submits multiple choices as an array",async()=>{
 const finish=setup(field({widget:"multi_choice",options:["步行","骑车"]}));fireEvent.click(screen.getByRole("checkbox",{name:"步行"}));fireEvent.click(screen.getByRole("checkbox",{name:"骑车"}));fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].demographics.score).toEqual(["步行","骑车"]);
});
it("keeps unmodified month field day precision",async()=>{
 const finish=setup(field({widget:"date",date_precision:"month"}),{demographics:{score:"2020-01-24"}});fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].demographics.score).toBe("2020-01-24");
});
it("writes calculated totals only after explicit use",async()=>{
 const finish=setup(field({storage:"visit.form_data.assessments.sppb.total"}),{assessments:{sppb:{balance:4,gait:3,chair_stand:2,total:5}}},true);
 expect(screen.getByRole("spinbutton")).toHaveValue("5");fireEvent.click(screen.getByRole("button",{name:"使用计算结果"}));fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].assessments.sppb.total).toBe(9);
});
it("saves optional handled reason in the business field",async()=>{
 const f=field({metadata:{storage:"patient_baseline.demographics._crf_field_meta",key:"patient_baseline.demographics.score",states:["value","unknown","not_applicable"]}});
 const finish=setup(f);fireEvent.click(screen.getByRole("button",{name:"测量值更多"}));fireEvent.click(await screen.findByRole("checkbox",{name:"不详"}));fireEvent.change(screen.getByRole("textbox",{name:"测量值原因"}),{target:{value:"无法测量"}});fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].demographics.score).toEqual({__crf_answer__:1,state:"unknown",value:null,reason:"无法测量"});
});
it("writes edited month precision without a fabricated day",async()=>{
 const finish=setup(field({widget:"date",date_precision:"month"}),{demographics:{score:"2020-01-24"}});
 const input=screen.getByRole("textbox",{name:"测量值"});fireEvent.change(input,{target:{value:"2021-03"}});fireEvent.keyDown(input,{key:"Enter",code:"Enter"});fireEvent.blur(input);fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].demographics.score).toBe("2021-03");
});
it("preserves old date parts inside a whole-field unknown answer",async()=>{
 const parts={year:{state:"value",value:2026},month:{state:"value",value:5},day:{state:"value",value:9}};
 const finish=setup(field({widget:"date",allow_partial_date:true,metadata:{storage:"patient_baseline.demographics._crf_field_meta",key:"patient_baseline.demographics.score",states:["value","unknown"]}}),{demographics:{score:parts}});
 fireEvent.click(screen.getByRole("button",{name:"测量值更多"}));fireEvent.click(await screen.findByRole("checkbox",{name:"不详"}));fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].demographics.score).toEqual({__crf_answer__:1,state:"unknown",value:parts,reason:null});
});
it("changes visit date precision without manufacturing a day",async()=>{
 const finish=setup(field({storage:"visit.visit_date",partial_date_storage:"visit.form_data.crf.meta.visit_date_parts",widget:"date",allow_partial_date:true}),{visit_date:"2026-05-09"},true);
 fireEvent.click(screen.getByRole("button",{name:"测量值更多"}));fireEvent.mouseDown(await screen.findByRole("combobox",{name:"测量值日期精度"}));fireEvent.click(await screen.findByText("年月"));fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].visit_date).toBe("2026-05");
});
it("keeps baseline canonical subject number read-only in visit context",()=>{
 setup(field({storage:"patient_baseline.subject_id",canonical_storage:"patient_baseline.subject_id",visit_types:["T0"],widget:"text"}),{patient_baseline:{subject_id:"SUB001"}},true);
 expect(screen.getByDisplayValue("SUB001")).toBeDisabled();
});
it("preserves a historical numeric string through unrelated save",async()=>{
 const finish=setup(field({}),{demographics:{score:"0"}});expect(screen.getByDisplayValue("0")).toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].demographics.score).toBe("0");
});
it("shows count and time percentages separately without changing completion rate",()=>{
 setup(field({storage:"visit.form_data.crf.adherence.completion_rate"}),{crf:{adherence:{actual_count:3,planned_count:4,actual_minutes:30,planned_minutes:60,completion_rate:80}}},true);
 expect(screen.getByText("次数比值：75%" )).toBeInTheDocument();expect(screen.getByText("时长比值：50%" )).toBeInTheDocument();expect(screen.getByRole("spinbutton")).toHaveValue("80");
});
it("allows clearing a short radio choice to explicit null",async()=>{
 const finish=setup(field({widget:"single_choice",options:["是","否"]}),{demographics:{score:"是"}});
 fireEvent.click(screen.getByRole("button",{name:"清除选择"}));fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].demographics.score).toBeNull();
});
it("shows illegal old dates as readable raw text without coercion",async()=>{
 const finish=setup(field({widget:"date",allow_partial_date:true}),{demographics:{score:"记不清年份"}});
 expect(screen.getByDisplayValue("记不清年份")).toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].demographics.score).toBe("记不清年份");
});
it("shows historical multi-choice scalar without inventing an array",async()=>{
 const finish=setup(field({widget:"multi_choice",options:["步行","骑车"]}),{demographics:{score:"原文散步"}});
 expect(screen.getByDisplayValue("原文散步")).toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].demographics.score).toBe("原文散步");
});
it("restores legacy unknown zero as an explicit business answer",async()=>{
 const key="patient_baseline.demographics.score";
 const before={demographics:{score:0,_crf_field_meta:{[key]:{state:"unknown",reason:"原原因"}}}};
 const form=setupStore(field({metadata:{storage:"patient_baseline.demographics._crf_field_meta",key,states:["value","unknown"]}}),before);
 fireEvent.click(screen.getByRole("button",{name:"测量值更多"}));fireEvent.click(await screen.findByRole("checkbox",{name:"不详"}));
 expect(form.values().demographics).toEqual({score:0,_crf_field_meta:{[key]:{state:null,reason:null}}});expect(buildCrfPatch(before,form.values())).toEqual({demographics:{score:0}});
 expect(screen.getByRole("spinbutton")).not.toBeDisabled();
});
it("can clear an old partial date using the built-in date clear",async()=>{
 const form=setupStore(field({widget:"date",allow_partial_date:true}),{demographics:{score:{year:{state:"value",value:2026},month:{state:"unknown"},day:null}}});
 const input=screen.getByRole("textbox",{name:"测量值"});fireEvent.change(input,{target:{value:"2026-10-10"}});fireEvent.keyDown(input,{key:"Enter",code:"Enter"});fireEvent.blur(input);
 const clear=input.closest('.ant-picker')!.querySelector('.ant-picker-clear')!;fireEvent.mouseDown(clear);fireEvent.click(clear);
 expect(form.values().demographics).toEqual({score:null});
});
it("replaces an explicitly edited empty old date with a year answer",async()=>{
 const form=setupStore(field({widget:"date",allow_partial_date:true}),{demographics:{score:{year:null,month:null,day:null}}});
 fireEvent.click(screen.getByRole("button",{name:"测量值更多"}));fireEvent.mouseDown(await screen.findByRole("combobox",{name:"测量值日期精度"}));fireEvent.click(await screen.findByText("仅年"));
 const input=screen.getByRole("textbox",{name:"测量值"});fireEvent.change(input,{target:{value:"2026"}});fireEvent.keyDown(input,{key:"Enter",code:"Enter"});fireEvent.blur(input);
 expect(form.values().demographics).toEqual({score:"2026"});
});

// Capture the full store, including values whose native control was unmounted.
function setupStore(f:RegistryField,initialValues:Record<string,unknown>,visit=false){
 let currentForm:FormInstance;
 const finish=vi.fn();
 function Harness(){
  const [form]=Form.useForm();currentForm=form;
  return <Form form={form} initialValues={initialValues} onFinish={()=>finish(normalizeCrfFormValues(form.getFieldsValue(true)))}>{visit?renderVisitRegistryField(f):renderBaselineRegistryField(f)}<Button htmlType="submit">保存</Button></Form>;
 }
 render(<Harness/>);
 return {finish,values:()=>normalizeCrfFormValues(currentForm.getFieldsValue(true))};
}
it.each(["text","textarea"])("explicit %s clearing writes null to the store and patch",async widget=>{
 const before={demographics:{score:"原说明"}};
 const form=setupStore(field({widget}),before);
 fireEvent.change(screen.getByRole("textbox"),{target:{value:""}});
 expect(form.values()).toEqual({demographics:{score:null}});
 expect(buildCrfPatch(before,form.values())).toEqual({demographics:{score:null}});
 fireEvent.click(screen.getByRole("button",{name:/保.*存/}));await waitFor(()=>expect(form.finish).toHaveBeenCalledWith({demographics:{score:null}}));
});
it("clears legacy reason into the same marked business answer",async()=>{
 const key="patient_baseline.demographics.score";const before={demographics:{score:0,_crf_field_meta:{[key]:{state:"unknown",reason:"旧原因"}}}};
 const form=setupStore(field({metadata:{storage:"patient_baseline.demographics._crf_field_meta",key,states:["value","unknown"]}}),before);
 fireEvent.click(screen.getByRole("button",{name:"测量值更多"}));fireEvent.change(await screen.findByRole("textbox",{name:"测量值原因"}),{target:{value:""}});
 expect(form.values().demographics).toEqual({score:{__crf_answer__:1,state:"unknown",value:0,reason:null},_crf_field_meta:before.demographics._crf_field_meta});
 expect(buildCrfPatch(before,form.values())).toEqual({demographics:{score:{__crf_answer__:1,state:"unknown",value:0,reason:null}}});
});
it.each(["text","textarea"] as const)("explicit other %s clearing writes null without changing the choice",async other_remark_widget=>{
 const before={demographics:{score:"其他",note:"其他说明原值"}};
 const form=setupStore(field({widget:"single_choice",options:["是","其他"],other_remark_storage:"patient_baseline.demographics.note",other_remark_widget}),before);
 fireEvent.change(screen.getByRole("textbox",{name:"其他说明"}),{target:{value:""}});
 expect(form.values()).toEqual({demographics:{score:"其他",note:null}});
 expect(buildCrfPatch(before,form.values())).toEqual({demographics:{note:null}});
 fireEvent.click(screen.getByRole("button",{name:/保.*存/}));await waitFor(()=>expect(form.finish).toHaveBeenCalledWith(form.values()));
});
it("does not change a historical empty string on mount or normalization",async()=>{
 const before={demographics:{score:""}};
 const form=setupStore(field({widget:"text"}),before);
 expect(form.values()).toEqual(before);expect(buildCrfPatch(before,form.values())).toEqual({});
 fireEvent.click(screen.getByRole("button",{name:/保.*存/}));await waitFor(()=>expect(form.finish).toHaveBeenCalledWith(before));
});
const conflictingDate={visit_date:"2026-05-09",crf:{meta:{visit_date_parts:{year:{state:"value",value:2026},month:{state:"value",value:6},day:{state:"value",value:10}}}}};
const visitDateField=()=>field({storage:"visit.visit_date",partial_date_storage:"visit.form_data.crf.meta.visit_date_parts",widget:"date",date_precision:"day",allow_partial_date:true});
it("shows both conflicting date representations and preserves them on unrelated save",async()=>{
 const form=setupStore(visitDateField(),conflictingDate,true);
 expect(screen.getByText("日期存储冲突，请核对")).toBeInTheDocument();
 expect(screen.getByText("原日期：2026-05-09")).toBeInTheDocument();
 expect(screen.getByText(`部分日期：${JSON.stringify(conflictingDate.crf.meta.visit_date_parts)}`)).toBeInTheDocument();
 expect(form.values()).toEqual(conflictingDate);expect(buildCrfPatch(conflictingDate,form.values())).toEqual({});
 fireEvent.click(screen.getByRole("button",{name:/保.*存/}));await waitFor(()=>expect(form.finish).toHaveBeenCalledWith(conflictingDate));
});
it("coordinates both old date paths only after explicit date replacement",async()=>{
 const form=setupStore(visitDateField(),conflictingDate,true);const input=screen.getByRole("textbox",{name:"测量值"});fireEvent.change(input,{target:{value:"2026-07-10"}});fireEvent.keyDown(input,{key:"Enter",code:"Enter"});fireEvent.blur(input);
 const revised={visit_date:"2026-07-10",crf:{meta:{visit_date_parts:null}}};expect(form.values()).toEqual(revised);expect(buildCrfPatch(conflictingDate,form.values())).toEqual(revised);expect(screen.queryByText("日期存储冲突，请核对")).not.toBeInTheDocument();
});
it("keeps an invalid historical partial date readable after its tab remounts",async()=>{
 const before={visit_date:null,crf:{meta:{visit_date_parts:{year:{state:"value",value:2026},month:{state:"value",value:2},day:{state:"value",value:31}}}}};let currentForm:FormInstance;
 function Harness(){const [form]=Form.useForm();currentForm=form;return <Form form={form} initialValues={before}><Tabs destroyOnHidden items={[{key:"date",label:"日期页",children:renderVisitRegistryField(visitDateField())},{key:"other",label:"其他页",children:<span>其他内容</span>}]}/></Form>;}
 render(<Harness/>);fireEvent.click(screen.getByRole("tab",{name:"其他页"}));fireEvent.click(screen.getByRole("tab",{name:"日期页"}));await waitFor(()=>expect(screen.getAllByText(/2026年2月31日/).length).toBeGreaterThan(0));expect(screen.getByText(/请输入有效日期/)).toBeInTheDocument();expect(currentForm!.getFieldsValue(true)).toEqual(before);
});
it("preserves unrecognizable date objects and their raw warning",async()=>{
 const raw={year:{state:"legacy",value:"旧年份"},original:"原始记载"};
 const finish=setup(field({widget:"date",allow_partial_date:true}),{demographics:{score:raw}});
 expect(screen.getByText(`原日期：${JSON.stringify(raw)}`)).toBeInTheDocument();
 expect(screen.getByText(`原值需核对：${JSON.stringify(raw)}`)).toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:/保.*存/}));
 await waitFor(()=>expect(finish).toHaveBeenCalled());expect(finish.mock.calls[0][0].demographics.score).toEqual(raw);
});
