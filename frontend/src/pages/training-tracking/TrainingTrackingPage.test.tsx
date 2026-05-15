import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TrainingTrackingPage } from "./TrainingTrackingPage";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/training-tracking"]}>
        <Routes>
          <Route path="/training-tracking" element={<TrainingTrackingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TrainingTrackingPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url === "/training/tracking/patients/") {
        return Promise.resolve({
          data: [
            {
              patient: {
                id: 201,
                name: "训练患者甲",
                phone_masked: "138****0201",
              },
              project_count: 2,
              last_training_at: "2026-05-14T10:30:00+08:00",
              last_30_days_completed_count: 12,
            },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  afterEach(() => cleanup());

  it("搜索全局患者并链接到训练追踪详情页", async () => {
    renderPage();

    expect(await screen.findByText("患者训练追踪")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("患者姓名或手机号"), { target: { value: "训练" } });
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/tracking/patients/", { params: { q: "训练" } });
    });

    expect(screen.getByText("训练患者甲")).toBeInTheDocument();
    expect(screen.getByText("138****0201")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("2026-05-14 10:30")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看追踪" })).toHaveAttribute(
      "href",
      "/training-tracking/patients/201",
    );
  });
});
