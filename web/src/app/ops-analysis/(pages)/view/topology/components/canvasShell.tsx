import React from 'react';
import { Spin } from 'antd';
import { AppstoreOutlined, CloseOutlined } from '@ant-design/icons';
import type { TopologyViewportConfig } from '@/app/ops-analysis/types/topology';
import styles from '../index.module.scss';

interface TopologyCanvasShellProps {
  canvasContainerRef: React.RefObject<HTMLDivElement | null>;
  containerRef: React.RefObject<HTMLDivElement | null>;
  minimapContainerRef: React.RefObject<HTMLDivElement | null>;
  presentationHostRef: React.RefObject<HTMLDivElement | null>;
  isFullscreen: boolean;
  isLetterboxFullscreen: boolean;
  isEditMode: boolean;
  loading: boolean;
  minimapVisible: boolean;
  presentationMode?: boolean;
  normalizedViewport: TopologyViewportConfig | null;
  letterboxLayout?: {
    renderedWidth: number;
    renderedHeight: number;
  } | null;
  panelStyle: React.CSSProperties;
  viewportGuideTransform: string;
  t: (key: string) => string;
  setMinimapVisible: (visible: boolean) => void;
}

const TopologyCanvasShell = ({
  canvasContainerRef,
  containerRef,
  minimapContainerRef,
  presentationHostRef,
  isFullscreen,
  isLetterboxFullscreen,
  isEditMode,
  loading,
  minimapVisible,
  presentationMode = false,
  normalizedViewport,
  letterboxLayout,
  panelStyle,
  viewportGuideTransform,
  t,
  setMinimapVisible,
}: TopologyCanvasShellProps) => {
  const shouldShowMinimap =
    minimapVisible && !presentationMode && !(isFullscreen && normalizedViewport);

  const viewportGuideOverlay =
    isEditMode && normalizedViewport && !isLetterboxFullscreen ? (
      <div
        className="absolute inset-0"
        style={{ pointerEvents: 'none', zIndex: 5 }}
      >
        <svg className="h-full w-full overflow-visible">
          <g transform={viewportGuideTransform || undefined}>
            <rect
              x={0}
              y={0}
              width={normalizedViewport.width}
              height={normalizedViewport.height}
              fill="none"
              stroke="rgba(92, 117, 153, 0.56)"
              strokeDasharray="6 8"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
          </g>
        </svg>
      </div>
    ) : null;

  const canvasInnerContent = (
    <>
      {loading && (
        <div
          className="absolute inset-0 flex items-center justify-center backdrop-blur-sm z-10"
          style={{
            backgroundColor: 'var(--color-bg-1)',
            opacity: 0.8,
          }}
        >
          <Spin size="large" />
        </div>
      )}
      {viewportGuideOverlay}
      <div ref={containerRef} className="absolute inset-0" tabIndex={-1} />

      <div
        className={styles.minimapContainer}
        style={{ display: shouldShowMinimap ? 'block' : 'none' }}
      >
        <div className={styles.minimapHeader}>
          <button
            onClick={() => setMinimapVisible(false)}
            className={styles.minimapCloseBtn}
            title={t('topology.minimapCollapse')}
          >
            <CloseOutlined />
          </button>
        </div>
        <div ref={minimapContainerRef} className={styles.minimapContent} />
      </div>
      {!isFullscreen && !presentationMode && !minimapVisible && (
        <button
          onClick={() => setMinimapVisible(true)}
          className={styles.minimapShowBtn}
          title={t('topology.minimapShow')}
        >
          <AppstoreOutlined />
        </button>
      )}
    </>
  );

  return (
    <div
      ref={presentationHostRef}
      className={`flex-1 overflow-hidden ${
        isLetterboxFullscreen ? 'flex items-center justify-center' : 'relative'
      }`}
      style={
        isLetterboxFullscreen && normalizedViewport
          ? {
            backgroundColor: normalizedViewport.letterboxColor || '#000000',
          }
          : undefined
      }
    >
      <div
        className={
          isLetterboxFullscreen
            ? 'relative shrink-0 overflow-hidden'
            : 'h-full w-full'
        }
        style={
          isLetterboxFullscreen && normalizedViewport
            ? {
              width:
                  letterboxLayout?.renderedWidth || normalizedViewport.width,
              height:
                  letterboxLayout?.renderedHeight || normalizedViewport.height,
            }
            : undefined
        }
      >
        <div
          ref={canvasContainerRef}
          className={`relative overflow-hidden ${
            isLetterboxFullscreen ? '' : 'h-full w-full'
          } ${isFullscreen ? 'rounded-none' : 'rounded-xl'}`}
          style={{
            ...panelStyle,
            ...(isLetterboxFullscreen && normalizedViewport
              ? {
                width:
                    letterboxLayout?.renderedWidth || normalizedViewport.width,
                height:
                    letterboxLayout?.renderedHeight ||
                    normalizedViewport.height,
              }
              : {}),
          }}
        >
          {canvasInnerContent}
        </div>
      </div>
    </div>
  );
};

export default TopologyCanvasShell;
