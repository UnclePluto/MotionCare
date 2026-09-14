import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import dayjs from "dayjs";

import { TrainingDetailExportModal } from "./TrainingDetailExportModal";

const { mockDownload } = vi.hoisted(() => ({ mockDownload: vi.fn() }));

vi.mock("./trainingDetailExport", () => ({
  downloadTrainingDetail: (...args: unknown[]) => mockDownload(...args),
}));

vi.mock("antd", async (importOriginal) => {
  const actual = await importOriginal<typeof import("antd")>();
  const React = await import("react");
  type MockRangePickerProps = {
    disabled?: boolean;
    onChange?: (dates: [dayjs.Dayjs, dayjs.Dayjs] | null) => void;
    placeholder?: [string, string];
  };
  const RangePicker = ({ disabled, onChange, placeholder = ["开始日期", "结束日期"] }: MockRangePickerProps) => {
    const [values, setValues] = React.useState<[string, string]>(["", ""]);
    const update = (index: 0 | 1, value: string) => {
      const next: [string, string] = [...values];
      next[index] = value;
      setValues(next);
      onChange?.(next[0] && next[1] ? [dayjs(next[0]), dayjs(next[1])] : null);
    };
    return (
      <div>
        <input disabled={disabled} placeholder={placeholder[0]} value={values[0]} onChange={(event) => update(0, event.target.value)} />
        <input disabled={disabled} placeholder={placeholder[1]} value={values[1]} onChange={(event) => update(1, event.target.value)} />
      </div>
    );
  };
  return { ...actual, DatePicker: { ...actual.DatePicker, RangePicker } };
});

const patient = { id: 3, name: "合成患者", phone_masked: "138****0003" };
const projects = [
  {
    id: 8,
    project: 80,
    project_name: "认知研究 A",
    project_status: "completed",
    group: 1,
    group_name: "试验组",
    enrolled_at: "2026-01-01T00:00:00+08:00",
    project_completed_at: "2026-06-01T00:00:00+08:00",
  },
  {
    id: 9,
    project: 90,
    project_name: "运动研究 B",
    project_status: "active",
    group: 2,
    group_name: "对照组",
    enrolled_at: "2026-02-01T00:00:00+08:00",
    project_completed_at: null,
  },
];

function modalProps(overrides: Partial<React.ComponentProps<typeof TrainingDetailExportModal>> = {}) {
  return {
    open: true,
    onClose: vi.fn(),
    patient,
    projects,
    defaultProjectPatientId: 8,
    ...overrides,
  };
}

async function chooseRange(name: string) {
  fireEvent.click(screen.getByRole("radio", { name }));
  await waitFor(() => expect(screen.getByRole("radio", { name })).toBeChecked());
}

function fillCustomDates(start: string, end: string) {
  const startInput = screen.getByPlaceholderText("开始日期");
  const endInput = screen.getByPlaceholderText("结束日期");
  fireEvent.change(startInput, { target: { value: start } });
  fireEvent.keyDown(startInput, { key: "Enter", code: "Enter" });
  fireEvent.change(endInput, { target: { value: end } });
  fireEvent.keyDown(endInput, { key: "Enter", code: "Enter" });
}

describe("TrainingDetailExportModal", () => {
  beforeEach(() => {
    mockDownload.mockReset();
    mockDownload.mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("初次打开默认当前项目和近30天，并仅展示项目名称", async () => {
    const props = modalProps();
    render(<TrainingDetailExportModal {...props} />);

    expect(screen.getByText("合成患者（138****0003）")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "项目" })).toBeInTheDocument();
    expect(screen.getByText("认知研究 A")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "近30天" })).toBeChecked();
    expect(screen.queryByText("completed")).not.toBeInTheDocument();
    expect(screen.queryByText("已完结")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /导出 Excel$/ }));

    await waitFor(() => {
      expect(mockDownload).toHaveBeenCalledWith(3, { project_patient: 8, range: "30d" });
      expect(props.onClose).toHaveBeenCalledTimes(1);
    });
  });

  it("默认项目不存在时回退到首个可访问项目", async () => {
    render(<TrainingDetailExportModal {...modalProps({ defaultProjectPatientId: 404 })} />);

    fireEvent.click(screen.getByRole("button", { name: "导出 Excel" }));

    await waitFor(() => expect(mockDownload).toHaveBeenCalledWith(3, { project_patient: 8, range: "30d" }));
  });

  it("自定义日期缺失、未来或反向时禁用导出", async () => {
    render(<TrainingDetailExportModal {...modalProps()} />);
    await chooseRange("自定义");

    const exportButton = screen.getByRole("button", { name: "导出 Excel" });
    expect(screen.getByPlaceholderText("开始日期")).toBeInTheDocument();
    expect(exportButton).toBeDisabled();

    fillCustomDates("2099-01-01", "2099-01-02");
    await waitFor(() => expect(screen.getByText("日期不能晚于今天")).toBeInTheDocument());
    expect(exportButton).toBeDisabled();

    fillCustomDates("2026-05-03", "2026-05-01");
    await waitFor(() => expect(screen.getByText("结束日期不能早于开始日期")).toBeInTheDocument());
    expect(exportButton).toBeDisabled();
    expect(mockDownload).not.toHaveBeenCalled();
  });

  it("自定义日期按上海日历日格式发送且包含首尾", async () => {
    render(<TrainingDetailExportModal {...modalProps()} />);
    await chooseRange("自定义");
    fillCustomDates("2026-05-01", "2026-05-03");

    const exportButton = screen.getByRole("button", { name: "导出 Excel" });
    await waitFor(() => expect(exportButton).toBeEnabled());
    fireEvent.click(exportButton);

    await waitFor(() => {
      expect(mockDownload).toHaveBeenCalledWith(3, {
        project_patient: 8,
        range: "custom",
        start_date: "2026-05-01",
        end_date: "2026-05-03",
      });
    });
  });

  it("生成中同步锁阻止重复请求，并阻止按钮、遮罩和 Esc 关闭", async () => {
    let resolveDownload: (() => void) | undefined;
    mockDownload.mockReturnValue(new Promise<void>((resolve) => { resolveDownload = resolve; }));
    const props = modalProps();
    render(<TrainingDetailExportModal {...props} />);

    const exportButton = screen.getByRole("button", { name: "导出 Excel" });
    fireEvent.click(exportButton);
    fireEvent.click(exportButton);

    await waitFor(() => expect(mockDownload).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: /Cancel|取消/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Close|关闭/ })).not.toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape", code: "Escape" });
    expect(props.onClose).not.toHaveBeenCalled();

    resolveDownload?.();
    await waitFor(() => expect(props.onClose).toHaveBeenCalledTimes(1));
  });

  it("失败后保留筛选条件并显示安全错误，重试成功才关闭", async () => {
    mockDownload.mockRejectedValueOnce(new Error("导出数据过多，请缩小日期范围")).mockResolvedValueOnce(undefined);
    const props = modalProps();
    render(<TrainingDetailExportModal {...props} />);
    await chooseRange("近7天");

    fireEvent.click(screen.getByRole("button", { name: /导出 Excel$/ }));

    expect(await screen.findByText("导出数据过多，请缩小日期范围")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "近7天" })).toBeChecked();
    expect(props.onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "导出 Excel" }));
    await waitFor(() => expect(props.onClose).toHaveBeenCalledTimes(1));
  });

  it("旧患者下载迟到完成时不关闭或清除新患者会话", async () => {
    let resolveOld: (() => void) | undefined;
    let resolveNew: (() => void) | undefined;
    mockDownload
      .mockReturnValueOnce(new Promise<void>((resolve) => { resolveOld = resolve; }))
      .mockReturnValueOnce(new Promise<void>((resolve) => { resolveNew = resolve; }));
    const oldProps = modalProps();
    const { rerender } = render(<TrainingDetailExportModal {...oldProps} />);

    fireEvent.click(screen.getByRole("button", { name: "导出 Excel" }));
    await waitFor(() => expect(mockDownload).toHaveBeenCalledTimes(1));

    const newClose = vi.fn();
    rerender(
      <TrainingDetailExportModal
        {...modalProps({
          patient: { id: 4, name: "合成患者乙", phone_masked: "139****0004" },
          onClose: newClose,
          defaultProjectPatientId: 9,
        })}
      />,
    );
    expect(await screen.findByText("合成患者乙（139****0004）")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /导出 Excel$/ }));
    await waitFor(() => expect(mockDownload).toHaveBeenCalledTimes(2));

    resolveOld?.();
    await Promise.resolve();
    expect(newClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Cancel|取消/ })).toBeDisabled();

    resolveNew?.();
    await waitFor(() => expect(newClose).toHaveBeenCalledTimes(1));
  });

  it("组件卸载后忽略旧下载的迟到完成", async () => {
    let resolveDownload: (() => void) | undefined;
    mockDownload.mockReturnValue(new Promise<void>((resolve) => { resolveDownload = resolve; }));
    const props = modalProps();
    const { unmount } = render(<TrainingDetailExportModal {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "导出 Excel" }));
    await waitFor(() => expect(mockDownload).toHaveBeenCalledTimes(1));
    unmount();
    resolveDownload?.();
    await Promise.resolve();

    expect(props.onClose).not.toHaveBeenCalled();
  });
});
