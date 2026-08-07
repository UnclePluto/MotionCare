import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

  it("在同一操作区展示患者绑定信息与未绑定设备操作", async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        code: "0387",
        expires_at: "2026-05-14T12:15:00+08:00",
      },
    });

    renderCard();

    expect(await screen.findByRole("heading", { name: "患者接入" })).toBeInTheDocument();
    expect(screen.getByText("患者绑定信息")).toBeInTheDocument();
    expect(screen.queryByText("小程序临时绑定码")).not.toBeInTheDocument();
    expect(screen.queryByText("穿戴设备")).not.toBeInTheDocument();
    const actions = screen.getByTestId("patient-binding-actions");
    expect(within(actions).getByRole("button", { name: "生成绑定码" })).toBeInTheDocument();
    expect(await within(actions).findByRole("button", { name: "绑定穿戴设备" })).toBeInTheDocument();
    expect(within(actions).getByRole("button", { name: "撤销绑定" })).toBeInTheDocument();
    expect(await screen.findByText("未绑定")).toBeInTheDocument();
    expect(screen.getByText("患者绑定状态")).toBeInTheDocument();
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

  it("绑定设备后在患者绑定信息表格中展示设备字段", async () => {
    const deviceBinding = {
      id: 33,
      patient_id: 101,
      device_id: 7,
      short_code: "0826",
      bound_at: "2026-07-24T10:00:00Z",
      unbound_at: null,
    };
    let activeBinding: typeof deviceBinding | null = null;
    mockGet.mockImplementation((url: string) => {
      if (url === "/studies/project-patients/12/binding-status/") {
        return Promise.resolve({
          data: {
            has_active_session: false,
            has_active_binding_code: false,
            binding_code_expires_at: null,
            last_bound_at: null,
            active_session_expires_at: null,
          },
        });
      }
      if (url === "/wearables/project-patients/12/binding/") {
        return Promise.resolve({
          data: { project_patient_id: 12, patient_id: 101, binding: activeBinding },
        });
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    mockPost.mockImplementation((url: string) => {
      if (url === "/wearables/project-patients/12/bind/") {
        activeBinding = deviceBinding;
        return Promise.resolve({ data: deviceBinding });
      }
      if (url === "/wearables/devices/7/check-status/") {
        return Promise.resolve({
          data: {
            device_id: 7,
            model: "M1",
            online: true,
            battery_level: 80,
            last_communication_at: "2026-07-24T10:00:00Z",
            capabilities: { ring: true },
          },
        });
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });

    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));
    fireEvent.change(await screen.findByLabelText("设备固定简码"), { target: { value: "0826" } });
    fireEvent.click(screen.getByRole("button", { name: "确认绑定" }));

    expect(await screen.findByText("0826")).toBeInTheDocument();
    const patientBindingTable = screen.getByText("患者绑定状态").closest("table");
    expect(patientBindingTable).not.toBeNull();
    expect(screen.getByText("设备简码").closest("table")).toBe(patientBindingTable);
    expect(screen.getByText("设备 ID").closest("table")).toBe(patientBindingTable);
    expect(screen.getByText("设备绑定时间").closest("table")).toBe(patientBindingTable);
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(document.querySelectorAll(".ant-descriptions table")).toHaveLength(1);
    expect(document.querySelector(".ant-divider")).not.toBeInTheDocument();

    const actions = within(screen.getByTestId("patient-binding-actions"));
    expect(actions.queryByRole("button", { name: "绑定穿戴设备" })).not.toBeInTheDocument();
    expect(actions.getByRole("button", { name: "生成绑定码" })).toBeInTheDocument();
    expect(actions.getByRole("button", { name: "撤销绑定" })).toBeInTheDocument();
    expect(actions.getByRole("button", { name: "通信测试" })).toBeInTheDocument();
    expect(actions.getByRole("button", { name: "解绑设备" })).toBeInTheDocument();
    expect(await actions.findByRole("button", { name: "让设备响铃" })).toBeInTheDocument();
  });

  it("解绑设备后在同一表格清空设备字段并恢复同一操作区绑定入口", async () => {
    const deviceBinding = {
      id: 33,
      patient_id: 101,
      device_id: 7,
      short_code: "0826",
      bound_at: "2026-07-24T10:00:00Z",
      unbound_at: null,
    };
    let activeBinding: typeof deviceBinding | null = deviceBinding;
    mockGet.mockImplementation((url: string) => {
      if (url === "/studies/project-patients/12/binding-status/") {
        return Promise.resolve({
          data: {
            has_active_session: false,
            has_active_binding_code: false,
            binding_code_expires_at: null,
            last_bound_at: null,
            active_session_expires_at: null,
          },
        });
      }
      if (url === "/wearables/project-patients/12/binding/") {
        return Promise.resolve({
          data: { project_patient_id: 12, patient_id: 101, binding: activeBinding },
        });
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    mockPost.mockImplementation((url: string) => {
      if (url === "/wearables/devices/7/check-status/") {
        return Promise.resolve({
          data: {
            device_id: 7,
            model: "M1",
            online: true,
            battery_level: 80,
            last_communication_at: "2026-07-24T10:00:00Z",
            capabilities: { ring: true },
          },
        });
      }
      if (url === "/wearables/bindings/33/unbind/") {
        activeBinding = null;
        return Promise.resolve({
          data: {
            binding: { ...deviceBinding, unbound_at: "2026-07-24T11:00:00Z" },
            historical_data_preserved: true,
          },
        });
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });

    renderCard();

    const actions = within(screen.getByTestId("patient-binding-actions"));
    fireEvent.click(await actions.findByRole("button", { name: "通信测试" }));
    expect(await actions.findByRole("button", { name: "让设备响铃" })).toBeInTheDocument();
    fireEvent.click(actions.getByRole("button", { name: "解绑设备" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认解绑" }));

    expect(await actions.findByRole("button", { name: "绑定穿戴设备" })).toBeInTheDocument();
    for (const label of ["设备简码", "设备 ID", "设备绑定时间"]) {
      const labelCell = screen.getByText(label).closest("th");
      expect(labelCell?.nextElementSibling).toHaveTextContent("—");
    }
    expect(actions.queryByRole("button", { name: "通信测试" })).not.toBeInTheDocument();
    expect(actions.queryByRole("button", { name: "解绑设备" })).not.toBeInTheDocument();
    expect(actions.queryByRole("button", { name: "让设备响铃" })).not.toBeInTheDocument();
    expect(actions.getByRole("button", { name: "生成绑定码" })).toBeInTheDocument();
    expect(actions.getByRole("button", { name: "撤销绑定" })).toBeInTheDocument();
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
