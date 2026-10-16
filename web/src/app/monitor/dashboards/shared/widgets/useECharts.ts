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
  const containerElementRef = useRef<HTMLDivElement | null>(null);
  const instanceRef = useRef<ECharts | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  const getInstance = useCallback(() => instanceRef.current, []);

  const disposeInstance = useCallback(() => {
    resizeObserverRef.current?.disconnect();
    resizeObserverRef.current = null;
    const instance = instanceRef.current;
    instanceRef.current = null;
    if (!instance || instance.isDisposed()) return;
    const dom = instance.getDom();
    if (!dom?.isConnected) return;
    instance.dispose();
  }, []);

  const containerRef = useCallback((node: HTMLDivElement | null) => {
    if (containerElementRef.current === node) return;

    if (!node) {
      const dying = instanceRef.current;
      resizeObserverRef.current?.disconnect();
      resizeObserverRef.current = null;
      instanceRef.current = null;
      containerElementRef.current = null;
      // ref 清空发生在 React commitDeletion 的 removeChild 之前。
      // 同步 dispose 会拆掉 appendToBody 的图表提示，和同一提交里的门户卸载撞车。
      // 推迟到本次提交结束后；若 Strict Mode 立刻把同一实例挂回，则不拆。
      if (dying && !dying.isDisposed()) {
        queueMicrotask(() => {
          if (instanceRef.current === dying || dying.isDisposed()) return;
          const dom = dying.getDom();
          if (!dom?.isConnected) return;
          dying.dispose();
        });
      }
      return;
    }

    const reused = echarts.getInstanceByDom(node);
    if (reused && !reused.isDisposed()) {
      instanceRef.current = reused;
    } else {
      disposeInstance();
      const instance = echarts.init(node);
      instanceRef.current = instance;
    }
    containerElementRef.current = node;

    const ro = new ResizeObserver(() => {
      instanceRef.current?.resize();
    });
    ro.observe(node);
    resizeObserverRef.current = ro;
  }, [disposeInstance]);

  useEffect(() => () => {
    if (!containerElementRef.current) return;
    disposeInstance();
  }, [disposeInstance]);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance) return;
    // option 为 null 表示当前无数据：清空画布，避免残留上一次的折线与空状态覆盖层叠加显示。
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
