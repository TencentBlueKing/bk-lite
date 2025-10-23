import { useEffect, useRef } from 'react';

/**
 * 自定义轮询Hook
 * 遵循BK-Lite Web项目的定时器处理标准
 * 
 * @param callback 轮询执行的回调函数
 * @param interval 轮询间隔时间（毫秒）
 * @param enabled 是否启用轮询
 */
export const usePolling = (
  callback: () => void,
  interval: number,
  enabled: boolean
) => {
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const savedCallback = useRef(callback);
  const enabledRef = useRef(enabled);

  // 保存最新的回调函数引用
  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  // 保存最新的enabled状态
  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  // 清理定时器函数
  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const startPolling = () => {
    if (!enabledRef.current) {
      return;
    }

    timerRef.current = setTimeout(() => {
      if (enabledRef.current) {
        savedCallback.current();
        startPolling();
      }
    }, interval);
  };

  // 定时器管理
  useEffect(() => {
    // 先清理之前的定时器
    clearTimer();

    if (enabled) {
      startPolling();
    }

    // 组件卸载时清理定时器
    return () => clearTimer();
  }, [interval, enabled]);

  // 组件卸载时确保清理定时器
  useEffect(() => {
    return () => clearTimer();
  }, []);

  return { clearTimer };
};

export default usePolling;