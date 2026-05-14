import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VisitFormPage } from "./VisitFormPage";

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

function renderAt(visitId: number) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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

    expect(await screen.findByDisplayValue("9")).toBeInTheDocument();
    expect(screen.getByDisplayValue("22")).toBeInTheDocument();
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

    expect(await screen.findByDisplayValue("8")).toBeInTheDocument();
    expect(screen.getByText("系统预填值")).toBeInTheDocument();
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

    const sppbInputs = await screen.findAllByRole("spinbutton", {
      name: "SPPB 总分",
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

    expect(await screen.findByText("完成后对应记录无法修改。")).toBeInTheDocument();
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
        visit_type: "T0",
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

    const platform = await screen.findByLabelText("平台账号/编号");
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
        visit_type: "T0",
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

    expect(await screen.findByText("项目已完结，访视表单只读。")).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "SPPB 总分" })).toBeDisabled();
    expect(screen.getByLabelText("平台账号/编号")).toBeDisabled();

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
        visit_type: "T0",
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

    expect(await screen.findByText("访视已完成，当前为只读查看。")).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "SPPB 总分" })).toBeDisabled();
    expect(screen.getByLabelText("平台账号/编号")).toBeDisabled();

    const saveBtn = r.container.querySelector('button[aria-label="暂存"]');
    const completeBtn = r.container.querySelector('button[aria-label="完成"]');
    expect(saveBtn).toBeDisabled();
    expect(completeBtn).toBeDisabled();

    fireEvent.click(saveBtn as Element);
    fireEvent.click(completeBtn as Element);
    expect(mockPatch).not.toHaveBeenCalled();
  });
});
