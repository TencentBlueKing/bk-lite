'use client';

import { useRef, useEffect, useCallback } from 'react';
import type { ECharts, EChartsOption } from 'echarts';
import echarts from './echarts-setup';

export interface UseEChartsOptions {
  notMerge?: boolean;
  onEvents?: Record<string, (params: any) => void>;
}

export function useECharts(
  option: EChartsOption | null,
  opts?: UseEChartsOptions
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<ECharts | null>(null);

  const getInstance = useCallback(() => instanceRef.current, []);

  useEffect(() => {
    if (!containerRef.current) return;

    const instance = echarts.init(containerRef.current);
    instanceRef.current = instance;

    const ro = new ResizeObserver(() => {
      instance.resize();
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      instance.dispose();
      instanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance || !option) return;
    instance.setOption(option, { notMerge: opts?.notMerge ?? true });
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
