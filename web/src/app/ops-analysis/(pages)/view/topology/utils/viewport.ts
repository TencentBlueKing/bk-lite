import type { TopologyViewportConfig } from '@/app/ops-analysis/types/topology';

export const DEFAULT_TOPOLOGY_LETTERBOX_COLOR = '#000000';

const normalizeDimension = (value?: number) => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    return undefined;
  }

  return Math.round(value);
};

export const getTopologyViewportDraft = (
  config?: TopologyViewportConfig | null,
): TopologyViewportConfig => ({
  width: normalizeDimension(config?.width),
  height: normalizeDimension(config?.height),
  letterboxColor: config?.letterboxColor || DEFAULT_TOPOLOGY_LETTERBOX_COLOR,
});

export const normalizeTopologyViewportConfig = (
  config?: TopologyViewportConfig | null,
): TopologyViewportConfig | null => {
  const width = normalizeDimension(config?.width);
  const height = normalizeDimension(config?.height);

  if (!width || !height) {
    return null;
  }

  return {
    width,
    height,
    letterboxColor:
      config?.letterboxColor || DEFAULT_TOPOLOGY_LETTERBOX_COLOR,
  };
};

export const buildTopologyLetterboxLayout = (
  containerWidth: number,
  containerHeight: number,
  viewport: TopologyViewportConfig | null,
) => {
  if (
    !viewport?.width ||
    !viewport?.height ||
    containerWidth <= 0 ||
    containerHeight <= 0
  ) {
    return null;
  }

  const scale = Math.min(
    containerWidth / viewport.width,
    containerHeight / viewport.height,
  );

  return {
    scale,
    renderedWidth: viewport.width * scale,
    renderedHeight: viewport.height * scale,
  };
};