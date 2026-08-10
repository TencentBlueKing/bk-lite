'use client';

/**
 * 必须在任何可能间接引入 antd-mobile 的模块之前执行。
 * layout 通过渲染本 Client Component 建立客户端边界，避免 Server Component 直接导入 react-dom/client。
 */
import './react-dom';
import './antd-mobile-render';

/** 挂在 RootLayout 内，确保 polyfill 早于业务 Client 树执行。 */
export function MobilePolyfills() {
  return null;
}
