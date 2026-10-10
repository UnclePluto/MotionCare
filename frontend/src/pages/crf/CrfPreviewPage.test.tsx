import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CrfPreviewPage } from "./CrfPreviewPage";
import { CrfReadOnlySections, type CrfReadOnlyField } from "../../crf/components/CrfReadOnlySections";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}));

describe("CrfPreviewPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url === "/studies/project-patients/") {
        return Promise.resolve({
          data: [{ id: 1, patient_name: "张三", patient_phone: "13800000001" }, { id: 2, patient_name: "李四", patient_phone: "13800000002" }],
        });
      }
      if (url === "/crf/project-patients/1/preview/" || url === "/crf/project-patients/2/preview/") {
        return Promise.resolve({
          data: {
            project_patient_id: 1,
            patient: { name: "张三", gender: "male", age: 30, phone: "13800000001" },
            patient_baseline: {
              subject_id: "S-0001",
              name_initials: "ZS",
              demographics: { education_years: 9 },
            },
            project: { name: "研究项目 A", crf_template_version: "v1" },
            group: { name: "" },
            visits: {},
            missing_fields: [],
            counts: { normal: 2, unknown: 1, not_applicable: 0, unresolved: 0 },
            issues: [{ code: 'conflicting_records', message: 'T0 与 T2 完成记录冲突，请复核', scope: 'T2', storage: 'completion_record' }],
            sections: [{ key: 'T0.legacy', title: '补充记录', scope: 'T0', table_ref: null, supplemental: true, fields: [{ field_id: 'old', storage: 'old', label: '补充记录', widget: 'raw', applicable: false, required: false, state: 'unresolved', value: { year: '旧年份', note: '必须保留的旧说明' }, raw_value: { year: '旧年份', note: '必须保留的旧说明' }, reason: '', issues: [], rows: [] }] }, { key: 'study.flow', title: '研究流程', scope: 'study', table_ref: '#T2', supplemental: false, fields: [], static_table: { headers: ['信息/评估项目', '筛选/入组 T0'], rows: [['知情同意书', '★']] } }, {
              key: 'T1.events', title: '不良事件', scope: 'T1', table_ref: '#T21', supplemental: false,
              fields: [{
                field_id: 'events', storage: 'events', label: '事件明细', widget: 'table_repeat',
                applicable: true, required: true, state: 'normal', value: [{ event_name: '头痛' }], raw_value: [{ event_name: '头痛' }], reason: '', issues: [],
                rows: [{ key: 'row-1', index: 0, fields: [{ field_id: 'name', storage: 'event_name', label: '事件名称', widget: 'text', applicable: true, required: true, state: 'normal', value: '头痛', raw_value: '头痛', reason: '', issues: [], rows: [] }] }],
              }, {
                field_id: 'feedback', storage: 'feedback', label: '受试者反馈', widget: 'text',
                applicable: true, required: false, state: 'normal', value: '提醒太频繁', raw_value: '提醒太频繁', reason: '', issues: [], rows: [],
              }, {
                field_id: 'date', storage: 'date', label: '发生日期', widget: 'date',
                applicable: true, required: true, state: 'unknown',
                value: { year: { state: 'value', value: 2026 }, month: { state: 'unknown', value: null }, day: { state: 'value', value: 8 } },
                raw_value: null, reason: '不记得月份', issues: [], rows: [],
              }],
            }],
          },
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    mockPost.mockResolvedValue({ data: { docx_file: null } });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders subject_id and education_years in summary", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={["/?projectPatientId=1"]}>
          <CrfPreviewPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/studies/project-patients/");
    });

    const subjectRow = (await screen.findByText("受试者编号")).closest("tr");
    expect(subjectRow).toBeTruthy();
    expect(subjectRow!).toHaveTextContent("S-0001");

    const eduRow = (await screen.findByText("教育年限")).closest("tr");
    expect(eduRow).toBeTruthy();
    expect(eduRow!).toHaveTextContent("9");
  });

  it("shows all details, feedback, mixed dates and explicit unknown counts", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={["/?projectPatientId=1"]}><CrfPreviewPage /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("columnheader", { name: "信息/评估项目" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "知情同意书" })).toBeInTheDocument();
    expect(await screen.findByText("头痛")).toBeInTheDocument();
    expect(screen.getByText("提醒太频繁")).toBeInTheDocument();
    expect(screen.getByText(/必须保留的旧说明/)).toBeInTheDocument();
    expect(screen.getByText("2026年 / 不详月 / 8日")).toBeInTheDocument();
    expect(screen.getByText("不记得月份")).toBeInTheDocument();
    expect(screen.getByText(/不详 1 项/)).toBeInTheDocument();
    expect(screen.getByText(/T0 与 T2 完成记录冲突/)).toBeInTheDocument();
    expect(screen.queryByText("暂无缺失字段")).not.toBeInTheDocument();
  });

  it("shows row metadata supplements without raw technical paths and leaves empty optional notes unflagged", () => {
    const base = {
      field_id: "name", storage: "patient_baseline.surgery_allergy.surgery_records.0.name",
      label: "手术名称", widget: "text", applicable: true, required: true, counted: true,
      state: "normal" as const, value: "阑尾手术", raw_value: "阑尾手术", reason: "",
      rows: [], issues: [],
    };
    const optional: CrfReadOnlyField = {
      ...base, field_id: "note", label: "普通备注", required: false,
      counted: false, state: "unresolved", value: null, raw_value: null,
    };
    render(<CrfReadOnlySections sections={[
      { key: "baseline.surgery", scope: "patient_baseline", title: "手术史", table_ref: "#T9", supplemental: false,
        fields: [{ ...base, field_id: "rows", label: "手术记录", widget: "table_repeat", rows: [{ key: "0:r1", index: 0,
          raw_value: { name: "阑尾手术", _field_meta: { old_reason: { state: "unknown", reason: "旧反馈须保留" } } },
          fields: [base, optional, { ...optional, field_id: "required", label: "必需日期", required: true, counted: true }],
        }] }],
      },
      { key: "baseline.supplemental", scope: "patient_baseline", title: "补充记录", table_ref: "#T9", supplemental: true,
        fields: [{ ...base, field_id: "legacy", storage: "patient_baseline.surgery_allergy.surgery_records.0._field_meta.old_reason.reason",
          label: "手术记录 第1行 · 历史补充记录1", widget: "raw", applicable: false, required: false, counted: false,
          state: "unresolved", value: "旧反馈须保留", raw_value: "旧反馈须保留" }],
      },
    ]} />);
    expect(screen.getByText("旧反馈须保留")).toBeInTheDocument();
    expect(screen.getAllByText("阑尾手术")).toHaveLength(1);
    expect(screen.getByText("普通备注").closest("tr")).toHaveTextContent("未填写");
    expect(screen.getByText("普通备注").closest("tr")).not.toHaveTextContent("待处理");
    expect(screen.getByText("必需日期").closest("tr")).toHaveTextContent("待处理");
    expect(document.body).not.toHaveTextContent("_field_meta");
    expect(document.body).not.toHaveTextContent("old_reason");
    expect(document.body).not.toHaveTextContent("patient_baseline.");
  });

  it("allows DOCX export for selected project patient", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={["/?projectPatientId=1"]}>
          <CrfPreviewPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const exportButton = await screen.findByRole("button", { name: "导出 DOCX / PDF" });
    fireEvent.click(exportButton);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/crf/project-patients/1/export/", {});
    });
  });

  it("keeps wearable health outside the CRF preview flow", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={["/?projectPatientId=1"]}>
          <CrfPreviewPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("张三")).toBeInTheDocument();
    expect(
      mockGet.mock.calls.some(
        ([url]) => typeof url === "string" && url.includes("/wearables/"),
      ),
    ).toBe(false);
    expect(screen.queryByText("穿戴健康")).not.toBeInTheDocument();
    expect(screen.queryByText("心率")).not.toBeInTheDocument();
    expect(screen.queryByText("血压")).not.toBeInTheDocument();
    expect(screen.queryByText("血氧")).not.toBeInTheDocument();
  });


  function renderExportPage() {
    return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={["/?projectPatientId=1"]}><CrfPreviewPage /></MemoryRouter>
    </QueryClientProvider>);
  }

  async function choosePatient(label: string) {
    fireEvent.mouseDown(screen.getByRole("combobox"));
    const option = (await screen.findAllByText(label)).find((element) => element.closest(".ant-select-item-option"));
    expect(option).toBeTruthy();
    fireEvent.click(option!);
    await waitFor(() => expect(screen.getByRole("combobox").closest(".ant-select")?.querySelector(".ant-select-selection-item")).toHaveAttribute("title", label));
  }

  it("renders both successful download URLs and removes obsolete technical copy", async () => {
    mockPost.mockResolvedValue({ data: { project_patient: 1, docx_file: "/media/one.docx", pdf_file: "/media/one.pdf" } });
    renderExportPage();
    fireEvent.click(await screen.findByRole("button", { name: "导出 DOCX / PDF" }));
    expect(await screen.findByRole("link", { name: "下载 DOCX" })).toHaveAttribute("href", "/media/one.docx");
    expect(screen.getByRole("link", { name: "下载 PDF" })).toHaveAttribute("href", "/media/one.pdf");
    expect(document.body).not.toHaveTextContent("后续接入");
    expect(document.body).not.toHaveTextContent("media 目录");
  });

  it("shows a readable failure and never offers an incomplete successful download", async () => {
    mockPost.mockResolvedValue({ data: { project_patient: 1, docx_file: "/media/partial.docx", pdf_file: null } });
    renderExportPage();
    fireEvent.click(await screen.findByRole("button", { name: "导出 DOCX / PDF" }));
    expect((await screen.findByText("导出失败，请稍后重试或联系管理员。")).closest('[role="alert"]')).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "下载 DOCX" })).not.toBeInTheDocument();
    expect(screen.queryByText("导出任务已完成")).not.toBeInTheDocument();
  });

  it("clears downloads on patient switch and ignores a late response even after switching back", async () => {
    let resolveLate!: (response: unknown) => void;
    mockPost.mockResolvedValueOnce({ data: { project_patient: 1, docx_file: "/media/first.docx", pdf_file: "/media/first.pdf" } });
    renderExportPage();
    fireEvent.click(await screen.findByRole("button", { name: "导出 DOCX / PDF" }));
    await screen.findByRole("link", { name: "下载 PDF" });
    await choosePatient("李四（13800000002）");
    expect(screen.queryByRole("link", { name: "下载 PDF" })).not.toBeInTheDocument();
    mockPost.mockImplementationOnce(() => new Promise((resolve) => { resolveLate = resolve; }));
    fireEvent.click(await screen.findByRole("button", { name: "导出 DOCX / PDF" }));
    await waitFor(() => expect(resolveLate).toBeDefined());
    await choosePatient("张三（13800000001）");
    await choosePatient("李四（13800000002）");
    await act(async () => { resolveLate({ data: { project_patient: 2, docx_file: "/media/late.docx", pdf_file: "/media/late.pdf" } }); });
    await waitFor(() => expect(screen.getByRole("button", { name: /导出 DOCX \/ PDF/ })).not.toHaveClass("ant-btn-loading"));
    expect(screen.queryByRole("link", { name: "下载 DOCX" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "下载 PDF" })).not.toBeInTheDocument();
  });

  it.each(["network", "wrong_patient"])("keeps download links hidden on %s failure", async (failure) => {
    if (failure === "network") mockPost.mockRejectedValue(new Error("offline"));
    else mockPost.mockResolvedValue({ data: { project_patient: 2, docx_file: "/media/wrong.docx", pdf_file: "/media/wrong.pdf" } });
    renderExportPage();
    fireEvent.click(await screen.findByRole("button", { name: "导出 DOCX / PDF" }));
    expect(await screen.findByText("导出失败，请稍后重试或联系管理员。")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "下载 PDF" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "下载 DOCX" })).not.toBeInTheDocument();
  });

  it("ignores a late export failure after changing patient", async () => {
    let rejectLate!: (error: Error) => void;
    mockPost.mockImplementation(() => new Promise((_resolve, reject) => { rejectLate = reject; }));
    renderExportPage();
    fireEvent.click(await screen.findByRole("button", { name: "导出 DOCX / PDF" }));
    await waitFor(() => expect(rejectLate).toBeDefined());
    await choosePatient("李四（13800000002）");
    await act(async () => { rejectLate(new Error("late failure")); });
    expect(screen.queryByText("导出失败，请稍后重试或联系管理员。")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "下载 PDF" })).not.toBeInTheDocument();
  });

  it.each([
    {state:"normal",value:{year:{state:"value",value:2026},month:{state:"value",value:2},day:{state:"value",value:28}},native:null,want:"2026年2月28日",issues:[]},
    {state:"unknown",value:{year:{state:"value",value:2026},month:{state:"unknown"},day:{state:"unknown"}},native:null,want:"2026年不详月不详日",issues:[]},
    {state:"unresolved",value:null,native:null,want:"未填写",issues:[]},
    {state:"unresolved",value:{year:{state:"value",value:2026},month:{state:"value",value:2},day:{state:"value",value:28}},native:"2026-03-01",want:"需核对",issues:[{code:"invalid_value",scope:"T1",storage:"visit.visit_date",message:"日期存储冲突"}]},
  ])("uses the projected visit date in node summary: $state $want",async({state,value,native,want,issues})=>{
    const original=mockGet.getMockImplementation()!;
    mockGet.mockImplementation(async(url:string)=>{
      const response=await original(url);
      if(url.endsWith("/preview/")) {
        response.data.visits={T1:{visit_date:native,status:"completed",form_data:{}}};
        response.data.sections.push({key:"T1.visit",scope:"T1",title:"访视信息",table_ref:"#T15",supplemental:false,fields:[{field_id:"vd_T1_visit_date",storage:"visit.visit_date",label:"访视日期",widget:"date",applicable:true,required:true,counted:true,state,value,raw_value:native,partial_date_value:value,reason:state==="unknown"?"记不清月份和日期":"",rows:[],issues}]});
      }
      return response;
    });
    renderExportPage();
    expect(await screen.findByText(`T1 · 访视日期：${want} · 完成状态：已完成`)).toBeInTheDocument();
    if(issues.length) {expect(screen.getByText("原值：2026-03-01")).toBeInTheDocument();expect(screen.getByText(/部分日期：2026年/)).toBeInTheDocument();}
  });
  it("retains the native date fallback for an older preview without sections",async()=>{
    const original=mockGet.getMockImplementation()!;
    mockGet.mockImplementation(async(url:string)=>{const response=await original(url);if(url.endsWith("/preview/")){response.data.visits={T1:{visit_date:"2026-02-28",status:"completed",form_data:{}}};delete response.data.sections;}return response;});
    renderExportPage();expect(await screen.findByText("T1 · 访视日期：2026-02-28 · 完成状态：已完成")).toBeInTheDocument();
  });

});
