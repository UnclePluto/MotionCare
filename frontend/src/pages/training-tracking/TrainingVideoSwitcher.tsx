import { Alert, Button, Radio, Skeleton, Space } from "antd";
import { useEffect, useRef, useState } from "react";

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
  const playbackRef = useRef<PlaybackSnapshot | null>(null);
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
      playbackRef.current = null;
      transitionRef.current += 1;
      setMediaError(false);
      setPlaybackWarning(false);
      if (activeSource !== "original") onChange("original");
    }
  }, [activeSource, onChange, resetKey]);

  useEffect(() => {
    if (!skeletonAvailable && activeSource === "skeleton") {
      playbackRef.current = null;
      transitionRef.current += 1;
      setMediaError(false);
      setPlaybackWarning(false);
      onChange("original");
    }
  }, [activeSource, onChange, skeletonAvailable]);

  useEffect(() => {
    const node = videoRef.current;
    return () => unload(node);
  }, [currentUrl]);

  const changeSource = (source: TrainingVideoSource) => {
    if (source === activeSource || (source === "skeleton" && !skeletonAvailable)) return;
    const node = videoRef.current;
    playbackRef.current = node
      ? { currentTime: node.currentTime, paused: node.paused }
      : { currentTime: 0, paused: true };
    transitionRef.current += 1;
    setMediaError(false);
    setPlaybackWarning(false);
    onChange(source);
  };

  const restorePlayback = async (node: HTMLVideoElement) => {
    const snapshot = playbackRef.current;
    if (!snapshot) return;
    const transition = transitionRef.current;
    try {
      node.currentTime = snapshot.currentTime;
    } catch {
      // 部分浏览器会在元数据不足时拒绝 seek；播放器仍可从起点安全播放。
    }
    if (snapshot.paused) {
      node.pause();
      return;
    }
    try {
      await node.play();
    } catch {
      if (transition !== transitionRef.current) return;
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
            onLoadedMetadata={(event) => void restorePlayback(event.currentTarget)}
            onError={() => setMediaError(true)}
          />
        ) : null}
      </div>

      {playbackWarning ? <Alert type="warning" showIcon message="浏览器未能继续播放，视频已保持暂停" /> : null}
    </Space>
  );
}
