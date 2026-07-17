import { useCallback, useState } from 'react';

/**
 * 侧栏 / 面板的「展开 / 收起」状态。
 *
 * 设计要点:
 * - 仅返回 boolean + setter + toggle,组件自己渲染按钮和切换动画,避免过度抽象。
 * - 不持久化:画布内部状态由各自画布的容器管理(localStorage 持久化另算)。
 * - topology 与 networkTopology 共用,见:
 *   - (pages)/view/topology/components/nodeSidebar.tsx
 *   - (pages)/view/networkTopology/components/networkLibrary.tsx
 */
export function useCollapsedState(defaultValue = false) {
  const [collapsed, setCollapsed] = useState<boolean>(defaultValue);
  const toggle = useCallback(() => setCollapsed((v) => !v), []);
  return { collapsed, setCollapsed, toggle };
}
