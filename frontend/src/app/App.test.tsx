import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { App } from "./App";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}));

describe("App", () => {
  beforeEach(() => {
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config
          ? (config as { params?: Record<string, unknown> }).params
          : undefined;

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
      if (url === "/studies/projects/") {
        return Promise.resolve({
          data: [{ id: 1, name: "研究项目 A" }],
        });
      }
      if (url === "/studies/projects/1/") {
        return Promise.resolve({
          data: {
            id: 1,
            name: "研究项目 A",
            description: "",
            crf_template_version: "v1",
            status: "active",
          },
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
      if (url === "/studies/project-patients/") {
        const p = params ?? {};
        if (p.patient === 101 || p.patient === 123) {
          return Promise.resolve({ data: [] });
        }
        if (p.project === 1) {
          return Promise.resolve({
            data: [
              {
                id: 9001,
                project: 1,
                patient: 201,
                patient_name: "项目患者甲",
                patient_phone: "13800000201",
                group: 10,
                group_name: "试验组",
              },
              {
                id: 9002,
                project: 1,
                patient: 202,
                patient_name: "项目患者乙",
                patient_phone: "13800000202",
                group: 11,
                group_name: "对照组",
              },
            ],
          });
        }
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
            {
              id: 201,
              name: "项目患者甲",
              gender: "male",
              age: 60,
              phone: "13800000201",
              primary_doctor: 1,
            },
            {
              id: 202,
              name: "项目患者乙",
              gender: "female",
              age: 65,
              phone: "13800000202",
              primary_doctor: 1,
            },
          ],
        });
      }
      if (url === "/patients/123/") {
        return Promise.resolve({
          data: {
            id: 123,
            name: "张三",
            gender: "male",
            phone: "13800000001",
          },
        });
      }
      if (url === "/patients/101/") {
        return Promise.resolve({
          data: {
            id: 101,
            name: "李四",
            phone: "13800000101",
          },
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    mockPost.mockImplementation((url: string) => {
      return Promise.reject(new Error(`unmocked POST ${url}`));
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

    screen.getAllByRole("link", { name: "详情" })[0].click();

    await waitFor(() => {
      expect(screen.getByText("患者详情")).toBeInTheDocument();
    });
  });

  it("renders patient name and phone when opening /patients/101", async () => {
    window.history.pushState({}, "", "/patients/101");
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getAllByText("李四").length).toBeGreaterThan(0);
      expect(screen.getByDisplayValue("13800000101")).toBeInTheDocument();
    });
  });

  it("renders project grouping board when opening /projects/1", async () => {
    window.history.pushState({}, "", "/projects/1");
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getAllByText("研究项目 A").length).toBeGreaterThan(0);
      expect(screen.getByText(/全量患者/)).toBeInTheDocument();
      expect(screen.getAllByText("项目患者甲").length).toBeGreaterThan(0);
      expect(screen.getAllByText("项目患者乙").length).toBeGreaterThan(0);
      expect(screen.getAllByText(/张三/).length).toBeGreaterThan(0);
    });
  });
});
