'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import Icon from '@/components/icon';
import { APP_TOP_SIDE_RAIL_WIDTH_PX, buildAppTopSideNavGroups } from '@/console-layout';
import { isMenuPathMatch, resolveMenuIcon } from '@/utils/menuHelpers';
import type { MenuItem } from '@/types/index';

interface AppTopSideNavProps {
  menus: MenuItem[];
  pathname: string | null;
}

const itemClassName = (active: boolean) => (
  `flex h-10 items-center rounded-[10px] px-3 text-sm ${
    active
      ? 'bg-[var(--color-components-nav-button-bg-active)] text-[var(--color-components-nav-button-text-active)]'
      : 'text-[var(--color-components-nav-button-text)] hover:bg-[var(--color-components-nav-button-bg-hover)]'
  }`
);

const AppTopSideNav = ({ menus, pathname }: AppTopSideNavProps) => {
  const currentPath = usePathname() ?? pathname;
  const groups = buildAppTopSideNavGroups(menus, currentPath);

  if (groups.length === 0) {
    return null;
  }

  return (
    <aside
      data-testid="app-top-side-nav"
      className="flex h-full shrink-0 flex-col self-stretch bg-[var(--color-bg-1)]"
      style={{ width: APP_TOP_SIDE_RAIL_WIDTH_PX }}
    >
      <nav
        data-testid="app-top-side-nav-menu"
        className="main-content min-h-0 flex-1 overflow-y-auto px-4 py-4"
      >
        <ul className="flex flex-col gap-1.5">
          {groups.map((group) => {
            const active = Boolean(
              currentPath && group.item.url && isMenuPathMatch(group.item.url, currentPath),
            );

            return (
              <li key={group.item.url}>
                <Link
                  href={group.item.url}
                  prefetch={false}
                  className={itemClassName(active)}
                >
                  {group.item.icon && (
                    <Icon type={resolveMenuIcon(group.item)} className="mr-2 h-4 w-4 shrink-0" />
                  )}
                  {group.item.title}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
};

export default AppTopSideNav;
