import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PatientCrfBaselinePage } from "./PatientCrfBaselinePage";

const { mockGet, mockPatch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPatch: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
  },
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/patients", "/patients/201/crf-baseline"]} initialIndex={1}>
        <Routes>
          <Route path="/patients" element={<div>患者列表上一页</div>} />
          <Route path="/patients/:patientId/crf-baseline" element={<PatientCrfBaselinePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {mockGet.mockReset();mockPatch.mockReset();});
afterEach(() => {cleanup();vi.restoreAllMocks();});

describe("PatientCrfBaselinePage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPatch.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url === "/patients/201/") {
        return Promise.resolve({
          data: {
            name: "项目患者甲",
            gender: "male",
            birth_date: null,
            age: null,
          },
        });
      }
      if (url === "/patients/201/baseline/") {
        return Promise.resolve({
          data: {
            subject_id: "",
            name_initials: "",
            demographics: {},
            surgery_allergy: {},
            comorbidities: {},
            lifestyle: {},
            baseline_medications: {},
          },
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });


  it("uses a generic back button that returns to the previous page", async () => {
    renderPage();

    const backButton = await screen.findByRole("button", { name: "返回" });
    expect(screen.queryByRole("button", { name: "返回详情" })).not.toBeInTheDocument();

    vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(backButton);

    expect(await screen.findByText("患者列表上一页")).toBeInTheDocument();
  });
});

it('prefills only empty values and saves unmounted repeat rows without rewriting legacy text', async () => {
 mockPatch.mockResolvedValue({data:{}});
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.endsWith('/baseline/')?{subject_id:'P201',name_initials:'LISI',demographics:{birth_date:'1960-01-01',age_years:81,gender:'女',address:'老地址原文'},surgery_allergy:{has_surgery:'是',surgery_records:[{_row_id:'old-row',name:'旧手术',hospital_note:'保留医院',_field_meta:{name:{state:'value'}}}]},comorbidities:{},lifestyle:{},baseline_medications:{}}:{name:'张三',gender:'male',birth_date:'1970-01-01',age:66}}));
 renderPage();
 expect(await screen.findByDisplayValue('P201')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('tab',{name:'人口学信息'}));
 expect(await screen.findByDisplayValue('81')).toBeInTheDocument();
 expect(screen.getByDisplayValue('1960-01-01')).toBeInTheDocument();
 expect(screen.getByText('老地址原文')).toBeInTheDocument();
 expect(screen.getByText('旧记录，待核对')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('tab',{name:'手术史与过敏史'}));
 fireEvent.change(await screen.findByLabelText('手术名称'),{target:{value:'修订手术'}});
 fireEvent.click(screen.getByRole('tab',{name:'基本标识'}));
 fireEvent.click(screen.getByRole('button',{name:/保.*存/}));
 await import('@testing-library/react').then(async({waitFor})=>waitFor(()=>expect(mockPatch).toHaveBeenCalledWith('/patients/201/baseline/',{surgery_allergy:{surgery_records:[{_row_id:'old-row',name:'修订手术',hospital_note:'保留医院',_field_meta:{name:{state:'value'}}}]}})));
 expect(screen.queryByText(/#T\d|registry|storage/)).not.toBeInTheDocument();
});

it('does not turn a historical scalar demographics container into a prefilled object',async()=>{
 mockPatch.mockResolvedValue({data:{}});
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.endsWith('/baseline/')?{subject_id:'P201',name_initials:'LISI',demographics:'旧人口原文',surgery_allergy:{},comorbidities:{},lifestyle:{},baseline_medications:{}}:{name:'李四',gender:'male',birth_date:'1960-01-01',age:66}}));
 renderPage();
 fireEvent.change(await screen.findByDisplayValue('P201'),{target:{value:'P202'}});
 fireEvent.click(screen.getByRole('button',{name:/保.*存/}));
 await import('@testing-library/react').then(async({waitFor})=>waitFor(()=>expect(mockPatch).toHaveBeenCalledWith('/patients/201/baseline/',{subject_id:'P202'})));
});

it('keeps ancestor rejection visible, opens its clinical section and clears it only on retry',async()=>{
 const reason='已有历史原文或标量，不能直接替换为结构化数据，请先核对原记录。';
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.endsWith('/baseline/')?{subject_id:'P201',name_initials:'LISI',demographics:{},surgery_allergy:{},comorbidities:{},lifestyle:{},baseline_medications:{}}:{name:'李四',gender:'male'}}));
 mockPatch.mockRejectedValueOnce({response:{data:{demographics:[reason]}}}).mockResolvedValue({data:{}});
 renderPage();fireEvent.change(await screen.findByDisplayValue('P201'),{target:{value:'P202'}});
 fireEvent.click(screen.getByRole('button',{name:/保.*存/}));
 expect(await screen.findByText(reason)).toBeInTheDocument();
 expect(screen.getByRole('tab',{name:'人口学信息'})).toHaveAttribute('aria-selected','true');
 expect(screen.getByText('保存失败，草稿已保留')).toBeInTheDocument();
 expect(screen.queryByText(/demographics|non_field_errors|#T8/)).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('tab',{name:'基本标识'}));
 expect(await screen.findByDisplayValue('P202')).toBeInTheDocument();expect(screen.getByText(reason)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/保.*存/}));
 await screen.findByRole('status');expect(screen.queryByText(reason)).not.toBeInTheDocument();
});


// 跨章节交互及保存后回读在共享 CI 运行器中需要超过默认 5 秒；保留全部断言。
it('retains independent age when changing the same birth date representation and then a part to unknown',async()=>{
 let baseline={subject_id:'AGE',demographics:{birth_date:'1960-01-01',age_years:81},surgery_allergy:{},comorbidities:{},lifestyle:{},baseline_medications:{}};
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.endsWith('/baseline/')?baseline:{name:'年龄回归'}}));
 mockPatch.mockImplementation((_url:string,patch:Record<string,unknown>)=>{baseline={...baseline,...patch,demographics:{...baseline.demographics,...patch.demographics as object}};return Promise.resolve({data:baseline});});
 renderPage();await screen.findByDisplayValue('AGE');
 fireEvent.click(screen.getByRole('tab',{name:'人口学信息'}));
 fireEvent.click(await screen.findByRole('button',{name:'出生日期更多'}));fireEvent.mouseDown(await screen.findByRole('combobox',{name:'出生日期日期精度'}));fireEvent.click(await screen.findByText('年月'));
 expect(screen.getByDisplayValue('81')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/保.*存/}));
 const {waitFor}=await import('@testing-library/react');
 await waitFor(()=>expect(mockPatch).toHaveBeenCalled());
 expect(baseline.demographics.age_years).toBe(81);
 fireEvent.click(screen.getByRole('button',{name:'出生日期更多'}));fireEvent.click(await screen.findByRole('checkbox',{name:'不详'}));
 expect(screen.getByDisplayValue('81')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/保.*存/}));
 await waitFor(()=>expect(mockPatch).toHaveBeenCalledTimes(2));
 expect(baseline.demographics.age_years).toBe(81);
 cleanup();renderPage();await screen.findByDisplayValue('AGE');fireEvent.click(screen.getByRole('tab',{name:'人口学信息'}));
 expect(await screen.findByDisplayValue('81')).toBeInTheDocument();
}, 15_000);
it('has no unsaved reminder after marked answer save and database-order readback',async()=>{
 let baseline:Record<string,unknown>={subject_id:'P201',name_initials:'HC',demographics:{age_years:66,gender:'男',birth_date:'1960-01-01'},surgery_allergy:{},comorbidities:{},lifestyle:{},baseline_medications:{}};
 const ordered=(v:unknown):unknown=>Array.isArray(v)?v.map(ordered):v&&typeof v==='object'?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b)).map(([k,x])=>[k,ordered(x)])):v;
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.endsWith('/baseline/')?baseline:{name:'合成',gender:'male',birth_date:'1960-01-01',age:66}}));
 mockPatch.mockImplementation((_url:string,patch:Record<string,unknown>)=>{baseline=ordered({...baseline,...patch,demographics:{...baseline.demographics as object,...patch.demographics as object}}) as Record<string,unknown>;return Promise.resolve({data:baseline});});
 renderPage();await screen.findByDisplayValue('P201');
 fireEvent.click(screen.getByRole('tab',{name:'人口学信息'}));
 fireEvent.click(screen.getByRole('button',{name:'年龄（周岁）更多'}));
 fireEvent.click(await screen.findByRole('checkbox',{name:'不详',exact:true}));
 fireEvent.click(screen.getByRole('button',{name:'年龄（周岁）更多'}));
 fireEvent.click(screen.getByRole('button',{name:/保.*存/}));
 const {waitFor}=await import('@testing-library/react');
 await waitFor(()=>expect(screen.getByRole('status')).toHaveTextContent('已保存'));
 await waitFor(()=>expect(screen.queryByText('有未保存的改动')).not.toBeInTheDocument());
});
