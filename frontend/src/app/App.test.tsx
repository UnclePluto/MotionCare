import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { App } from "./App";

const { mockGet } = vi.hoisted(() => ({
  mockGet: vi.fn(),
}));

vi.mock("../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: vi.fn(),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}));

describe("App", () => {
  beforeEach(() => {
    mockGet.mockImplementation((url: string) => {
      if (url === "/me/") {
        return Promise.resolve({
          data: {
            id: 1,
            phone: "13800000000",
            name: "测试医生",
            role: "doctor",
            roles: ["doctor"],
            permissions: ["patient.read"],
          },
        });
      }
      if (url === "/patients/") {
        return Promise.resolve({ data: [] });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  it("renders the admin navigation", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getAllByText("患者档案").length).toBeGreaterThan(0);
      expect(screen.getAllByText("研究项目").length).toBeGreaterThan(0);
      expect(screen.getAllByText("CRF 报告").length).toBeGreaterThan(0);
    });
  });
});
