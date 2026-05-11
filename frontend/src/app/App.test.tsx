import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { App } from "./App";

const { mockGet, mockPost, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDelete: vi.fn(),
}));

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

vi.mock("../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}));

describe("App", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockDelete.mockReset();

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
      if (url === "/studies/grouping-batches/" && params?.project === 1) {
        return Promise.resolve({ data: [] });
      }
      if (url === "/studies/project-patients/") {
        const p = params ?? {};
        if (p.patient === 101 || p.patient === 123) {
          return Promise.resolve({ data: [] });
        }
        if (p.project === 1) {
          return Promise.resolve({ data: [] });
        }
      }
      if (url === "/studies/project-patients/?patient=123") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/studies/project-patients/?patient=124") {
        return Promise.resolve({
          data: [
            {
              id: 900,
              project: 1,
              patient_name: "王五",
              group_name: "试验组",
              grouping_status: "confirmed",
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
              primary_doctor_name: "测试医生",
            },
            {
              id: 124,
              name: "王五",
              gender: "female",
              age: 68,
              phone: "13900000002",
              primary_doctor: null,
              primary_doctor_name: null,
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

    mockDelete.mockImplementation((url: string) => {
      return Promise.reject(new Error(`unmocked DELETE ${url}`));
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

  it("navigates to patient detail when clicking the patient name from the patient list", async () => {
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

    expect(screen.queryByRole("link", { name: "详情" })).not.toBeInTheDocument();

    screen.getByRole("link", { name: "张三" }).click();

    await waitFor(() => {
      expect(screen.getByText("患者详情")).toBeInTheDocument();
    });
  });

  it("renders masked phone numbers and primary doctor names on the patient list", async () => {
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
      expect(screen.getByText("138****0001")).toBeInTheDocument();
      expect(screen.queryByText("13800000001")).not.toBeInTheDocument();
      expect(screen.getByText("测试医生")).toBeInTheDocument();
      expect(screen.getByText("主治医生")).toBeInTheDocument();
      expect(screen.queryByText("主治医生 ID")).not.toBeInTheDocument();
    });

    const wangRow = document.querySelector('tr[data-row-key="124"]');
    expect(wangRow).not.toBeNull();
    expect(within(wangRow).getByText("—")).toBeInTheDocument();
  });

  it("allows deleting a patient without project links after confirmation", async () => {
    mockDelete.mockResolvedValue({ data: {} });
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
      expect(document.querySelector('tr[data-row-key="123"]')).not.toBeNull();
    });
    const zhangRow = document.querySelector('tr[data-row-key="123"]');
    fireEvent.click(within(zhangRow).getByRole("button", { name: "删除" }));

    const dialog = await screen.findByRole("dialog", { name: "确认删除患者档案？" });
    expect(dialog).toHaveTextContent("当前未检测到研究项目入组关联。");

    fireEvent.click(within(dialog).getByRole("button", { name: /删\s*除/ }));

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith("/patients/123/");
    });
  });

  it("blocks deleting a patient with project links and does not call DELETE", async () => {
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
      expect(document.querySelector('tr[data-row-key="124"]')).not.toBeNull();
    });
    const wangRow = document.querySelector('tr[data-row-key="124"]');
    fireEvent.click(within(wangRow).getByRole("button", { name: "删除" }));

    const dialog = await screen.findByRole("dialog", { name: "确认删除患者档案？" });
    expect(within(dialog).getByText("当前无法执行该操作")).toBeInTheDocument();
    expect(within(dialog).getByText(/需先到项目中删除或解绑该患者/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /删\s*除/ })).toBeDisabled();
    expect(mockDelete).not.toHaveBeenCalledWith("/patients/124/");
  });

  it("ignores stale successful delete checks after switching to another patient", async () => {
    const baseGet = mockGet.getMockImplementation();
    const zhangCheck = deferred<{ data: unknown[] }>();
    const wangCheck = deferred<{ data: unknown[] }>();
    mockDelete.mockResolvedValue({ data: {} });
    mockGet.mockImplementation((url: string, config?: unknown) => {
      if (url === "/studies/project-patients/?patient=123") return zhangCheck.promise;
      if (url === "/studies/project-patients/?patient=124") return wangCheck.promise;
      return baseGet?.(url, config) ?? Promise.reject(new Error(`unmocked GET ${url}`));
    });

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
      expect(document.querySelector('tr[data-row-key="123"]')).not.toBeNull();
      expect(document.querySelector('tr[data-row-key="124"]')).not.toBeNull();
    });

    const zhangRow = document.querySelector('tr[data-row-key="123"]');
    const wangRow = document.querySelector('tr[data-row-key="124"]');
    fireEvent.click(within(zhangRow).getByRole("button", { name: "删除" }));
    await screen.findByRole("dialog", { name: "确认删除患者档案？" });

    fireEvent.click(within(wangRow).getByRole("button", { name: "删除" }));

    await act(async () => {
      zhangCheck.resolve({ data: [] });
      await zhangCheck.promise;
    });

    const pendingDialog = await screen.findByRole("dialog", { name: "确认删除患者档案？" });
    fireEvent.click(within(pendingDialog).getByRole("button", { name: /删\s*除/ }));
    expect(mockDelete).not.toHaveBeenCalledWith("/patients/124/");

    await act(async () => {
      wangCheck.resolve({
        data: [
          {
            id: 900,
            project: 1,
            patient_name: "王五",
            group_name: "试验组",
            grouping_status: "confirmed",
          },
        ],
      });
      await wangCheck.promise;
    });

    const blockedDialog = await screen.findByRole("dialog", { name: "确认删除患者档案？" });
    expect(within(blockedDialog).getByText("当前无法执行该操作")).toBeInTheDocument();
    expect(within(blockedDialog).getByText(/需先到项目中删除或解绑该患者/)).toBeInTheDocument();
    expect(within(blockedDialog).getByRole("button", { name: /删\s*除/ })).toBeDisabled();
    expect(mockDelete).not.toHaveBeenCalledWith("/patients/124/");
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
      expect(screen.getByText("研究项目 A")).toBeInTheDocument();
      expect(screen.getByText("患者池（尚未加入本项目）")).toBeInTheDocument();
    });
  });
});
