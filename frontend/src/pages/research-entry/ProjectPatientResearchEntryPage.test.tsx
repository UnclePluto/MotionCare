import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectPatientResearchEntryPage } from "./ProjectPatientResearchEntryPage";

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

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/research-entry/project-patients/:projectPatientId" element={<ProjectPatientResearchEntryPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const projectPatient = {
  id: 9001,
  project: 1,
  project_name: "研究项目 A",
  project_status: "active",
  patient: 201,
  patient_name: "项目患者甲",
  patient_phone: "13800000201",
  group: 10,
  group_name: "试验组",
  enrolled_at: "2026-05-12T10:00:00+08:00",
  visit_ids: { T0: 11, T1: 12, T2: 13 },
  visit_summaries: {
    T0: { id: 11, status: "completed", visit_date: "2026-05-12" },
    T1: { id: 12, status: "draft", visit_date: null },
    T2: { id: 13, status: "draft", visit_date: null },
  },
};

describe("ProjectPatientResearchEntryPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPatch.mockReset();
    mockPatch.mockResolvedValue({ data: {} });
    mockGet.mockImplementation((url: string) => {
      if (url === "/studies/project-patients/9001/") return Promise.resolve({ data: projectPatient });
      if (url === "/visits/11/") {
        return Promise.resolve({
          data: {
            id: 11,
            project_patient: 9001,
            project_status: "active",
            visit_type: "T0",
            status: "completed",
            visit_date: "2026-05-12",
            form_data: { assessments: { sppb: { total: 9 } }, computed_assessments: {}, crf: {} },
          },
        });
      }
      if (url === "/visits/12/") {
        return Promise.resolve({
          data: {
            id: 12,
            project_patient: 9001,
            project_status: "active",
            visit_type: "T1",
            status: "draft",
            visit_date: null,
            form_data: { assessments: {}, computed_assessments: {}, crf: {} },
          },
        });
      }
      if (url === "/visits/13/") {
        return Promise.resolve({
          data: {
            id: 13,
            project_patient: 9001,
            project_status: "active",
            visit_type: "T2",
            status: "draft",
            visit_date: null,
            form_data: { assessments: {}, computed_assessments: {}, crf: {} },
          },
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  afterEach(() => cleanup());

  it("defaults to first unfinished visit when no query visit is provided", async () => {
    renderAt("/research-entry/project-patients/9001");

    expect(await screen.findByText("项目患者甲 · 研究项目 A")).toBeInTheDocument();
    expect(screen.getByText("试验组")).toBeInTheDocument();
    expect(screen.getByText("进行中")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /T0 已完成 2026-05-12/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /T1 草稿 未填写日期/ })).toBeInTheDocument();
    expect(await screen.findByText(/干预 12 周节点/)).toBeInTheDocument();
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("/visits/12/"));
  });

  it("opens the query-selected tab", async () => {
    renderAt("/research-entry/project-patients/9001?visit=T0");

    expect(await screen.findByText(/筛选\/入组节点/)).toBeInTheDocument();
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("/visits/11/"));
    expect(await screen.findByText("访视已完成，当前为只读查看。")).toBeInTheDocument();
  });

  it("renders baseline and CRF links in project context", async () => {
    renderAt("/research-entry/project-patients/9001?visit=T1");

    expect(await screen.findByRole("link", { name: "基线资料" })).toHaveAttribute("href", "/patients/201/crf-baseline");
    expect(screen.getByRole("link", { name: "打开 CRF" })).toHaveAttribute("href", "/crf?projectPatientId=9001");
  });

  it("refreshes project patient summary after marking a visit completed", async () => {
    renderAt("/research-entry/project-patients/9001?visit=T1");

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("/visits/12/"));
    fireEvent.click(await screen.findByRole("button", { name: "标记已完成" }));

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith("/visits/12/", { status: "completed" });
    });
    await waitFor(() => {
      const projectReloads = mockGet.mock.calls.filter(
        ([url]) => url === "/studies/project-patients/9001/",
      );
      expect(projectReloads.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("shows an error when the visit detail cannot be loaded", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === "/studies/project-patients/9001/") return Promise.resolve({ data: projectPatient });
      if (url === "/visits/12/") return Promise.reject(new Error("not found"));
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    renderAt("/research-entry/project-patients/9001?visit=T1");

    expect(await screen.findByText("访视记录不存在或无权限访问")).toBeInTheDocument();
  });
});
