import {expect,it} from "vitest";
import {calculateCrfDerivedValue as calc} from "./fieldCalculations";
it("sums SPPB without defaulting missing scores",()=>{
 expect(calc("sppb_total",{assessments:{sppb:{balance:4,gait:3,chair_stand:2}}})).toBe(9);
 expect(calc("sppb_total",{assessments:{sppb:{balance:0,gait:0,chair_stand:0}}})).toBe(0);
 expect(calc("sppb_total",{assessments:{sppb:{balance:4,gait:3}}})).toBeNull();
});
it("caps corrected MoCA at thirty",()=>{expect(calc("moca_total",{assessments:{moca:{subscores:{visuospatial:5,naming:3,attention:6,language:3,abstraction:2,delayed_recall:5,orientation:6,education_bonus:1}}}})).toBe(30);});
it("sums five satisfaction items",()=>{expect(calc("satisfaction_total",{crf:{satisfaction:{items:{operation:{score:5},clarity:{score:4},reminders:{score:5},burden:{score:4},recommendation:{score:5}}}}})).toBe(23);});
it("takes fastest walk and maximum grip",()=>{
 const values={assessments:{physical:{gait:{first_seconds:8,second_seconds:6},grip:{trial_1_kg:15,trial_2_kg:20,trial_3_kg:18}}}};
 expect(calc("fastest_walk",values)).toBe(6);expect(calc("maximum_grip",values)).toBe(20);
 expect(calc("fastest_walk",{assessments:{physical:{gait:{first_seconds:"8",second_seconds:6}}}})).toBeNull();
});
it("keeps count/time ratios separate and refuses zero denominator",()=>{
 expect(calc("count_ratio",{crf:{adherence:{actual_count:3,planned_count:4}}})).toBe(75);
 expect(calc("time_ratio",{crf:{adherence:{actual_minutes:30,planned_minutes:60}}})).toBe(50);
 expect(calc("count_ratio",{crf:{adherence:{actual_count:0,planned_count:0}}})).toBeNull();
});
it("rejects unknown and illegal calculation operands",()=>{
 expect(calc("sppb_total",{assessments:{sppb:{balance:4,gait:3,chair_stand:2}},crf:{_field_meta:{"visit.form_data.assessments.sppb.gait":{state:"unknown"}}}})).toBeNull();
 expect(calc("sppb_total",{assessments:{sppb:{balance:7,gait:3,chair_stand:2}}})).toBeNull();
});
