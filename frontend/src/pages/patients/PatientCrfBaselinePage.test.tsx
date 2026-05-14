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

  afterEach(() => cleanup());

  it("uses a generic back button that returns to the previous page", async () => {
    renderPage();

    const backButton = await screen.findByRole("button", { name: "返回" });
    expect(screen.queryByRole("button", { name: "返回详情" })).not.toBeInTheDocument();

    fireEvent.click(backButton);

    expect(await screen.findByText("患者列表上一页")).toBeInTheDocument();
  });
});
