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
});
