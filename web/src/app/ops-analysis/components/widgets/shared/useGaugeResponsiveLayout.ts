import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type EChartsReact from 'echarts-for-react';
import {
  getGaugeResponsiveLayout,
  type GaugeLayoutTier,
  type GaugeResponsiveLayout,
} from './gaugeResponsiveLayout';
import {
  fitGaugeSeriesGeometry,
  type GaugeSeriesGeometry,
} from './gaugeGeometry';

interface UseGaugeResponsiveLayoutOptions {
  gaugeShape?: 'semicircle' | 'circle';
  desiredRadiusPercent?: number;
  desiredCenterPercent?: [number, number];
  axisLineWidth?: number;
}

interface UseGaugeResponsiveLayoutResult {
  containerRef: (node: HTMLDivElement | null) => void;
  chartRef: React.RefObject<EChartsReact | null>;
  layout: GaugeResponsiveLayout;
  geometry: GaugeSeriesGeometry;
  hasValidContainerSize: boolean;
}

export function useGaugeResponsiveLayout(
  options: UseGaugeResponsiveLayoutOptions = {},
): UseGaugeResponsiveLayoutResult {
  const chartRef = useRef<EChartsReact>(null);
  const tierRef = useRef<GaugeLayoutTier>('medium');
  const nodeRef = useRef<HTMLDivElement | null>(null);
  const observerRef = useRef<ResizeObserver | null>(null);
  const frameIdRef = useRef(0);
  const [size, setSize] = useState({ width: 0, height: 0 });

  const disconnectObserver = useCallback(() => {
    cancelAnimationFrame(frameIdRef.current);
    frameIdRef.current = 0;
    observerRef.current?.disconnect();
    observerRef.current = null;
  }, []);

  const updateSize = useCallback(() => {
    const node = nodeRef.current;
    if (!node) {
      return;
    }

    const rect = node.getBoundingClientRect();
    const width = Math.round(rect.width);
    const height = Math.round(rect.height);
    setSize((prev) =>
      prev.width === width && prev.height === height
        ? prev
        : { width, height },
    );
  }, []);

  const containerRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (nodeRef.current === node) {
        return;
      }

      disconnectObserver();
      nodeRef.current = node;

      if (!node) {
        return;
      }

      updateSize();

      const observer = new ResizeObserver(() => {
        cancelAnimationFrame(frameIdRef.current);
        frameIdRef.current = requestAnimationFrame(updateSize);
      });
      observer.observe(node);
      observerRef.current = observer;
    },
    [disconnectObserver, updateSize],
  );

  useEffect(() => {
    return () => {
      disconnectObserver();
      nodeRef.current = null;
    };
  }, [disconnectObserver]);

  const layout = useMemo(() => {
    const next = getGaugeResponsiveLayout({
      width: size.width,
      height: size.height,
      gaugeShape: options.gaugeShape,
      previousTier: tierRef.current,
    });

    if (size.width > 0 && size.height > 0) {
      tierRef.current = next.tier;
    }

    return next;
  }, [options.gaugeShape, size.height, size.width]);

  const geometry = useMemo(() => {
    const desiredRadiusPercent = options.desiredRadiusPercent ?? 100;
    const desiredCenterPercent = options.desiredCenterPercent ?? [50, 50];
    const axisLineWidth = options.axisLineWidth ?? 14;

    return fitGaugeSeriesGeometry({
      width: size.width,
      height: size.height,
      gaugeShape: options.gaugeShape,
      desiredRadiusPercent,
      desiredCenterPercent,
      axisLineWidth,
      layout,
    });
  }, [
    layout,
    options.axisLineWidth,
    options.desiredCenterPercent,
    options.desiredRadiusPercent,
    options.gaugeShape,
    size.height,
    size.width,
  ]);

  useEffect(() => {
    if (size.width <= 0 || size.height <= 0) {
      return;
    }

    chartRef.current?.getEchartsInstance()?.resize();
  }, [layout, size.height, size.width]);

  return {
    containerRef,
    chartRef,
    layout,
    geometry,
    hasValidContainerSize: size.width > 0 && size.height > 0,
  };
}
