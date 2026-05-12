import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PatientListPage } from "./PatientListPage";

const mockGet = vi.fn();

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    delete: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}));

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({ me: { id: 1, name: "医生", phone: "13900000000" } }),
}));

describe("PatientListPage", () => {
  beforeEach(() => {
    mockGet.mockImplementation((url: string) => {
      if (url === "/patients/") {
        return Promise.resolve({
          data: [
            {
              id: 1,
              name: "王五",
              gender: "male",
              age: 40,
              phone: "13812345678",
              primary_doctor: 1,
              primary_doctor_name: "李医生",
            },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  it("masks phone in list and does not show details link", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <PatientListPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("138****5678")).toBeInTheDocument();
    });
    expect(screen.queryByRole("link", { name: "详情" })).toBeNull();
  });
});
