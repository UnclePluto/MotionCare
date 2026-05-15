import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DoctorEditPage } from "./DoctorEditPage";

const { mockGet, mockPatch, mockNavigate } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPatch: vi.fn(),
  mockNavigate: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
  },
}));
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate, useParams: () => ({ doctorId: "3" }) };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DoctorEditPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DoctorEditPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPatch.mockReset();
    mockNavigate.mockReset();
  });

  afterEach(() => cleanup());

  it("loads and saves doctor profile", async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        id: 3,
        name: "旧医生",
        phone: "13812345678",
        gender: "female",
        role: "doctor",
        date_joined: "2026-05-15T10:20:00+08:00",
        must_change_password: false,
        is_active: true,
      },
    });
    mockPatch.mockResolvedValueOnce({ data: {} });

    renderPage();

    expect(await screen.findByDisplayValue("旧医生")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("姓名"), { target: { value: " 新医生 " } });
    fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith("/accounts/users/3/", {
        name: "新医生",
        gender: "female",
        phone: "13812345678",
      });
      expect(mockNavigate).toHaveBeenCalledWith("/doctors");
    });
  });

  it("shows backend phone errors on the phone field", async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        id: 3,
        name: "旧医生",
        phone: "13812345678",
        gender: "female",
        role: "doctor",
        date_joined: "2026-05-15T10:20:00+08:00",
        must_change_password: false,
        is_active: true,
      },
    });
    mockPatch.mockRejectedValueOnce({
      response: { data: { phone: ["该手机号已存在"] } },
    });

    renderPage();

    expect(await screen.findByDisplayValue("旧医生")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));

    expect(await screen.findByText("该手机号已存在")).toBeInTheDocument();
  });
});
