import type { TopologyViewportConfig } from '@/app/ops-analysis/types/topology';

export const DEFAULT_TOPOLOGY_LETTERBOX_COLOR = '#000000';

const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

const normalizeDimension = (value?: number) => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    return undefined;
  }

  return Math.round(value);
};

export const normalizeTopologyLetterboxColor = (value?: string) => {
  const normalized = value?.trim();

  if (!normalized) {
    return DEFAULT_TOPOLOGY_LETTERBOX_COLOR;
  }

  return HEX_COLOR_PATTERN.test(normalized)
    ? normalized
    : DEFAULT_TOPOLOGY_LETTERBOX_COLOR;
};

export const getTopologyViewportDraft = (
  config?: TopologyViewportConfig | null,
): TopologyViewportConfig => ({
  width: normalizeDimension(config?.width),
  height: normalizeDimension(config?.height),
  letterboxColor: normalizeTopologyLetterboxColor(config?.letterboxColor),
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
    letterboxColor: normalizeTopologyLetterboxColor(config?.letterboxColor),
  };
};

export const buildTopologyViewportFocusTransform = (
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

  const horizontalPadding = Math.min(64, containerWidth * 0.08);
  const verticalPadding = Math.min(64, containerHeight * 0.08);
  const safeWidth = Math.max(containerWidth - horizontalPadding * 2, 1);
  const safeHeight = Math.max(containerHeight - verticalPadding * 2, 1);

  const scale = Math.min(
    safeWidth / viewport.width,
    safeHeight / viewport.height,
    1,
  );

  return {
    scale,
    tx: (containerWidth - viewport.width * scale) / 2,
    ty: (containerHeight - viewport.height * scale) / 2,
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
