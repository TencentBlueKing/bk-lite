import type { ReactNode } from 'react';
import styles from './index.module.css';

interface MobileSafeHeaderProps {
  children: ReactNode;
  contentClassName?: string;
  elevated?: boolean;
}

export default function MobileSafeHeader({
  children,
  contentClassName = '',
  elevated = false,
}: MobileSafeHeaderProps) {
  return (
    <header className={`${styles.header} ${elevated ? styles.headerElevated : ''}`.trim()}>
      <div className={`${styles.content} ${contentClassName}`.trim()}>
        {children}
      </div>
    </header>
  );
}
