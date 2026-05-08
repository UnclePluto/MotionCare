import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
      if (url === "/studies/project-patients/" && params?.project === 1) {
        return Promise.resolve({
          data: [
            {
              id: 1,
              patient: 123,
              patient_name: "张三",
              patient_phone: "13800000001",
              group: null,
              group_name: null,
              grouping_batch: null,
              grouping_status: "pending",
              visit_ids: { T0: 11, T1: 12, T2: 13 },
            },
          ],
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
      expect(screen.getByText("13800000101")).toBeInTheDocument();
    });
  });

  it("adds a patient to a project from the 项目患者 tab", async () => {
    window.history.pushState({}, "", "/projects/1");
    mockPost.mockImplementation((url: string) => {
      if (url === "/studies/project-patients/") {
        return Promise.resolve({ data: { id: 1 } });
      }
      return Promise.reject(new Error(`unmocked POST ${url}`));
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("研究项目 A")).toBeInTheDocument();
    });

    screen.getByRole("tab", { name: "项目患者" }).click();

    const addButton = await screen.findByRole("button", { name: "添加患者" });
    addButton.click();

    const dialog = await screen.findByRole("dialog");
    const patientSelect = within(dialog).getByRole("combobox");
    fireEvent.mouseDown(patientSelect);
    await screen.findByText("张三（13800000001）");
    screen.getByText("张三（13800000001）").click();

    within(dialog).getByRole("button", { name: /添\s*加/ }).click();

    await waitFor(() => {
      expect(screen.getAllByText("张三").length).toBeGreaterThan(0);
    });
  });

  it("renders T0/T1/T2 links per project patient row", async () => {
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
      expect(screen.getByText("研究项目 A")).toBeInTheDocument();
    });
    screen.getByRole("tab", { name: "项目患者" }).click();

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "T0" })).toHaveAttribute(
        "href",
        "/visits/11",
      );
      expect(screen.getByRole("link", { name: "T1" })).toHaveAttribute(
        "href",
        "/visits/12",
      );
      expect(screen.getByRole("link", { name: "T2" })).toHaveAttribute(
        "href",
        "/visits/13",
      );
    });
  });
});
