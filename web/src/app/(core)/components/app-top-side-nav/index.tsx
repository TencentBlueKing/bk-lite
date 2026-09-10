'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import {
  APP_TOP_SIDE_RAIL_COLLAPSED_WIDTH_PX,
  APP_TOP_SIDE_RAIL_WIDTH_PX,
  buildAppTopSideNavGroups,
  resolveMenuNavHref,
  useConsoleLayout,
} from '@/console-layout';
import { isMenuPathMatch, resolveMenuIcon } from '@/utils/menuHelpers';
import { useTranslation } from '@/utils/i18n';
import type { MenuItem } from '@/types/index';

interface AppTopSideNavProps {
  menus: MenuItem[];
  pathname: string | null;
}

const itemClassName = (active: boolean, showLabels: boolean) => (
  `flex h-10 items-center rounded-[10px] text-sm ${showLabels ? 'px-2.5' : 'justify-center px-0'} ${
    active
      ? 'bg-[var(--color-components-nav-button-bg-active)] text-[var(--color-components-nav-button-text-active)]'
      : 'text-[var(--color-components-nav-button-text)] hover:bg-[var(--color-components-nav-button-bg-hover)]'
  }`
);

const AppTopSideNav = ({ menus, pathname }: AppTopSideNavProps) => {
  const { t } = useTranslation();
  const currentPath = usePathname() ?? pathname;
  const { sideNav, setSideNav } = useConsoleLayout();
  const [peeking, setPeeking] = useState(false);
  const groups = buildAppTopSideNavGroups(menus, currentPath);

  if (groups.length === 0) {
    return null;
  }

  const collapsed = sideNav === 'collapsed';
  const flyout = collapsed && peeking;
  const showLabels = !collapsed || flyout;
  const railWidth = collapsed ? APP_TOP_SIDE_RAIL_COLLAPSED_WIDTH_PX : APP_TOP_SIDE_RAIL_WIDTH_PX;
  const panelWidth = showLabels ? APP_TOP_SIDE_RAIL_WIDTH_PX : APP_TOP_SIDE_RAIL_COLLAPSED_WIDTH_PX;

  const startPeeking = () => {
    if (collapsed) {
      setPeeking(true);
    }
  };
  const stopPeeking = () => setPeeking(false);
  const peekIfOverItem = (event: React.MouseEvent<HTMLElement>) => {
    if (!collapsed || peeking) {
      return;
    }
    if ((event.target as HTMLElement | null)?.closest('[data-side-nav-item]')) {
      setPeeking(true);
    }
  };
  const toggle = () => {
    setPeeking(false);
    setSideNav(collapsed ? 'expanded' : 'collapsed');
  };

  return (
    <aside
      data-testid="app-top-side-nav"
      data-side-nav={collapsed ? 'collapsed' : 'expanded'}
      className="relative h-full shrink-0 self-stretch"
      style={{ width: railWidth }}
      onMouseEnter={startPeeking}
      onMouseLeave={stopPeeking}
      onMouseMove={peekIfOverItem}
      onFocus={startPeeking}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          stopPeeking();
        }
      }}
    >
      <div
        data-testid="app-top-side-nav-panel"
        data-flyout={flyout ? 'true' : undefined}
        className={`absolute inset-y-0 left-0 flex flex-col bg-[var(--color-bg-1)] transition-[width] duration-150 ease-out ${
          flyout ? 'z-30 shadow-[4px_0_6px_-4px_rgba(0,0,0,0.08)]' : ''
        }`}
        style={{ width: panelWidth }}
      >
        <nav
          data-testid="app-top-side-nav-menu"
          className="main-content min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 py-4"
        >
          <ul className="flex flex-col gap-1.5">
            {groups.map((group) => {
              const active = Boolean(
                currentPath && group.item.url && isMenuPathMatch(group.item.url, currentPath),
              );
              const iconType = resolveMenuIcon(group.item);
              const href = resolveMenuNavHref(group.item);

              return (
                <li key={group.item.url}>
                  <Link
                    href={href}
                    prefetch={false}
                    data-side-nav-item
                    title={showLabels ? undefined : group.item.title}
                    aria-label={showLabels ? undefined : group.item.title}
                    className={itemClassName(active, showLabels)}
                    onMouseEnter={startPeeking}
                  >
                    {iconType ? (
                      <Icon type={iconType} className="h-4 w-4 shrink-0" />
                    ) : (
                      <span
                        aria-hidden
                        className="flex h-4 w-4 shrink-0 items-center justify-center text-xs leading-none"
                      >
                        {group.item.title.slice(0, 1)}
                      </span>
                    )}
                    {showLabels && (
                      <span className="ml-2 truncate whitespace-nowrap">{group.item.title}</span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className={`shrink-0 px-3 pb-3 ${showLabels ? '' : 'flex justify-center'}`}>
          <button
            type="button"
            aria-label={collapsed ? t('common.expandSideNav') : t('common.collapseSideNav')}
            onClick={toggle}
            className="flex h-8 w-8 appearance-none items-center justify-center rounded-[8px] border-0 bg-transparent p-0 text-[var(--color-text-3)] transition-colors hover:bg-[var(--color-components-nav-button-bg-hover)] hover:text-[var(--color-text-1)]"
          >
            {collapsed ? (
              <MenuUnfoldOutlined className="text-[14px]" />
            ) : (
              <MenuFoldOutlined className="text-[14px]" />
            )}
          </button>
        </div>
      </div>
    </aside>
  );
};

export default AppTopSideNav;
