import type { PlaybackSlide } from '@/app/ops-analysis/components/carousel/playbackCanvas';

/**
 * 切张舞台：同类型不因 visit 拆壳。
 * 画布实例键含 canvasId，换盘时重挂以释放 WebGL / X6 / Isoflow。
 * visit 不进入任一键。
 */
export interface HeldPlaybackFrame {
  slide: PlaybackSlide;
  detail: unknown;
}

export type PlaybackStageResolution =
  | { kind: 'unavailable' }
  | { kind: 'pending' }
  | {
    kind: 'frame';
    slide: PlaybackSlide;
    detail: unknown;
    shellKey: string;
    canvasKey: string;
    holding: boolean;
  };

export const playbackShellKey = (resourceType: string): string => resourceType;

export const playbackCanvasKey = (
  slide: Pick<PlaybackSlide, 'resourceType' | 'canvasId'>,
): string => `${slide.resourceType}:${slide.canvasId}`;

export type PlaybackFrameErrorDecision =
  | { type: 'release-hold' }
  | { type: 'mark-unavailable'; key: string };

/**
 * 保留上一帧时画布出错：撤下保留帧，舞台回到 pending，避免错误边界留白。
 * 当前帧出错仍标记不可用并跳过。
 */
export const reducePlaybackFrameError = (
  holding: boolean,
  slideKey: string,
): PlaybackFrameErrorDecision | null => {
  if (holding) {
    return { type: 'release-hold' };
  }
  if (!slideKey) {
    return null;
  }
  return { type: 'mark-unavailable', key: slideKey };
};

const paintFrame = (
  slide: PlaybackSlide,
  detail: unknown,
  holding: boolean,
): PlaybackStageResolution => ({
  kind: 'frame',
  slide,
  detail,
  shellKey: playbackShellKey(slide.resourceType),
  canvasKey: playbackCanvasKey(slide),
  holding,
});

/**
 * 已确认，或详情缓存命中：立刻画目标盘。
 * 同类型尚未拿到详情：留着上一帧，避免空 Spin。
 * 跨类型且没有缓存：允许整段等待（pending）。
 */
export const resolvePlaybackStage = ({
  slide,
  ready,
  confirmedDetail,
  cached,
  held,
}: {
  slide: PlaybackSlide | undefined;
  ready: boolean;
  confirmedDetail: unknown;
  cached: { hit: true; detail: unknown } | { hit: false };
  held: HeldPlaybackFrame | null;
}): PlaybackStageResolution => {
  if (!slide?.available) {
    return { kind: 'unavailable' };
  }
  if (ready) {
    return paintFrame(slide, confirmedDetail, false);
  }
  if (cached.hit) {
    return paintFrame(slide, cached.detail, false);
  }
  if (held && held.slide.resourceType === slide.resourceType) {
    return paintFrame(held.slide, held.detail, true);
  }
  return { kind: 'pending' };
};
