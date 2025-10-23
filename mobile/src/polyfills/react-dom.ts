/**
 * React 18/19 兼容性 Polyfill
 * 为 antd-mobile 等老版本库提供 unmountComponentAtNode 兼容
 */

/* eslint-disable @typescript-eslint/ban-ts-comment, react/no-deprecated */

import ReactDOM from 'react-dom';
import * as ReactDOMClient from 'react-dom/client';

// 类型定义
type Container = Element | Document | DocumentFragment;

type ReactDOMAny = typeof ReactDOM & {
  createRoot?: (container: Container, options?: any) => any;
  unmountComponentAtNode?: (container: Container | null) => boolean;
  render?: (element: any, container: Container, callback?: () => void) => void;
};

if (typeof window !== 'undefined') {
  const ReactDOMExt = ReactDOM as ReactDOMAny;

  // 抑制 antd-mobile 的 React 版本警告
  (window as any).__ANTD_MOBILE_COMPATIBLE__ = true;

  // 屏蔽 antd-mobile 的 React 18+ 兼容性警告
  const originalConsoleError = console.error;
  console.error = function(...args: any[]) {
    // 过滤掉 antd-mobile 的 React 版本警告
    if (
      typeof args[0] === 'string' &&
      args[0].includes('[Compatible] antd-mobile v5 support React is 16 ~ 18')
    ) {
      return;
    }
    // 其他错误正常输出
    originalConsoleError.apply(console, args);
  };

  // 存储所有的 roots
  const roots = new WeakMap<Container, any>();

  // 确保 ReactDOM 有 createRoot 方法
  if (!ReactDOMExt.createRoot && ReactDOMClient.createRoot) {
    ReactDOMExt.createRoot = ReactDOMClient.createRoot;
  }

  // 拦截 createRoot 来追踪 roots
  if (ReactDOMExt.createRoot) {
    const originalCreateRoot = ReactDOMExt.createRoot;
    ReactDOMExt.createRoot = function(container: Container, options?: any) {
      const root = originalCreateRoot.call(this, container, options);
      roots.set(container, root);
      return root;
    };
  }

  // 添加 unmountComponentAtNode 方法（兼容旧版 API）
  if (!ReactDOMExt.unmountComponentAtNode) {
    console.log('[Polyfill] Adding unmountComponentAtNode for antd-mobile compatibility');

    ReactDOMExt.unmountComponentAtNode = function(container: Container | null): boolean {
      if (!container) return false;

      // 尝试从 WeakMap 获取 root 并卸载
      const root = roots.get(container);
      if (root && typeof root.unmount === 'function') {
        try {
          root.unmount();
          roots.delete(container);
          return true;
        } catch (e) {
          console.warn('[Polyfill] Error unmounting root:', e);
        }
      }

      // 降级方案：清空容器
      try {
        if ('innerHTML' in container) {
          container.innerHTML = '';
        }
        return true;
      } catch (e) {
        console.warn('[Polyfill] Failed to clear container:', e);
        return false;
      }
    };
  }

  // 添加 render 方法（兼容旧版 API）
  if (!ReactDOMExt.render && ReactDOMExt.createRoot) {
    // @ts-ignore - React 18 类型兼容问题
    ReactDOMExt.render = function(element: any, container: Container | null, callback?: () => void) {
      if (!container) return;

      let root = roots.get(container);
      if (!root) {
        root = ReactDOMExt.createRoot!(container);
        roots.set(container, root);
      }
      root.render(element);
      if (callback) {
        setTimeout(callback, 0);
      }
    };
  }
}

export { };
