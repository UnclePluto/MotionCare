import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ForcePasswordChangeModal } from "./ForcePasswordChangeModal";

const { mockPost } = vi.hoisted(() => ({
  mockPost: vi.fn(),
}));

vi.mock("../api/client", () => ({
  apiClient: {
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

afterEach(() => {
  cleanup();
  mockPost.mockReset();
});

function renderModal(options?: { onChanged?: () => void; onLogout?: () => void }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onChanged = options?.onChanged ?? vi.fn();
  const onLogout = options?.onLogout ?? vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <ForcePasswordChangeModal open onChanged={onChanged} onLogout={onLogout} />
    </QueryClientProvider>,
  );
  return { onChanged, onLogout };
}

describe("ForcePasswordChangeModal", () => {
  it("renders as a blocking dialog without close controls", () => {
    renderModal();

    expect(screen.getByText("请先修改默认密码")).toBeInTheDocument();
    expect(screen.queryByLabelText("Close")).not.toBeInTheDocument();
    expect(screen.queryByText("稍后再说")).not.toBeInTheDocument();
  });

  it("submits password change and notifies caller", async () => {
    mockPost.mockResolvedValueOnce({ data: { detail: "密码已修改" } });
    const { onChanged } = renderModal();

    fireEvent.change(screen.getByLabelText("原密码"), { target: { value: "888888" } });
    fireEvent.change(screen.getByLabelText("新密码"), { target: { value: "newpass123456" } });
    fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value: "newpass123456" } });
    fireEvent.click(screen.getByRole("button", { name: "修改密码" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/accounts/users/me/change-password/", {
        old_password: "888888",
        new_password: "newpass123456",
        confirm_password: "newpass123456",
      });
      expect(onChanged).toHaveBeenCalled();
    });
  });

  it("allows logout from the blocking dialog", () => {
    const { onLogout } = renderModal();

    fireEvent.click(screen.getByRole("button", { name: "退出登录" }));

    expect(onLogout).toHaveBeenCalled();
  });
});
