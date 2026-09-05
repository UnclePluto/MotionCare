import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TrainingVideoSwitcher, type TrainingVideoSource } from "./TrainingVideoSwitcher";

function ControlledSwitcher({
  originalUrl = "original",
  skeletonUrl = "skeleton",
  skeletonAvailable = true,
  resetKey = "video-1",
  onSkeletonRetry,
}: {
  originalUrl?: string | null;
  skeletonUrl?: string | null;
  skeletonAvailable?: boolean;
  resetKey?: string;
  onSkeletonRetry?: () => void;
}) {
  const [activeSource, setActiveSource] = React.useState<TrainingVideoSource>("original");
  return (
    <TrainingVideoSwitcher
      originalUrl={originalUrl}
      skeletonUrl={skeletonUrl}
      skeletonAvailable={skeletonAvailable}
      resetKey={resetKey}
      activeSource={activeSource}
      onChange={setActiveSource}
      onSkeletonRetry={onSkeletonRetry}
    />
  );
}

function ErrorRetrySwitcher() {
  const [originalUrl, setOriginalUrl] = React.useState("original-v1");
  const [activeSource, setActiveSource] = React.useState<TrainingVideoSource>("original");
  return (
    <TrainingVideoSwitcher
      originalUrl={originalUrl}
      skeletonUrl="skeleton"
      skeletonAvailable
      resetKey="video-1"
      activeSource={activeSource}
      onChange={setActiveSource}
      onOriginalRetry={() => setOriginalUrl("original-v2")}
    />
  );
}

function setMediaState(node: HTMLVideoElement, state: { currentTime: number; paused: boolean }) {
  Object.defineProperty(node, "currentTime", { configurable: true, writable: true, value: state.currentTime });
  Object.defineProperty(node, "paused", { configurable: true, get: () => state.paused });
}

describe("TrainingVideoSwitcher", () => {
  beforeEach(() => {
    vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("切换骨架视频时复制 currentTime 和暂停状态", async () => {
    render(<ControlledSwitcher />);
    const original = screen.getByLabelText("原视频播放器") as HTMLVideoElement;
    setMediaState(original, { currentTime: 42.5, paused: true });

    fireEvent.click(screen.getByRole("radio", { name: "骨架视频" }));
    const skeleton = screen.getByLabelText("骨架视频播放器") as HTMLVideoElement;
    fireEvent.loadedMetadata(skeleton);

    expect(skeleton.currentTime).toBeCloseTo(42.5);
    expect(skeleton.pause).toHaveBeenCalled();
    expect(skeleton.play).not.toHaveBeenCalled();
  });

  it("切换时恢复播放，play 被拒绝则保持暂停并给出提示", async () => {
    vi.mocked(window.HTMLMediaElement.prototype.play).mockRejectedValueOnce(new DOMException("blocked"));
    render(<ControlledSwitcher />);
    const original = screen.getByLabelText("原视频播放器") as HTMLVideoElement;
    setMediaState(original, { currentTime: 17, paused: false });

    fireEvent.click(screen.getByRole("radio", { name: "骨架视频" }));
    fireEvent.loadedMetadata(screen.getByLabelText("骨架视频播放器"));

    expect(await screen.findByText("浏览器未能继续播放，视频已保持暂停")).toBeInTheDocument();
    expect(window.HTMLMediaElement.prototype.pause).toHaveBeenCalled();
  });

  it("骨架不可用时禁用切换并提供文字说明", () => {
    render(<ControlledSwitcher skeletonAvailable={false} skeletonUrl={null} />);

    expect(screen.getByRole("radio", { name: "骨架视频" })).toBeDisabled();
    expect(screen.getByText("骨架视频将在自动分析成功后提供")).toBeInTheDocument();
  });

  it("骨架短期地址加载失败时不显示 URL，并允许重新获取", async () => {
    const onSkeletonRetry = vi.fn();
    render(<ControlledSwitcher onSkeletonRetry={onSkeletonRetry} />);

    fireEvent.click(screen.getByRole("radio", { name: "骨架视频" }));
    fireEvent.error(screen.getByLabelText("骨架视频播放器"));

    expect(await screen.findByText("骨架视频地址已失效或加载失败")).toBeInTheDocument();
    expect(screen.queryByText("skeleton")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新获取骨架视频" }));
    expect(onSkeletonRetry).toHaveBeenCalledTimes(1);
  });

  it("更换训练记录会卸载旧播放器并回到原视频", async () => {
    const { rerender } = render(<ControlledSwitcher />);
    fireEvent.click(screen.getByRole("radio", { name: "骨架视频" }));
    expect(screen.getByLabelText("骨架视频播放器")).toBeInTheDocument();

    rerender(<ControlledSwitcher resetKey="video-2" />);

    await waitFor(() => expect(screen.getByRole("radio", { name: "原视频" })).toBeChecked());
    expect(screen.getByLabelText("原视频播放器")).toHaveAttribute("src", "original");
    expect(window.HTMLMediaElement.prototype.pause).toHaveBeenCalled();
    expect(window.HTMLMediaElement.prototype.load).toHaveBeenCalled();
  });

  it("骨架能力失效时自动回到原视频", async () => {
    const { rerender } = render(<ControlledSwitcher />);
    fireEvent.click(screen.getByRole("radio", { name: "骨架视频" }));
    expect(screen.getByLabelText("骨架视频播放器")).toBeInTheDocument();

    rerender(<ControlledSwitcher skeletonAvailable={false} />);

    await waitFor(() => expect(screen.getByRole("radio", { name: "原视频" })).toBeChecked());
    expect(screen.getByLabelText("原视频播放器")).toBeInTheDocument();
  });

  it("同一来源签名 URL 更新后恢复当前时间和播放状态", async () => {
    const { rerender } = render(<ControlledSwitcher originalUrl="original-v1" />);
    const original = screen.getByLabelText("原视频播放器") as HTMLVideoElement;
    setMediaState(original, { currentTime: 23, paused: false });

    rerender(<ControlledSwitcher originalUrl="original-v2" />);
    const refreshed = screen.getByLabelText("原视频播放器") as HTMLVideoElement;
    Object.defineProperty(refreshed, "duration", { configurable: true, value: 60 });
    fireEvent.loadedMetadata(refreshed);

    expect(refreshed.currentTime).toBe(23);
    expect(refreshed.play).toHaveBeenCalled();
  });

  it("目标元数据未加载时快速往返仍使用最初播放快照", async () => {
    render(<ControlledSwitcher />);
    const original = screen.getByLabelText("原视频播放器") as HTMLVideoElement;
    setMediaState(original, { currentTime: 42, paused: false });

    fireEvent.click(screen.getByRole("radio", { name: "骨架视频" }));
    const staleSkeleton = screen.getByLabelText("骨架视频播放器") as HTMLVideoElement;
    fireEvent.click(screen.getByRole("radio", { name: "原视频" }));
    const restoredOriginal = screen.getByLabelText("原视频播放器") as HTMLVideoElement;
    Object.defineProperty(restoredOriginal, "duration", { configurable: true, value: 90 });

    fireEvent.loadedMetadata(staleSkeleton);
    fireEvent.loadedMetadata(restoredOriginal);

    await waitFor(() => expect(restoredOriginal.currentTime).toBe(42));
    expect(restoredOriginal.play).toHaveBeenCalled();
  });

  it("恢复时间会过滤非有限负值并限制在目标视频时长内", () => {
    const { rerender } = render(<ControlledSwitcher originalUrl="original-v1" />);
    const original = screen.getByLabelText("原视频播放器") as HTMLVideoElement;
    setMediaState(original, { currentTime: 42, paused: true });
    rerender(<ControlledSwitcher originalUrl="original-v2" />);
    const shorter = screen.getByLabelText("原视频播放器") as HTMLVideoElement;
    Object.defineProperty(shorter, "duration", { configurable: true, value: 10 });
    fireEvent.loadedMetadata(shorter);
    expect(shorter.currentTime).toBeLessThan(10);
    expect(shorter.currentTime).toBeGreaterThanOrEqual(9.9);
  });

  it.each([Number.NaN, -4])("恢复时间会把非有限或负值 %s 安全归零", (invalidTime) => {
    const { rerender } = render(<ControlledSwitcher originalUrl="original-v1" />);
    const original = screen.getByLabelText("原视频播放器") as HTMLVideoElement;
    setMediaState(original, { currentTime: invalidTime, paused: true });
    rerender(<ControlledSwitcher originalUrl="original-v2" />);
    const refreshed = screen.getByLabelText("原视频播放器") as HTMLVideoElement;
    Object.defineProperty(refreshed, "duration", { configurable: true, value: 30 });

    fireEvent.loadedMetadata(refreshed);

    expect(refreshed.currentTime).toBe(0);
  });

  it("媒体加载错误时立即卸载失败节点", () => {
    render(<ControlledSwitcher />);
    const video = screen.getByLabelText("原视频播放器") as HTMLVideoElement;

    fireEvent.error(video);

    expect(video.pause).toHaveBeenCalled();
    expect(video.load).toHaveBeenCalled();
    expect(video).not.toHaveAttribute("src");
  });

  it("媒体错误重取同源 URL 后恢复错误前的时间和播放状态", async () => {
    vi.mocked(window.HTMLMediaElement.prototype.load).mockImplementation(function resetMedia(this: HTMLMediaElement) {
      Object.defineProperty(this, "currentTime", { configurable: true, writable: true, value: 0 });
      Object.defineProperty(this, "paused", { configurable: true, get: () => true });
    });
    render(<ErrorRetrySwitcher />);
    const failedVideo = screen.getByLabelText("原视频播放器") as HTMLVideoElement;
    setMediaState(failedVideo, { currentTime: 27, paused: false });

    fireEvent.error(failedVideo);
    fireEvent.click(await screen.findByRole("button", { name: "重新获取原视频" }));
    const recoveredVideo = await screen.findByLabelText("原视频播放器") as HTMLVideoElement;
    Object.defineProperty(recoveredVideo, "duration", { configurable: true, value: 20 });
    fireEvent.loadedMetadata(recoveredVideo);

    expect(recoveredVideo.currentTime).toBeGreaterThanOrEqual(19.9);
    expect(recoveredVideo.currentTime).toBeLessThan(20);
    expect(recoveredVideo.play).toHaveBeenCalled();
  });
});
