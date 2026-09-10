import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/client";
import { downloadTrainingDetail } from "./trainingDetailExport";

vi.mock("../../api/client", () => ({
  apiClient: { post: vi.fn() },
}));

function jsonErrorBlob(detail: string) {
  const blob = new Blob([], { type: "application/json" });
  Object.defineProperty(blob, "text", {
    value: vi.fn().mockResolvedValue(JSON.stringify({ detail })),
  });
  return blob;
}

describe("downloadTrainingDetail", () => {
  let clickSpy: ReturnType<typeof vi.spyOn>;
  let removeSpy: ReturnType<typeof vi.spyOn>;
  let createObjectUrl: ReturnType<typeof vi.fn>;
  let revokeObjectUrl: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(apiClient.post).mockReset();
    createObjectUrl = vi.fn().mockReturnValue("blob:training-detail");
    revokeObjectUrl = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectUrl });
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    removeSpy = vi.spyOn(HTMLAnchorElement.prototype, "remove");
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("使用后端 UTF-8 文件名下载非空 Excel，并在下一任务清理临时资源", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: new Blob(["xlsx"], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
      headers: {
        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "content-disposition": "attachment; filename*=UTF-8''%E6%82%A3%E8%80%85_3_%E8%AE%AD%E7%BB%83%E6%98%8E%E7%BB%86.xlsx",
      },
    });

    await downloadTrainingDetail(3, { project_patient: 8, range: "30d" });

    expect(apiClient.post).toHaveBeenCalledWith(
      "/training/tracking/patients/3/export/",
      { project_patient: 8, range: "30d" },
      { responseType: "blob", timeout: 75_000 },
    );
    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(document.querySelector('a[download="患者_3_训练明细.xlsx"]')).not.toBeNull();
    expect(revokeObjectUrl).not.toHaveBeenCalled();
    expect(removeSpy).not.toHaveBeenCalled();

    await vi.runAllTimersAsync();

    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:training-detail");
    expect(removeSpy).toHaveBeenCalledTimes(1);
    expect(document.querySelector('a[download="患者_3_训练明细.xlsx"]')).toBeNull();
  });

  it("JSON 错误不会被保存为 Excel", async () => {
    vi.mocked(apiClient.post).mockRejectedValue({
      response: {
        headers: { "content-type": "application/json" },
        data: jsonErrorBlob("导出数据过多，请缩小日期范围"),
      },
    });

    await expect(downloadTrainingDetail(3, { project_patient: 8, range: "all" })).rejects.toThrow(
      "导出数据过多，请缩小日期范围",
    );
    expect(createObjectUrl).not.toHaveBeenCalled();
    expect(clickSpy).not.toHaveBeenCalled();
  });

  it("拒绝把敏感后端异常原文展示给用户", async () => {
    vi.mocked(apiClient.post).mockRejectedValue({
      response: {
        headers: { "content-type": "application/json; charset=utf-8" },
        data: jsonErrorBlob("https://private.example/export?token=secret"),
      },
    });

    await expect(downloadTrainingDetail(3, { project_patient: 8, range: "7d" })).rejects.toThrow(
      "导出失败，请稍后重试",
    );
    expect(createObjectUrl).not.toHaveBeenCalled();
  });

  it("错误 MIME 或空响应不会触发下载", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: new Blob([], { type: "text/html" }),
      headers: { "content-type": "text/html" },
    });

    await expect(downloadTrainingDetail(3, { project_patient: 8, range: "30d" })).rejects.toThrow(
      "导出失败，请稍后重试",
    );
    expect(createObjectUrl).not.toHaveBeenCalled();
  });

  it("文件名解码失败时使用安全回退名", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: new Blob(["xlsx"], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
      headers: {
        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "content-disposition": "attachment; filename*=UTF-8''%E0%A4%A",
      },
    });

    await downloadTrainingDetail(3, { project_patient: 8, range: "custom", start_date: "2026-09-01", end_date: "2026-09-09" });

    expect(document.querySelector('a[download="患者编号_训练明细.xlsx"]')).not.toBeNull();
  });

  it("清除响应文件名中的路径分隔符和控制字符", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: new Blob(["xlsx"], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }),
      headers: {
        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "content-disposition": 'attachment; filename="../患者\\训练\u0007.xlsx"',
      },
    });

    await downloadTrainingDetail(3, { project_patient: 8, range: "7d" });

    expect(document.querySelector('a[download=".._患者_训练_.xlsx"]')).not.toBeNull();
  });

  it("触发浏览器下载异常时仍延迟清理临时资源", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: new Blob(["xlsx"], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }),
      headers: { "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
    });
    clickSpy.mockImplementationOnce(() => { throw new Error("browser blocked"); });

    await expect(downloadTrainingDetail(3, { project_patient: 8, range: "30d" })).rejects.toThrow(
      "导出失败，请稍后重试",
    );
    expect(revokeObjectUrl).not.toHaveBeenCalled();

    await vi.runAllTimersAsync();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:training-detail");
    expect(removeSpy).toHaveBeenCalledTimes(1);
  });
});
