import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PrescriptionEntryPage } from "./PrescriptionEntryPage";

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
      <MemoryRouter initialEntries={["/prescriptions"]}>
        <Routes>
          <Route path="/prescriptions" element={<PrescriptionEntryPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PrescriptionEntryPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url === "/studies/projects/") {
        return Promise.resolve({ data: [{ id: 1, name: "研究项目 A" }] });
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
              patient_name: "项目患者甲",
              patient_phone: "13800000201",
              group: 10,
              group_name: "试验组",
              enrolled_at: "2026-05-12T10:00:00+08:00",
              updated_at: "2026-05-14T09:30:00+08:00",
            },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  afterEach(() => cleanup());

  it("renders project patients as an independent prescription entry", async () => {
    renderPage();

    expect(screen.getByText("处方管理")).toBeInTheDocument();
    expect(await screen.findByText("项目患者甲")).toBeInTheDocument();
    expect(screen.getByText("研究项目 A")).toBeInTheDocument();
    expect(screen.getByText("进行中")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "处方" })).toHaveAttribute(
      "href",
      "/prescriptions/project-patients/9001",
    );
    expect(screen.getByRole("link", { name: "跟练模拟" })).toHaveAttribute(
      "href",
      "/patient-sim/project-patients/9001",
    );
  });

  it("passes patient search params to backend", async () => {
    renderPage();

    await screen.findByText("项目患者甲");
    fireEvent.change(screen.getByPlaceholderText("患者姓名或手机号"), { target: { value: "项目患者" } });
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/studies/project-patients/",
        expect.objectContaining({ params: expect.objectContaining({ patient_name: "项目患者" }) }),
      );
    });
  });
});
