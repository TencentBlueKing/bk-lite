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
 * Mobile 统一搜索框。
 * 高度与圆角只允许走 `--mobile-search-bar-*` 变量，业务页不要再覆盖 `.adm-search-bar-input-box`。
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
