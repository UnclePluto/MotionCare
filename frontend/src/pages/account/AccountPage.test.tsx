import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AccountPage } from "./AccountPage";

const { mockPatch, mockPost, mockRefetchSession } = vi.hoisted(() => ({
  mockPatch: vi.fn(),
  mockPost: vi.fn(),
  mockRefetchSession: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    patch: (...args: unknown[]) => mockPatch(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));
vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({
    me: {
      id: 9,
      name: "当前医生",
      phone: "13812345678",
      gender: "male",
      role: "doctor",
      roles: ["doctor"],
      permissions: ["user.manage"],
      must_change_password: false,
    },
    refetchSession: mockRefetchSession,
  }),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AccountPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AccountPage", () => {
  beforeEach(() => {
    mockPatch.mockReset();
    mockPost.mockReset();
    mockRefetchSession.mockReset();
  });

  afterEach(() => cleanup());

  it("updates current profile and refreshes session", async () => {
    mockPatch.mockResolvedValueOnce({ data: {} });
    mockRefetchSession.mockResolvedValueOnce(undefined);
    renderPage();

    fireEvent.change(screen.getByLabelText("姓名"), { target: { value: " 新姓名 " } });
    fireEvent.click(screen.getByRole("button", { name: "保存资料" }));

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith("/accounts/users/9/", {
        name: "新姓名",
        gender: "male",
        phone: "13812345678",
      });
      expect(mockRefetchSession).toHaveBeenCalled();
    });
  });

  it("changes current password and refreshes session", async () => {
    mockPost.mockResolvedValueOnce({ data: { detail: "密码已修改" } });
    mockRefetchSession.mockResolvedValueOnce(undefined);
    renderPage();

    fireEvent.change(screen.getByLabelText("原密码"), { target: { value: "oldpass123456" } });
    fireEvent.change(screen.getByLabelText("新密码"), { target: { value: "newpass123456" } });
    fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value: "newpass123456" } });
    fireEvent.click(screen.getByRole("button", { name: "修改密码" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/accounts/users/me/change-password/", {
        old_password: "oldpass123456",
        new_password: "newpass123456",
        confirm_password: "newpass123456",
      });
      expect(mockRefetchSession).toHaveBeenCalled();
    });
  });
});
