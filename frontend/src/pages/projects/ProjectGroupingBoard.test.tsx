import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
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
            { id: 1, name: "池外甲", gender: "male", phone: "13900000001" },
            { id: 201, name: "已入组乙", gender: "female", phone: "13900000201" },
            { id: 202, name: "待确认丙", gender: "male", phone: "13900000202" },
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
              patient_name: "已入组乙",
              patient_phone: "13900000201",
              group: 10,
              grouping_status: "confirmed",
            },
            {
              id: 9002,
              project: 1,
              patient: 202,
              patient_name: "待确认丙",
              patient_phone: "13900000202",
              group: 11,
              grouping_status: "pending",
            },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  it("患者池不包含已入本项目者且列内已确认卡片含已确认标签", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoard projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/患者池/)).toBeInTheDocument();
    });
    const poolCard = screen.getByText(/患者池/).closest(".ant-card");
    expect(poolCard).toBeTruthy();
    expect(within(poolCard as HTMLElement).getByText(/池外甲/)).toBeInTheDocument();
    expect(within(poolCard as HTMLElement).queryByText(/已入组乙/)).not.toBeInTheDocument();
    expect(within(poolCard as HTMLElement).queryByText(/待确认丙/)).not.toBeInTheDocument();
    expect(screen.getAllByText("已确认").length).toBeGreaterThan(0);
  });
});
