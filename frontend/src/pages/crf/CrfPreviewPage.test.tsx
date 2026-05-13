import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CrfPreviewPage } from "./CrfPreviewPage";

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
          data: [{ id: 1, patient_name: "张三", patient_phone: "13800000001" }],
        });
      }
      if (url === "/crf/project-patients/1/preview/") {
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
        <MemoryRouter initialEntries={["/?projectPatientId=1"]}>
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

  it("allows DOCX export for selected project patient", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/?projectPatientId=1"]}>
          <CrfPreviewPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const exportButton = await screen.findByRole("button", { name: "导出 DOCX" });
    fireEvent.click(exportButton);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/crf/project-patients/1/export/", {});
    });
  });
});
