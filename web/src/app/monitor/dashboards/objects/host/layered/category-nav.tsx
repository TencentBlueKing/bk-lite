'use client';

import React from 'react';
import styles from './layered.module.scss';

export interface CategoryNavItem {
  key: string;
  label: string;
  count?: number;
}

export default function CategoryNav({
  items,
  activeKey,
  onChange
}: {
  items: CategoryNavItem[];
  activeKey: string;
  onChange: (key: string) => void;
}) {
  return (
    <nav className={styles.nav} aria-label="分层分类">
      <div className={styles.navLabel}>分层</div>
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className={`${styles.navItem} ${activeKey === item.key ? styles.navItemActive : ''}`}
          onClick={() => onChange(item.key)}
        >
          <span>{item.label}</span>
          {item.count != null ? <span className={styles.navCount}>{item.count}</span> : null}
        </button>
      ))}
    </nav>
  );
}
