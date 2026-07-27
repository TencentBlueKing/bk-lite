'use client';

import React, { useMemo } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { Breadcrumb } from 'antd';
import Icon from '@/components/icon';
import styles from './index.module.scss';
import {
  defaultAlarmBreadcrumbMenus,
  type AlarmBreadcrumbMenus,
} from './menu';

interface Crumb {
  title: string;
  url: string;
}

export interface AlarmPageBreadcrumbProps {
  children?: React.ReactNode;
  pathnameOverride?: string;
  localeOverride?: 'zh' | 'en';
  menus?: AlarmBreadcrumbMenus;
  onNavigate?: (path: string) => void;
}

const AlarmPageBreadcrumb: React.FC<AlarmPageBreadcrumbProps> = ({
  children,
  pathnameOverride,
  localeOverride,
  menus = defaultAlarmBreadcrumbMenus,
  onNavigate,
}) => {
  const router = useRouter();
  const pathnameFromHook = usePathname();
  const pathname = pathnameOverride || pathnameFromHook;
  const parentPath =
    pathname.lastIndexOf('/') > 0
      ? pathname.substring(0, pathname.lastIndexOf('/'))
      : '/';
  const locale =
    localeOverride ||
    ((typeof window !== 'undefined'
      ? localStorage.getItem('locale')
      : null) as 'zh' | 'en' | null) ||
    'en';

  const crumbs = useMemo<Crumb[]>(() => {
    const localeMenus = menus[locale === 'en' ? 'en' : 'zh'] || [];
    const nextCrumbs: Crumb[] = [];

    for (const item of localeMenus) {
      if (item.url === pathname) {
        nextCrumbs.push({ title: item.title, url: item.url });
        break;
      }
      if (item.children) {
        const child = item.children.find((entry) => entry.url === pathname);
        if (child) {
          nextCrumbs.push(
            { title: item.title, url: item.url },
            { title: child.title, url: child.url },
          );
          break;
        }
      }
    }

    return nextCrumbs;
  }, [locale, menus, pathname]);

  const handleNavigate = (path: string) => {
    if (onNavigate) {
      onNavigate(path);
      return;
    }
    router.push(path);
  };

  return (
    <Breadcrumb className={styles.breadcrumb}>
      <Breadcrumb.Item
        onClick={() => handleNavigate(parentPath)}
        className={styles.backIcon}
      >
        <Icon type="xiangzuojiantou" />
      </Breadcrumb.Item>
      {crumbs.map(({ title, url }, index) => {
        const isCurrent = url === pathname;
        return (
          <Breadcrumb.Item
            key={`${url}-${index}`}
            onClick={() => !isCurrent && handleNavigate(url)}
            className={!isCurrent ? styles.link : undefined}
          >
            {title}
          </Breadcrumb.Item>
        );
      })}
      {children}
    </Breadcrumb>
  );
};

export default AlarmPageBreadcrumb;
