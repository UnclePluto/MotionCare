import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VisitFormPage } from "./VisitFormPage";

// 完整 CRF 表单的渲染、切换和保存回读在共享 CI 中会超过默认 5 秒。
vi.setConfig({ testTimeout: 15_000 });

const { mockGet, mockPatch, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPatch: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

function renderAt(visitId: number, qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/visits/${visitId}`]}>
        <Routes>
          <Route path="/visits/:visitId" element={<VisitFormPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("VisitFormPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPatch.mockReset();
    mockPatch.mockResolvedValue({ data: {} });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders existing assessments values", async () => {
    mockGet.mockResolvedValue({
      data: {
        id: 11,
        project_patient: 1,
        visit_type: "T0",
        status: "draft",
        visit_date: "2026-05-08",
        form_data: {
          assessments: { sppb: { total: 9 }, moca: { total: 22 } },
          computed_assessments: {},
        },
      },
    });

    renderAt(11);
    fireEvent.click(await screen.findByRole("tab", {name:"身体机能"}));

    expect(
      await screen.findByDisplayValue("9", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", {name:"MoCA评估"}));
    expect(await screen.findByDisplayValue("22")).toBeInTheDocument();
    expect(screen.getAllByText("T0").length).toBeGreaterThan(0);
  }, 10000);

  it("falls back to computed_assessments and shows '系统预填值' hint when assessments missing", async () => {
    mockGet.mockResolvedValue({
      data: {
        id: 12,
        project_patient: 1,
        visit_type: "T0",
        status: "draft",
        visit_date: null,
        form_data: {
          assessments: {},
          computed_assessments: { sppb: { total: 8 } },
        },
      },
    });

    renderAt(12);
    fireEvent.click(await screen.findByRole("tab", {name:"身体机能"}));

    expect(await screen.findByDisplayValue("8")).toBeInTheDocument();
    expect(screen.getByText("系统预填值")).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab',{name:'访视信息'}));
    fireEvent.change(await screen.findByLabelText('评估者姓名'),{target:{value:'研究员'}});
    fireEvent.click(screen.getByRole('button',{name:'暂存'}));
    await waitFor(()=>expect(mockPatch).toHaveBeenCalledWith('/visits/12/',{form_data:{crf:{meta:{assessor_name:'研究员'}}}}));

  });

  it("save button sends only changed sppb.total", async () => {
    mockGet.mockResolvedValue({
      data: {
        id: 13,
        project_patient: 1,
        visit_type: "T0",
        status: "draft",
        visit_date: null,
        form_data: { assessments: {}, computed_assessments: {} },
      },
    });

    const r = renderAt(13);
    fireEvent.click(await screen.findByRole("tab", {name:"身体机能"}));

    const sppbInputs = await screen.findAllByRole("spinbutton", {
      name: /SPPB\s*总分/,
    });
    const sppbInput = sppbInputs[0];
    fireEvent.change(sppbInput, { target: { value: "9" } });
    fireEvent.blur(sppbInput);

    const saveBtn = r.container.querySelector('button[aria-label="暂存"]');
    expect(saveBtn).toBeTruthy();
    fireEvent.click(saveBtn as Element);

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledTimes(1);
    });
    const [url, body] = mockPatch.mock.calls[0];
    expect(url).toBe("/visits/13/");
    expect(body).toEqual({
      form_data: { assessments: { sppb: { total: 9 } } },
    });
  });

  it("complete button asks for confirmation before sending standalone status patch", async () => {
    mockGet.mockResolvedValue({
      data: {
        id: 14,
        project_patient: 1,
        visit_type: "T0",
        status: "draft",
        visit_date: null,
        form_data: { assessments: {}, computed_assessments: {} },
      },
    });

    const r = renderAt(14);

    // Wait for page to load, then click button inside this render container.
    await waitFor(() => {
      expect(
        r.container.querySelector('button[aria-label="完成"]'),
      ).toBeTruthy();
    });
    const completeBtn = r.container.querySelector(
      'button[aria-label="完成"]',
    );
    expect(completeBtn).toHaveClass("ant-btn-primary");
    fireEvent.click(completeBtn as Element);

    expect(await screen.findByText("请确认报告填写无误。若仅希望保存填写进度，请点击取消后选择暂存按钮。")).toBeInTheDocument();
    expect(mockPatch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "确认完成" }));

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith("/visits/14/", { status: "completed" });
    });
  });

  it("save sends nested form_data.crf when CRF extension field changes", async () => {
    mockGet.mockResolvedValue({
      data: {
        id: 20,
        project_patient: 1,
        visit_type: "T1",
        status: "draft",
        visit_date: null,
        form_data: {
          assessments: {},
          computed_assessments: {},
          crf: {},
        },
      },
    });

    const r = renderAt(20);
    fireEvent.click(await screen.findByRole("tab", {name:"干预依从性"}));

    const platform = await screen.findByLabelText("平台编号");
    fireEvent.change(platform, { target: { value: "PID-99" } });

    const saveBtn = r.container.querySelector('button[aria-label="暂存"]');
    expect(saveBtn).toBeTruthy();
    fireEvent.click(saveBtn as Element);

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledTimes(1);
    });
    const [, body] = mockPatch.mock.calls[0] as [string, { form_data: { crf?: { adherence?: { platform_id?: string } } } }];
    expect(body.form_data.crf?.adherence?.platform_id).toBe("PID-99");
  });

  it("renders archived project visits as readonly and blocks mutations", async () => {
    mockGet.mockResolvedValue({
      data: {
        id: 21,
        project_patient: 1,
        project_status: "archived",
        visit_type: "T1",
        status: "draft",
        visit_date: null,
        form_data: {
          assessments: { sppb: { total: 9 } },
          computed_assessments: {},
          crf: { adherence: { platform_id: "PID-99" } },
        },
      },
    });

    const r = renderAt(21);
    fireEvent.click(await screen.findByRole("tab", {name:"身体机能"}));

    expect(await screen.findByText("当前表单只读")).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: /SPPB\s*总分/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("tab", {name:"干预依从性"}));
    expect(await screen.findByLabelText("平台编号")).toBeDisabled();

    const saveBtn = r.container.querySelector('button[aria-label="暂存"]');
    const completeBtn = r.container.querySelector('button[aria-label="完成"]');
    expect(saveBtn).toBeDisabled();
    expect(completeBtn).toBeDisabled();

    fireEvent.click(saveBtn as Element);
    fireEvent.click(completeBtn as Element);
    expect(mockPatch).not.toHaveBeenCalled();
  });

  it("renders completed visits as readonly and blocks mutations", async () => {
    mockGet.mockResolvedValue({
      data: {
        id: 22,
        project_patient: 1,
        project_status: "active",
        visit_type: "T1",
        status: "completed",
        visit_date: null,
        form_data: {
          assessments: { sppb: { total: 9 } },
          computed_assessments: {},
          crf: { adherence: { platform_id: "PID-99" } },
        },
      },
    });

    const r = renderAt(22);
    fireEvent.click(await screen.findByRole("tab", {name:"身体机能"}));

    expect(await screen.findByText("访视已完成，当前为只读查看。")).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: /SPPB\s*总分/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("tab", {name:"干预依从性"}));
    expect(await screen.findByLabelText("平台编号")).toBeDisabled();

    const saveBtn = r.container.querySelector('button[aria-label="暂存"]');
    const completeBtn = r.container.querySelector('button[aria-label="完成"]');
    expect(saveBtn).toBeDisabled();
    expect(completeBtn).toBeDisabled();

    fireEvent.click(saveBtn as Element);
    fireEvent.click(completeBtn as Element);
    expect(mockPatch).not.toHaveBeenCalled();
  });
});

beforeEach(() => { mockGet.mockReset(); mockPatch.mockReset(); mockPost.mockReset(); mockPatch.mockResolvedValue({data: {}}); });
afterEach(() => cleanup());
function visitFixture(id = 30) { return { id, project_patient: 1, project_status: "active", visit_type: "T1", status: "draft", visit_date: null, form_data: { assessments: {}, computed_assessments: {}, crf: {} } }; }

// 恢复、暂存、完成包含多次表单渲染和回读，沿用同类完整流程的 CI 时限。
it('已完成报告点击编辑后保留答案，可重新暂存和完成', async () => {
 let visit = {...visitFixture(60), status:'completed', form_data:{assessments:{sppb:{total:8}},computed_assessments:{},crf:{meta:{assessor_name:'原评估者'}}}};
 mockGet.mockImplementation(async (url:string)=>({data:url.startsWith('/visits/')?visit:{patient:201}}));
 mockPost.mockImplementation(async()=>{visit={...visit,status:'draft'};return {data:visit};});
 mockPatch.mockImplementation(async(_url:string,payload:Record<string,unknown>)=>{visit={...visit,...payload} as typeof visit;return {data:visit};});
 renderAt(60);
 const edit = await screen.findByRole('button',{name:'编辑'});
 expect(edit).toBeEnabled();
 expect(screen.getByRole('button',{name:'完成'})).toBeDisabled();
 fireEvent.click(edit);
 await waitFor(()=>expect(screen.getByRole('button',{name:'暂存'})).toBeEnabled());
 expect(mockPost).toHaveBeenCalledWith('/visits/60/reopen/',{});
 fireEvent.click(screen.getByRole('tab',{name:'访视信息'}));
 const input=await screen.findByLabelText('评估者姓名');
 expect(input).toHaveValue('原评估者');
 fireEvent.change(input,{target:{value:'复核者'}});
 fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 await waitFor(()=>expect(mockPatch).toHaveBeenCalledWith('/visits/60/',{form_data:{crf:{meta:{assessor_name:'复核者'}}}}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'完成'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'完成'}));
 fireEvent.click(await screen.findByRole('button',{name:'确认完成'}));
 await waitFor(()=>expect(mockPatch).toHaveBeenLastCalledWith('/visits/60/',{status:'completed'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'编辑'})).toBeEnabled());
}, 15_000);

it('取消完成后保留输入，选择暂存只保存进度', async()=>{
 const visit=visitFixture(61);
 mockGet.mockImplementation(async(url:string)=>({data:url.startsWith('/visits/')?visit:{patient:201}}));
 renderAt(61);
 fireEvent.click(await screen.findByRole('tab',{name:'访视信息'}));
 fireEvent.change(await screen.findByLabelText('评估者姓名'),{target:{value:'进度'}});
 fireEvent.click(screen.getByRole('button',{name:'完成'}));
 expect(await screen.findByText('请确认报告填写无误。若仅希望保存填写进度，请点击取消后选择暂存按钮。')).toBeInTheDocument();
 expect(mockPatch).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:/取\s*消/}));
 expect(screen.getByLabelText('评估者姓名')).toHaveValue('进度');
 fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 await waitFor(()=>expect(mockPatch).toHaveBeenCalledWith('/visits/61/',{form_data:{crf:{meta:{assessor_name:'进度'}}}}));
});

it('恢复编辑失败仍保持只读，允许重试',async()=>{
 mockGet.mockImplementation(async(url:string)=>({data:url.startsWith('/visits/')?{...visitFixture(62),status:'completed'}:{patient:201}}));
 mockPost.mockRejectedValue(new Error('网络失败'));
 renderAt(62);
 fireEvent.click(await screen.findByRole('button',{name:'编辑'}));
 await waitFor(()=>expect(mockPost).toHaveBeenCalledTimes(1));
 await waitFor(()=>expect(screen.getByRole('button',{name:'编辑'})).toBeEnabled());
 expect(screen.getByRole('button',{name:'暂存'})).toBeDisabled();
 expect(screen.getByRole('button',{name:'完成'})).toBeDisabled();
});

it('恢复编辑等待回读期间保持按钮禁用，回读完成后可操作',async()=>{
 let visit={...visitFixture(65),status:'completed'};
 let visitReads=0;
 let finishRead!:()=>void;
 const readback=new Promise<{data:typeof visit}>(resolve=>{finishRead=()=>resolve({data:visit});});
 mockGet.mockImplementation(async(url:string)=>{
  if(!url.startsWith('/visits/')) return {data:{patient:201}};
  visitReads+=1;
  return visitReads===1?{data:visit}:readback;
 });
 mockPost.mockImplementation(async()=>{visit={...visit,status:'draft'};return {data:visit};});
 renderAt(65);
 fireEvent.click(await screen.findByRole('button',{name:'编辑'}));
 await waitFor(()=>expect(visitReads).toBe(2));
 expect(screen.getByRole('button',{name:'暂存'})).toBeDisabled();
 expect(screen.getByRole('button',{name:'完成'})).toBeDisabled();
 finishRead();
 await waitFor(()=>expect(screen.getByRole('button',{name:'暂存'})).toBeEnabled());
 expect(screen.getByRole('button',{name:'完成'})).toBeEnabled();
});

it('已归档项目的完成报告不能恢复编辑',async()=>{
 mockGet.mockImplementation(async(url:string)=>({data:url.startsWith('/visits/')?{...visitFixture(63),status:'completed',project_status:'archived'}:{patient:201}}));
 renderAt(63);
 expect(await screen.findByRole('button',{name:'编辑'})).toBeDisabled();
 expect(mockPost).not.toHaveBeenCalled();
});

it('恢复编辑采用服务端最新答案，不把旧缓存重新提交',async()=>{
 let visit={...visitFixture(64),status:'completed',form_data:{assessments:{},computed_assessments:{},crf:{meta:{assessor_name:'旧缓存'}}}};
 mockGet.mockImplementation(async(url:string)=>({data:url.startsWith('/visits/')?visit:{patient:201}}));
 mockPost.mockImplementation(async()=>{visit={...visit,status:'draft',form_data:{...visit.form_data,crf:{meta:{assessor_name:'服务端最新'}}}};return {data:visit};});
 renderAt(64);
 fireEvent.click(await screen.findByRole('tab',{name:'访视信息'}));
 expect(await screen.findByLabelText('评估者姓名')).toHaveValue('旧缓存');
 fireEvent.click(screen.getByRole('button',{name:'编辑'}));
 await waitFor(()=>expect(screen.getByLabelText('评估者姓名')).toHaveValue('服务端最新'));
 fireEvent.click(screen.getByRole('button',{name:'完成'}));
 fireEvent.click(await screen.findByRole('button',{name:'确认完成'}));
 await waitFor(()=>expect(mockPatch).toHaveBeenCalledWith('/visits/64/',{status:'completed'}));
});
// 跨章节交互及保存后回读在共享 CI 运行器中需要超过默认 5 秒；保留全部断言。
it("test_complete_submits_unsaved_measurement_feedback_and_visit_date", async () => {
  mockGet.mockImplementation((url: string) => Promise.resolve({data: url.startsWith("/visits/") ? visitFixture() : {patient: 201, subject_id: "P-201"}}));
  renderAt(30);
  fireEvent.click(await screen.findByRole("tab", {name:"身体机能"}));
  fireEvent.change(await screen.findByRole("spinbutton", { name: /SPPB\s*总分/ }), {target: {value: "9"}});
  fireEvent.click(screen.getByRole("tab", {name:"平台满意度"}));
  fireEvent.change(await screen.findByLabelText("操作简单、易学习备注"), {target: {value: "字号清晰"}});
  fireEvent.click(screen.getByRole("tab", {name:"访视信息"}));
  const date = await screen.findByRole("textbox", {name: "访视日期"});
  fireEvent.change(date, {target: {value: "2026-10-08"}});
  fireEvent.keyDown(date, {key: "Enter", code: "Enter"}); fireEvent.blur(date);
  fireEvent.click(screen.getByRole("button", {name: "完成"}));
  expect(await screen.findByText(/^仍有 \d+ 项未处理/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "确认完成"}));
  await waitFor(() => expect(mockPatch).toHaveBeenCalledTimes(1));
  const payload = mockPatch.mock.calls[0][1];
  expect(payload).toMatchObject({visit_date: "2026-10-08", status: "completed"});
  expect(payload).toEqual({visit_date: "2026-10-08", status: "completed", form_data: {assessments: {sppb: {total: 9}}, crf: {satisfaction: {items: {operation: {remark: "字号清晰"}}}}}});
}, 15_000);
it("test_refetch_does_not_overwrite_dirty_values", async () => {
  let finish!: (value: unknown) => void; let calls = 0;
  mockGet.mockImplementation((url: string) => {
    if (!url.startsWith("/visits/")) return Promise.resolve({data: {patient: 201, subject_id: "P-201"}});
    return ++calls === 1 ? Promise.resolve({data: visitFixture(31)}) : new Promise(resolve => {finish = resolve;});
  });
  const qc = new QueryClient({defaultOptions: {queries: {retry: false}}}); renderAt(31, qc);
  fireEvent.click(await screen.findByRole("tab", {name:"身体机能"}));
  const score = await screen.findByRole("spinbutton", {name: /SPPB\s*总分/});
  const refetch = qc.invalidateQueries({queryKey: ["visit", 31]});
  await waitFor(() => expect(finish).toBeTypeOf("function"));
  fireEvent.change(score, {target: {value: "8"}});
  await act(async () => {finish({data: {...visitFixture(31), form_data: {assessments: {sppb: {total: 3}}, computed_assessments: {grip_strength_kg:17}, crf: {}}}}); await refetch;});
  await screen.findByText("系统预填值"); // Confirms the refetched QueryClient result has actually rendered.
  expect(screen.getByRole("spinbutton", {name:/SPPB\s*总分/})).toHaveValue("8");
  fireEvent.click(screen.getByRole("button", {name: "暂存"}));
  await waitFor(() => expect(mockPatch).toHaveBeenCalledWith("/visits/31/", {form_data: {assessments: {sppb: {total: 8}}}}));
}, 15_000);

it.each(['T0','T1'])('allows early withdrawal on %s and preserves it after changing section',async visitType=>{
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?{...visitFixture(32),visit_type:visitType}:{patient:201,subject_id:'P201'}}));
 renderAt(32);
 fireEvent.click(await screen.findByRole('tab',{name:'完成与退出'}));
 fireEvent.click(await screen.findByRole('radio',{name:'提前退出'}));
 fireEvent.change(await screen.findByLabelText('安全随访说明'),{target:{value:'已电话随访'}});
 fireEvent.click(screen.getByRole('tab',{name:'访视信息'}));
 fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 await waitFor(()=>expect(mockPatch).toHaveBeenCalledWith('/visits/32/',{form_data:{crf:{completion_record:{status:'提前退出',safety_note:'已电话随访'}}}}));
});

it('late save response keeps subsequent input dirty and blocks duplicate submits',async()=>{
 let resolvePatch!:(value:unknown)=>void;
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?visitFixture(33):{patient:201,subject_id:'P201'}}));
 mockPatch.mockImplementationOnce(()=>new Promise(resolve=>{resolvePatch=resolve;}));
 renderAt(33);fireEvent.click(await screen.findByRole('tab',{name:'平台满意度'}));
 const input=await screen.findByLabelText('操作简单、易学习备注');
 fireEvent.change(input,{target:{value:'第一次'}});fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 await waitFor(()=>expect(mockPatch).toHaveBeenCalledTimes(1));
 fireEvent.click(screen.getByRole('button',{name:'完成'}));expect(screen.queryByRole('button',{name:'确认完成'})).not.toBeInTheDocument();
 fireEvent.change(input,{target:{value:'第二次'}});
  await act(async()=>{resolvePatch({data: {...visitFixture(33), form_data: {assessments:{}, computed_assessments:{}, crf:{satisfaction:{items:{operation:{remark:"第一次"}}}}}}});});
 await screen.findByRole('status');expect(screen.getByLabelText('操作简单、易学习备注')).toHaveValue('第二次');
 expect(screen.getByText('有未保存的改动')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 await waitFor(()=>expect(mockPatch).toHaveBeenCalledTimes(2));
 expect(mockPatch.mock.calls[1][1]).toEqual({form_data:{crf:{satisfaction:{items:{operation:{remark:'第二次'}}}}}});
});

it('shows T0 legacy data separately and does not submit untouched invalid history',async()=>{
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?{...visitFixture(34),visit_type:'T0',form_data:{assessments:{sppb:{total:'bad old value'}},crf:{adherence:{platform_id:'旧平台号'},completion:'旧退出原文'},computed_assessments:{}}}:{patient:201,subject_id:'P201'}}));
 renderAt(34);
 expect(await screen.findByText('旧退出原文')).toBeInTheDocument();expect(screen.getByText('旧平台号')).toBeInTheDocument();
 expect(screen.queryByLabelText('平台编号')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('tab',{name:'访视信息'}));
 fireEvent.change(await screen.findByLabelText('评估者姓名'),{target:{value:'研究员甲'}});
 fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 await waitFor(()=>expect(mockPatch).toHaveBeenCalledWith('/visits/34/',{form_data:{crf:{meta:{assessor_name:'研究员甲'}}}}));
});
it('submits a year precision answer while another section is active',async()=>{
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?{...visitFixture(35),visit_date:'2026-10-08'}:{patient:201,subject_id:'P201'}}));
 renderAt(35);
 const date=await screen.findByRole('textbox',{name:'访视日期'});
 fireEvent.click(screen.getByRole('button',{name:'访视日期更多'}));fireEvent.mouseDown(await screen.findByRole('combobox',{name:'访视日期日期精度'}));fireEvent.click(await screen.findByText('仅年'));expect(date).toHaveValue('2026');
 fireEvent.click(screen.getByRole('tab',{name:'平台满意度'}));
 fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 await waitFor(()=>expect(mockPatch).toHaveBeenCalledWith('/visits/35/',{visit_date:'2026',form_data:{crf:{meta:{assessed_on:'2026-10-08'}}}}));
});
it('server field errors open the relevant section and retain the actual input',async()=>{
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?visitFixture(36):{patient:201,subject_id:'P201'}}));
 mockPatch.mockRejectedValue({response:{data:{'crf.satisfaction.items.operation.remark':['备注不符合要求']}}});
 renderAt(36);fireEvent.click(await screen.findByRole('tab',{name:'平台满意度'}));
 fireEvent.change(await screen.findByLabelText('操作简单、易学习备注'),{target:{value:'保留草稿'}});
 fireEvent.click(screen.getByRole('tab',{name:'访视信息'}));fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 const input = await screen.findByLabelText('操作简单、易学习备注');
 await waitFor(()=>expect(input.closest('.ant-form-item')).toHaveTextContent('备注不符合要求'));
 expect(input).toHaveValue('保留草稿');
});


it('late failed save does not attach previous-record errors to a new record',async()=>{
 let rejectPatch!:(value:unknown)=>void;
 vi.spyOn(window,'confirm').mockReturnValue(true);
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?visitFixture(Number(url.split('/')[2])):{patient:201,subject_id:'P201'}}));
 mockPatch.mockImplementationOnce(()=>new Promise((_resolve,reject)=>{rejectPatch=reject;}));
 const router=createMemoryRouter([{path:'/visits/:visitId',element:<VisitFormPage/>}],{initialEntries:['/visits/41']});
 render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><RouterProvider router={router}/></QueryClientProvider>);
 fireEvent.change(await screen.findByLabelText('评估者姓名'),{target:{value:'原记录输入'}});
 fireEvent.click(screen.getByRole('button',{name:'暂存'}));await waitFor(()=>expect(rejectPatch).toBeTypeOf('function'));
 await act(async()=>{await router.navigate('/visits/42');});
 const input=await screen.findByLabelText('评估者姓名');fireEvent.change(input,{target:{value:'新记录输入'}});
 await act(async()=>{rejectPatch({response:{data:{'crf.meta.assessor_name':['旧请求失败']}}});});
 expect(screen.getByLabelText('评估者姓名')).toHaveValue('新记录输入');expect(screen.queryByText('旧请求失败')).not.toBeInTheDocument();
 vi.restoreAllMocks();
});
it('maps a server metadata container error to its concrete status input',async()=>{
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?visitFixture(43):{patient:201,subject_id:'P201'}}));
 mockPatch.mockRejectedValue({response:{data:{'crf._field_meta.visit.form_data.crf.meta.assessor_name':['字段状态无效']}}});
 renderAt(43);fireEvent.change(await screen.findByLabelText('评估者姓名'),{target:{value:'研究员'}});
 fireEvent.click(screen.getByRole('tab',{name:'平台满意度'}));fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 const status=await screen.findByRole('textbox',{name:'评估者姓名'});
 await waitFor(()=>expect(status.closest('.ant-form-item')).toHaveTextContent('字段状态无效'));
});
it.each(['complete','change','clear'])('computed display baseline preserves manual semantics on %s',async action=>{
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?{...visitFixture(44),form_data:{assessments:{grip_strength_kg:0},computed_assessments:{sppb:{total:8},grip_strength_kg:30,extra_result:99},crf:{}}}:{patient:201,subject_id:'P201'}}));
 renderAt(44);
 if(action!=='complete'){
  fireEvent.click(await screen.findByRole('tab',{name:'身体机能'}));
  const score=await screen.findByRole('spinbutton',{name:/SPPB\s*总分/});
  expect(score).toHaveValue('8');expect(screen.getByRole('spinbutton',{name:'握力最大值'})).toHaveValue('0');
  fireEvent.change(score,{target:{value:action==='clear'?'':'9'}});fireEvent.blur(score);
  fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 }else{
  fireEvent.click(await screen.findByRole('button',{name:'完成'}));fireEvent.click(await screen.findByRole('button',{name:'确认完成'}));
 }
 await waitFor(()=>expect(mockPatch).toHaveBeenCalledTimes(1));
 expect(mockPatch.mock.calls[0][1]).toEqual(action==='complete'?{status:'completed'}:{form_data:{assessments:{sppb:{total:action==='clear'?null:9}}}});
});

it.each(['detail','non_field_errors'])('keeps a non-field %s rejection visible without assigning it to an input',async key=>{
 const reason='已完成访视只读，不能继续编辑。';
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?visitFixture(45):{patient:201,subject_id:'P201'}}));
 mockPatch.mockRejectedValue({response:{data:{[key]:key==='detail'?reason:[reason]}}});
 renderAt(45);fireEvent.change(await screen.findByLabelText('评估者姓名'),{target:{value:'仍需保留'}});
 fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 expect(await screen.findByText(reason)).toBeInTheDocument();
 expect(screen.getByText('保存失败，草稿已保留')).toBeInTheDocument();
 expect(screen.getByLabelText('评估者姓名')).toHaveValue('仍需保留');
 expect(screen.getByLabelText('评估者姓名').closest('.ant-form-item')).not.toHaveTextContent(reason);
 expect(screen.queryByText(/detail|non_field_errors/)).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('tab',{name:'平台满意度'}));expect(screen.getByText(reason)).toBeInTheDocument();
});
it.each(['crf.medication_change.entries','crf.medication_change.entries.0'])('shows a repeat container error at the clinical section for %s',async path=>{
 const reason=path.endsWith('.0')?'明细行必须是对象':'已有历史原文或标量，不能直接替换为结构化数据，请先核对原记录。';
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?visitFixture(46):{patient:201,subject_id:'P201'}}));
 mockPatch.mockRejectedValue({response:{data:{[path]:[reason]}}});
 renderAt(46);fireEvent.change(await screen.findByLabelText('评估者姓名'),{target:{value:'保留研究者'}});
 fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 expect(await screen.findByText(reason)).toBeInTheDocument();
 expect(screen.getByRole('tab',{name:'合并用药变化'})).toHaveAttribute('aria-selected','true');
 expect(screen.getByText('保存失败，草稿已保留')).toBeInTheDocument();
 expect(screen.queryByText(/crf\.medication_change|entries\.0/)).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('tab',{name:'访视信息'}));expect(await screen.findByLabelText('评估者姓名')).toHaveValue('保留研究者');
});
it('keeps a plain Chinese fallback for an unstructured network failure',async()=>{
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?visitFixture(47):{patient:201,subject_id:'P201'}}));
 mockPatch.mockRejectedValue({response:{data:'<html>Bad Gateway</html>'}});
 renderAt(47);fireEvent.change(await screen.findByLabelText('评估者姓名'),{target:{value:'网络失败草稿'}});
 fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 expect(await screen.findByText('暂时无法保存，请稍后重试。')).toBeInTheDocument();
 expect(screen.getByLabelText('评估者姓名')).toHaveValue('网络失败草稿');
 expect(screen.queryByText(/Bad Gateway|<html>/)).not.toBeInTheDocument();
});


it.each(['save','complete'])('explicitly adopts the same computed total, survives a hidden section/refetch and persists on %s',async action=>{
 let saved={...visitFixture(46),form_data:{assessments:{sppb:{balance:4,gait:3,chair_stand:2}},computed_assessments:{sppb:{total:9}},crf:{}}};
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?saved:{patient:201,subject_id:'P201'}}));
 mockPatch.mockImplementation((_url:string,payload:{status?:'completed';form_data:{assessments:{sppb:{total:number}}}})=>{saved={...saved,status:payload.status??saved.status,form_data:{...saved.form_data,assessments:{sppb:{...saved.form_data.assessments.sppb,...payload.form_data.assessments.sppb}}}};return Promise.resolve({data:saved});});
 const qc=new QueryClient({defaultOptions:{queries:{retry:false}}});
 renderAt(46,qc);await screen.findByDisplayValue('P201');fireEvent.click(await screen.findByRole('tab',{name:'身体机能'}));
 expect(await screen.findByRole('spinbutton',{name:/SPPB\s*总分/})).toHaveValue('9');
 const before=Number(screen.getAllByText(/正常已填/)[0].textContent!.match(/正常已填 (\d+)/)![1]);
 const adopt=screen.getAllByRole('button',{name:'使用计算结果'}).find(button=>!button.hasAttribute('disabled'))!;
 fireEvent.click(adopt);
 await waitFor(()=>expect(screen.getAllByText(/正常已填/)[0]).toHaveTextContent(`正常已填 ${before+1}`));
 fireEvent.click(screen.getByRole('tab',{name:'平台满意度'}));
 await act(async()=>{await qc.invalidateQueries({queryKey:['visit',46]});});
 expect(screen.getByText('有未保存的改动')).toBeInTheDocument();
 if(action==='complete'){fireEvent.click(screen.getByRole('button',{name:'完成'}));fireEvent.click(await screen.findByRole('button',{name:'确认完成'}));}
 else fireEvent.click(screen.getByRole('button',{name:'暂存'}));
 await waitFor(()=>expect(mockPatch).toHaveBeenCalledTimes(1));
 expect(mockPatch.mock.calls[0][1]).toEqual({...action==='complete'?{status:'completed'}:{},form_data:{assessments:{sppb:{total:9}}}});
 await waitFor(()=>expect(screen.queryByText('系统预填值')).not.toBeInTheDocument());
 cleanup();renderAt(46);fireEvent.click(await screen.findByRole('tab',{name:'身体机能'}));
 expect(await screen.findByRole('spinbutton',{name:/SPPB\s*总分/})).toHaveValue('9');
 expect(screen.queryByText('系统预填值')).not.toBeInTheDocument();
}, 15_000);

it('lists all invalid historical array scores before saving the current candidate as completed',async()=>{
 const metadata=Object.fromEntries(['balance','gait','chair_stand','total'].map(key=>[`visit.form_data.assessments.sppb.${key}`,{state:'unknown',reason:'历史父容器待核对'}]));
 let saved={...visitFixture(48),form_data:{assessments:{sppb:[]},computed_assessments:{},crf:{_field_meta:metadata,meta:{assessor_name:''}}}};
 mockGet.mockImplementation((url:string)=>Promise.resolve({data:url.startsWith('/visits/')?saved:{patient:201,subject_id:'P201'}}));
 mockPatch.mockImplementation(()=>{saved={...saved,status:'completed',form_data:{...saved.form_data,crf:{...saved.form_data.crf,meta:{assessor_name:'保留历史的评估者'}}}};return Promise.resolve({data:saved});});
 renderAt(48);await screen.findByDisplayValue('P201');
 fireEvent.change(screen.getByLabelText('评估者姓名'),{target:{value:'保留历史的评估者'}});
 fireEvent.click(screen.getByRole('button',{name:'完成'}));
 for(const label of ['SPPB平衡得分','SPPB步速得分','SPPB坐立得分','SPPB总分'])expect(await screen.findByRole('button',{name:label,exact:true})).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'确认完成'}));
 await waitFor(()=>expect(mockPatch).toHaveBeenCalledTimes(1));
 expect(mockPatch.mock.calls[0][1]).toEqual({form_data:{crf:{meta:{assessor_name:'保留历史的评估者'}}},status:'completed'});
 expect(await screen.findByText('访视已完成，当前为只读查看。')).toBeInTheDocument();
 expect(saved.form_data.assessments.sppb).toEqual([]);
 expect(saved.form_data.crf._field_meta).toEqual(metadata);
}, 15_000);
