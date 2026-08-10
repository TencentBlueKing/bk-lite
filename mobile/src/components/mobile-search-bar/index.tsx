'use client';

import { SearchBar } from 'antd-mobile';
import type { SearchBarProps } from 'antd-mobile';
import type { ReactElement } from 'react';
import styles from './index.module.css';

export type MobileSearchBarSize = 'compact' | 'page';

export type MobileSearchBarProps = SearchBarProps & {
  /** compact：列表工具条；page：独立搜索页 / Popup 内筛选 */
  size?: MobileSearchBarSize;
  className?: string;
};

/**
 * Mobile 统一搜索框（antd-mobile SearchBar）。
 * 高度与圆角只允许走 `--mobile-search-bar-*` 变量，业务页不要再覆盖 `.adm-search-bar-input-box`。
 *
 * 交互约定（见 `mobile/DESIGN.md` §3）：
 * - 远程搜索：`onChange` 只改草稿，`onSearch` 提交后才请求；`onClear` 清草稿并恢复未筛选态。
 * - 本地短列表筛选：可以输入即滤，但仍优先复用本组件以保持盒型一致。
 */
export default function MobileSearchBar({
  size = 'compact',
  className,
  ...props
}: MobileSearchBarProps): ReactElement {
  const rootClass = [
    styles.root,
    size === 'page' ? styles.rootPage : '',
    className || '',
  ].filter(Boolean).join(' ');

  return (
    <div className={rootClass}>
      <SearchBar {...props} />
    </div>
  );
}
