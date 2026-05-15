import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectPatientBindingCard } from "./ProjectPatientBindingCard";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

function renderCard(projectPatientId = 12) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <ProjectPatientBindingCard projectPatientId={projectPatientId} />
    </QueryClientProvider>,
  );
  return {
    ...view,
    rerenderCard: (nextProjectPatientId: number) =>
      view.rerender(
        <QueryClientProvider client={qc}>
          <ProjectPatientBindingCard projectPatientId={nextProjectPatientId} />
        </QueryClientProvider>,
      ),
  };
}

describe("ProjectPatientBindingCard", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockResolvedValue({
      data: {
        has_active_session: false,
        has_active_binding_code: false,
        binding_code_expires_at: null,
        last_bound_at: null,
        active_session_expires_at: null,
      },
    });
  });

  afterEach(() => cleanup());

  it("shows binding status and generated code", async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        code: "0387",
        expires_at: "2026-05-14T12:15:00+08:00",
      },
    });

    renderCard();

    expect(await screen.findByText("未绑定")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "生成绑定码" }));

    expect(await screen.findByText("0387")).toBeInTheDocument();
    expect(screen.getByText("15 分钟内有效，请提供给患者。")).toBeInTheDocument();
    expect(screen.getByText(/绑定码只显示一次/)).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith("/studies/project-patients/12/binding-code/");
    await waitFor(() => {
      expect(
        mockGet.mock.calls.filter(
          ([url]) => url === "/studies/project-patients/12/binding-status/",
        ).length,
      ).toBeGreaterThanOrEqual(2);
    });
  });

  it("clears generated code when switching project patient", async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        code: "0387",
        expires_at: "2026-05-14T12:15:00+08:00",
      },
    });
    const { rerenderCard } = renderCard(12);

    expect(await screen.findByText("未绑定")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "生成绑定码" }));
    expect(await screen.findByText("0387")).toBeInTheDocument();

    rerenderCard(13);

    await waitFor(() => {
      expect(screen.queryByText("0387")).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/studies/project-patients/13/binding-status/");
    });
  });

  it("ignores a generated code response from a previous project patient", async () => {
    let resolveCreateCode!: (value: {
      data: { code: string; expires_at: string };
    }) => void;
    const createCodeRequest = new Promise<{ data: { code: string; expires_at: string } }>(
      (resolve) => {
        resolveCreateCode = resolve;
      },
    );
    mockPost.mockReturnValueOnce(createCodeRequest);
    const { rerenderCard } = renderCard(12);

    expect(await screen.findByText("未绑定")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "生成绑定码" }));
    rerenderCard(13);

    await act(async () => {
      resolveCreateCode({
        data: {
          code: "0387",
          expires_at: "2026-05-14T12:15:00+08:00",
        },
      });
      await createCodeRequest;
    });

    expect(screen.queryByText("0387")).not.toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith("/studies/project-patients/12/binding-code/");
  });

  it("can revoke an active binding", async () => {
    mockGet.mockResolvedValue({
      data: {
        has_active_session: true,
        has_active_binding_code: false,
        binding_code_expires_at: null,
        last_bound_at: "2026-05-14T12:00:00+08:00",
        active_session_expires_at: "2026-06-13T12:00:00+08:00",
      },
    });
    mockPost.mockResolvedValueOnce({ data: {} });

    renderCard();

    expect(await screen.findByText("已绑定")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "撤销绑定" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/studies/project-patients/12/revoke-binding/");
    });
  });
});
