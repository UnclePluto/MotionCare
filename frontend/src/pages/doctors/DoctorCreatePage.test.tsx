import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DoctorCreatePage } from "./DoctorCreatePage";

const { mockPost, mockNavigate } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockNavigate: vi.fn(),
}));

vi.mock("../../api/client", () => ({ apiClient: { post: (...args: unknown[]) => mockPost(...args) } }));
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DoctorCreatePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DoctorCreatePage", () => {
  beforeEach(() => {
    mockPost.mockReset();
    mockNavigate.mockReset();
  });

  afterEach(() => cleanup());

  it("validates phone before submit", async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("姓名"), { target: { value: "新医生" } });
    fireEvent.change(screen.getByLabelText("手机号"), { target: { value: "12345" } });
    fireEvent.click(screen.getByRole("button", { name: /创\s*建/ }));

    expect(await screen.findByText("请输入 11 位有效手机号")).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("creates doctor and returns to list", async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 2 } });
    renderPage();

    fireEvent.change(screen.getByLabelText("姓名"), { target: { value: " 新医生 " } });
    fireEvent.change(screen.getByLabelText("手机号"), { target: { value: " 13812345678 " } });
    fireEvent.click(screen.getByRole("button", { name: /创\s*建/ }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/accounts/users/", {
        name: "新医生",
        gender: "unknown",
        phone: "13812345678",
      });
      expect(mockNavigate).toHaveBeenCalledWith("/doctors");
    });
  });

  it("shows backend phone errors on the phone field", async () => {
    mockPost.mockRejectedValueOnce({
      response: { data: { phone: ["该手机号已存在"] } },
    });
    renderPage();

    fireEvent.change(screen.getByLabelText("姓名"), { target: { value: "新医生" } });
    fireEvent.change(screen.getByLabelText("手机号"), { target: { value: "13812345678" } });
    fireEvent.click(screen.getByRole("button", { name: /创\s*建/ }));

    expect(await screen.findByText("该手机号已存在")).toBeInTheDocument();
  });
});
