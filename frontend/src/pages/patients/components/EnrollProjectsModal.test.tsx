import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EnrollProjectsModal } from "./EnrollProjectsModal";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

describe("EnrollProjectsModal", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url === "/studies/projects/") {
        return Promise.resolve({ data: [{ id: 1, name: "项目甲" }] });
      }
      if (url.startsWith("/studies/project-patients/?patient=")) {
        return Promise.resolve({ data: [] });
      }
      if (url === "/studies/groups/") {
        return Promise.resolve({
          data: [
            { id: 10, project: 1, name: "干预组", is_active: true },
            { id: 11, project: 1, name: "对照组", is_active: true },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    mockPost.mockResolvedValue({
      data: { detail: "已确认入组", created: [{ project_id: 1, group_id: 10 }] },
    });
  });

  it("posts new enrollments payload with project_id + group_id", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onClose = vi.fn();

    render(
      <QueryClientProvider client={qc}>
        <EnrollProjectsModal open onClose={onClose} patientId={42} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("项目甲")).toBeInTheDocument();
    });

    const combo = await screen.findByRole("combobox");
    fireEvent.mouseDown(combo);
    const interventionOption = await screen.findByText("干预组");
    fireEvent.click(interventionOption);

    fireEvent.click(screen.getByRole("button", { name: "确认入组" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalled();
    });
    const [calledUrl, payload] = mockPost.mock.calls[0];
    expect(calledUrl).toBe("/patients/42/enroll-projects/");
    expect(payload).toEqual({
      enrollments: [{ project_id: 1, group_id: 10 }],
    });
  });

  it("does not show archived projects", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === "/studies/projects/") {
        return Promise.resolve({
          data: [
            { id: 1, name: "进行中项目", status: "active" },
            { id: 2, name: "已完结项目", status: "archived" },
          ],
        });
      }
      if (url.startsWith("/studies/project-patients/?patient=")) {
        return Promise.resolve({ data: [] });
      }
      if (url === "/studies/groups/") {
        return Promise.resolve({
          data: [
            { id: 10, project: 1, name: "干预组", is_active: true },
            { id: 20, project: 2, name: "对照组", is_active: true },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={qc}>
        <EnrollProjectsModal open onClose={vi.fn()} patientId={42} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("进行中项目")).toBeInTheDocument();
    expect(screen.queryByText("已完结项目")).not.toBeInTheDocument();
  });
});
