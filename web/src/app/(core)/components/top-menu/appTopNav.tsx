'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  countVisibleAppSlots,
  findActiveApp,
  resolveAppNavigation,
  splitOverflowApps,
} from '@/console-layout';
import type { ClientData } from '@/types/index';
import Icon from '@/components/icon';
import styles from './index.module.scss';

interface AppTopNavProps {
  apps: ClientData[];
  pathname: string | null;
}

const AppTopNav = ({ apps, pathname }: AppTopNavProps) => {
  const { t } = useTranslation();
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const [visibleCount, setVisibleCount] = useState(apps.length);
  const origin = typeof window === 'undefined' ? '' : window.location.origin;

  useEffect(() => {
    const element = containerRef.current;
    if (!element || typeof ResizeObserver === 'undefined') {
      return undefined;
    }
    const update = () => {
      setVisibleCount(countVisibleAppSlots(element.clientWidth, apps.length));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [apps.length]);

  const activeApp = pathname ? findActiveApp(apps, pathname, origin) : undefined;
  const { visible, overflow } = splitOverflowApps(apps, visibleCount, activeApp?.url);

  const overflowMenu: MenuProps['items'] = overflow.map((app) => ({
    key: app.url,
    label: (
      <span className="flex items-center">
        <Icon type={app.icon || app.name} className="mr-1.5 h-4 w-4 shrink-0" />
        {app.display_name || app.name}
      </span>
    ),
    onClick: () => {
      const target = resolveAppNavigation(app, origin);
      if (target.mode === 'new-tab') {
        window.open(target.href, '_blank');
        return;
      }
      router.push(target.href);
    },
  }));

  return (
    <div
      ref={containerRef}
      className="z-10 flex w-full min-w-0 items-center justify-start space-x-4 overflow-hidden"
    >
      {visible.map((app) => (
        <AppTopNavItem
          key={app.url}
          app={app}
          active={activeApp?.url === app.url}
          origin={origin}
        />
      ))}
      {overflow.length > 0 && (
        <Dropdown menu={{ items: overflowMenu }} trigger={['click']}>
          <button
            type="button"
            className={`flex shrink-0 cursor-pointer items-center rounded-[10px] px-3 py-2 ${styles.menuCol}`}
          >
            {t('common.more')}
          </button>
        </Dropdown>
      )}
    </div>
  );
};

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
        className={className}
      >
        {icon}
        {label}
      </a>
    );
  }

  return (
    <Link href={target.href} prefetch={false} className={className}>
      {icon}
      {label}
    </Link>
  );
};

export default AppTopNav;
