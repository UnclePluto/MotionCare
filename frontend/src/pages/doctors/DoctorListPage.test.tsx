import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DoctorListPage } from "./DoctorListPage";

const { mockGet, mockNavigate } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockNavigate: vi.fn(),
}));

vi.mock("../../api/client", () => ({ apiClient: { get: (...args: unknown[]) => mockGet(...args) } }));
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DoctorListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DoctorListPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockNavigate.mockReset();
  });

  afterEach(() => cleanup());

  it("renders doctors with masked phone and navigates to create/edit", async () => {
    mockGet.mockResolvedValueOnce({
      data: [
        {
          id: 1,
          name: "王医生",
          phone: "13812345678",
          gender: "male",
          role: "doctor",
          date_joined: "2026-05-15T10:20:00+08:00",
          must_change_password: false,
          is_active: true,
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("王医生")).toBeInTheDocument();
    expect(screen.getByText("138****5678")).toBeInTheDocument();
    expect(screen.getByText("2026-05-15 10:20")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "添加医生" }));
    expect(mockNavigate).toHaveBeenCalledWith("/doctors/new");
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/doctors/1/edit"));
  });
});
