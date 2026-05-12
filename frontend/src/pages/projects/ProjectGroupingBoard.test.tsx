import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { ProjectGroupingBoard } from "./ProjectGroupingBoard";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

describe("ProjectGroupingBoard", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config
          ? (config as { params?: Record<string, unknown> }).params
          : undefined;

      if (url === "/patients/") {
        return Promise.resolve({
          data: [
            { id: 1, name: "未入组甲", gender: "male", phone: "13900000001" },
            { id: 2, name: "未入组乙", gender: "female", phone: "13900000002" },
            { id: 201, name: "已确认丙", gender: "male", phone: "13900000201" },
          ],
        });
      }
      if (url === "/studies/groups/" && params?.project === 1) {
        return Promise.resolve({
          data: [
            { id: 10, name: "试验组", target_ratio: 1, sort_order: 0, is_active: true },
            { id: 11, name: "对照组", target_ratio: 1, sort_order: 1, is_active: true },
          ],
        });
      }
      if (url === "/studies/project-patients/" && params?.project === 1) {
        return Promise.resolve({
          data: [
            {
              id: 9001,
              project: 1,
              patient: 201,
              patient_name: "已确认丙",
              patient_phone: "13900000201",
              group: 10,
            },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  it("全量患者中已确认患者置灰禁选，组列仍展示已确认患者", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoard projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/全量患者|患者选择/)).toBeInTheDocument());
    const patientSelection = screen.getByText(/全量患者|患者选择/).closest(".ant-card");
    expect(patientSelection).toBeTruthy();
    expect(within(patientSelection as HTMLElement).getByText(/未入组甲/)).toBeInTheDocument();
    expect(within(patientSelection as HTMLElement).getByText(/未入组乙/)).toBeInTheDocument();
    expect(within(patientSelection as HTMLElement).getByText(/已确认丙/)).toBeInTheDocument();
    expect(screen.getByLabelText(/选择患者 已确认丙/)).toBeDisabled();

    const experimentGroup = screen.getByText("试验组").closest(".ant-card");
    expect(experimentGroup).toBeTruthy();
    expect(within(experimentGroup as HTMLElement).getByText("已确认丙")).toBeInTheDocument();
    expect(within(experimentGroup as HTMLElement).getByText("已确认")).toBeInTheDocument();
  });

  it("随机只生成本地临时结果，不调用后端 randomize", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoard projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
    fireEvent.click(screen.getByRole("button", { name: "随机分组" }));

    await waitFor(() => expect(screen.getByText("本次随机")).toBeInTheDocument());
    expect(mockPost.mock.calls.map((call) => call[0])).not.toContain("/studies/projects/1/randomize/");
  });

  it("确认分组提交本地 assignments 并刷新", async () => {
    mockPost.mockResolvedValueOnce({
      data: { confirmed: 1, created: [{ project_patient_id: 9010, patient_id: 1, group_id: 10 }] },
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoard projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
    fireEvent.click(screen.getByRole("button", { name: "随机分组" }));
    await waitFor(() => expect(screen.getByText("本次随机")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, payload] = mockPost.mock.calls.at(-1) ?? [];
    expect(url).toBe("/studies/projects/1/confirm-grouping/");
    expect(payload.assignments).toHaveLength(1);
    expect(payload.assignments[0].patient_id).toBe(1);
    expect([10, 11]).toContain(payload.assignments[0].group_id);
  });
});
