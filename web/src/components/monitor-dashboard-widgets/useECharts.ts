'use client';

import { useRef, useEffect, useCallback } from 'react';
import type { ECharts, EChartsOption } from 'echarts';
import echarts from '@/components/monitor-dashboard-widgets/echarts-setup';

export interface UseEChartsOptions {
  notMerge?: boolean;
  onEvents?: Record<string, (params: any) => void>;
}

export function useECharts(option: EChartsOption | null, opts?: UseEChartsOptions) {
  const containerElementRef = useRef<HTMLDivElement | null>(null);
  const instanceRef = useRef<ECharts | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  const getInstance = useCallback(() => instanceRef.current, []);

  const disposeInstance = useCallback(() => {
    resizeObserverRef.current?.disconnect();
    resizeObserverRef.current = null;
    instanceRef.current?.dispose();
    instanceRef.current = null;
  }, []);

  const containerRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (containerElementRef.current === node) return;

      disposeInstance();
      containerElementRef.current = node;

      if (!node) return;

      const instance = echarts.init(node);
      instanceRef.current = instance;

      const ro = new ResizeObserver(() => {
        instance.resize();
      });
      ro.observe(node);
      resizeObserverRef.current = ro;
    },
    [disposeInstance]
  );

  useEffect(() => () => disposeInstance(), [disposeInstance]);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance) return;
    if (!option) {
      instance.clear();
      return;
    }
    instance.setOption(option, { notMerge: opts?.notMerge ?? true });
    const frameId = requestAnimationFrame(() => {
      instance.resize();
    });
    return () => {
      cancelAnimationFrame(frameId);
    };
  }, [option, opts?.notMerge]);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance || !opts?.onEvents) return;

    const entries = Object.entries(opts.onEvents);
    entries.forEach(([event, handler]) => {
      instance.on(event, handler);
    });

    return () => {
      entries.forEach(([event, handler]) => {
        instance.off(event, handler);
      });
    };
  }, [opts?.onEvents]);

  return { containerRef, getInstance };
}
