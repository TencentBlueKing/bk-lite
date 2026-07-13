import React from 'react';
import { Spin } from 'antd';
import { AppstoreOutlined, CloseOutlined } from '@ant-design/icons';
import styles from '../index.module.scss';

interface TopologyCanvasShellProps {
  canvasContainerRef: React.RefObject<HTMLDivElement | null>;
  containerRef: React.RefObject<HTMLDivElement | null>;
  minimapContainerRef: React.RefObject<HTMLDivElement | null>;
  canvasHostRef: React.RefObject<HTMLDivElement | null>;
  isFullscreen: boolean;
  loading: boolean;
  minimapVisible: boolean;
  panelStyle: React.CSSProperties;
  t: (key: string) => string;
  setMinimapVisible: (visible: boolean) => void;
}

const TopologyCanvasShell = ({
  canvasContainerRef,
  containerRef,
  minimapContainerRef,
  canvasHostRef,
  isFullscreen,
  loading,
  minimapVisible,
  panelStyle,
  t,
  setMinimapVisible,
}: TopologyCanvasShellProps) => {
  const shouldShowMinimap = minimapVisible;

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
      {!isFullscreen && !minimapVisible && (
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
      ref={canvasHostRef}
      className="relative min-h-0 w-full flex-1 overflow-hidden"
    >
      <div className="h-full min-h-0 w-full">
        <div
          ref={canvasContainerRef}
          className="relative h-full min-h-0 w-full overflow-hidden"
          style={panelStyle}
        >
          {canvasInnerContent}
        </div>
      </div>
    </div>
  );
};

export default TopologyCanvasShell;
