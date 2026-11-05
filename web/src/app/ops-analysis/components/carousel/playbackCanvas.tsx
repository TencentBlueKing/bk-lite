'use client';

import React from 'react';
import { Spin } from 'antd';
import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';
import type { DirItem } from '@/app/ops-analysis/types';
import Dashboard from '@/app/ops-analysis/(pages)/view/dashBoard';
import Topology from '@/app/ops-analysis/(pages)/view/topology';
import Architecture from '@/app/ops-analysis/(pages)/view/architecture';
import Screen from '@/app/ops-analysis/(pages)/view/screen';
import Report from '@/app/ops-analysis/(pages)/view/report';
import NetworkTopology from '@/app/ops-analysis/(pages)/view/networkTopology';
import { PlaybackInitialDetailProvider } from '@/app/ops-analysis/context/playbackInitialDetail';
import { playbackCanvasKey } from './playbackStage';

export interface PlaybackSlide {
  key: string;
  resourceType: CanvasType;
  canvasId: number;
  name: string;
  dwellSeconds: number;
  available: boolean;
}

const toDirItem = (slide: PlaybackSlide): DirItem => ({
  id: `${slide.resourceType}_${slide.canvasId}`,
  data_id: String(slide.canvasId),
  name: slide.name,
  type: slide.resourceType,
});

const PlaybackCanvas = ({
  slide,
  presentFullscreen = false,
}: {
  slide: PlaybackSlide;
  presentFullscreen?: boolean;
}) => {
  const item = toDirItem(slide);
  // 同类型换盘必须重挂页面：Room3D / Isoflow / X6 在卸载时 dispose。
  // visit 不在键里，同一张盘的再次确认不会拆实例。
  const canvasKey = playbackCanvasKey(slide);
  switch (slide.resourceType) {
    case 'dashboard':
      return <Dashboard key={canvasKey} selectedDashboard={item} playbackMode />;
    case 'topology':
      return <Topology key={canvasKey} selectedTopology={item} playbackMode />;
    case 'architecture':
      return <Architecture key={canvasKey} selectedArchitecture={item} playbackMode />;
    case 'screen':
      return (
        <Screen
          key={canvasKey}
          selectedScreen={item}
          playbackMode
          playbackFullscreen={presentFullscreen}
        />
      );
    case 'report':
      return <Report key={canvasKey} selectedReport={item} playbackMode />;
    case 'networkTopology':
      return <NetworkTopology key={canvasKey} selectedNetworkTopology={item} playbackMode />;
    default:
      return null;
  }
};

interface BoundaryProps {
  slideKey: string;
  onError: () => void;
  children: React.ReactNode;
}

interface BoundaryState {
  failedKey: string | null;
}

class PlaybackCanvasBoundary extends React.Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { failedKey: null };

  static getDerivedStateFromError(): BoundaryState {
    return { failedKey: 'error' };
  }

  componentDidCatch() {
    this.props.onError();
  }

  componentDidUpdate(previous: BoundaryProps) {
    if (previous.slideKey !== this.props.slideKey && this.state.failedKey) {
      this.setState({ failedKey: null });
    }
  }

  render() {
    if (this.state.failedKey) {
      return (
        <div className="flex h-full items-center justify-center">
          <Spin />
        </div>
      );
    }
    return this.props.children;
  }
}

interface PlaybackSlideFrameProps {
  slide: PlaybackSlide;
  initialDetail: unknown;
  onError: () => void;
  presentFullscreen?: boolean;
}

const samePlaybackFrame = (
  previous: PlaybackSlideFrameProps,
  next: PlaybackSlideFrameProps,
): boolean => (
  previous.slide.key === next.slide.key
  && previous.slide.resourceType === next.slide.resourceType
  && previous.slide.canvasId === next.slide.canvasId
  && previous.slide.name === next.slide.name
  && previous.slide.available === next.slide.available
  && previous.initialDetail === next.initialDetail
  && previous.presentFullscreen === next.presentFullscreen
  && previous.onError === next.onError
);

export const PlaybackSlideFrame = React.memo(function PlaybackSlideFrame({
  slide,
  initialDetail,
  onError,
  presentFullscreen = false,
}: PlaybackSlideFrameProps) {
  const seeded = React.useMemo(() => ({
    resourceType: slide.resourceType,
    canvasId: slide.canvasId,
    detail: initialDetail,
  }), [initialDetail, slide.canvasId, slide.resourceType]);
  return (
    <PlaybackInitialDetailProvider value={seeded}>
      <PlaybackCanvasBoundary slideKey={slide.key} onError={onError}>
        <PlaybackCanvas slide={slide} presentFullscreen={presentFullscreen} />
      </PlaybackCanvasBoundary>
    </PlaybackInitialDetailProvider>
  );
}, samePlaybackFrame);

export default PlaybackCanvas;
