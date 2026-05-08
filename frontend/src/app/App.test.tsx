import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

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
        return Promise.resolve({
          data: [
            {
              id: 123,
              name: "张三",
              gender: "male",
              age: 30,
              phone: "13800000001",
              primary_doctor: 1,
            },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  it("imports global fullscreen styles from the app entry", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const mainTsx = readFileSync(resolve(here, "../main.tsx"), "utf-8");

    expect(mainTsx).toMatch(/import\s+["']\.\/styles\/global\.css["'];/);

    const globalCss = readFileSync(resolve(here, "../styles/global.css"), "utf-8");
    expect(globalCss).toContain("margin: 0");
    expect(globalCss).toMatch(/html\s*,\s*body\s*,\s*#root/);
    expect(globalCss).toContain("height: 100%");
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

  it("navigates to patient detail when clicking details from the patient list", async () => {
    window.history.pushState({}, "", "/patients");
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("张三")).toBeInTheDocument();
    });

    screen.getByText("详情").click();

    await waitFor(() => {
      expect(screen.getByText("患者详情")).toBeInTheDocument();
    });
  });
});
