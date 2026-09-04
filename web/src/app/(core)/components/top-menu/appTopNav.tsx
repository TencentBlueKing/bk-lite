'use client';

import React, { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  findActiveApp,
  getAppStripOverflow,
  resolveAppNavigation,
} from '@/console-layout';
import type { ClientData } from '@/types/index';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';

interface AppTopNavProps {
  apps: ClientData[];
  pathname: string | null;
}

const AppTopNav = ({ apps, pathname }: AppTopNavProps) => {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const [overflow, setOverflow] = useState({ left: false, right: false });
  const origin = typeof window === 'undefined' ? '' : window.location.origin;
  const activeApp = pathname ? findActiveApp(apps, pathname, origin) : undefined;

  const measureOverflow = useCallback(() => {
    const node = containerRef.current;
    if (!node) {
      return;
    }
    setOverflow(getAppStripOverflow(node.scrollLeft, node.clientWidth, node.scrollWidth));
  }, []);

  useLayoutEffect(() => {
    const node = containerRef.current;
    if (!node) {
      return;
    }

    measureOverflow();
    node.addEventListener('scroll', measureOverflow, { passive: true });
    window.addEventListener('resize', measureOverflow);
    const observer = new ResizeObserver(measureOverflow);
    observer.observe(node);

    return () => {
      node.removeEventListener('scroll', measureOverflow);
      window.removeEventListener('resize', measureOverflow);
      observer.disconnect();
    };
  }, [apps.length, measureOverflow]);

  useLayoutEffect(() => {
    const active = containerRef.current?.querySelector<HTMLElement>('[data-app-active="true"]');
    active?.scrollIntoView?.({ inline: 'nearest', block: 'nearest', behavior: 'instant' });
    measureOverflow();
  }, [activeApp?.url, apps.length, measureOverflow]);

  const handleWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    const node = containerRef.current;
    if (!node || node.scrollWidth <= node.clientWidth) {
      return;
    }
    if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) {
      return;
    }
    node.scrollLeft += event.deltaY;
    event.preventDefault();
  };

  const scrollByDirection = (direction: -1 | 1) => {
    const node = containerRef.current;
    if (!node) {
      return;
    }
    const delta = Math.max(180, Math.round(node.clientWidth * 0.7)) * direction;
    if (typeof node.scrollBy === 'function') {
      node.scrollBy({ left: delta, behavior: 'smooth' });
      return;
    }
    node.scrollLeft += delta;
  };

  const maskClass = overflow.left && overflow.right
    ? '[mask-image:linear-gradient(to_right,transparent,#000_18px,#000_calc(100%-18px),transparent)] [-webkit-mask-image:linear-gradient(to_right,transparent,#000_18px,#000_calc(100%-18px),transparent)]'
    : overflow.left
      ? '[mask-image:linear-gradient(to_right,transparent,#000_18px,#000)] [-webkit-mask-image:linear-gradient(to_right,transparent,#000_18px,#000)]'
      : overflow.right
        ? '[mask-image:linear-gradient(to_right,#000_calc(100%-18px),transparent)] [-webkit-mask-image:linear-gradient(to_right,#000_calc(100%-18px),transparent)]'
        : '';

  return (
    <div
      role="navigation"
      aria-label={t('common.appList')}
      className="flex min-w-0 items-center gap-0.5 pr-2"
    >
      {overflow.left && (
        <StripArrow
          direction="left"
          label={t('common.scrollAppsLeft')}
          onClick={() => scrollByDirection(-1)}
        />
      )}
      <div
        ref={containerRef}
        data-app-strip
        onWheel={handleWheel}
        className={`flex min-w-0 flex-1 items-center justify-start gap-4 overflow-x-auto overflow-y-hidden [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden ${maskClass}`}
      >
        {apps.map((app) => (
          <AppTopNavItem
            key={app.url}
            app={app}
            active={activeApp?.url === app.url}
            origin={origin}
          />
        ))}
      </div>
      {overflow.right && (
        <StripArrow
          direction="right"
          label={t('common.scrollAppsRight')}
          onClick={() => scrollByDirection(1)}
        />
      )}
    </div>
  );
};

const StripArrow = ({
  direction,
  label,
  onClick,
}: {
  direction: 'left' | 'right';
  label: string;
  onClick: () => void;
}) => (
  <button
    type="button"
    aria-label={label}
    onClick={onClick}
    className="flex h-6 w-6 shrink-0 appearance-none items-center justify-center rounded-full border-0 bg-[color-mix(in_srgb,var(--color-bg-1)_28%,transparent)] p-0 text-[var(--color-text-3)] shadow-none backdrop-blur-[2px] transition-colors hover:bg-[color-mix(in_srgb,var(--color-fill-2)_45%,transparent)] hover:text-[var(--color-text-1)]"
  >
    <StripChevron direction={direction} />
  </button>
);

const StripChevron = ({ direction }: { direction: 'left' | 'right' }) => (
  <svg
    viewBox="0 0 12 12"
    aria-hidden
    className={`h-2.5 w-2.5 ${direction === 'left' ? '-scale-x-100' : ''}`}
  >
    <path
      d="M4.2 2.35 8.15 6 4.2 9.65"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.35"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const AppTopNavItem = ({
  app,
  active,
  origin,
}: {
  app: ClientData;
  active: boolean;
  origin: string;
}) => {
  const target = useMemo(() => resolveAppNavigation(app, origin), [app, origin]);
  const className = `flex shrink-0 items-center rounded-[10px] px-3 py-2 ${styles.menuCol} ${active ? styles.active : ''}`;
  const label = app.display_name || app.name;
  const icon = <Icon type={app.icon || app.name} className="mr-1.5 h-4 w-4 shrink-0" />;

  if (target.mode === 'new-tab') {
    return (
      <a
        href={target.href}
        target="_blank"
        rel="noreferrer"
        data-app-active={active ? 'true' : undefined}
        className={className}
      >
        {icon}
        {label}
      </a>
    );
  }

  return (
    <Link
      href={target.href}
      prefetch={false}
      data-app-active={active ? 'true' : undefined}
      className={className}
    >
      {icon}
      {label}
    </Link>
  );
};

export default AppTopNav;
