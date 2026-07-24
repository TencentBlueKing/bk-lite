import type { ReactNode } from 'react';
import styles from './index.module.css';

interface MobileSafeHeaderProps {
  children: ReactNode;
  contentClassName?: string;
}

export default function MobileSafeHeader({
  children,
  contentClassName = '',
}: MobileSafeHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={`${styles.content} ${contentClassName}`.trim()}>
        {children}
      </div>
    </header>
  );
}
