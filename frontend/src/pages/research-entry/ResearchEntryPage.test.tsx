import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ResearchEntryPage } from "./ResearchEntryPage";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/research-entry"]}>
        <Routes>
          <Route path="/research-entry" element={<ResearchEntryPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ResearchEntryPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url === "/studies/projects/") {
        return Promise.resolve({ data: [{ id: 1, name: "研究项目 A" }, { id: 2, name: "研究项目 B" }] });
      }
      if (url === "/studies/project-patients/") {
        return Promise.resolve({
          data: [
            {
              id: 9001,
              project: 1,
              project_name: "研究项目 A",
              project_status: "active",
              patient: 201,
              patient_name: "同名患者",
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
            },
            {
              id: 9002,
              project: 2,
              project_name: "研究项目 B",
              project_status: "active",
              patient: 201,
              patient_name: "同名患者",
              patient_phone: "13800000201",
              group: 20,
              group_name: "对照组",
              enrolled_at: "2026-05-13T10:00:00+08:00",
              visit_ids: { T0: 21, T1: 22, T2: 23 },
              visit_summaries: {
                T0: { id: 21, status: "draft", visit_date: null },
                T1: { id: 22, status: "draft", visit_date: null },
                T2: { id: 23, status: "draft", visit_date: null },
              },
            },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  afterEach(() => cleanup());

  it("renders one row per project patient and no visit-type filter", async () => {
    renderPage();

    expect(await screen.findByText("研究项目 A")).toBeInTheDocument();
    expect(screen.getByText("研究项目 B")).toBeInTheDocument();
    expect(screen.getAllByText("同名患者").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("访视类型")).not.toBeInTheDocument();
  });

  it("links record and visit status to project-patient research-entry page", async () => {
    renderPage();

    const recordLinks = await screen.findAllByRole("link", { name: "录入" });
    expect(recordLinks[0]).toHaveAttribute("href", "/research-entry/project-patients/9001");
    expect(screen.getAllByRole("link", { name: /T1 草稿/ })[0]).toHaveAttribute(
      "href",
      "/research-entry/project-patients/9001?visit=T1",
    );
    expect(screen.getAllByRole("link", { name: "基线资料" })[0]).toHaveAttribute("href", "/patients/201/crf-baseline");
  });

  it("passes project and patient filters to backend", async () => {
    renderPage();

    await screen.findByText("研究项目 A");
    fireEvent.change(screen.getByPlaceholderText("患者姓名或手机号"), { target: { value: "同名" } });
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/studies/project-patients/",
        expect.objectContaining({ params: expect.objectContaining({ patient_name: "同名" }) }),
      );
    });
  });
});
