import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { message } from 'antd';
import type { TopologyViewportConfig } from '@/app/ops-analysis/types/topology';
import {
  buildTopologyLetterboxLayout,
  buildTopologyViewportFocusTransform,
  getTopologyViewportDraft,
  normalizeTopologyViewportConfig,
} from '../utils/viewport';

export const PRESENTATION_PRESETS = [
  { key: '1366x768', width: 1366, height: 768, label: '1366 x 768' },
  { key: '1600x900', width: 1600, height: 900, label: '1600 x 900' },
  { key: '1920x1080', width: 1920, height: 1080, label: '1920 x 1080' },
  { key: '2560x1440', width: 2560, height: 1440, label: '2560 x 1440' },
];

interface UseTopologyPresentationParams {
  graphInstance: unknown;
  isEditMode: boolean;
  toggleEditMode: () => void;
  viewportConfig: TopologyViewportConfig;
  setViewportConfig: (value: TopologyViewportConfig) => void;
  containerRef: React.RefObject<HTMLDivElement | null>;
  canvasContainerRef: React.RefObject<HTMLDivElement | null>;
  presentationHostRef: React.RefObject<HTMLDivElement | null>;
  resizeCanvas: (width: number, height: number) => void;
  handleCanvasResize: () => void;
  isFullscreen: boolean;
  enterFullscreen: () => void;
  exitFullscreen: () => void;
  t: (key: string) => string;
}

export const useTopologyPresentation = ({
  graphInstance,
  isEditMode,
  toggleEditMode,
  viewportConfig,
  setViewportConfig,
  containerRef,
  canvasContainerRef,
  presentationHostRef,
  resizeCanvas,
  handleCanvasResize,
  isFullscreen,
  enterFullscreen,
  exitFullscreen,
  t,
}: UseTopologyPresentationParams) => {
  const fullscreenViewportSnapshotRef = useRef<{
    zoom: number;
    tx: number;
    ty: number;
  } | null>(null);
  const resumeEditModeAfterFullscreenRef = useRef(false);
  const [presentationConfigModalVisible, setPresentationConfigModalVisible] =
    useState(false);
  const [presentationConfigDraft, setPresentationConfigDraft] =
    useState<TopologyViewportConfig>(() => getTopologyViewportDraft(null));
  const [viewportGuideTransform, setViewportGuideTransform] = useState('');
  const [presentationBounds, setPresentationBounds] = useState({
    width: 0,
    height: 0,
  });

  const normalizedViewport = useMemo(
    () => normalizeTopologyViewportConfig(viewportConfig),
    [viewportConfig],
  );
  const isLetterboxFullscreen = isFullscreen && Boolean(normalizedViewport);
  const letterboxLayout = useMemo(
    () =>
      buildTopologyLetterboxLayout(
        presentationBounds.width,
        presentationBounds.height,
        normalizedViewport,
      ),
    [normalizedViewport, presentationBounds.height, presentationBounds.width],
  );
  const activePresentationPresetKey = useMemo(
    () =>
      PRESENTATION_PRESETS.find(
        (preset) =>
          preset.width === presentationConfigDraft.width &&
          preset.height === presentationConfigDraft.height,
      )?.key,
    [presentationConfigDraft.height, presentationConfigDraft.width],
  );

  useEffect(() => {
    if (!presentationHostRef.current || !isLetterboxFullscreen) {
      return;
    }

    const updateBounds = () => {
      if (!presentationHostRef.current) {
        return;
      }
      setPresentationBounds({
        width: presentationHostRef.current.clientWidth,
        height: presentationHostRef.current.clientHeight,
      });
    };

    updateBounds();

    const observer = new ResizeObserver(updateBounds);
    observer.observe(presentationHostRef.current);

    return () => {
      observer.disconnect();
    };
  }, [isLetterboxFullscreen, presentationHostRef]);

  useEffect(() => {
    if (!normalizedViewport || !containerRef.current) {
      setViewportGuideTransform('');
      return;
    }

    const viewportElement = containerRef.current.querySelector(
      '.x6-graph-svg-viewport',
    );

    if (!(viewportElement instanceof SVGGElement)) {
      setViewportGuideTransform('');
      return;
    }

    const syncTransform = () => {
      setViewportGuideTransform(
        viewportElement.getAttribute('transform') || '',
      );
    };

    syncTransform();

    const observer = new MutationObserver(syncTransform);
    observer.observe(viewportElement, {
      attributes: true,
      attributeFilter: ['transform'],
    });

    return () => {
      observer.disconnect();
    };
  }, [containerRef, graphInstance, normalizedViewport]);

  const handleOpenPresentationConfig = useCallback(() => {
    setPresentationConfigDraft(getTopologyViewportDraft(viewportConfig));
    setPresentationConfigModalVisible(true);
  }, [viewportConfig]);

  const handlePresentationPresetSelect = useCallback(
    (preset: { width: number; height: number }) => {
      setPresentationConfigDraft((prev) =>
        getTopologyViewportDraft({
          letterboxColor: prev.letterboxColor,
          width: preset.width,
          height: preset.height,
        }),
      );
    },
    [],
  );

  const handlePresentationDraftChange = useCallback(
    (patch: { width?: number; height?: number }) => {
      setPresentationConfigDraft((prev) => ({
        ...prev,
        ...patch,
      }));
    },
    [],
  );

  const focusViewportGuide = useCallback(
    (nextViewport?: TopologyViewportConfig | null) => {
      const graph = graphInstance as any;
      const host = canvasContainerRef.current;
      const normalized = normalizeTopologyViewportConfig(nextViewport);

      if (!graph || !host || !normalized) {
        return;
      }

      const nextTransform = buildTopologyViewportFocusTransform(
        host.clientWidth,
        host.clientHeight,
        normalized,
      );

      if (!nextTransform) {
        return;
      }

      if (typeof graph.zoom === 'function') {
        graph.zoom(nextTransform.scale, { absolute: true });
      }

      if (typeof graph.translate === 'function') {
        graph.translate(nextTransform.tx, nextTransform.ty);
      }
    },
    [canvasContainerRef, graphInstance],
  );

  const handleClearPresentationConfig = useCallback(() => {
    setPresentationConfigDraft(getTopologyViewportDraft(null));
  }, []);

  const handlePresentationConfigConfirm = useCallback(() => {
    const hasAnyDimension = Boolean(
      presentationConfigDraft.width || presentationConfigDraft.height,
    );
    const nextViewport = normalizeTopologyViewportConfig(
      presentationConfigDraft,
    );

    if (hasAnyDimension && !nextViewport) {
      message.warning(t('topology.fixedResolutionIncomplete'));
      return;
    }

    setViewportConfig(getTopologyViewportDraft(nextViewport));
    setPresentationConfigModalVisible(false);

    if (nextViewport) {
      window.requestAnimationFrame(() => {
        focusViewportGuide(nextViewport);
      });
    }
  }, [focusViewportGuide, presentationConfigDraft, setViewportConfig, t]);

  useEffect(() => {
    if (isFullscreen || !resumeEditModeAfterFullscreenRef.current) {
      return;
    }

    resumeEditModeAfterFullscreenRef.current = false;
    if (!isEditMode) {
      toggleEditMode();
    }
  }, [isFullscreen, isEditMode, toggleEditMode]);

  const handleFullscreenToggle = useCallback(() => {
    if (isFullscreen) {
      exitFullscreen();
      return;
    }

    resumeEditModeAfterFullscreenRef.current = isEditMode;
    if (isEditMode) {
      toggleEditMode();
    }
    enterFullscreen();
  }, [
    enterFullscreen,
    exitFullscreen,
    isEditMode,
    isFullscreen,
    toggleEditMode,
  ]);

  useEffect(() => {
    const graph = graphInstance as any;

    if (!graph) {
      return;
    }

    if (isLetterboxFullscreen && normalizedViewport) {
      if (!letterboxLayout) {
        return;
      }

      if (!fullscreenViewportSnapshotRef.current) {
        const translation =
          typeof graph.translate === 'function' ? graph.translate() : null;

        fullscreenViewportSnapshotRef.current = {
          zoom: typeof graph.zoom === 'function' ? graph.zoom() : 1,
          tx: typeof translation?.tx === 'number' ? translation.tx : 0,
          ty: typeof translation?.ty === 'number' ? translation.ty : 0,
        };
      }

      resizeCanvas(
        Math.round(letterboxLayout.renderedWidth),
        Math.round(letterboxLayout.renderedHeight),
      );

      if (typeof graph.zoom === 'function') {
        graph.zoom(letterboxLayout.scale, { absolute: true });
      }
      if (typeof graph.translate === 'function') {
        graph.translate(0, 0);
      }
      return;
    }

    if (fullscreenViewportSnapshotRef.current) {
      const snapshot = fullscreenViewportSnapshotRef.current;
      if (typeof graph.zoom === 'function') {
        graph.zoom(snapshot.zoom, { absolute: true });
      }
      if (typeof graph.translate === 'function') {
        graph.translate(snapshot.tx, snapshot.ty);
      }
      fullscreenViewportSnapshotRef.current = null;
    }

    handleCanvasResize();
  }, [
    graphInstance,
    handleCanvasResize,
    isLetterboxFullscreen,
    letterboxLayout,
    normalizedViewport,
    resizeCanvas,
  ]);

  return {
    activePresentationPresetKey,
    exitFullscreen,
    handleClearPresentationConfig,
    handleFullscreenToggle,
    handleOpenPresentationConfig,
    handlePresentationConfigConfirm,
    handlePresentationDraftChange,
    handlePresentationPresetSelect,
    isFullscreen,
    isLetterboxFullscreen,
    letterboxLayout,
    normalizedViewport,
    presentationConfigDraft,
    presentationConfigModalVisible,
    setPresentationConfigDraft,
    setPresentationConfigModalVisible,
    viewportGuideTransform,
  };
};
