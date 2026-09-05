import { Alert, Button, Radio, Skeleton, Space } from "antd";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

export type TrainingVideoSource = "original" | "skeleton";

type TrainingVideoSwitcherProps = {
  originalUrl: string | null;
  skeletonUrl: string | null;
  skeletonAvailable: boolean;
  resetKey: string | number;
  activeSource: TrainingVideoSource;
  onChange: (source: TrainingVideoSource) => void;
  originalLoading?: boolean;
  skeletonLoading?: boolean;
  originalError?: boolean;
  skeletonError?: boolean;
  onOriginalRetry?: () => void;
  onSkeletonRetry?: () => void;
};

type PlaybackSnapshot = {
  currentTime: number;
  paused: boolean;
};

type PlaybackTransaction = {
  generation: number;
  targetSource: TrainingVideoSource;
  snapshot: PlaybackSnapshot;
};

function snapshotPlayback(node: HTMLVideoElement | null): PlaybackSnapshot {
  const currentTime = node?.currentTime;
  return {
    currentTime: typeof currentTime === "number" && Number.isFinite(currentTime) && currentTime >= 0 ? currentTime : 0,
    paused: node?.paused ?? true,
  };
}

function clampedPlaybackTime(node: HTMLVideoElement, requested: number) {
  let lower = 0;
  let upper = Number.POSITIVE_INFINITY;
  if (Number.isFinite(node.duration) && node.duration > 0) {
    upper = Math.max(0, node.duration - 0.05);
  }
  try {
    if (node.seekable.length > 0) {
      lower = Math.max(0, node.seekable.start(0));
      const seekableEnd = node.seekable.end(node.seekable.length - 1);
      if (Number.isFinite(seekableEnd)) upper = Math.min(upper, Math.max(lower, seekableEnd - 0.05));
    }
  } catch {
    // 浏览器可能在元数据刚就绪时暂时拒绝读取 seekable，退回 duration 边界。
  }
  return Math.min(Math.max(requested, lower), upper);
}

function unload(node: HTMLVideoElement | null) {
  if (!node) return;
  node.pause();
  node.removeAttribute("src");
  node.load();
}

export function TrainingVideoSwitcher({
  originalUrl,
  skeletonUrl,
  skeletonAvailable,
  resetKey,
  activeSource,
  onChange,
  originalLoading = false,
  skeletonLoading = false,
  originalError = false,
  skeletonError = false,
  onOriginalRetry,
  onSkeletonRetry,
}: TrainingVideoSwitcherProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const playbackTransactionRef = useRef<PlaybackTransaction | null>(null);
  const transitionRef = useRef(0);
  const previousResetKeyRef = useRef(resetKey);
  const [mediaError, setMediaError] = useState(false);
  const [playbackWarning, setPlaybackWarning] = useState(false);

  const currentUrl = activeSource === "original" ? originalUrl : skeletonUrl;
  const loading = activeSource === "original" ? originalLoading : skeletonLoading;
  const requestError = activeSource === "original" ? originalError : skeletonError;

  useEffect(() => {
    if (previousResetKeyRef.current !== resetKey) {
      previousResetKeyRef.current = resetKey;
      playbackTransactionRef.current = null;
      transitionRef.current += 1;
      setMediaError(false);
      setPlaybackWarning(false);
      if (activeSource !== "original") onChange("original");
    }
  }, [activeSource, onChange, resetKey]);

  useEffect(() => {
    if (!skeletonAvailable && activeSource === "skeleton") {
      playbackTransactionRef.current = null;
      transitionRef.current += 1;
      setMediaError(false);
      setPlaybackWarning(false);
      onChange("original");
    }
  }, [activeSource, onChange, skeletonAvailable]);

  useLayoutEffect(() => {
    const node = videoRef.current;
    return () => {
      if (node && !playbackTransactionRef.current) {
        transitionRef.current += 1;
        playbackTransactionRef.current = {
          generation: transitionRef.current,
          targetSource: activeSource,
          snapshot: snapshotPlayback(node),
        };
      }
      unload(node);
    };
  }, [activeSource, currentUrl]);

  const changeSource = (source: TrainingVideoSource) => {
    if (source === activeSource || (source === "skeleton" && !skeletonAvailable)) return;
    const node = videoRef.current;
    transitionRef.current += 1;
    playbackTransactionRef.current = {
      generation: transitionRef.current,
      targetSource: source,
      snapshot: playbackTransactionRef.current?.snapshot ?? snapshotPlayback(node),
    };
    setMediaError(false);
    setPlaybackWarning(false);
    onChange(source);
  };

  const restorePlayback = async (
    node: HTMLVideoElement,
    source: TrainingVideoSource,
  ) => {
    const transaction = playbackTransactionRef.current;
    if (!transaction || transaction.targetSource !== source || videoRef.current !== node) return;
    try {
      node.currentTime = clampedPlaybackTime(node, transaction.snapshot.currentTime);
    } catch {
      // 部分浏览器会在元数据不足时拒绝 seek；播放器仍可从起点安全播放。
    }
    if (transaction.snapshot.paused) {
      node.pause();
      if (playbackTransactionRef.current === transaction) playbackTransactionRef.current = null;
      return;
    }
    try {
      await node.play();
      if (playbackTransactionRef.current === transaction) playbackTransactionRef.current = null;
    } catch {
      if (playbackTransactionRef.current !== transaction || videoRef.current !== node) return;
      playbackTransactionRef.current = null;
      node.pause();
      setPlaybackWarning(true);
    }
  };

  const retry = () => {
    setMediaError(false);
    setPlaybackWarning(false);
    if (activeSource === "original") onOriginalRetry?.();
    else onSkeletonRetry?.();
  };

  const loadErrorMessage = activeSource === "skeleton"
    ? "骨架视频地址已失效或加载失败"
    : "原视频地址已失效或加载失败";

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <div className="training-video-switcher-toolbar">
        <Radio.Group
          aria-label="视频来源"
          optionType="button"
          buttonStyle="solid"
          value={activeSource}
          onChange={(event) => changeSource(event.target.value as TrainingVideoSource)}
        >
          <Radio value="original">原视频</Radio>
          <Radio value="skeleton" disabled={!skeletonAvailable}>骨架视频</Radio>
        </Radio.Group>
        {!skeletonAvailable ? <span className="training-video-hint">骨架视频将在自动分析成功后提供</span> : null}
      </div>

      <div className="training-video-stage">
        {loading && !currentUrl ? (
          <Skeleton active paragraph={{ rows: 6 }} title={false} />
        ) : requestError || mediaError ? (
          <Alert
            type="error"
            showIcon
            message={loadErrorMessage}
            action={(activeSource === "original" ? onOriginalRetry : onSkeletonRetry) ? (
              <Button size="small" onClick={retry}>
                {activeSource === "skeleton" ? "重新获取骨架视频" : "重新获取原视频"}
              </Button>
            ) : null}
          />
        ) : currentUrl ? (
          <video
            key={`${activeSource}:${currentUrl}`}
            ref={videoRef}
            aria-label={activeSource === "skeleton" ? "骨架视频播放器" : "原视频播放器"}
            controls
            preload="metadata"
            src={currentUrl}
            onLoadedMetadata={(event) => void restorePlayback(event.currentTarget, activeSource)}
            onError={(event) => {
              transitionRef.current += 1;
              playbackTransactionRef.current = {
                generation: transitionRef.current,
                targetSource: activeSource,
                snapshot: snapshotPlayback(event.currentTarget),
              };
              unload(event.currentTarget);
              setMediaError(true);
            }}
          />
        ) : null}
      </div>

      {playbackWarning ? <Alert type="warning" showIcon message="浏览器未能继续播放，视频已保持暂停" /> : null}
    </Space>
  );
}
