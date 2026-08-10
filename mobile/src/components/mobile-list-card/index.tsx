'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { RightOutline } from 'antd-mobile-icons';
import styles from './index.module.css';

type MobileListCardVariant = 'flush' | 'raised';

interface MobileListCardProps {
  variant?: MobileListCardVariant;
  href?: string;
  onClick?: () => void;
  leading?: ReactNode;
  eyebrow?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  trailing?: ReactNode;
  chevron?: boolean;
  className?: string;
  'aria-label'?: string;
  'data-status'?: string;
}

export default function MobileListCard({
  variant = 'flush',
  href,
  onClick,
  leading,
  eyebrow,
  title,
  meta,
  trailing,
  chevron = true,
  className,
  'aria-label': ariaLabel,
  'data-status': dataStatus,
}: MobileListCardProps) {
  const classNames = [
    styles.card,
    variant === 'raised' ? styles.cardRaised : styles.cardFlush,
    variant === 'flush' && leading ? styles.cardFlushHasLeading : '',
    className || '',
  ].filter(Boolean).join(' ');

  const content = (
    <>
      {leading ? <span className={styles.leading}>{leading}</span> : null}
      <span className={styles.body}>
        {(eyebrow || trailing) && (
          <span className={styles.topline}>
            <span className={styles.eyebrow}>{eyebrow}</span>
            {trailing ? <span className={styles.trailing}>{trailing}</span> : null}
          </span>
        )}
        <strong className={styles.title}>{title}</strong>
        {meta ? <span className={styles.meta}>{meta}</span> : null}
      </span>
      {chevron ? <RightOutline className={styles.chevron} aria-hidden="true" /> : null}
    </>
  );

  if (href) {
    return (
      <Link
        className={classNames}
        href={href}
        aria-label={ariaLabel}
        data-status={dataStatus}
        onClick={onClick}
      >
        {content}
      </Link>
    );
  }

  return (
    <button
      type="button"
      className={classNames}
      aria-label={ariaLabel}
      data-status={dataStatus}
      onClick={onClick}
    >
      {content}
    </button>
  );
}
